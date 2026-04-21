"""
Graph Service — Neo4j Bolt driver wrapper (Layers 5A–5G).

D-3: all operations catch exceptions and return None/False.
Falls back silently when NEO4J_PASSWORD is unset or neo4j package is absent.
"""

import logging
from typing import Any

logger = logging.getLogger("deckr.graph_service")


def _driver():
    from services.db_factory import get_neo4j_driver
    return get_neo4j_driver()


def _run(cypher: str, params: dict | None = None) -> list[dict] | None:
    """Execute a Cypher statement. Returns list of record dicts, or None on failure."""
    driver = _driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]
    except Exception as exc:
        logger.warning("Cypher query failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Schema init — run once on first boot
# ---------------------------------------------------------------------------

def init_graph_schema() -> bool:
    """Create Neo4j constraints and indexes from graph_models.CYPHER_SCHEMA."""
    try:
        from models.graph_models import CYPHER_SCHEMA
        from services.db_factory import ping_neo4j
        if not ping_neo4j():
            logger.info("Neo4j unavailable — skipping graph schema init (D-3)")
            return False
        driver = _driver()
        if driver is None:
            return False
        for stmt in [s.strip() for s in CYPHER_SCHEMA.strip().split(";") if s.strip()]:
            _run(stmt)
        logger.info("Neo4j schema initialized")
        return True
    except Exception as exc:
        logger.warning("init_graph_schema failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Layer 5A — Internal Deal Graph node writes
# ---------------------------------------------------------------------------

def write_company_node(deal_id: str, entity_id: str, legal_name: str,
                       naics_code: str | None = None,
                       role: str | None = None,
                       dba: str | None = None,
                       formation_date: str | None = None,
                       status: str | None = None,
                       **kwargs) -> bool:
    """Company node — identity fields only; no amounts."""
    cypher = """
    MERGE (c:Company {entity_id: $entity_id})
    SET c += $props
    """
    props = {
        "deal_id": deal_id, "legal_name": legal_name,
        "naics_code": naics_code, "role": role,
        "dba": dba, "formation_date": formation_date, "status": status,
        **kwargs,
    }
    return _run(cypher, {"entity_id": entity_id, "props": props}) is not None


def write_individual_node(deal_id: str, entity_id: str, legal_name: str,
                          role: str | None = None,
                          pep_flag: bool | None = None, **kwargs) -> bool:
    """Individual node — identity fields only; no SSN or full financial detail."""
    cypher = """
    MERGE (i:Individual {entity_id: $entity_id})
    SET i += $props
    """
    props = {"deal_id": deal_id, "legal_name": legal_name, "role": role, "pep_flag": pep_flag, **kwargs}
    return _run(cypher, {"entity_id": entity_id, "props": props}) is not None


def write_loan_node(deal_id: str, loan_terms_id: str,
                    loan_type: str | None = None,
                    term_months: int | None = None,
                    rate_type: str | None = None,
                    status: str | None = None,
                    **kwargs) -> bool:
    """Loan node — categorical identity fields only; no amounts, no rate numbers."""
    cypher = """
    MERGE (l:Loan {loan_terms_id: $loan_terms_id})
    SET l += $props
    """
    props = {
        "deal_id": deal_id,
        "loan_type": loan_type, "term_months": term_months,
        "rate_type": rate_type, "status": status,
        **kwargs,
    }
    return _run(cypher, {"loan_terms_id": loan_terms_id, "props": props}) is not None


def write_collateral_node(deal_id: str, collateral_id: str,
                          collateral_type: str, **kwargs) -> bool:
    """Collateral node — type/position/address only; appraised_value lives in SQL."""
    cypher = """
    MERGE (c:Collateral {collateral_id: $collateral_id})
    SET c += $props
    """
    props = {"deal_id": deal_id, "collateral_type": collateral_type, **kwargs}
    return _run(cypher, {"collateral_id": collateral_id, "props": props}) is not None


def write_document_node(document_id: str, deal_id: str, file_name: str,
                        document_type: str | None = None,
                        upload_date: str | None = None) -> bool:
    """Document node — one node per uploaded file, linked to deal."""
    cypher = """
    MERGE (d:Document {document_id: $document_id})
    SET d += $props
    """
    props = {
        "deal_id": deal_id, "file_name": file_name,
        "document_type": document_type, "upload_date": upload_date,
    }
    return _run(cypher, {"document_id": document_id, "props": props}) is not None


def write_pipeline_run_node(pipeline_run_id: str, deal_id: str,
                             started_at: str | None = None,
                             status: str | None = None) -> bool:
    """PipelineRun node — links Loan to specific evaluation run."""
    cypher = """
    MERGE (pr:PipelineRun {pipeline_run_id: $pipeline_run_id})
    SET pr += $props
    """
    props = {"deal_id": deal_id, "started_at": started_at, "status": status}
    return _run(cypher, {"pipeline_run_id": pipeline_run_id, "props": props}) is not None


def write_property_node(property_id: str, deal_id: str,
                        parcel_id: str | None = None,
                        address: str | None = None,
                        property_type: str | None = None) -> bool:
    """Property node — real-estate identity; appraised_value stays in SQL."""
    cypher = """
    MERGE (p:Property {property_id: $property_id})
    SET p += $props
    """
    props = {
        "deal_id": deal_id, "parcel_id": parcel_id,
        "address": address, "property_type": property_type,
    }
    return _run(cypher, {"property_id": property_id, "props": props}) is not None


# ---------------------------------------------------------------------------
# Layer 5A — Relationship writers
# ---------------------------------------------------------------------------

def write_guarantees_relationship(entity_id: str, loan_terms_id: str,
                                   guarantee_type: str | None = None,
                                   coverage_pct: float | None = None) -> bool:
    """Individual -[:GUARANTEES]-> Loan with guarantee_type and coverage_pct on edge."""
    cypher = """
    MATCH (i:Individual {entity_id: $entity_id})
    MATCH (l:Loan {loan_terms_id: $loan_terms_id})
    MERGE (i)-[r:GUARANTEES]->(l)
    SET r.guarantee_type = $guarantee_type, r.coverage_pct = $coverage_pct
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "loan_terms_id": loan_terms_id,
        "guarantee_type": guarantee_type,
        "coverage_pct": coverage_pct,
    }) is not None


def write_requests_relationship(entity_id: str, loan_terms_id: str,
                                 submitted_at: str | None = None) -> bool:
    """Company -[:REQUESTS]-> Loan with optional submitted_at timestamp."""
    cypher = """
    MATCH (c:Company {entity_id: $entity_id})
    MATCH (l:Loan {loan_terms_id: $loan_terms_id})
    MERGE (c)-[r:REQUESTS]->(l)
    SET r.submitted_at = $submitted_at
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "loan_terms_id": loan_terms_id,
        "submitted_at": submitted_at,
    }) is not None


def write_secured_by_relationship(loan_terms_id: str, collateral_id: str,
                                   lien_position: int | None = None,
                                   lien_type: str | None = None) -> bool:
    """Loan -[:SECURED_BY]-> Collateral"""
    cypher = """
    MATCH (l:Loan {loan_terms_id: $loan_terms_id})
    MATCH (c:Collateral {collateral_id: $collateral_id})
    MERGE (l)-[r:SECURED_BY]->(c)
    SET r.lien_position = $lien_position, r.lien_type = $lien_type
    """
    return _run(cypher, {
        "loan_terms_id": loan_terms_id,
        "collateral_id": collateral_id,
        "lien_position": lien_position,
        "lien_type": lien_type,
    }) is not None


def write_pledges_relationship(entity_id: str, collateral_id: str,
                                pledged_at: str | None = None) -> bool:
    """Company -[:PLEDGES]-> Collateral"""
    cypher = """
    MATCH (c:Company {entity_id: $entity_id})
    MATCH (col:Collateral {collateral_id: $collateral_id})
    MERGE (c)-[r:PLEDGES]->(col)
    SET r.pledged_at = $pledged_at
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "collateral_id": collateral_id,
        "pledged_at": pledged_at,
    }) is not None


def write_owns_relationship(entity_id: str, property_id: str,
                             ownership_type: str | None = None,
                             since: str | None = None) -> bool:
    """Individual/Company -[:OWNS]-> Property"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (p:Property {property_id: $property_id})
    MERGE (e)-[r:OWNS]->(p)
    SET r.ownership_type = $ownership_type, r.since = $since
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "property_id": property_id,
        "ownership_type": ownership_type,
        "since": since,
    }) is not None


def write_appears_in_edge(entity_id: str, document_id: str,
                           role: str | None = None,
                           page_reference: str | None = None) -> bool:
    """Individual/Company -[:APPEARS_IN]-> Document"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (d:Document {document_id: $document_id})
    MERGE (e)-[r:APPEARS_IN]->(d)
    SET r.role = $role, r.page_reference = $page_reference
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "document_id": document_id,
        "role": role,
        "page_reference": page_reference,
    }) is not None


def write_evaluated_in_edge(loan_terms_id: str, pipeline_run_id: str,
                             evaluated_at: str | None = None) -> bool:
    """Loan -[:EVALUATED_IN]-> PipelineRun"""
    cypher = """
    MATCH (l:Loan {loan_terms_id: $loan_terms_id})
    MATCH (pr:PipelineRun {pipeline_run_id: $pipeline_run_id})
    MERGE (l)-[r:EVALUATED_IN]->(pr)
    SET r.evaluated_at = $evaluated_at
    """
    return _run(cypher, {
        "loan_terms_id": loan_terms_id,
        "pipeline_run_id": pipeline_run_id,
        "evaluated_at": evaluated_at,
    }) is not None


def write_operates_in_relationship(entity_id: str, naics_code: str,
                                   sector: str | None = None,
                                   primary_flag: bool | None = None,
                                   since: str | None = None) -> bool:
    """Company -[:OPERATES_IN]-> Industry with primary_flag and since on edge."""
    cypher = """
    MATCH (c:Company {entity_id: $entity_id})
    MERGE (n:Industry {naics_code: $naics_code})
    ON CREATE SET n.sector = $sector
    MERGE (c)-[r:OPERATES_IN]->(n)
    SET r.primary_flag = $primary_flag, r.since = $since
    """
    return _run(cypher, {
        "entity_id": entity_id, "naics_code": naics_code,
        "sector": sector, "primary_flag": primary_flag, "since": since,
    }) is not None


# ---------------------------------------------------------------------------
# Layer 5B — External World enrichment node writes
# ---------------------------------------------------------------------------

def write_industry_enrichment(naics_code: str, macro_risk_tier: str | None = None,
                               geopolitical_risk_tier: str | None = None,
                               geopolitical_risk_factors: list | None = None) -> bool:
    """Enrich Industry node after Industry Agent runs."""
    cypher = """
    MERGE (n:Industry {naics_code: $naics_code})
    SET n.macro_risk_tier = $macro_risk_tier,
        n.geopolitical_risk_tier = $geopolitical_risk_tier,
        n.geopolitical_risk_factors = $geopolitical_risk_factors
    """
    return _run(cypher, {
        "naics_code": naics_code,
        "macro_risk_tier": macro_risk_tier,
        "geopolitical_risk_tier": geopolitical_risk_tier,
        "geopolitical_risk_factors": geopolitical_risk_factors or [],
    }) is not None


def write_news_article_node(url: str, title: str, published_date: str | None = None,
                             source: str | None = None) -> bool:
    cypher = """
    MERGE (a:NewsArticle {url: $url})
    SET a.title = $title, a.published_date = $published_date, a.source = $source
    """
    return _run(cypher, {"url": url, "title": title,
                          "published_date": published_date, "source": source}) is not None


def write_legal_action_node(entity_id: str, action_id: str,
                             case_number: str, case_type: str,
                             status: str, filed_date: str | None = None,
                             court: str | None = None,
                             jurisdiction: str | None = None) -> bool:
    """Company/Individual -[:SUBJECT_OF]-> LegalAction"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MERGE (la:LegalAction {action_id: $action_id})
    SET la.case_number = $case_number, la.case_type = $case_type,
        la.status = $status, la.filed_date = $filed_date,
        la.court = $court, la.jurisdiction = $jurisdiction,
        la.entity_id = $entity_id
    MERGE (e)-[:SUBJECT_OF]->(la)
    """
    return _run(cypher, {
        "entity_id": entity_id, "action_id": action_id,
        "case_number": case_number, "case_type": case_type,
        "status": status, "filed_date": filed_date,
        "court": court, "jurisdiction": jurisdiction,
    }) is not None


def write_party_to_edge(entity_id: str, action_id: str,
                         role: str | None = None,
                         filing_date: str | None = None) -> bool:
    """Individual/Company -[:PARTY_TO]-> LegalAction (richer than SUBJECT_OF)."""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (la:LegalAction {action_id: $action_id})
    MERGE (e)-[r:PARTY_TO]->(la)
    SET r.role = $role, r.filing_date = $filing_date
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "action_id": action_id,
        "role": role,
        "filing_date": filing_date,
    }) is not None


def write_ucc_filing_node(entity_id: str, filing_id: str,
                           filing_date: str | None = None,
                           secured_party: str | None = None,
                           state: str | None = None) -> bool:
    """Company -[:HAS_UCC_FILING]-> UccFiling (collateral_description removed — text → MongoDB)."""
    cypher = """
    MATCH (c:Company {entity_id: $entity_id})
    MERGE (u:UccFiling {filing_id: $filing_id})
    SET u.filing_date = $filing_date, u.secured_party = $secured_party, u.state = $state
    MERGE (c)-[:HAS_UCC_FILING]->(u)
    """
    return _run(cypher, {
        "entity_id": entity_id, "filing_id": filing_id,
        "filing_date": filing_date, "secured_party": secured_party, "state": state,
    }) is not None


def write_external_company_node(company_id: str, legal_name: str,
                                  jurisdiction: str | None = None,
                                  deal_id: str | None = None) -> bool:
    """Standalone ExternalCompany node — officers replaced by OFFICER_OF edges."""
    cypher = """
    MERGE (e:ExternalCompany {company_id: $company_id})
    SET e.legal_name = $legal_name, e.jurisdiction = $jurisdiction,
        e.deal_id = $deal_id
    """
    return _run(cypher, {
        "company_id": company_id, "legal_name": legal_name,
        "jurisdiction": jurisdiction, "deal_id": deal_id,
    }) is not None


def write_address_node(address_id: str, street: str | None = None,
                        city: str | None = None, state: str | None = None,
                        zip_code: str | None = None,
                        address_type: str | None = None) -> bool:
    """Address node for Layer 5B entity → address links."""
    cypher = """
    MERGE (a:Address {address_id: $address_id})
    SET a.street = $street, a.city = $city, a.state = $state,
        a.zip_code = $zip_code, a.address_type = $address_type
    """
    return _run(cypher, {
        "address_id": address_id, "street": street, "city": city,
        "state": state, "zip_code": zip_code, "address_type": address_type,
    }) is not None


def write_registered_agent_node(agent_id: str, name: str,
                                  address: str | None = None,
                                  state: str | None = None) -> bool:
    """RegisteredAgent node — for OpenCorporates shared-agent detection."""
    cypher = """
    MERGE (r:RegisteredAgent {agent_id: $agent_id})
    SET r.name = $name, r.address = $address, r.state = $state
    """
    return _run(cypher, {
        "agent_id": agent_id, "name": name,
        "address": address, "state": state,
    }) is not None


def write_review_node(review_id: str, platform: str | None = None,
                       rating: float | None = None,
                       review_date: str | None = None) -> bool:
    """Review node — star rating from public platforms; no review text (→ MongoDB)."""
    cypher = """
    MERGE (r:Review {review_id: $review_id})
    SET r.platform = $platform, r.rating = $rating, r.review_date = $review_date
    """
    return _run(cypher, {
        "review_id": review_id, "platform": platform,
        "rating": rating, "review_date": review_date,
    }) is not None


def write_judgment_node(judgment_id: str, creditor: str | None = None,
                         debtor: str | None = None,
                         filing_date: str | None = None,
                         satisfied_flag: bool | None = None) -> bool:
    """Judgment node — identity only; no judgment amount."""
    cypher = """
    MERGE (j:Judgment {judgment_id: $judgment_id})
    SET j.creditor = $creditor, j.debtor = $debtor,
        j.filing_date = $filing_date, j.satisfied_flag = $satisfied_flag
    """
    return _run(cypher, {
        "judgment_id": judgment_id, "creditor": creditor, "debtor": debtor,
        "filing_date": filing_date, "satisfied_flag": satisfied_flag,
    }) is not None


def write_subject_to_judgment_edge(entity_id: str, judgment_id: str) -> bool:
    """Property/Company -[:SUBJECT_TO_JUDGMENT]-> Judgment"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (j:Judgment {judgment_id: $judgment_id})
    MERGE (e)-[:SUBJECT_TO_JUDGMENT]->(j)
    """
    return _run(cypher, {"entity_id": entity_id, "judgment_id": judgment_id}) is not None


def write_bankruptcy_node(bk_id: str, chapter: str | None = None,
                           filing_date: str | None = None,
                           discharge_date: str | None = None,
                           status: str | None = None) -> bool:
    """Bankruptcy node — case identity only."""
    cypher = """
    MERGE (b:Bankruptcy {bk_id: $bk_id})
    SET b.chapter = $chapter, b.filing_date = $filing_date,
        b.discharge_date = $discharge_date, b.status = $status
    """
    return _run(cypher, {
        "bk_id": bk_id, "chapter": chapter, "filing_date": filing_date,
        "discharge_date": discharge_date, "status": status,
    }) is not None


def write_filed_bankruptcy_edge(entity_id: str, bk_id: str) -> bool:
    """Individual/Company -[:FILED_BANKRUPTCY]-> Bankruptcy"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (b:Bankruptcy {bk_id: $bk_id})
    MERGE (e)-[:FILED_BANKRUPTCY]->(b)
    """
    return _run(cypher, {"entity_id": entity_id, "bk_id": bk_id}) is not None


def write_affiliated_with_edge(entity_id: str, company_id: str,
                                title: str | None = None,
                                since: str | None = None) -> bool:
    """Individual -[:AFFILIATED_WITH]-> ExternalCompany"""
    cypher = """
    MATCH (i {entity_id: $entity_id})
    MATCH (c:ExternalCompany {company_id: $company_id})
    MERGE (i)-[r:AFFILIATED_WITH]->(c)
    SET r.title = $title, r.since = $since
    """
    return _run(cypher, {
        "entity_id": entity_id, "company_id": company_id,
        "title": title, "since": since,
    }) is not None


# ---------------------------------------------------------------------------
# Layer 5B — Relationship writers
# ---------------------------------------------------------------------------

def link_industry_to_article(naics_code: str, article_url: str) -> bool:
    """Industry -[:MENTIONED_IN]-> NewsArticle"""
    cypher = """
    MATCH (n:Industry {naics_code: $naics_code})
    MATCH (a:NewsArticle {url: $url})
    MERGE (n)-[:MENTIONED_IN]->(a)
    """
    return _run(cypher, {"naics_code": naics_code, "url": article_url}) is not None


def link_company_to_news_article(entity_id: str, article_url: str) -> bool:
    """Company/Individual -[:MENTIONED_IN]-> NewsArticle"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:NewsArticle {url: $url})
    MERGE (e)-[:MENTIONED_IN]->(a)
    """
    return _run(cypher, {"entity_id": entity_id, "url": article_url}) is not None


def write_located_at_edge(entity_id: str, address_id: str,
                           address_type: str | None = None) -> bool:
    """Company/Individual -[:LOCATED_AT]-> Address (5B physical address link)."""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:Address {address_id: $address_id})
    MERGE (e)-[r:LOCATED_AT]->(a)
    SET r.address_type = $address_type
    """
    return _run(cypher, {
        "entity_id": entity_id, "address_id": address_id,
        "address_type": address_type,
    }) is not None


def write_resides_at_edge(entity_id: str, address_id: str) -> bool:
    """Individual -[:RESIDES_AT]-> Address"""
    cypher = """
    MATCH (i:Individual {entity_id: $entity_id})
    MATCH (a:Address {address_id: $address_id})
    MERGE (i)-[:RESIDES_AT]->(a)
    """
    return _run(cypher, {"entity_id": entity_id, "address_id": address_id}) is not None


def write_shares_address_edge(entity_id_a: str, entity_id_b: str,
                               address_id: str) -> bool:
    """Company -[:SHARES_ADDRESS]-> Company (insider detection)."""
    cypher = """
    MATCH (a {entity_id: $entity_id_a})
    MATCH (b {entity_id: $entity_id_b})
    MERGE (a)-[r:SHARES_ADDRESS]->(b)
    SET r.address_id = $address_id
    """
    return _run(cypher, {
        "entity_id_a": entity_id_a,
        "entity_id_b": entity_id_b,
        "address_id": address_id,
    }) is not None


def write_shares_agent_edge(entity_id: str, agent_id: str) -> bool:
    """Company -[:SHARES_AGENT]-> RegisteredAgent"""
    cypher = """
    MATCH (c {entity_id: $entity_id})
    MATCH (r:RegisteredAgent {agent_id: $agent_id})
    MERGE (c)-[:SHARES_AGENT]->(r)
    """
    return _run(cypher, {"entity_id": entity_id, "agent_id": agent_id}) is not None


def write_connected_to_edge(entity_id_a: str, entity_id_b: str,
                             reason: str = "shared_address") -> bool:
    """Cross-entity insider detection edge."""
    cypher = """
    MATCH (a {entity_id: $entity_id_a})
    MATCH (b {entity_id: $entity_id_b})
    MERGE (a)-[r:CONNECTED_TO]->(b)
    SET r.reason = $reason
    """
    return _run(cypher, {
        "entity_id_a": entity_id_a,
        "entity_id_b": entity_id_b,
        "reason": reason,
    }) is not None


# ---------------------------------------------------------------------------
# Collateral enrichment — APPRAISED_BY / SUBJECT_TO edges
# ---------------------------------------------------------------------------

def write_appraised_by_edge(collateral_id: str, appraiser_name: str,
                             appraisal_date: str | None = None) -> bool:
    """Collateral -[:APPRAISED_BY]-> Appraiser. Only appraisal_date on edge per Phase 2C target."""
    cypher = """
    MATCH (c:Collateral {collateral_id: $collateral_id})
    MERGE (a:Appraiser {appraiser_name: $appraiser_name})
    MERGE (c)-[r:APPRAISED_BY]->(a)
    SET r.appraisal_date = $appraisal_date
    """
    return _run(cypher, {
        "collateral_id": collateral_id,
        "appraiser_name": appraiser_name,
        "appraisal_date": appraisal_date,
    }) is not None


def write_subject_to_lien(collateral_id: str, lien_id: str,
                           lien_type: str = "UCC",
                           filing_date: str | None = None,
                           status: str | None = None,
                           state: str | None = None,
                           recording_date: str | None = None) -> bool:
    """Collateral -[:SUBJECT_TO]-> Lien.

    Lien node: lien_type, filing_date, status, state (identity only — no amount, no secured_party).
    SUBJECT_TO edge: lien_type, recording_date (per Phase 2C target).
    """
    cypher = """
    MATCH (c:Collateral {collateral_id: $collateral_id})
    MERGE (l:Lien {lien_id: $lien_id})
    SET l.lien_type = $lien_type, l.filing_date = $filing_date,
        l.status = $status, l.state = $state
    MERGE (c)-[r:SUBJECT_TO]->(l)
    SET r.lien_type = $lien_type, r.recording_date = $recording_date
    """
    return _run(cypher, {
        "collateral_id": collateral_id,
        "lien_id": lien_id,
        "lien_type": lien_type,
        "filing_date": filing_date,
        "status": status,
        "state": state,
        "recording_date": recording_date,
    }) is not None


# ---------------------------------------------------------------------------
# Layer 5C — Deep Identity & Ownership Network
# ---------------------------------------------------------------------------

def write_trust_entity_node(trust_id: str, trust_name: str,
                             trustee_entity_id: str | None = None,
                             trust_type: str | None = None) -> bool:
    cypher = """
    MERGE (t:TrustEntity {trust_id: $trust_id})
    SET t.trust_name = $trust_name, t.trustee_entity_id = $trustee_entity_id,
        t.trust_type = $trust_type
    """
    return _run(cypher, {
        "trust_id": trust_id, "trust_name": trust_name,
        "trustee_entity_id": trustee_entity_id, "trust_type": trust_type,
    }) is not None


def write_ubo_node(entity_id: str, ownership_pct_total: float | None = None,
                    verification_method: str | None = None) -> bool:
    """Add :UltimateBeneficialOwner label to an existing Individual node (label alias per Phase 2C).
    The Individual node must already exist. UBO classification is additive, not a new node."""
    cypher = """
    MATCH (i:Individual {entity_id: $entity_id})
    SET i:UltimateBeneficialOwner,
        i.ownership_pct_total = $ownership_pct_total,
        i.verification_method = $verification_method
    """
    return _run(cypher, {
        "entity_id": entity_id,
        "ownership_pct_total": ownership_pct_total,
        "verification_method": verification_method,
    }) is not None


def write_sanctioned_entity_node(ofac_id: str, name: str,
                                   aliases: list | None = None,
                                   listing_date: str | None = None,
                                   list_type: str | None = None) -> bool:
    cypher = """
    MERGE (s:SanctionedEntity {ofac_id: $ofac_id})
    SET s.name = $name, s.aliases = $aliases,
        s.listing_date = $listing_date, s.list_type = $list_type
    """
    return _run(cypher, {
        "ofac_id": ofac_id, "name": name,
        "aliases": aliases or [], "listing_date": listing_date, "list_type": list_type,
    }) is not None


def write_pep_node(pep_id: str, name: str, office: str | None = None,
                    jurisdiction: str | None = None,
                    tenure_start: str | None = None,
                    tenure_end: str | None = None) -> bool:
    cypher = """
    MERGE (p:PEP {pep_id: $pep_id})
    SET p.name = $name, p.office = $office, p.jurisdiction = $jurisdiction,
        p.tenure_start = $tenure_start, p.tenure_end = $tenure_end
    """
    return _run(cypher, {
        "pep_id": pep_id, "name": name, "office": office,
        "jurisdiction": jurisdiction, "tenure_start": tenure_start, "tenure_end": tenure_end,
    }) is not None


def write_shell_indicator_node(indicator_id: str, pattern_type: str | None = None,
                                confidence_score: float | None = None,
                                detected_at: str | None = None) -> bool:
    cypher = """
    MERGE (s:ShellIndicator {indicator_id: $indicator_id})
    SET s.pattern_type = $pattern_type, s.confidence_score = $confidence_score,
        s.detected_at = $detected_at
    """
    return _run(cypher, {
        "indicator_id": indicator_id, "pattern_type": pattern_type,
        "confidence_score": confidence_score, "detected_at": detected_at,
    }) is not None


def write_controls_edge(entity_id_controller: str, entity_id_controlled: str,
                         title: str | None = None, since: str | None = None,
                         control_type: str | None = None) -> bool:
    """Entity -[:CONTROLS]-> Entity (ownership chain traversal)."""
    cypher = """
    MATCH (a {entity_id: $controller})
    MATCH (b {entity_id: $controlled})
    MERGE (a)-[r:CONTROLS]->(b)
    SET r.title = $title, r.since = $since, r.control_type = $control_type
    """
    return _run(cypher, {
        "controller": entity_id_controller, "controlled": entity_id_controlled,
        "title": title, "since": since, "control_type": control_type,
    }) is not None


def write_beneficial_owner_edge(entity_id: str, company_id: str,
                                  pct_beneficial: float | None = None,
                                  verification_method: str | None = None) -> bool:
    """Individual -[:BENEFICIAL_OWNER]-> Company"""
    cypher = """
    MATCH (i {entity_id: $entity_id})
    MATCH (c {entity_id: $company_id})
    MERGE (i)-[r:BENEFICIAL_OWNER]->(c)
    SET r.pct_beneficial = $pct_beneficial,
        r.verification_method = $verification_method
    """
    return _run(cypher, {
        "entity_id": entity_id, "company_id": company_id,
        "pct_beneficial": pct_beneficial, "verification_method": verification_method,
    }) is not None


def write_holds_in_trust_edge(entity_id: str, trust_id: str,
                               beneficiary_role: str | None = None) -> bool:
    """Entity -[:HOLDS_IN_TRUST]-> TrustEntity (makes TrustEntity nodes traversable)."""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (t:TrustEntity {trust_id: $trust_id})
    MERGE (e)-[r:HOLDS_IN_TRUST]->(t)
    SET r.beneficiary_role = $beneficiary_role
    """
    return _run(cypher, {
        "entity_id": entity_id, "trust_id": trust_id,
        "beneficiary_role": beneficiary_role,
    }) is not None


def write_managed_by_edge(entity_id_managed: str, entity_id_manager: str,
                           title: str | None = None,
                           since: str | None = None) -> bool:
    """Entity -[:MANAGED_BY]-> Manager"""
    cypher = """
    MATCH (a {entity_id: $managed})
    MATCH (b {entity_id: $manager})
    MERGE (a)-[r:MANAGED_BY]->(b)
    SET r.title = $title, r.since = $since
    """
    return _run(cypher, {
        "managed": entity_id_managed, "manager": entity_id_manager,
        "title": title, "since": since,
    }) is not None


def write_officer_of_edge(individual_id: str, company_id: str,
                           title: str | None = None,
                           since: str | None = None) -> bool:
    """Individual -[:OFFICER_OF]-> ExternalCompany (replaces officers[] list on node)."""
    cypher = """
    MATCH (i {entity_id: $individual_id})
    MATCH (c:ExternalCompany {company_id: $company_id})
    MERGE (i)-[r:OFFICER_OF]->(c)
    SET r.title = $title, r.since = $since
    """
    return _run(cypher, {
        "individual_id": individual_id, "company_id": company_id,
        "title": title, "since": since,
    }) is not None


def write_formerly_owned_edge(entity_id: str, company_id: str,
                               from_date: str | None = None,
                               to_date: str | None = None,
                               exit_reason: str | None = None,
                               outcome: str | None = None) -> bool:
    """Individual/Company -[:FORMERLY_OWNED]-> Company"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (c {entity_id: $company_id})
    MERGE (e)-[r:FORMERLY_OWNED]->(c)
    SET r.from_date = $from_date, r.to_date = $to_date,
        r.exit_reason = $exit_reason, r.outcome = $outcome
    """
    return _run(cypher, {
        "entity_id": entity_id, "company_id": company_id,
        "from_date": from_date, "to_date": to_date,
        "exit_reason": exit_reason, "outcome": outcome,
    }) is not None


def write_successor_to_edge(company_id_a: str, company_id_b: str,
                             via: str | None = None,
                             effective_date: str | None = None) -> bool:
    """Company -[:SUCCESSOR_TO]-> Company"""
    cypher = """
    MATCH (a {entity_id: $company_id_a})
    MATCH (b {entity_id: $company_id_b})
    MERGE (a)-[r:SUCCESSOR_TO]->(b)
    SET r.via = $via, r.effective_date = $effective_date
    """
    return _run(cypher, {
        "company_id_a": company_id_a, "company_id_b": company_id_b,
        "via": via, "effective_date": effective_date,
    }) is not None


def write_spouse_of_edge(entity_id_a: str, entity_id_b: str,
                          as_of: str | None = None) -> bool:
    """Individual -[:SPOUSE_OF]-> Individual"""
    cypher = """
    MATCH (a {entity_id: $entity_id_a})
    MATCH (b {entity_id: $entity_id_b})
    MERGE (a)-[r:SPOUSE_OF]->(b)
    SET r.as_of = $as_of
    """
    return _run(cypher, {
        "entity_id_a": entity_id_a, "entity_id_b": entity_id_b,
        "as_of": as_of,
    }) is not None


def write_related_to_edge(entity_id_a: str, entity_id_b: str,
                           relationship_type: str | None = None,
                           relevance: str | None = None) -> bool:
    """Entity -[:RELATED_TO]-> Entity"""
    cypher = """
    MATCH (a {entity_id: $entity_id_a})
    MATCH (b {entity_id: $entity_id_b})
    MERGE (a)-[r:RELATED_TO]->(b)
    SET r.relationship_type = $relationship_type, r.relevance = $relevance
    """
    return _run(cypher, {
        "entity_id_a": entity_id_a, "entity_id_b": entity_id_b,
        "relationship_type": relationship_type, "relevance": relevance,
    }) is not None


def write_is_pep_edge(entity_id: str, agency_id: str,
                       office: str | None = None,
                       tenure_start: str | None = None,
                       tenure_end: str | None = None,
                       active_flag: bool | None = None) -> bool:
    """Individual -[:IS_PEP]-> GovernmentAgency"""
    cypher = """
    MATCH (i {entity_id: $entity_id})
    MATCH (a:GovernmentAgency {agency_id: $agency_id})
    MERGE (i)-[r:IS_PEP]->(a)
    SET r.office = $office, r.tenure_start = $tenure_start,
        r.tenure_end = $tenure_end, r.active_flag = $active_flag
    """
    return _run(cypher, {
        "entity_id": entity_id, "agency_id": agency_id,
        "office": office, "tenure_start": tenure_start,
        "tenure_end": tenure_end, "active_flag": active_flag,
    }) is not None


def write_connected_to_sanction_edge(entity_id: str, ofac_id: str,
                                      hop_distance: int | None = None,
                                      connection_type: str | None = None) -> bool:
    """Entity -[:CONNECTED_TO_SANCTION]-> SanctionedEntity"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (s:SanctionedEntity {ofac_id: $ofac_id})
    MERGE (e)-[r:CONNECTED_TO_SANCTION]->(s)
    SET r.hop_distance = $hop_distance, r.connection_type = $connection_type
    """
    return _run(cypher, {
        "entity_id": entity_id, "ofac_id": ofac_id,
        "hop_distance": hop_distance, "connection_type": connection_type,
    }) is not None


# ---------------------------------------------------------------------------
# Layer 5D — Market Network
# ---------------------------------------------------------------------------

def write_competitor_node(competitor_id: str, legal_name: str,
                           naics_code: str | None = None,
                           market_overlap_pct: float | None = None,
                           deal_id: str | None = None) -> bool:
    """Add :Competitor label to an existing or new Company node (Company alias per Phase 2C)."""
    cypher = """
    MERGE (c:Company {entity_id: $competitor_id})
    ON CREATE SET c.legal_name = $legal_name, c.naics_code = $naics_code, c.deal_id = $deal_id
    SET c:Competitor, c.market_overlap_pct = $market_overlap_pct
    """
    return _run(cypher, {
        "competitor_id": competitor_id, "legal_name": legal_name,
        "naics_code": naics_code, "market_overlap_pct": market_overlap_pct,
        "deal_id": deal_id,
    }) is not None


def write_key_customer_node(customer_id: str, legal_name: str,
                             revenue_concentration_flag: bool | None = None,
                             deal_id: str | None = None) -> bool:
    """Add :KeyCustomer label to an existing or new Company node (Company alias per Phase 2C)."""
    cypher = """
    MERGE (k:Company {entity_id: $customer_id})
    ON CREATE SET k.legal_name = $legal_name, k.deal_id = $deal_id
    SET k:KeyCustomer, k.revenue_concentration_flag = $revenue_concentration_flag
    """
    return _run(cypher, {
        "customer_id": customer_id, "legal_name": legal_name,
        "revenue_concentration_flag": revenue_concentration_flag, "deal_id": deal_id,
    }) is not None


def write_key_supplier_node(supplier_id: str, legal_name: str,
                             supply_dependency_flag: bool | None = None,
                             deal_id: str | None = None) -> bool:
    """Add :KeySupplier label to an existing or new Company node (Company alias per Phase 2C)."""
    cypher = """
    MERGE (k:Company {entity_id: $supplier_id})
    ON CREATE SET k.legal_name = $legal_name, k.deal_id = $deal_id
    SET k:KeySupplier, k.supply_dependency_flag = $supply_dependency_flag
    """
    return _run(cypher, {
        "supplier_id": supplier_id, "legal_name": legal_name,
        "supply_dependency_flag": supply_dependency_flag, "deal_id": deal_id,
    }) is not None


def write_franchise_system_node(franchise_id: str, franchise_name: str,
                                  franchisor_entity_id: str | None = None) -> bool:
    cypher = """
    MERGE (f:FranchiseSystem {franchise_id: $franchise_id})
    SET f.franchise_name = $franchise_name,
        f.franchisor_entity_id = $franchisor_entity_id
    """
    return _run(cypher, {
        "franchise_id": franchise_id, "franchise_name": franchise_name,
        "franchisor_entity_id": franchisor_entity_id,
    }) is not None


def write_joint_venture_node(jv_id: str, jv_name: str,
                              formation_date: str | None = None) -> bool:
    cypher = """
    MERGE (j:JointVenture {jv_id: $jv_id})
    SET j.jv_name = $jv_name, j.formation_date = $formation_date
    """
    return _run(cypher, {
        "jv_id": jv_id, "jv_name": jv_name, "formation_date": formation_date,
    }) is not None


def write_trade_association_node(association_id: str, name: str,
                                   industry_scope: str | None = None) -> bool:
    cypher = """
    MERGE (t:TradeAssociation {association_id: $association_id})
    SET t.name = $name, t.industry_scope = $industry_scope
    """
    return _run(cypher, {
        "association_id": association_id, "name": name,
        "industry_scope": industry_scope,
    }) is not None


def write_industry_certification_node(cert_id: str, cert_name: str,
                                        issuing_body: str | None = None,
                                        expiration_date: str | None = None) -> bool:
    cypher = """
    MERGE (c:IndustryCertification {cert_id: $cert_id})
    SET c.cert_name = $cert_name, c.issuing_body = $issuing_body,
        c.expiration_date = $expiration_date
    """
    return _run(cypher, {
        "cert_id": cert_id, "cert_name": cert_name,
        "issuing_body": issuing_body, "expiration_date": expiration_date,
    }) is not None


def write_competes_with_edge(entity_id_a: str, entity_id_b: str) -> bool:
    cypher = """
    MATCH (a {entity_id: $a})
    MATCH (b {entity_id: $b})
    MERGE (a)-[:COMPETES_WITH]->(b)
    """
    return _run(cypher, {"a": entity_id_a, "b": entity_id_b}) is not None


def write_supplies_to_edge(supplier_id: str, entity_id: str) -> bool:
    cypher = """
    MATCH (s {entity_id: $supplier_id})
    MATCH (e {entity_id: $entity_id})
    MERGE (s)-[:SUPPLIES_TO]->(e)
    """
    return _run(cypher, {"supplier_id": supplier_id, "entity_id": entity_id}) is not None


def write_purchases_from_edge(entity_id: str, supplier_id: str) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (s {entity_id: $supplier_id})
    MERGE (e)-[:PURCHASES_FROM]->(s)
    """
    return _run(cypher, {"entity_id": entity_id, "supplier_id": supplier_id}) is not None


def write_franchisee_of_edge(entity_id: str, franchise_id: str) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (f:FranchiseSystem {franchise_id: $franchise_id})
    MERGE (e)-[:FRANCHISEE_OF]->(f)
    """
    return _run(cypher, {"entity_id": entity_id, "franchise_id": franchise_id}) is not None


def write_member_of_edge(entity_id: str, association_id: str,
                          since: str | None = None) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:TradeAssociation {association_id: $association_id})
    MERGE (e)-[r:MEMBER_OF]->(a)
    SET r.since = $since
    """
    return _run(cypher, {
        "entity_id": entity_id, "association_id": association_id, "since": since,
    }) is not None


def write_holds_cert_edge(entity_id: str, cert_id: str,
                           issued_date: str | None = None) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (c:IndustryCertification {cert_id: $cert_id})
    MERGE (e)-[r:HOLDS_CERT]->(c)
    SET r.issued_date = $issued_date
    """
    return _run(cypher, {
        "entity_id": entity_id, "cert_id": cert_id, "issued_date": issued_date,
    }) is not None


# ---------------------------------------------------------------------------
# Layer 5E — Regulatory Network
# ---------------------------------------------------------------------------

def write_government_agency_node(agency_id: str, name: str,
                                   agency_type: str | None = None,
                                   jurisdiction: str | None = None) -> bool:
    cypher = """
    MERGE (g:GovernmentAgency {agency_id: $agency_id})
    SET g.name = $name, g.agency_type = $agency_type, g.jurisdiction = $jurisdiction
    """
    return _run(cypher, {
        "agency_id": agency_id, "name": name,
        "agency_type": agency_type, "jurisdiction": jurisdiction,
    }) is not None


def write_court_node(court_id: str, court_name: str,
                      court_type: str | None = None,
                      jurisdiction: str | None = None) -> bool:
    cypher = """
    MERGE (c:Court {court_id: $court_id})
    SET c.court_name = $court_name, c.court_type = $court_type,
        c.jurisdiction = $jurisdiction
    """
    return _run(cypher, {
        "court_id": court_id, "court_name": court_name,
        "court_type": court_type, "jurisdiction": jurisdiction,
    }) is not None


def write_regulatory_action_node(action_id: str, action_type: str,
                                   agency_id: str | None = None,
                                   filing_date: str | None = None,
                                   resolution_status: str | None = None) -> bool:
    cypher = """
    MERGE (r:RegulatoryAction {action_id: $action_id})
    SET r.action_type = $action_type, r.agency_id = $agency_id,
        r.filing_date = $filing_date, r.resolution_status = $resolution_status
    """
    return _run(cypher, {
        "action_id": action_id, "action_type": action_type,
        "agency_id": agency_id, "filing_date": filing_date,
        "resolution_status": resolution_status,
    }) is not None


def write_government_contract_node(contract_id: str, contract_type: str | None = None,
                                     agency_id: str | None = None,
                                     period_of_performance: str | None = None) -> bool:
    cypher = """
    MERGE (g:GovernmentContract {contract_id: $contract_id})
    SET g.contract_type = $contract_type, g.agency_id = $agency_id,
        g.period_of_performance = $period_of_performance
    """
    return _run(cypher, {
        "contract_id": contract_id, "contract_type": contract_type,
        "agency_id": agency_id, "period_of_performance": period_of_performance,
    }) is not None


def write_sba_guarantee_node(sba_id: str, program_type: str | None = None,
                               guarantee_pct: float | None = None) -> bool:
    cypher = """
    MERGE (s:SBAGuarantee {sba_id: $sba_id})
    SET s.program_type = $program_type, s.guarantee_pct = $guarantee_pct
    """
    return _run(cypher, {
        "sba_id": sba_id, "program_type": program_type,
        "guarantee_pct": guarantee_pct,
    }) is not None


def write_jurisdiction_node(jurisdiction_id: str, name: str,
                              jurisdiction_type: str | None = None) -> bool:
    cypher = """
    MERGE (j:Jurisdiction {jurisdiction_id: $jurisdiction_id})
    SET j.name = $name, j.jurisdiction_type = $jurisdiction_type
    """
    return _run(cypher, {
        "jurisdiction_id": jurisdiction_id, "name": name,
        "jurisdiction_type": jurisdiction_type,
    }) is not None


def write_regulated_by_edge(entity_id: str, agency_id: str) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:GovernmentAgency {agency_id: $agency_id})
    MERGE (e)-[:REGULATED_BY]->(a)
    """
    return _run(cypher, {"entity_id": entity_id, "agency_id": agency_id}) is not None


def write_licensed_by_edge(entity_id: str, agency_id: str,
                            license_type: str | None = None,
                            expiration_date: str | None = None) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:GovernmentAgency {agency_id: $agency_id})
    MERGE (e)-[r:LICENSED_BY]->(a)
    SET r.license_type = $license_type, r.expiration_date = $expiration_date
    """
    return _run(cypher, {
        "entity_id": entity_id, "agency_id": agency_id,
        "license_type": license_type, "expiration_date": expiration_date,
    }) is not None


def write_investigated_by_edge(entity_id: str, agency_id: str,
                                 action_id: str | None = None) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:GovernmentAgency {agency_id: $agency_id})
    MERGE (e)-[r:INVESTIGATED_BY]->(a)
    SET r.action_id = $action_id
    """
    return _run(cypher, {
        "entity_id": entity_id, "agency_id": agency_id, "action_id": action_id,
    }) is not None


def write_presided_by_edge(action_id: str, court_id: str) -> bool:
    cypher = """
    MATCH (a:LegalAction {action_id: $action_id})
    MATCH (c:Court {court_id: $court_id})
    MERGE (a)-[:PRESIDED_BY]->(c)
    """
    return _run(cypher, {"action_id": action_id, "court_id": court_id}) is not None


def write_filed_with_edge(entity_id: str, agency_id: str,
                           filing_type: str | None = None) -> bool:
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:GovernmentAgency {agency_id: $agency_id})
    MERGE (e)-[r:FILED_WITH]->(a)
    SET r.filing_type = $filing_type
    """
    return _run(cypher, {
        "entity_id": entity_id, "agency_id": agency_id, "filing_type": filing_type,
    }) is not None


def write_sba_backed_edge(loan_terms_id: str, sba_id: str) -> bool:
    """Loan -[:SBA_BACKED]-> SBAGuarantee"""
    cypher = """
    MATCH (l:Loan {loan_terms_id: $loan_terms_id})
    MATCH (s:SBAGuarantee {sba_id: $sba_id})
    MERGE (l)-[:SBA_BACKED]->(s)
    """
    return _run(cypher, {"loan_terms_id": loan_terms_id, "sba_id": sba_id}) is not None


# ---------------------------------------------------------------------------
# Layer 5F — Geographic Network
# ---------------------------------------------------------------------------

def write_city_node(city_id: str, city_name: str,
                     state_code: str | None = None,
                     county: str | None = None) -> bool:
    cypher = """
    MERGE (c:City {city_id: $city_id})
    SET c.city_name = $city_name, c.state_code = $state_code, c.county = $county
    """
    return _run(cypher, {
        "city_id": city_id, "city_name": city_name,
        "state_code": state_code, "county": county,
    }) is not None


def write_state_node(state_code: str, state_name: str,
                      country_code: str | None = None) -> bool:
    cypher = """
    MERGE (s:State {state_code: $state_code})
    SET s.state_name = $state_name, s.country_code = $country_code
    """
    return _run(cypher, {
        "state_code": state_code, "state_name": state_name, "country_code": country_code,
    }) is not None


def write_country_node(country_code: str, country_name: str,
                        sanctions_flag: bool | None = None) -> bool:
    cypher = """
    MERGE (c:Country {country_code: $country_code})
    SET c.country_name = $country_name, c.sanctions_flag = $sanctions_flag
    """
    return _run(cypher, {
        "country_code": country_code, "country_name": country_name,
        "sanctions_flag": sanctions_flag,
    }) is not None


def write_economic_zone_node(zone_id: str, zone_name: str,
                               zone_type: str | None = None) -> bool:
    cypher = """
    MERGE (e:EconomicZone {zone_id: $zone_id})
    SET e.zone_name = $zone_name, e.zone_type = $zone_type
    """
    return _run(cypher, {
        "zone_id": zone_id, "zone_name": zone_name, "zone_type": zone_type,
    }) is not None


def write_incorporated_in_edge(entity_id: str, state_code: str) -> bool:
    """Company -[:INCORPORATED_IN]-> State"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (s:State {state_code: $state_code})
    MERGE (e)-[:INCORPORATED_IN]->(s)
    """
    return _run(cypher, {"entity_id": entity_id, "state_code": state_code}) is not None


def write_operating_in_edge(entity_id: str, state_code: str) -> bool:
    """Company -[:OPERATING_IN]-> State"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (s:State {state_code: $state_code})
    MERGE (e)-[:OPERATING_IN]->(s)
    """
    return _run(cypher, {"entity_id": entity_id, "state_code": state_code}) is not None


def write_located_at_geo_edge(entity_id: str, geo_node_id: str,
                               geo_type: str = "City") -> bool:
    """Company/Individual -[:LOCATED_AT_GEO]-> City/State (5F geographic link).

    geo_type must be 'City' or 'State'. Distinct from 5B LOCATED_AT (entity → Address).
    """
    if geo_type == "City":
        cypher = """
        MATCH (e {entity_id: $entity_id})
        MATCH (g:City {city_id: $geo_node_id})
        MERGE (e)-[:LOCATED_AT_GEO]->(g)
        """
    else:
        cypher = """
        MATCH (e {entity_id: $entity_id})
        MATCH (g:State {state_code: $geo_node_id})
        MERGE (e)-[:LOCATED_AT_GEO]->(g)
        """
    return _run(cypher, {"entity_id": entity_id, "geo_node_id": geo_node_id}) is not None


# ---------------------------------------------------------------------------
# Layer 5G — Banking & Credit Network
# ---------------------------------------------------------------------------

def write_bank_node(bank_id: str, bank_name: str,
                     fdic_cert: str | None = None,
                     charter_type: str | None = None) -> bool:
    cypher = """
    MERGE (b:Bank {bank_id: $bank_id})
    SET b.bank_name = $bank_name, b.fdic_cert = $fdic_cert,
        b.charter_type = $charter_type
    """
    return _run(cypher, {
        "bank_id": bank_id, "bank_name": bank_name,
        "fdic_cert": fdic_cert, "charter_type": charter_type,
    }) is not None


def write_prior_lender_node(lender_id: str, lender_name: str,
                              lender_type: str | None = None) -> bool:
    cypher = """
    MERGE (p:PriorLender {lender_id: $lender_id})
    SET p.lender_name = $lender_name, p.lender_type = $lender_type
    """
    return _run(cypher, {
        "lender_id": lender_id, "lender_name": lender_name, "lender_type": lender_type,
    }) is not None


def write_credit_facility_node(facility_id: str, facility_type: str | None = None,
                                 term_months: int | None = None,
                                 outcome: str | None = None) -> bool:
    cypher = """
    MERGE (c:CreditFacility {facility_id: $facility_id})
    SET c.facility_type = $facility_type, c.term_months = $term_months,
        c.outcome = $outcome
    """
    return _run(cypher, {
        "facility_id": facility_id, "facility_type": facility_type,
        "term_months": term_months, "outcome": outcome,
    }) is not None


def write_insurance_carrier_node(carrier_id: str, carrier_name: str,
                                   am_best_rating: str | None = None) -> bool:
    cypher = """
    MERGE (i:InsuranceCarrier {carrier_id: $carrier_id})
    SET i.carrier_name = $carrier_name, i.am_best_rating = $am_best_rating
    """
    return _run(cypher, {
        "carrier_id": carrier_id, "carrier_name": carrier_name,
        "am_best_rating": am_best_rating,
    }) is not None


def write_banks_with_edge(entity_id: str, bank_id: str,
                           since: str | None = None) -> bool:
    """Company -[:BANKS_WITH]-> Bank"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (b:Bank {bank_id: $bank_id})
    MERGE (e)-[r:BANKS_WITH]->(b)
    SET r.since = $since
    """
    return _run(cypher, {
        "entity_id": entity_id, "bank_id": bank_id, "since": since,
    }) is not None


def write_had_loan_with_edge(entity_id: str, lender_id: str,
                              facility_id: str | None = None) -> bool:
    """Company -[:HAD_LOAN_WITH]-> PriorLender"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (l:PriorLender {lender_id: $lender_id})
    MERGE (e)-[r:HAD_LOAN_WITH]->(l)
    SET r.facility_id = $facility_id
    """
    return _run(cypher, {
        "entity_id": entity_id, "lender_id": lender_id, "facility_id": facility_id,
    }) is not None


def write_insured_by_edge(entity_id: str, carrier_id: str,
                           policy_type: str | None = None) -> bool:
    """Company -[:INSURED_BY]-> InsuranceCarrier"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (c:InsuranceCarrier {carrier_id: $carrier_id})
    MERGE (e)-[r:INSURED_BY]->(c)
    SET r.policy_type = $policy_type
    """
    return _run(cypher, {
        "entity_id": entity_id, "carrier_id": carrier_id, "policy_type": policy_type,
    }) is not None


# ---------------------------------------------------------------------------
# Traversal queries (used by /api/graph/* endpoints)
# ---------------------------------------------------------------------------

def get_deal_graph(deal_id: str) -> dict[str, Any]:
    """Return all nodes and relationships scoped to a deal_id."""
    nodes_result = _run(
        "MATCH (n {deal_id: $deal_id}) RETURN labels(n) AS labels, properties(n) AS props",
        {"deal_id": deal_id}
    )
    rels_result = _run(
        """
        MATCH (a {deal_id: $deal_id})-[r]-(b)
        RETURN properties(a) AS source, type(r) AS rel_type, properties(b) AS target
        """,
        {"deal_id": deal_id}
    )
    nodes = [
        {"labels": row.get("labels", []), **dict(row.get("props") or {})}
        for row in (nodes_result or [])
    ]
    relationships = [
        {
            "source": dict(row.get("source") or {}),
            "type":   row.get("rel_type"),
            "target": dict(row.get("target") or {}),
        }
        for row in (rels_result or [])
    ]
    return {
        "nodes": nodes,
        "relationships": relationships,
    }


def get_guarantor_network(deal_id: str) -> list[dict]:
    """Return all guarantors and their GUARANTEES relationships for a deal."""
    result = _run(
        """
        MATCH (i:Individual {deal_id: $deal_id})-[:GUARANTEES]->(l:Loan {deal_id: $deal_id})
        RETURN i.legal_name AS guarantor, l.loan_terms_id AS loan_terms_id,
               i.entity_id AS entity_id
        """,
        {"deal_id": deal_id}
    )
    return result or []


# ---------------------------------------------------------------------------
# IP2 gate check helpers
# ---------------------------------------------------------------------------

def get_industry_macro_risk_tier(naics_code: str) -> str | None:
    """Return the macro_risk_tier for an Industry node, or None if unset/missing."""
    result = _run(
        "MATCH (n:Industry {naics_code: $code}) RETURN n.macro_risk_tier AS tier",
        {"code": naics_code}
    )
    if not result:
        return None
    return result[0].get("tier")
