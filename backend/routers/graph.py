"""
Graph Router — deal knowledge graph endpoints.
Reads from Neo4j Layer 5A/5B nodes populated by the pipeline.
"""

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("deckr.routers.graph")
router = APIRouter()

_NOT_IMPL = {"status": "not_implemented", "message": "Phase 10 required"}


@router.get("/deal")
def get_deal_graph(request: Request, deal_id: str | None = None):
    """Return all nodes and relationships scoped to a deal_id."""
    if deal_id is None:
        return {"status": "error", "message": "deal_id required"}
    try:
        from services.graph_service import get_deal_graph
        return {"deal_id": deal_id, "graph": get_deal_graph(deal_id)}
    except Exception as exc:
        logger.warning("get_deal_graph failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/guarantors")
def get_guarantors(request: Request, deal_id: str | None = None):
    """Return guarantor network — Individual nodes + GUARANTEES relationships."""
    if deal_id is None:
        return {"status": "error", "message": "deal_id required"}
    try:
        from services.graph_service import get_guarantor_network
        return {"deal_id": deal_id, "guarantors": get_guarantor_network(deal_id)}
    except Exception as exc:
        logger.warning("get_guarantors failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/industry/{naics_code}")
def get_industry_node(naics_code: str, request: Request):
    """Return enrichment data for an Industry node (shared across deals)."""
    try:
        from services.graph_service import _run
        result = _run(
            "MATCH (n:Industry {naics_code: $code}) RETURN properties(n) AS props",
            {"code": naics_code}
        )
        if not result:
            return {"naics_code": naics_code, "node": None}
        return {"naics_code": naics_code, "node": result[0].get("props", {})}
    except Exception as exc:
        logger.warning("get_industry_node failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/external")
def get_external_graph(request: Request, deal_id: str | None = None):
    """Return Layer 5B enrichment nodes + edges via traversal-based query (Issue C fix).

    External enrichment nodes (NewsArticle, UccFiling, LegalAction, ExternalCompany)
    don't carry deal_id as a property, so the previous MATCH (n {deal_id}) approach
    returned disconnected nodes. This endpoint uses get_enrichment_graph() which
    traverses edges from deal-scoped Company/Individual anchors.
    """
    if deal_id is None:
        return {"status": "error", "message": "deal_id required"}
    try:
        from services.graph_service import get_enrichment_graph
        return {"deal_id": deal_id, "graph": get_enrichment_graph(deal_id)}
    except Exception as exc:
        logger.warning("get_external_graph failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/node/{node_id}")
def get_node_by_id(node_id: str, request: Request):
    """Return full property set for a single node by its deal_id-scoped identifier."""
    try:
        from services.graph_service import _run
        result = _run(
            "MATCH (n) WHERE n.entity_id = $id OR n.node_id = $id OR toString(id(n)) = $id "
            "RETURN labels(n) AS labels, properties(n) AS props LIMIT 1",
            {"id": node_id}
        )
        if not result:
            return {"node_id": node_id, "node": None}
        row = result[0]
        return {
            "node_id": node_id,
            "node": {"labels": row.get("labels", []), **dict(row.get("props") or {})},
        }
    except Exception as exc:
        logger.warning("get_node_by_id failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/enrichment-status")
def get_enrichment_status(request: Request, deal_id: str | None = None):
    """
    Return Phase 10B enrichment status for a deal or all deals.
    Includes per-pass results (serpapi_news, opencorporates, courtlistener, etc.)
    and the ENRICHMENT_ENABLED feature flag.
    """
    import os
    enabled = os.getenv("ENRICHMENT_ENABLED", "true").lower() not in ("false", "0", "off")
    try:
        from services.enrichment_service import get_enrichment_status
        status = get_enrichment_status(deal_id)
    except Exception as exc:
        logger.warning("get_enrichment_status failed: %s", exc)
        status = {"error": str(exc)}
    return {
        "enrichment_enabled": enabled,
        "deal_id": deal_id,
        "status": status,
    }
