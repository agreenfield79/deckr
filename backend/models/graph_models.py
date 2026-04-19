"""
Graph model constants — Node labels, relationship types, and Cypher schema
for Data Dictionary Layer 5A (Internal Deal Graph) and 5B (External World Network).

These are string constants used by graph_service.py when creating nodes/relationships.
No runtime dependencies — safe to import anywhere.
"""

# ---------------------------------------------------------------------------
# Layer 5A — Internal Deal Graph (deal-scoped nodes)
# ---------------------------------------------------------------------------

class NodeLabel:
    """Cypher node labels for deal-scoped entities."""
    COMPANY = "Company"
    INDIVIDUAL = "Individual"
    LOAN = "Loan"
    COLLATERAL = "Collateral"
    PROPERTY = "Property"
    PIPELINE_RUN = "PipelineRun"
    INDUSTRY = "Industry"          # shared lookup — keyed by naics_code, NOT deal_id
    APPRAISER = "Appraiser"        # IP2 collateral hook — appraiser firm node
    LIEN = "Lien"                  # IP2 collateral hook — lien on pledged collateral


class RelType:
    """Cypher relationship types."""
    # Layer 5A — internal
    GUARANTEES = "GUARANTEES"           # Individual → Loan
    OWNS = "OWNS"                       # Company/Individual → Property/Collateral
    PLEDGES = "PLEDGES"                 # Company → Collateral
    OPERATES_IN = "OPERATES_IN"         # Company → Industry
    PART_OF = "PART_OF"                 # Loan → Company (borrower)
    SECURED_BY = "SECURED_BY"           # Loan → Collateral
    APPRAISED_BY = "APPRAISED_BY"       # Collateral → Appraiser
    SUBJECT_TO = "SUBJECT_TO"           # Collateral → Lien

    # Layer 5B — external world
    MENTIONED_IN = "MENTIONED_IN"       # Industry/Company → NewsArticle
    AFFILIATED_WITH = "AFFILIATED_WITH" # Individual → Company (external affiliations)
    SUBJECT_OF = "SUBJECT_OF"           # Individual/Company → LegalAction
    HAS_UCC_FILING = "HAS_UCC_FILING"  # Company → UccFiling
    LOCATED_IN = "LOCATED_IN"           # Company/Property → Region
    CONNECTED_TO = "CONNECTED_TO"       # cross-entity insider detection


# ---------------------------------------------------------------------------
# Layer 5A — Required node properties
# ---------------------------------------------------------------------------

# All deal-scoped nodes carry deal_id so they can be pruned atomically.
# Industry is the exception — shared across deals, keyed by naics_code only.

COMPANY_PROPS = [
    "deal_id", "entity_id", "legal_name", "entity_type",
    "naics_code", "state_of_incorporation", "years_in_business",
]

INDIVIDUAL_PROPS = [
    "deal_id", "entity_id", "legal_name", "entity_type",
    "tax_id_masked", "state_of_incorporation",
]

LOAN_PROPS = [
    "deal_id", "loan_terms_id", "loan_amount", "interest_rate",
    "rate_type", "amortization_years", "term_months",
    "proposed_annual_debt_service",
]

COLLATERAL_PROPS = [
    "deal_id", "collateral_id", "collateral_type", "appraised_value",
    "ltv_ratio", "lien_position", "address",
]

INDUSTRY_PROPS = [
    "naics_code", "name", "sector",
    "macro_risk_tier",          # low / medium / high — written by Industry Agent
    "geopolitical_risk_tier",   # low / medium / high — written by Industry Agent
    "geopolitical_risk_factors",# string array: sanctions, tariffs, export controls, etc.
]


# ---------------------------------------------------------------------------
# Layer 5B — External World Network node labels
# ---------------------------------------------------------------------------

class ExternalNodeLabel:
    NEWS_ARTICLE = "NewsArticle"
    LEGAL_ACTION = "LegalAction"
    UCC_FILING = "UccFiling"
    REGION = "Region"
    EXTERNAL_COMPANY = "ExternalCompany"  # OpenCorporates affiliate/subsidiary


# ---------------------------------------------------------------------------
# Cypher schema block — constraints and indexes
# Run once against Neo4j on first boot (graph_service.py init_graph_schema())
# ---------------------------------------------------------------------------

CYPHER_SCHEMA = """
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.entity_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (i:Individual) REQUIRE i.entity_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (l:Loan) REQUIRE l.loan_terms_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Collateral) REQUIRE c.collateral_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Industry) REQUIRE n.naics_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:NewsArticle) REQUIRE n.url IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (u:UccFiling) REQUIRE u.filing_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:LegalAction) REQUIRE a.action_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Appraiser) REQUIRE a.appraiser_name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (l:Lien) REQUIRE l.lien_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:ExternalCompany) REQUIRE e.company_id IS UNIQUE;
CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.deal_id);
CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.deal_id);
CREATE INDEX IF NOT EXISTS FOR (l:Loan) ON (l.deal_id);
CREATE INDEX IF NOT EXISTS FOR (c:Collateral) ON (c.deal_id);
CREATE INDEX IF NOT EXISTS FOR (l:LegalAction) ON (l.entity_id);
"""

# ---------------------------------------------------------------------------
# OCC Rating Map — deterministic lookup applied at INSERT time by sql_service.py
# Never set by the agent or LLM.
# ---------------------------------------------------------------------------

OCC_MAP: dict[str, str] = {
    "Low Risk":      "Pass",
    "Moderate Risk": "Pass",          # escalate to Special Mention if DSCR < 1.40x
    "Elevated Risk": "Special Mention",
    "High Risk":     "Substandard",
    "Decline":       "Doubtful",
}


def occ_classify(internal_rating: str, dscr: float | None = None) -> str:
    """
    Derive OCC classification from Deckr internal rating.
    Moderate Risk escalates to Special Mention when most-recent DSCR < 1.40x.
    """
    base = OCC_MAP.get(internal_rating, "Pass")
    if internal_rating == "Moderate Risk" and dscr is not None and dscr < 1.40:
        return "Special Mention"
    return base
