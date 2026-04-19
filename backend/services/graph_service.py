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
