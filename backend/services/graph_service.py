"""
Graph Service — Neo4j Bolt driver wrapper (Layer 5A + 5B).

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
                       naics_code: str | None = None, **kwargs) -> bool:
    cypher = """
    MERGE (c:Company {entity_id: $entity_id})
    SET c += $props
    """
    props = {"deal_id": deal_id, "legal_name": legal_name,
             "naics_code": naics_code, **kwargs}
    return _run(cypher, {"entity_id": entity_id, "props": props}) is not None


def write_individual_node(deal_id: str, entity_id: str, legal_name: str,
                          **kwargs) -> bool:
    cypher = """
    MERGE (i:Individual {entity_id: $entity_id})
    SET i += $props
    """
    props = {"deal_id": deal_id, "legal_name": legal_name, **kwargs}
    return _run(cypher, {"entity_id": entity_id, "props": props}) is not None


def write_loan_node(deal_id: str, loan_terms_id: str, loan_amount: float,
                    **kwargs) -> bool:
    cypher = """
    MERGE (l:Loan {loan_terms_id: $loan_terms_id})
    SET l += $props
    """
    props = {"deal_id": deal_id, "loan_amount": loan_amount, **kwargs}
    return _run(cypher, {"loan_terms_id": loan_terms_id, "props": props}) is not None


def write_collateral_node(deal_id: str, collateral_id: str,
                          collateral_type: str, appraised_value: float | None = None,
                          **kwargs) -> bool:
    cypher = """
    MERGE (c:Collateral {collateral_id: $collateral_id})
    SET c += $props
    """
    props = {"deal_id": deal_id, "collateral_type": collateral_type,
             "appraised_value": appraised_value, **kwargs}
    return _run(cypher, {"collateral_id": collateral_id, "props": props}) is not None


def write_guarantees_relationship(entity_id: str, loan_terms_id: str) -> bool:
    """Individual -[:GUARANTEES]-> Loan"""
    cypher = """
    MATCH (i:Individual {entity_id: $entity_id})
    MATCH (l:Loan {loan_terms_id: $loan_terms_id})
    MERGE (i)-[:GUARANTEES]->(l)
    """
    return _run(cypher, {"entity_id": entity_id, "loan_terms_id": loan_terms_id}) is not None


def write_operates_in_relationship(entity_id: str, naics_code: str,
                                   sector: str | None = None) -> bool:
    """Company -[:OPERATES_IN]-> Industry"""
    cypher = """
    MATCH (c:Company {entity_id: $entity_id})
    MERGE (n:Industry {naics_code: $naics_code})
    ON CREATE SET n.sector = $sector
    MERGE (c)-[:OPERATES_IN]->(n)
    """
    return _run(cypher, {"entity_id": entity_id, "naics_code": naics_code,
                          "sector": sector}) is not None


# ---------------------------------------------------------------------------
# Layer 5B — External World enrichment node writes
# ---------------------------------------------------------------------------

def write_industry_enrichment(naics_code: str, macro_risk_tier: str | None = None,
                               geopolitical_risk_tier: str | None = None,
                               geopolitical_risk_factors: list | None = None) -> bool:
    """Enrich Industry node after Industry Agent runs (OPERATES_IN node must already exist)."""
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


def link_industry_to_article(naics_code: str, article_url: str) -> bool:
    """Industry -[:MENTIONED_IN]-> NewsArticle"""
    cypher = """
    MATCH (n:Industry {naics_code: $naics_code})
    MATCH (a:NewsArticle {url: $url})
    MERGE (n)-[:MENTIONED_IN]->(a)
    """
    return _run(cypher, {"naics_code": naics_code, "url": article_url}) is not None


# ---------------------------------------------------------------------------
# Traversal queries (used by /api/graph/* endpoints)
# ---------------------------------------------------------------------------

def get_deal_graph(deal_id: str) -> dict[str, Any]:
    """Return all nodes and relationships scoped to a deal_id."""
    nodes_result = _run(
        "MATCH (n {deal_id: $deal_id}) RETURN n",
        {"deal_id": deal_id}
    )
    rels_result = _run(
        "MATCH (a {deal_id: $deal_id})-[r]-(b) RETURN a, type(r) AS rel_type, b",
        {"deal_id": deal_id}
    )
    return {
        "nodes": nodes_result or [],
        "relationships": rels_result or [],
    }


def get_guarantor_network(deal_id: str) -> list[dict]:
    """Return all guarantors and their GUARANTEES relationships for a deal."""
    result = _run(
        """
        MATCH (i:Individual {deal_id: $deal_id})-[:GUARANTEES]->(l:Loan {deal_id: $deal_id})
        RETURN i.legal_name AS guarantor, l.loan_amount AS loan_amount,
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


# ---------------------------------------------------------------------------
# Collateral enrichment — APPRAISED_BY / SUBJECT_TO edges
# ---------------------------------------------------------------------------

def write_appraised_by_edge(collateral_id: str, appraiser_name: str,
                             appraisal_date: str | None = None,
                             appraised_value: float | None = None) -> bool:
    """Collateral -[:APPRAISED_BY]-> Appraiser"""
    cypher = """
    MATCH (c:Collateral {collateral_id: $collateral_id})
    MERGE (a:Appraiser {appraiser_name: $appraiser_name})
    MERGE (c)-[r:APPRAISED_BY]->(a)
    SET r.appraisal_date = $appraisal_date,
        r.appraised_value = $appraised_value
    """
    return _run(cypher, {
        "collateral_id": collateral_id,
        "appraiser_name": appraiser_name,
        "appraisal_date": appraisal_date,
        "appraised_value": appraised_value,
    }) is not None


def write_subject_to_lien(collateral_id: str, lien_id: str,
                           lien_type: str = "UCC",
                           amount: float | None = None,
                           secured_party: str | None = None) -> bool:
    """Collateral -[:SUBJECT_TO]-> Lien"""
    cypher = """
    MATCH (c:Collateral {collateral_id: $collateral_id})
    MERGE (l:Lien {lien_id: $lien_id})
    SET l.lien_type = $lien_type, l.amount = $amount, l.secured_party = $secured_party
    MERGE (c)-[:SUBJECT_TO]->(l)
    """
    return _run(cypher, {
        "collateral_id": collateral_id,
        "lien_id": lien_id,
        "lien_type": lien_type,
        "amount": amount,
        "secured_party": secured_party,
    }) is not None


# ---------------------------------------------------------------------------
# Phase 10B — External world enrichment writes
# ---------------------------------------------------------------------------

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


def write_ucc_filing_node(entity_id: str, filing_id: str,
                           filing_date: str | None = None,
                           secured_party: str | None = None,
                           collateral_description: str | None = None,
                           state: str | None = None) -> bool:
    """Company -[:HAS_UCC_FILING]-> UccFiling"""
    cypher = """
    MATCH (c:Company {entity_id: $entity_id})
    MERGE (u:UccFiling {filing_id: $filing_id})
    SET u.filing_date = $filing_date, u.secured_party = $secured_party,
        u.collateral_description = $collateral_description, u.state = $state
    MERGE (c)-[:HAS_UCC_FILING]->(u)
    """
    return _run(cypher, {
        "entity_id": entity_id, "filing_id": filing_id,
        "filing_date": filing_date, "secured_party": secured_party,
        "collateral_description": collateral_description, "state": state,
    }) is not None


def write_external_company_node(company_id: str, legal_name: str,
                                  jurisdiction: str | None = None,
                                  officers: list | None = None,
                                  deal_id: str | None = None) -> bool:
    """Standalone ExternalCompany node — used for OpenCorporates affiliates."""
    cypher = """
    MERGE (e:ExternalCompany {company_id: $company_id})
    SET e.legal_name = $legal_name, e.jurisdiction = $jurisdiction,
        e.officers = $officers, e.deal_id = $deal_id
    """
    return _run(cypher, {
        "company_id": company_id, "legal_name": legal_name,
        "jurisdiction": jurisdiction, "officers": officers or [],
        "deal_id": deal_id,
    }) is not None


def link_company_to_news_article(entity_id: str, article_url: str) -> bool:
    """Company/Individual -[:MENTIONED_IN]-> NewsArticle"""
    cypher = """
    MATCH (e {entity_id: $entity_id})
    MATCH (a:NewsArticle {url: $url})
    MERGE (e)-[:MENTIONED_IN]->(a)
    """
    return _run(cypher, {"entity_id": entity_id, "url": article_url}) is not None


def write_connected_to_edge(entity_id_a: str, entity_id_b: str,
                             reason: str = "shared_address") -> bool:
    """Cross-entity insider detection edge: Entity -[:CONNECTED_TO]-> Entity"""
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
