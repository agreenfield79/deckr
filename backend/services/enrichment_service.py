"""
Enrichment Service — Layer 5B External World Network.

STUB — full implementation in Phase 10B.
Populates Neo4j with external enrichment nodes (news, legal actions, UCC filings, etc.)
via SerpAPI, OpenCorporates, CourtListener/PACER, Whitepages, and other external APIs.

Called asynchronously after extraction in the pipeline (does not block IP1 gate).
"""

import logging

logger = logging.getLogger("deckr.enrichment_service")


async def enrich_deal(deal_id: str, workspace_root: str) -> dict:
    """
    Phase 10B stub.
    Full implementation will:
      1. Read entity names / NAICS codes from SQL entities table
      2. Call SerpAPI for industry news → write NewsArticle nodes + MENTIONED_IN edges
      3. Call OpenCorporates for affiliates → write ExternalCompany nodes
      4. Call CourtListener/PACER for legal actions → write LegalAction nodes
      5. Call UCC search API for filings → write UccFiling nodes
      6. Call Whitepages for guarantor address verification → enrich Individual nodes
    """
    logger.info("[enrichment] stub called for deal_id=%s — Phase 10B not yet implemented", deal_id)
    return {"status": "stub", "deal_id": deal_id, "enriched": False}
