"""
Graph model constants — Node labels, relationship types, and Cypher schema
for Data Dictionary Layers 5A–5G.

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
    DOCUMENT = "Document"
    PIPELINE_RUN = "PipelineRun"
    INDUSTRY = "Industry"      # shared lookup — keyed by naics_code, NOT deal_id
    APPRAISER = "Appraiser"    # IP2 collateral hook — appraiser firm node
    LIEN = "Lien"              # IP2 collateral hook — lien on pledged collateral


class RelType:
    """Cypher relationship types."""
    # Layer 5A — internal
    GUARANTEES = "GUARANTEES"           # Individual → Loan
    REQUESTS = "REQUESTS"               # Company → Loan
    OWNS = "OWNS"                       # Individual/Company → Property/Collateral
    PLEDGES = "PLEDGES"                 # Company → Collateral
    OPERATES_IN = "OPERATES_IN"         # Company → Industry
    SECURED_BY = "SECURED_BY"           # Loan → Collateral
    APPRAISED_BY = "APPRAISED_BY"       # Collateral → Appraiser
    SUBJECT_TO = "SUBJECT_TO"           # Collateral → Lien
    APPEARS_IN = "APPEARS_IN"           # Individual/Company → Document
    EVALUATED_IN = "EVALUATED_IN"       # Loan → PipelineRun

    # Layer 5B — external world
    MENTIONED_IN = "MENTIONED_IN"       # Industry/Company → NewsArticle
    AFFILIATED_WITH = "AFFILIATED_WITH" # Individual → ExternalCompany
    SUBJECT_OF = "SUBJECT_OF"           # Individual/Company → LegalAction
    PARTY_TO = "PARTY_TO"               # Individual/Company → LegalAction (richer than SUBJECT_OF)
    SUBJECT_TO_JUDGMENT = "SUBJECT_TO_JUDGMENT"  # Property/Company → Judgment
    HAS_UCC_FILING = "HAS_UCC_FILING"   # Company → UccFiling
    LOCATED_AT = "LOCATED_AT"           # Company/Individual → Address (5B)
    RESIDES_AT = "RESIDES_AT"           # Individual → Address
    SHARES_ADDRESS = "SHARES_ADDRESS"   # Company ↔ Company
    SHARES_AGENT = "SHARES_AGENT"       # Company → RegisteredAgent
    FILED_BANKRUPTCY = "FILED_BANKRUPTCY"  # Individual/Company → Bankruptcy
    CONNECTED_TO = "CONNECTED_TO"       # cross-entity insider detection

    # Layer 5C — compliance
    CONTROLS = "CONTROLS"
    BENEFICIAL_OWNER = "BENEFICIAL_OWNER"
    HOLDS_IN_TRUST = "HOLDS_IN_TRUST"
    MANAGED_BY = "MANAGED_BY"
    OFFICER_OF = "OFFICER_OF"
    FORMERLY_OWNED = "FORMERLY_OWNED"
    SUCCESSOR_TO = "SUCCESSOR_TO"
    SPOUSE_OF = "SPOUSE_OF"
    RELATED_TO = "RELATED_TO"
    IS_PEP = "IS_PEP"
    CONNECTED_TO_SANCTION = "CONNECTED_TO_SANCTION"

    # Layer 5D — market network
    COMPETES_WITH = "COMPETES_WITH"
    SUPPLIES_TO = "SUPPLIES_TO"
    PURCHASES_FROM = "PURCHASES_FROM"
    FRANCHISEE_OF = "FRANCHISEE_OF"
    MEMBER_OF = "MEMBER_OF"
    HOLDS_CERT = "HOLDS_CERT"

    # Layer 5E — regulatory network
    REGULATED_BY = "REGULATED_BY"
    LICENSED_BY = "LICENSED_BY"
    INVESTIGATED_BY = "INVESTIGATED_BY"
    PRESIDED_BY = "PRESIDED_BY"
    FILED_WITH = "FILED_WITH"
    SBA_BACKED = "SBA_BACKED"

    # Layer 5F — geographic network
    INCORPORATED_IN = "INCORPORATED_IN"
    OPERATING_IN = "OPERATING_IN"
    LOCATED_AT_GEO = "LOCATED_AT_GEO"  # Company/Individual → City/State (distinct from 5B LOCATED_AT)

    # Layer 5G — banking & credit network
    BANKS_WITH = "BANKS_WITH"
    HAD_LOAN_WITH = "HAD_LOAN_WITH"
    INSURED_BY = "INSURED_BY"


# ---------------------------------------------------------------------------
# Layer 5A — Required node properties (identity-only; no amounts/long text)
# ---------------------------------------------------------------------------

COMPANY_PROPS = [
    "deal_id", "entity_id", "legal_name", "entity_type", "role",
    "naics_code", "state_of_incorporation", "years_in_business",
    "dba", "formation_date", "status",
]

INDIVIDUAL_PROPS = [
    "deal_id", "entity_id", "legal_name", "entity_type", "role",
    "tax_id_masked", "state_of_incorporation",
    "pep_flag",
]

LOAN_PROPS = [
    "deal_id", "loan_terms_id",
    # Only categorical/rate identity fields — no dollar amounts, no amortization schedule
    "loan_type", "term_months", "rate_type", "status",
]

COLLATERAL_PROPS = [
    "deal_id", "collateral_id", "collateral_type",
    # appraised_value and ltv_ratio removed — numeric; belongs in SQL collateral table
    "lien_position", "address",
]

INDUSTRY_PROPS = [
    "naics_code", "name", "sector",
    "macro_risk_tier",           # low / medium / high — written by Industry Agent
    "geopolitical_risk_tier",    # low / medium / high — written by Industry Agent
    "geopolitical_risk_factors", # string array: sanctions, tariffs, export controls, etc.
]


# ---------------------------------------------------------------------------
# Layer 5B — External World Network node labels
# ---------------------------------------------------------------------------

class ExternalNodeLabel:
    NEWS_ARTICLE = "NewsArticle"
    LEGAL_ACTION = "LegalAction"
    UCC_FILING = "UccFiling"
    EXTERNAL_COMPANY = "ExternalCompany"   # OpenCorporates affiliate/subsidiary
    ADDRESS = "Address"
    REGISTERED_AGENT = "RegisteredAgent"
    REVIEW = "Review"
    JUDGMENT = "Judgment"
    BANKRUPTCY = "Bankruptcy"
    # REGION removed — replaced by City/State in Layer 5F


# ---------------------------------------------------------------------------
# Layer 5C — Deep Identity & Ownership Network
# ---------------------------------------------------------------------------

class Layer5CLabel:
    TRUST_ENTITY = "TrustEntity"
    ULTIMATE_BENEFICIAL_OWNER = "UltimateBeneficialOwner"
    SANCTIONED_ENTITY = "SanctionedEntity"
    PEP = "PEP"
    SHELL_INDICATOR = "ShellIndicator"


# ---------------------------------------------------------------------------
# Layer 5D — Market Network
# ---------------------------------------------------------------------------

class Layer5DLabel:
    COMPETITOR = "Competitor"
    KEY_CUSTOMER = "KeyCustomer"
    KEY_SUPPLIER = "KeySupplier"
    FRANCHISE_SYSTEM = "FranchiseSystem"
    JOINT_VENTURE = "JointVenture"
    TRADE_ASSOCIATION = "TradeAssociation"
    INDUSTRY_CERTIFICATION = "IndustryCertification"


# ---------------------------------------------------------------------------
# Layer 5E — Regulatory Network
# ---------------------------------------------------------------------------

class Layer5ELabel:
    GOVERNMENT_AGENCY = "GovernmentAgency"
    COURT = "Court"
    REGULATORY_ACTION = "RegulatoryAction"
    GOVERNMENT_CONTRACT = "GovernmentContract"
    SBA_GUARANTEE = "SBAGuarantee"
    JURISDICTION = "Jurisdiction"


# ---------------------------------------------------------------------------
# Layer 5F — Geographic Network
# ---------------------------------------------------------------------------

class Layer5FLabel:
    CITY = "City"
    STATE = "State"
    COUNTRY = "Country"
    ECONOMIC_ZONE = "EconomicZone"


# ---------------------------------------------------------------------------
# Layer 5G — Banking & Credit Network
# ---------------------------------------------------------------------------

class Layer5GLabel:
    BANK = "Bank"
    PRIOR_LENDER = "PriorLender"
    CREDIT_FACILITY = "CreditFacility"
    INSURANCE_CARRIER = "InsuranceCarrier"


# ---------------------------------------------------------------------------
# Cypher schema block — constraints and indexes
# Run once against Neo4j on first boot via graph_service.init_graph_schema()
# ---------------------------------------------------------------------------

CYPHER_SCHEMA = """
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.entity_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (i:Individual) REQUIRE i.entity_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (l:Loan) REQUIRE l.loan_terms_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Collateral) REQUIRE c.collateral_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Property) REQUIRE p.property_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.document_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (pr:PipelineRun) REQUIRE pr.pipeline_run_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Industry) REQUIRE n.naics_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Appraiser) REQUIRE a.appraiser_name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (l:Lien) REQUIRE l.lien_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:NewsArticle) REQUIRE n.url IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (u:UccFiling) REQUIRE u.filing_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:LegalAction) REQUIRE a.action_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:ExternalCompany) REQUIRE e.company_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Address) REQUIRE a.address_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (r:RegisteredAgent) REQUIRE r.agent_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (r:Review) REQUIRE r.review_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (j:Judgment) REQUIRE j.judgment_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (b:Bankruptcy) REQUIRE b.bk_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (t:TrustEntity) REQUIRE t.trust_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:SanctionedEntity) REQUIRE s.ofac_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:PEP) REQUIRE p.pep_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:ShellIndicator) REQUIRE s.indicator_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (f:FranchiseSystem) REQUIRE f.franchise_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (j:JointVenture) REQUIRE j.jv_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (t:TradeAssociation) REQUIRE t.association_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:IndustryCertification) REQUIRE c.cert_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (g:GovernmentAgency) REQUIRE g.agency_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Court) REQUIRE c.court_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (r:RegulatoryAction) REQUIRE r.action_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (g:GovernmentContract) REQUIRE g.contract_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:SBAGuarantee) REQUIRE s.sba_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (j:Jurisdiction) REQUIRE j.jurisdiction_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:City) REQUIRE c.city_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:State) REQUIRE s.state_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:Country) REQUIRE c.country_code IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (e:EconomicZone) REQUIRE e.zone_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (b:Bank) REQUIRE b.bank_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:PriorLender) REQUIRE p.lender_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (c:CreditFacility) REQUIRE c.facility_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (i:InsuranceCarrier) REQUIRE i.carrier_id IS UNIQUE;
CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.deal_id);
CREATE INDEX IF NOT EXISTS FOR (i:Individual) ON (i.deal_id);
CREATE INDEX IF NOT EXISTS FOR (l:Loan) ON (l.deal_id);
CREATE INDEX IF NOT EXISTS FOR (c:Collateral) ON (c.deal_id);
CREATE INDEX IF NOT EXISTS FOR (l:LegalAction) ON (l.entity_id);
CREATE INDEX IF NOT EXISTS FOR (pr:PipelineRun) ON (pr.deal_id);
CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.deal_id);
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
