"""
Phase 3D Neo4j Migration Script
================================
Strips properties from existing nodes that violate the Phase 2C "no amounts / no long text
in Neo4j" principle.  All steps are idempotent — safe to re-run.

Run with venv active, Neo4j running:
    python migrate_neo4j_phase3d.py
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
    except ImportError:
        pass


def _driver():
    uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER",     "neo4j")
    pwd  = os.getenv("NEO4J_PASSWORD", "")
    if not pwd:
        logger.error("NEO4J_PASSWORD not set — aborting")
        sys.exit(1)
    from neo4j import GraphDatabase
    return GraphDatabase.driver(uri, auth=(user, pwd))


def run(cypher: str, driver, label: str) -> int:
    """Execute a Cypher write and return affected-count hint (best-effort)."""
    try:
        with driver.session() as session:
            result = session.run(cypher)
            summary = result.consume()
            affected = (
                summary.counters.properties_set
                or summary.counters.nodes_deleted
                or 0
            )
            logger.info("  ✓ %-55s  affected=%d", label, affected)
            return affected
    except Exception as exc:
        logger.error("  ✗ %-55s  ERROR: %s", label, exc)
        return 0


def main():
    _load_env()
    driver = _driver()

    logger.info("Phase 3D — Neo4j property migration")
    logger.info("=" * 60)

    # ── 3D.1: Strip numeric properties from nodes ─────────────────────────────

    run(
        "MATCH (c:Collateral) WHERE c.appraised_value IS NOT NULL "
        "REMOVE c.appraised_value RETURN count(c)",
        driver,
        "Collateral: remove appraised_value",
    )
    run(
        "MATCH (c:Collateral) WHERE c.ltv_ratio IS NOT NULL "
        "REMOVE c.ltv_ratio RETURN count(c)",
        driver,
        "Collateral: remove ltv_ratio",
    )
    run(
        "MATCH (l:Loan) WHERE l.loan_amount IS NOT NULL "
        "REMOVE l.loan_amount RETURN count(l)",
        driver,
        "Loan: remove loan_amount",
    )
    run(
        "MATCH (l:Lien) WHERE l.amount IS NOT NULL "
        "REMOVE l.amount RETURN count(l)",
        driver,
        "Lien: remove amount (D2)",
    )
    run(
        "MATCH (u:UccFiling) WHERE u.collateral_description IS NOT NULL "
        "REMOVE u.collateral_description RETURN count(u)",
        driver,
        "UccFiling: remove collateral_description (D3)",
    )
    run(
        "MATCH (e:ExternalCompany) WHERE e.officers IS NOT NULL "
        "REMOVE e.officers RETURN count(e)",
        driver,
        "ExternalCompany: remove officers list",
    )

    # ── 3D.7: Additional property corrections ─────────────────────────────────

    run(
        "MATCH (l:Loan) WHERE l.interest_rate IS NOT NULL "
        "REMOVE l.interest_rate RETURN count(l)",
        driver,
        "Loan: remove interest_rate (D2 — numeric, belongs in SQL)",
    )
    run(
        "MATCH (l:Loan) WHERE l.amortization_years IS NOT NULL "
        "REMOVE l.amortization_years RETURN count(l)",
        driver,
        "Loan: remove amortization_years (D2 — numeric, belongs in SQL)",
    )
    run(
        "MATCH (l:Loan) WHERE l.proposed_annual_debt_service IS NOT NULL "
        "REMOVE l.proposed_annual_debt_service RETURN count(l)",
        driver,
        "Loan: remove proposed_annual_debt_service (D2 — dollar amount)",
    )
    run(
        "MATCH (l:Lien) WHERE l.secured_party IS NOT NULL "
        "REMOVE l.secured_party RETURN count(l)",
        driver,
        "Lien: remove secured_party (D3 — not in target schema)",
    )
    run(
        "MATCH ()-[r:APPRAISED_BY]-() WHERE r.appraised_value IS NOT NULL "
        "REMOVE r.appraised_value RETURN count(r)",
        driver,
        "APPRAISED_BY edge: remove appraised_value (D6 — numeric, belongs in SQL)",
    )

    # ── Apply new constraints (Layers 5A additions + 5B–5G) ──────────────────
    logger.info("")
    logger.info("Applying new CYPHER_SCHEMA constraints ...")

    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from models.graph_models import CYPHER_SCHEMA
        stmts = [s.strip() for s in CYPHER_SCHEMA.strip().split(";") if s.strip()]
        for stmt in stmts:
            label = stmt.split("\n")[0][:70].strip()
            run(stmt, driver, label)
    except Exception as exc:
        logger.error("Could not apply CYPHER_SCHEMA: %s", exc)

    driver.close()
    logger.info("")
    logger.info("Phase 3D migration complete.")


if __name__ == "__main__":
    main()
