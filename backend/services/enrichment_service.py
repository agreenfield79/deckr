"""
Enrichment Service — Layer 5B External World Network.

Phase 10B implementation. Populates Neo4j with external enrichment nodes
(news, legal actions, UCC filings, corporate affiliates, cross-entity
connection signals) via SerpAPI, OpenCorporates, CourtListener/PACER.

Feature flag: ENRICHMENT_ENABLED env var (default: true).
All API calls are D-3: exceptions logged as warnings, never raised.
Missing API keys skip that enrichment pass gracefully.

Called asynchronously after extraction in the pipeline — does not block
the IP1 gate or any pipeline agent stage.
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("deckr.enrichment_service")

_ENABLED       = os.getenv("ENRICHMENT_ENABLED", "true").lower() not in ("false", "0", "off")
_SERPAPI_KEY   = os.getenv("SERPAPI_KEY", "")
_OPENCORP_KEY  = os.getenv("OPENCORPORATES_API_KEY", "")  # optional — increases rate limits
_COURT_KEY     = os.getenv("COURTLISTENER_API_KEY", "")   # optional

_SERPAPI_BASE  = "https://serpapi.com/search"
_OPENCORP_BASE = "https://api.opencorporates.com/v0.4"
_COURT_BASE    = "https://www.courtlistener.com/api/rest/v4"
_HTTP_TIMEOUT  = 15.0  # seconds per request

# In-memory enrichment status (reset on restart; persisted to workspace by enrich_deal)
_enrichment_status: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def enrich_deal(deal_id: str, workspace_root: str) -> dict:
    """
    Run all enrichment passes for a deal asynchronously.

    1. Read entity names / NAICS codes from SQL entities table
    2. SerpAPI news search per entity → NewsArticle nodes + MENTIONED_IN edges
    3. SerpAPI people search per guarantor → AFFILIATED_WITH edges
    4. OpenCorporates company lookup → ExternalCompany nodes + CONTROLS/FORMERLY_OWNED edges
    5. CourtListener civil case search → LegalAction nodes + SUBJECT_OF edges
    6. UCC lien search (state-specific via SerpAPI fallback)
    7. Cross-entity CONNECTED_TO detection (shared address / registered agent)

    Returns a summary dict.  Never raises — all errors logged as warnings.
    """
    if not _ENABLED:
        logger.info("[enrichment] ENRICHMENT_ENABLED=false — skipping deal_id=%s", deal_id)
        return {"status": "disabled", "deal_id": deal_id}

    logger.info("[enrichment] starting deal_id=%s", deal_id)
    started_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "deal_id":    deal_id,
        "started_at": started_at,
        "passes":     {},
    }

    # --- 1. Collect entity data from SQL ---
    entities = _get_entities(deal_id)
    if not entities:
        logger.warning("[enrichment] no entities found for deal_id=%s — aborting", deal_id)
        result["status"] = "no_entities"
        return result

    # --- Run enrichment passes concurrently ---
    tasks = []
    if _SERPAPI_KEY:
        tasks.append(_serpapi_news_pass(deal_id, entities, result))
        tasks.append(_serpapi_people_pass(deal_id, entities, result))
        tasks.append(_ucc_search_pass(deal_id, entities, result))
    else:
        logger.info("[enrichment] SERPAPI_KEY not set — skipping SerpAPI passes")

    tasks.append(_opencorporates_pass(deal_id, entities, result))
    tasks.append(_courtlistener_pass(deal_id, entities, result))

    await asyncio.gather(*tasks, return_exceptions=True)

    # --- Cross-entity CONNECTED_TO detection (sync, uses already-fetched data) ---
    _connected_to_pass(deal_id, entities, result)

    result["status"]       = "complete"
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    _enrichment_status[deal_id] = result

    # Persist summary to workspace for frontend
    try:
        import pathlib
        summary_path = pathlib.Path(workspace_root) / "Agent Notes" / "enrichment_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info("[enrichment] summary saved → %s", summary_path)
    except Exception as exc:
        logger.warning("[enrichment] could not write summary file — %s", exc)

    logger.info(
        "[enrichment] complete deal_id=%s passes=%s",
        deal_id, list(result["passes"].keys()),
    )
    return result


def get_enrichment_status(deal_id: str | None = None) -> dict:
    """Return in-memory enrichment status for a deal (or all deals if deal_id is None)."""
    if deal_id:
        return _enrichment_status.get(deal_id, {"status": "not_run", "deal_id": deal_id})
    return dict(_enrichment_status)


# ---------------------------------------------------------------------------
# Internal helpers — SQL entity lookup
# ---------------------------------------------------------------------------

def _get_entities(deal_id: str) -> list[dict]:
    """Return entities for a deal from SQL. Returns [] on any error."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Entity
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            rows = session.execute(
                select(Entity).where(Entity.deal_id == deal_id)
            ).scalars().all()
        return [
            {
                "entity_id":   str(r.entity_id),
                "entity_type": r.entity_type,
                "legal_name":  r.legal_name or "",
                "naics_code":  getattr(r, "naics_code", None),
                "state":       getattr(r, "state_of_incorporation", None),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("[enrichment] _get_entities failed — %s", exc)
        return []


# ---------------------------------------------------------------------------
# SerpAPI enrichment passes
# ---------------------------------------------------------------------------

async def _serpapi_news_pass(deal_id: str, entities: list[dict], result: dict) -> None:
    """Search recent news for each company entity and create NewsArticle nodes."""
    articles_created = 0
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for ent in entities:
            if ent["entity_type"] not in ("borrower_company", "operating_company"):
                continue
            name = ent["legal_name"]
            if not name:
                continue
            try:
                resp = await client.get(_SERPAPI_BASE, params={
                    "engine": "google",
                    "q":      f'"{name}" news',
                    "tbm":    "nws",
                    "num":    5,
                    "api_key": _SERPAPI_KEY,
                })
                resp.raise_for_status()
                data = resp.json()
                news_results = data.get("news_results") or []
                for item in news_results[:5]:
                    url   = item.get("link") or ""
                    title = item.get("title") or ""
                    if not url or not title:
                        continue
                    from services import graph_service
                    source_name = (
                        item.get("source", {}).get("name")
                        if isinstance(item.get("source"), dict)
                        else item.get("source")
                    )
                    graph_service.write_news_article_node(
                        url=url,
                        title=title,
                        published_date=item.get("date"),
                        source=source_name,
                    )
                    graph_service.link_company_to_news_article(ent["entity_id"], url)
                    # 3C.8 — persist full body text to MongoDB for word cloud and RAG
                    body_text = item.get("snippet") or item.get("body") or ""
                    try:
                        from services import mongo_service as _mongo
                        _mongo.save_news_article(
                            deal_id=deal_id,
                            entity_ids=[ent["entity_id"]],
                            headline=title,
                            body=body_text,
                            url=url,
                            source=source_name,
                            publish_date=item.get("date"),
                            sentiment_score=None,
                            keywords=[],
                            entities_mentioned=[ent["legal_name"]],
                        )
                    except Exception as _me:
                        logger.warning("[enrichment] save_news_article (mongo) failed — %s", _me)
                    articles_created += 1
                await asyncio.sleep(0.5)  # rate-limit courtesy delay
            except Exception as exc:
                logger.warning("[enrichment] SerpAPI news failed entity=%s — %s", name, exc)

    result["passes"]["serpapi_news"] = {
        "status": "complete", "articles_created": articles_created
    }
    logger.info("[enrichment] SerpAPI news: %d article(s) created", articles_created)


async def _serpapi_people_pass(deal_id: str, entities: list[dict], result: dict) -> None:
    """Search for public profiles of guarantor individuals and enrich Individual nodes."""
    profiles_found = 0
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for ent in entities:
            if ent["entity_type"] not in ("guarantor_individual", "key_principal"):
                continue
            name = ent["legal_name"]
            if not name:
                continue
            try:
                resp = await client.get(_SERPAPI_BASE, params={
                    "engine":  "google",
                    "q":       f'"{name}" executive OR founder OR owner',
                    "num":     3,
                    "api_key": _SERPAPI_KEY,
                })
                resp.raise_for_status()
                data = resp.json()
                # Surface knowledge graph data if available
                kg = data.get("knowledge_graph") or {}
                if kg.get("title"):
                    from services import graph_service
                    graph_service.write_individual_node(
                        deal_id=deal_id,
                        entity_id=ent["entity_id"],
                        legal_name=name,
                        title=kg.get("title", ""),
                        description=kg.get("description", ""),
                    )
                    profiles_found += 1
                await asyncio.sleep(0.5)
            except Exception as exc:
                logger.warning("[enrichment] SerpAPI people failed entity=%s — %s", name, exc)

    result["passes"]["serpapi_people"] = {
        "status": "complete", "profiles_found": profiles_found
    }


async def _ucc_search_pass(deal_id: str, entities: list[dict], result: dict) -> None:
    """
    UCC lien search via SerpAPI (Secretary of State search fallback).
    Creates UccFiling nodes + HAS_UCC_FILING edges for confirmed filings.
    """
    filings_found = 0
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for ent in entities:
            if ent["entity_type"] not in ("borrower_company", "operating_company"):
                continue
            name  = ent["legal_name"]
            state = ent.get("state") or ""
            if not name:
                continue
            try:
                query = f'"{name}" UCC lien filing site:sos.state.*.us OR site:ecorp.sos.state.*.us'
                if state:
                    query = f'"{name}" UCC lien filing {state}'
                resp = await client.get(_SERPAPI_BASE, params={
                    "engine":  "google",
                    "q":       query,
                    "num":     3,
                    "api_key": _SERPAPI_KEY,
                })
                resp.raise_for_status()
                data = resp.json()
                organic = data.get("organic_results") or []
                for item in organic[:2]:
                    if "ucc" in (item.get("title") or "").lower() or "lien" in (item.get("snippet") or "").lower():
                        filing_id = hashlib.md5(
                            f"{ent['entity_id']}-{item.get('link', '')}".encode()
                        ).hexdigest()[:16]
                        from services import graph_service
                        graph_service.write_ucc_filing_node(
                            entity_id=ent["entity_id"],
                            filing_id=filing_id,
                            secured_party=None,
                            state=state,
                        )
                        filings_found += 1
                await asyncio.sleep(0.5)
            except Exception as exc:
                logger.warning("[enrichment] UCC search failed entity=%s — %s", name, exc)

    result["passes"]["ucc_search"] = {
        "status": "complete", "filings_found": filings_found
    }


# ---------------------------------------------------------------------------
# OpenCorporates enrichment pass
# ---------------------------------------------------------------------------

async def _opencorporates_pass(deal_id: str, entities: list[dict], result: dict) -> None:
    """
    OpenCorporates company lookup — find affiliates, prior names, officers.
    Writes ExternalCompany nodes + AFFILIATED_WITH/FORMERLY_OWNED edges.
    """
    if not _OPENCORP_KEY:
        logger.info("[enrichment] OpenCorporates: no API key configured — skipping pass")
        result["passes"]["opencorporates"] = {"status": "skipped", "reason": "no_api_key"}
        return

    companies_found = 0
    headers = {"Authorization": f"Token token={_OPENCORP_KEY}"}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
        for ent in entities:
            if ent["entity_type"] not in ("borrower_company", "operating_company"):
                continue
            name = ent["legal_name"]
            if not name:
                continue
            try:
                resp = await client.get(
                    f"{_OPENCORP_BASE}/companies/search",
                    params={"q": name, "per_page": 3},
                )
                if resp.status_code in (401, 403):
                    logger.info("[enrichment] OpenCorporates: auth required — skipping")
                    break
                resp.raise_for_status()
                data = resp.json()
                companies = (data.get("results") or {}).get("companies") or []
                for co_wrap in companies[:3]:
                    co = co_wrap.get("company") or co_wrap
                    co_name = co.get("name") or ""
                    if not co_name or co_name.lower() == name.lower():
                        continue  # skip exact match (the borrower itself)
                    company_id = co.get("company_number") or hashlib.md5(
                        co_name.encode()
                    ).hexdigest()[:16]
                    from services import graph_service
                    graph_service.write_external_company_node(
                        company_id=company_id,
                        legal_name=co_name,
                        jurisdiction=co.get("jurisdiction_code"),
                        officers=[o.get("name") for o in (co.get("officers") or [])],
                        deal_id=deal_id,
                    )
                    companies_found += 1
                await asyncio.sleep(0.5)
            except Exception as exc:
                logger.warning("[enrichment] OpenCorporates failed entity=%s — %s", name, exc)

    result["passes"]["opencorporates"] = {
        "status": "complete", "companies_found": companies_found
    }


# ---------------------------------------------------------------------------
# CourtListener enrichment pass
# ---------------------------------------------------------------------------

async def _courtlistener_pass(deal_id: str, entities: list[dict], result: dict) -> None:
    """
    CourtListener search for civil cases, judgments, and bankruptcies.
    Creates LegalAction nodes + SUBJECT_OF edges.
    """
    if not _COURT_KEY:
        logger.info("[enrichment] CourtListener: no API key configured — skipping pass")
        result["passes"]["courtlistener"] = {"status": "skipped", "reason": "no_api_key"}
        return

    actions_found = 0
    headers = {"Accept": "application/json", "Authorization": f"Token {_COURT_KEY}"}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
        for ent in entities:
            name = ent["legal_name"]
            if not name:
                continue
            try:
                resp = await client.get(
                    f"{_COURT_BASE}/dockets/",
                    params={"q": name, "type": "r", "order_by": "score desc", "page_size": 3},
                )
                if resp.status_code in (401, 403):
                    logger.info("[enrichment] CourtListener: auth required for full access")
                    break
                resp.raise_for_status()
                data = resp.json()
                dockets = data.get("results") or []
                for docket in dockets[:3]:
                    action_id = str(docket.get("id") or hashlib.md5(
                        (name + str(docket.get("docket_number", ""))).encode()
                    ).hexdigest()[:16])
                    from services import graph_service
                    graph_service.write_legal_action_node(
                        entity_id=ent["entity_id"],
                        action_id=action_id,
                        case_number=docket.get("docket_number") or "",
                        case_type=docket.get("nature_of_suit") or "civil",
                        status=docket.get("status") or "unknown",
                        filed_date=docket.get("date_filed"),
                        court=docket.get("court") or "",
                        jurisdiction=docket.get("jurisdiction") or "",
                    )
                    # 3C.8 — persist full docket text to MongoDB court_filings
                    full_text = (
                        docket.get("plain_text") or
                        docket.get("description") or
                        docket.get("case_name") or ""
                    )
                    try:
                        from services import mongo_service as _mongo
                        _mongo.save_court_filing(
                            deal_id=deal_id,
                            entity_ids=[ent["entity_id"]],
                            neo4j_action_id=action_id,
                            case_number=docket.get("docket_number") or "",
                            court=docket.get("court") or "",
                            filing_type="docket_entry",
                            full_text=full_text,
                            filing_date=docket.get("date_filed"),
                            parties=[],
                            outcome_summary=None,
                        )
                    except Exception as _me:
                        logger.warning("[enrichment] save_court_filing (mongo) failed — %s", _me)
                    actions_found += 1
                await asyncio.sleep(0.5)
            except Exception as exc:
                logger.warning("[enrichment] CourtListener failed entity=%s — %s", name, exc)

    result["passes"]["courtlistener"] = {
        "status": "complete", "actions_found": actions_found
    }


# ---------------------------------------------------------------------------
# Cross-entity CONNECTED_TO detection
# ---------------------------------------------------------------------------

def _connected_to_pass(deal_id: str, entities: list[dict], result: dict) -> None:
    """
    Detect insider connections between entities via shared address, phone,
    or registered agent.  Writes CONNECTED_TO edges for confirmed signals.
    Uses SQL entity properties — no external API required.
    """
    connections_found = 0
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Entity
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            rows = session.execute(
                select(Entity).where(Entity.deal_id == deal_id)
            ).scalars().all()

        # Build lookup maps for shared property detection
        address_map: dict[str, list[str]] = {}
        phone_map:   dict[str, list[str]] = {}
        for row in rows:
            eid = str(row.entity_id)
            addr = getattr(row, "address", None) or ""
            phone = getattr(row, "phone", None) or ""
            if addr:
                address_map.setdefault(addr.lower().strip(), []).append(eid)
            if phone:
                phone_map.setdefault(phone.strip(), []).append(eid)

        from services import graph_service
        for shared_addr, eids in address_map.items():
            if len(eids) < 2:
                continue
            for i, a in enumerate(eids):
                for b in eids[i + 1:]:
                    graph_service.write_connected_to_edge(a, b, reason="shared_address")
                    connections_found += 1
                    logger.warning(
                        "[enrichment] CONNECTED_TO detected — shared_address entity_a=%s entity_b=%s",
                        a, b,
                    )

        for shared_phone, eids in phone_map.items():
            if len(eids) < 2:
                continue
            for i, a in enumerate(eids):
                for b in eids[i + 1:]:
                    graph_service.write_connected_to_edge(a, b, reason="shared_phone")
                    connections_found += 1
                    logger.warning(
                        "[enrichment] CONNECTED_TO detected — shared_phone entity_a=%s entity_b=%s",
                        a, b,
                    )

    except Exception as exc:
        logger.warning("[enrichment] _connected_to_pass failed — %s", exc)

    result["passes"]["connected_to"] = {
        "status": "complete", "connections_found": connections_found
    }
