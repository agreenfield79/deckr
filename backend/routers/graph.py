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
            "MATCH (n:Industry {naics_code: $code}) RETURN n",
            {"code": naics_code}
        )
        if not result:
            return {"naics_code": naics_code, "node": None}
        return {"naics_code": naics_code, "node": result[0].get("n", {})}
    except Exception as exc:
        logger.warning("get_industry_node failed: %s", exc)
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
