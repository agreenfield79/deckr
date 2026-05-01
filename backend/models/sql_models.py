"""
SQLAlchemy ORM — all Data Dictionary Layer 3 tables (Phase 3B target schema).

SQLite / PostgreSQL dual-mode compatibility:
  - String(36) for UUID PKs/FKs (no native UUID in SQLite)
  - DateTime(timezone=True) for TIMESTAMPTZ
  - Enum(..., native_enum=False) for named ENUMs (string-backed in SQLite)
  - JSON for JSONB columns
  - vector(768) column is skipped in SQLite mode; ChromaDB handles local embeddings.
    pgvector is imported conditionally — missing in SQLite environments is not an error.
"""

import enum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


# Use JSON universally — JSONB is a PostgreSQL dialect column; JSON works for both.
# When running on PostgreSQL, swap to JSONB via the migration DDL (init_schema.sql).
JsonCol = JSON


# ---------------------------------------------------------------------------
# Named ENUM types — native_enum=False for SQLite compatibility
# ---------------------------------------------------------------------------

class DealStatus(str, enum.Enum):
    draft    = "draft"
    review   = "review"
    approved = "approved"
    declined = "declined"
    closed   = "closed"


class ExtractionStatus(str, enum.Enum):
    pending  = "pending"
    running  = "running"
    complete = "complete"
    partial  = "partial"
    failed   = "failed"


class PipelineStatus(str, enum.Enum):
    pending  = "pending"
    running  = "running"
    complete = "complete"
    failed   = "failed"
    partial  = "partial"


class CovenantStatus(str, enum.Enum):
    compliant = "compliant"
    tight     = "tight"
    breach    = "breach"
    waived    = "waived"


class CovenantType(str, enum.Enum):
    financial   = "financial"
    affirmative = "affirmative"
    negative    = "negative"
    reporting   = "reporting"


class SourceAgentType(str, enum.Enum):
    risk        = "risk"
    review      = "review"
    financial   = "financial"
    collateral  = "collateral"
    guarantor   = "guarantor"
    industry    = "industry"
    packaging   = "packaging"
    extraction  = "extraction"


class ContactType(str, enum.Enum):
    primary              = "primary"
    legal                = "legal"
    cpa                  = "cpa"
    appraiser            = "appraiser"
    relationship_manager = "relationship_manager"
    lender               = "lender"


class GuaranteeType(str, enum.Enum):
    full        = "full"
    limited     = "limited"
    completion  = "completion"
    payment     = "payment"
    performance = "performance"


class UserRole(str, enum.Enum):
    analyst     = "analyst"
    underwriter = "underwriter"
    approver    = "approver"
    admin       = "admin"
    readonly    = "readonly"


class AccessLevel(str, enum.Enum):
    read    = "read"
    write   = "write"
    approve = "approve"


def _enum(py_enum):
    """Return an Enum column type that is string-backed in all DB dialects."""
    return SAEnum(py_enum, native_enum=False)


# ---------------------------------------------------------------------------
# Group A — Deal & Entity Core (3 tables)
# ---------------------------------------------------------------------------

class Workspace(Base):
    __tablename__ = "workspaces"

    workspace_id  = Column(String(36), primary_key=True, default=_uuid)
    project_path  = Column(Text, nullable=False, unique=True)
    borrower_name = Column(String(255))
    deal_id       = Column(String(36), ForeignKey("deals.deal_id", ondelete="SET NULL",
                           use_alter=True, name="fk_workspaces_deal_id"), nullable=True)
    created_at    = Column(DateTime(timezone=True))
    updated_at    = Column(DateTime(timezone=True))


class Deal(Base):
    __tablename__ = "deals"

    deal_id               = Column(String(36), primary_key=True, default=_uuid)
    workspace_id          = Column(String(36), ForeignKey("workspaces.workspace_id"), nullable=False)
    borrower_entity_name  = Column(String(255), nullable=False)
    entity_structure      = Column(String(50))
    requested_loan_amount = Column(Numeric(18, 2))
    loan_purpose          = Column(Text)
    naics_code            = Column(String(10))
    status                = Column(_enum(DealStatus), default=DealStatus.draft)
    pipeline_version      = Column(String(20))
    storage_backend       = Column(String(20), default="local")
    created_at            = Column(DateTime(timezone=True), nullable=False)
    updated_at            = Column(DateTime(timezone=True))


class Entity(Base):
    __tablename__ = "entities"

    entity_id              = Column(String(36), primary_key=True, default=_uuid)
    deal_id                = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)
    entity_type            = Column(String(30), nullable=False)
    legal_name             = Column(String(255), nullable=False)
    tax_id_masked          = Column(String(20))
    state_of_incorporation = Column(String(2))
    years_in_business      = Column(Integer)
    role                   = Column(String(30))
    dba                    = Column(String(255))
    ein                    = Column(String(15))
    created_at             = Column(DateTime(timezone=True))


class Contact(Base):
    __tablename__ = "contacts"

    contact_id   = Column(String(36), primary_key=True, default=_uuid)
    entity_id    = Column(String(36), ForeignKey("entities.entity_id", ondelete="CASCADE"))
    deal_id      = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    name         = Column(String(255), nullable=False)
    title        = Column(String(100))
    email        = Column(String(255))
    phone        = Column(String(30))
    contact_type = Column(_enum(ContactType), nullable=False)
    created_at   = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_contacts_deal_id", "deal_id"),
        Index("ix_contacts_entity_id", "entity_id"),
    )


# ---------------------------------------------------------------------------
# Group B — Historical Financial Statements (5 tables)
# ---------------------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    document_id        = Column(String(36), primary_key=True, default=_uuid)
    workspace_id       = Column(String(36), ForeignKey("workspaces.workspace_id"))
    deal_id            = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    entity_id          = Column(String(36), ForeignKey("entities.entity_id"))
    file_name          = Column(Text, nullable=False)
    file_path          = Column(Text, nullable=False)
    document_type      = Column(String(30), nullable=False)
    upload_timestamp   = Column(DateTime(timezone=True), nullable=False)
    extraction_status  = Column(_enum(ExtractionStatus), default=ExtractionStatus.pending)
    extracted_at       = Column(DateTime(timezone=True))
    extraction_run_id  = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    content_hash       = Column(String(64))
    page_count         = Column(Integer)
    file_size_bytes    = Column(BigInteger)


class IncomeStatement(Base):
    __tablename__ = "income_statements"

    statement_id                 = Column(String(36), primary_key=True, default=_uuid)
    entity_id                    = Column(String(36), ForeignKey("entities.entity_id"), nullable=False)
    document_id                  = Column(String(36), ForeignKey("documents.document_id"))
    fiscal_year                  = Column(Integer, nullable=False)
    fiscal_year_end              = Column(Date)
    period_type                  = Column(String(10), default="annual")
    revenue                      = Column(Numeric(18, 2))
    cost_of_goods_sold           = Column(Numeric(18, 2))
    cogs_product                 = Column(Numeric(18, 2))
    cogs_services                = Column(Numeric(18, 2))
    gross_profit                 = Column(Numeric(18, 2))
    research_and_development     = Column(Numeric(18, 2))
    selling_general_administrative = Column(Numeric(18, 2))
    stock_based_compensation     = Column(Numeric(18, 2))
    restructuring_charges        = Column(Numeric(18, 2))
    operating_expenses           = Column(Numeric(18, 2))
    ebitda                       = Column(Numeric(18, 2))
    depreciation_amortization    = Column(Numeric(18, 2))
    ebit                         = Column(Numeric(18, 2))
    interest_expense             = Column(Numeric(18, 2))
    pre_tax_income               = Column(Numeric(18, 2))
    effective_tax_rate           = Column(Numeric(8, 6))
    tax_expense                  = Column(Numeric(18, 2))
    net_income                   = Column(Numeric(18, 2))
    shares_outstanding           = Column(BigInteger)
    eps                          = Column(Numeric(10, 4))
    extracted_at                 = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("entity_id", "fiscal_year", "period_type",
                         name="uq_income_statement_entity_year_period"),
    )


class BalanceSheet(Base):
    __tablename__ = "balance_sheets"

    balance_sheet_id             = Column(String(36), primary_key=True, default=_uuid)
    entity_id                    = Column(String(36), ForeignKey("entities.entity_id"))
    document_id                  = Column(String(36), ForeignKey("documents.document_id"))
    as_of_date                   = Column(Date, nullable=False)
    cash_and_equivalents         = Column(Numeric(18, 2))
    accounts_receivable          = Column(Numeric(18, 2))
    days_sales_outstanding       = Column(Numeric(8, 2))
    inventory                    = Column(Numeric(18, 2))
    days_inventory_outstanding   = Column(Numeric(8, 2))
    deferred_revenue             = Column(Numeric(18, 2))
    accrued_liabilities          = Column(Numeric(18, 2))
    other_current_assets         = Column(Numeric(18, 2))
    total_current_assets         = Column(Numeric(18, 2))
    pp_e_net                     = Column(Numeric(18, 2))
    other_long_term_assets       = Column(Numeric(18, 2))
    total_assets                 = Column(Numeric(18, 2))
    accounts_payable             = Column(Numeric(18, 2))
    days_payable_outstanding     = Column(Numeric(8, 2))
    short_term_debt              = Column(Numeric(18, 2))
    other_current_liabilities    = Column(Numeric(18, 2))
    total_current_liabilities    = Column(Numeric(18, 2))
    long_term_debt               = Column(Numeric(18, 2))
    funded_debt_rate_type        = Column(String(20))
    weighted_avg_interest_rate   = Column(Numeric(8, 6))
    debt_maturity_schedule       = Column(JsonCol)
    other_long_term_liabilities  = Column(Numeric(18, 2))
    total_liabilities            = Column(Numeric(18, 2))
    distributions                = Column(Numeric(18, 2))
    retained_earnings            = Column(Numeric(18, 2))
    total_equity                 = Column(Numeric(18, 2))
    extracted_at                 = Column(DateTime(timezone=True))


class CashFlowStatement(Base):
    __tablename__ = "cash_flow_statements"

    cashflow_id                  = Column(String(36), primary_key=True, default=_uuid)
    entity_id                    = Column(String(36), ForeignKey("entities.entity_id"))
    document_id                  = Column(String(36), ForeignKey("documents.document_id"))
    fiscal_year                  = Column(Integer, nullable=False)
    operating_cash_flow          = Column(Numeric(18, 2))
    stock_based_compensation     = Column(Numeric(18, 2))
    working_capital_change       = Column(Numeric(18, 2))
    working_capital_change_detail = Column(JsonCol)
    capital_expenditures         = Column(Numeric(18, 2))
    maintenance_capex            = Column(Numeric(18, 2))
    growth_capex                 = Column(Numeric(18, 2))
    acquisitions                 = Column(Numeric(18, 2))
    investing_cash_flow          = Column(Numeric(18, 2))
    debt_repayment               = Column(Numeric(18, 2))
    share_repurchases            = Column(Numeric(18, 2))
    financing_cash_flow          = Column(Numeric(18, 2))
    net_change_in_cash           = Column(Numeric(18, 2))
    free_cash_flow               = Column(Numeric(18, 2))
    normalized_free_cash_flow    = Column(Numeric(18, 2))
    extracted_at                 = Column(DateTime(timezone=True))


class RevenueSegment(Base):
    __tablename__ = "revenue_segments"

    segment_id          = Column(String(36), primary_key=True, default=_uuid)
    entity_id           = Column(String(36), ForeignKey("entities.entity_id"), nullable=False)
    statement_id        = Column(String(36), ForeignKey("income_statements.statement_id"))
    fiscal_year         = Column(Integer, nullable=False)
    segment_name        = Column(String(100), nullable=False)
    segment_type        = Column(String(30))
    segment_revenue     = Column(Numeric(18, 2))
    gross_profit        = Column(Numeric(18, 2))
    segment_margin      = Column(Numeric(8, 6))
    pct_of_total_revenue = Column(Numeric(8, 6))
    yoy_growth           = Column(Numeric(8, 6))

    __table_args__ = (
        UniqueConstraint("entity_id", "fiscal_year", "segment_name",
                         name="uq_revenue_segment_entity_year_name"),
    )


class ManagementGuidance(Base):
    __tablename__ = "management_guidance"

    guidance_id             = Column(String(36), primary_key=True, default=_uuid)
    entity_id               = Column(String(36), ForeignKey("entities.entity_id"))
    document_id             = Column(String(36), ForeignKey("documents.document_id"))
    extracted_at            = Column(DateTime(timezone=True))
    guidance_period         = Column(String(20))
    next_year_revenue_low   = Column(Numeric(18, 2))
    next_year_revenue_mid   = Column(Numeric(18, 2))
    next_year_revenue_high  = Column(Numeric(18, 2))
    next_year_ebitda_margin = Column(Numeric(8, 6))
    growth_drivers          = Column(JsonCol)
    risk_factors            = Column(JsonCol)
    source                  = Column(String(50))


class PersonalFinancialStatement(Base):
    __tablename__ = "personal_financial_statements"

    pfs_id              = Column(String(36), primary_key=True, default=_uuid)
    entity_id           = Column(String(36), ForeignKey("entities.entity_id", ondelete="CASCADE"))
    document_id         = Column(String(36), ForeignKey("documents.document_id"))
    as_of_date          = Column(Date)
    cash_savings        = Column(Numeric(18, 2))
    real_estate_value   = Column(Numeric(18, 2))
    retirement_accounts = Column(Numeric(18, 2))
    other_assets        = Column(Numeric(18, 2))
    total_assets        = Column(Numeric(18, 2))
    mortgage_balance    = Column(Numeric(18, 2))
    auto_loans          = Column(Numeric(18, 2))
    other_liabilities   = Column(Numeric(18, 2))
    total_liabilities   = Column(Numeric(18, 2))
    net_worth           = Column(Numeric(18, 2))
    annual_income       = Column(Numeric(18, 2))
    monthly_obligations = Column(Numeric(18, 2))
    extracted_at        = Column(DateTime(timezone=True))
    deal_id             = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)


# ---------------------------------------------------------------------------
# Group C — Industry & Benchmarks (1 table)
# ---------------------------------------------------------------------------

class Benchmark(Base):
    __tablename__ = "benchmarks"

    benchmark_id   = Column(String(36), primary_key=True, default=_uuid)
    naics_code     = Column(String(10), nullable=False)
    metric_name    = Column(String(50), nullable=False)
    percentile_25  = Column(Numeric(10, 4))
    percentile_50  = Column(Numeric(10, 4))
    percentile_75  = Column(Numeric(10, 4))
    source         = Column(String(100))
    as_of_year     = Column(Integer)
    created_at     = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("naics_code", "metric_name", "as_of_year",
                         name="uq_benchmark_naics_metric_year"),
        Index("ix_benchmarks_naics", "naics_code"),
        Index("ix_benchmarks_metric", "metric_name"),
    )


# ---------------------------------------------------------------------------
# Group D — Loan Structure (4 tables)
# ---------------------------------------------------------------------------

class LoanTerms(Base):
    __tablename__ = "loan_terms"

    loan_terms_id               = Column(String(36), primary_key=True, default=_uuid)
    deal_id                     = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)
    entity_id                   = Column(String(36), ForeignKey("entities.entity_id"))
    loan_amount                 = Column(Numeric(18, 2), nullable=False)
    loan_type                   = Column(String(30))
    interest_rate               = Column(Numeric(8, 6))
    rate_type                   = Column(String(20))
    rate_index                  = Column(String(20))
    spread_bps                  = Column(Integer)
    amortization_years          = Column(Integer)
    term_months                 = Column(Integer)
    balloon_payment             = Column(Numeric(18, 2))
    proposed_annual_debt_service = Column(Numeric(18, 2))
    origination_fee_bps         = Column(Integer)
    prepayment_penalty          = Column(Boolean)
    draw_period_months          = Column(Integer)
    revolver_availability       = Column(Numeric(18, 2))
    target_close_date           = Column(Date)
    status                      = Column(String(20), default="proposed")
    created_at                  = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("deal_id", name="uq_loan_terms_deal"),
    )


class Collateral(Base):
    __tablename__ = "collateral"

    collateral_id   = Column(String(36), primary_key=True, default=_uuid)
    deal_id         = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    entity_id       = Column(String(36), ForeignKey("entities.entity_id"))
    document_id     = Column(String(36), ForeignKey("documents.document_id"))
    collateral_type = Column(String(30))
    description     = Column(String(255))
    appraised_value = Column(Numeric(18, 2))
    appraisal_date  = Column(Date)
    appraiser_name  = Column(String(255))
    ltv_ratio       = Column(Numeric(5, 4))
    lien_position   = Column(Integer)
    address         = Column(Text)
    parcel_id       = Column(String(50))


class Covenant(Base):
    __tablename__ = "covenants"

    covenant_id         = Column(String(36), primary_key=True, default=_uuid)
    deal_id             = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    loan_terms_id       = Column(String(36), ForeignKey("loan_terms.loan_terms_id"))
    pipeline_run_id     = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    covenant_type       = Column(_enum(CovenantType))
    description         = Column(String(255))
    metric              = Column(String(50))
    threshold_value     = Column(Numeric(10, 4))
    threshold_operator  = Column(String(5))
    actual_value        = Column(Numeric(10, 4))
    unit                = Column(String(20))
    pass_fail           = Column(Boolean)
    headroom_pct        = Column(Numeric(8, 4))
    test_frequency      = Column(String(20))
    last_tested_at      = Column(Date)
    cure_period_days    = Column(Integer)
    waiver_count        = Column(Integer, default=0)
    source_agent        = Column(_enum(SourceAgentType), nullable=False)
    status              = Column(_enum(CovenantStatus))


class Guarantee(Base):
    __tablename__ = "guarantees"

    guarantee_id        = Column(String(36), primary_key=True, default=_uuid)
    deal_id             = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)
    guarantor_entity_id = Column(String(36), ForeignKey("entities.entity_id", ondelete="CASCADE"), nullable=False)
    loan_terms_id       = Column(String(36), ForeignKey("loan_terms.loan_terms_id"))
    guarantee_type      = Column(_enum(GuaranteeType), nullable=False)
    coverage_amount     = Column(Numeric(18, 2))
    coverage_pct        = Column(Numeric(5, 4))
    personal_net_worth  = Column(Numeric(18, 2))
    liquid_assets       = Column(Numeric(18, 2))
    executed_at         = Column(Date)
    expires_at          = Column(Date)
    created_at          = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("deal_id", "guarantor_entity_id", name="uq_guarantee_deal_guarantor"),
    )


# ---------------------------------------------------------------------------
# Group E — Projections & Scenario Analysis (4 tables)
# ---------------------------------------------------------------------------

class ProjectionAssumptions(Base):
    __tablename__ = "projection_assumptions"

    assumptions_id          = Column(String(36), primary_key=True, default=_uuid)
    deal_id                 = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id         = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    model_id                = Column(String(36), ForeignKey("model_versions.model_id", use_alter=True, name="fk_proj_assumptions_model"))
    scenario                = Column(String(10), nullable=False)
    revenue_growth_rate     = Column(Numeric(8, 6))
    ebitda_margin_assumption = Column(Numeric(8, 6))
    capex_pct_revenue       = Column(Numeric(8, 6))
    interest_rate_assumption = Column(Numeric(8, 6))
    debt_paydown_rate       = Column(Numeric(8, 6))
    macro_scenario_tag      = Column(String(50))
    created_at              = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("deal_id", "pipeline_run_id", "scenario",
                         name="uq_proj_assumptions_deal_run_scenario"),
    )


class Projection(Base):
    __tablename__ = "projections"

    projection_id            = Column(String(36), primary_key=True, default=_uuid)
    entity_id                = Column(String(36), ForeignKey("entities.entity_id"))
    deal_id                  = Column(String(36), ForeignKey("deals.deal_id"))
    pipeline_run_id          = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    assumptions_id           = Column(String(36), ForeignKey("projection_assumptions.assumptions_id"))
    scenario                 = Column(String(10), nullable=False)
    projection_year          = Column(Integer, nullable=False)
    projection_date          = Column(Date)
    revenue                  = Column(Numeric(18, 2))
    ebitda                   = Column(Numeric(18, 2))
    ebit                     = Column(Numeric(18, 2))
    net_income               = Column(Numeric(18, 2))
    operating_cash_flow      = Column(Numeric(18, 2))
    capital_expenditures     = Column(Numeric(18, 2))
    free_cash_flow           = Column(Numeric(18, 2))
    dscr                     = Column(Numeric(10, 4))
    leverage_ratio           = Column(Numeric(10, 4))
    funded_debt              = Column(Numeric(18, 2))
    funded_debt_to_ebitda    = Column(Numeric(10, 4))
    debt_balance             = Column(Numeric(18, 2))
    ending_cash              = Column(Numeric(18, 2))
    revenue_growth_assumption = Column(Numeric(8, 6))
    ebitda_margin_assumption  = Column(Numeric(8, 6))
    computed_at              = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("entity_id", "pipeline_run_id", "scenario", "projection_year",
                         name="uq_projection_entity_run_scenario_year"),
    )


class CovenantComplianceProjection(Base):
    __tablename__ = "covenant_compliance_projections"

    compliance_id      = Column(String(36), primary_key=True, default=_uuid)
    deal_id            = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id    = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    covenant_id        = Column(String(36), ForeignKey("covenants.covenant_id"))
    scenario           = Column(String(10), nullable=False)
    projection_year    = Column(Integer, nullable=False)
    covenant_type      = Column(String(40), nullable=False)
    formula            = Column(Text)
    threshold_value    = Column(Numeric(10, 4))
    threshold_operator = Column(String(5))
    computed_value     = Column(Numeric(10, 4))
    headroom_pct       = Column(Numeric)
    status             = Column(_enum(CovenantStatus))
    is_breach_year     = Column(Boolean, default=False)
    trigger_action     = Column(String(255))

    __table_args__ = (
        UniqueConstraint("deal_id", "pipeline_run_id", "scenario", "projection_year",
                         "covenant_type", name="uq_covenant_compliance_projection"),
    )


class SensitivityAnalysis(Base):
    __tablename__ = "sensitivity_analyses"

    sensitivity_id       = Column(String(36), primary_key=True, default=_uuid)
    deal_id              = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id      = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    variable_shocked     = Column(String(30), nullable=False)
    shock_magnitude_pct  = Column(Numeric(8, 4), nullable=False)
    resulting_dscr       = Column(Numeric(10, 4))
    resulting_leverage   = Column(Numeric(10, 4))
    resulting_fcf        = Column(Numeric(18, 2))
    covenant_breach_year = Column(Integer)
    computed_at          = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("deal_id", "pipeline_run_id", "variable_shocked", "shock_magnitude_pct",
                         name="uq_sensitivity_deal_run_variable_shock"),
    )


# ---------------------------------------------------------------------------
# Group F — Pipeline & Document Catalog (3 tables)
# ---------------------------------------------------------------------------

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    pipeline_run_id   = Column(String(36), primary_key=True, default=_uuid)
    deal_id           = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    workspace_id      = Column(String(36), ForeignKey("workspaces.workspace_id"))
    started_at        = Column(DateTime(timezone=True), nullable=False)
    completed_at      = Column(DateTime(timezone=True))
    status            = Column(_enum(PipelineStatus))
    stages_completed  = Column(JsonCol)
    total_elapsed_ms  = Column(Integer)
    triggered_by      = Column(String(50))
    pipeline_version  = Column(String(20))


class PipelineStageLog(Base):
    __tablename__ = "pipeline_stage_logs"

    log_id            = Column(String(36), primary_key=True, default=_uuid)
    pipeline_run_id   = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    agent_name        = Column(String(50), nullable=False)
    stage_order       = Column(Integer)
    started_at        = Column(DateTime(timezone=True))
    completed_at      = Column(DateTime(timezone=True))
    elapsed_ms        = Column(Integer)
    output_file_path  = Column(Text)
    status            = Column(_enum(PipelineStatus))
    error_code        = Column(String(30))
    token_count_input  = Column(Integer)
    token_count_output = Column(Integer)


# ---------------------------------------------------------------------------
# Group G — AI/ML Feature Store & Model Governance (3 tables)
# ---------------------------------------------------------------------------

class ModelVersion(Base):
    __tablename__ = "model_versions"

    model_id                  = Column(String(36), primary_key=True, default=_uuid)
    model_name                = Column(String(100), nullable=False)
    version                   = Column(String(20), nullable=False)
    architecture              = Column(String(50))
    deployed_at               = Column(DateTime(timezone=True), nullable=False)
    deprecated_at             = Column(DateTime(timezone=True))
    training_dataset_hash     = Column(String(64))
    validation_auc            = Column(Numeric(6, 4))
    validation_ks_statistic   = Column(Numeric(6, 4))
    calibration_brier_score   = Column(Numeric(6, 4))
    feature_names             = Column(JsonCol)
    created_at                = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_model_version_name_ver"),
    )


class SlacrScore(Base):
    __tablename__ = "slacr_scores"

    score_id                  = Column(String(36), primary_key=True, default=_uuid)
    deal_id                   = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    entity_id                 = Column(String(36), ForeignKey("entities.entity_id"))
    pipeline_run_id           = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    model_id                  = Column(String(36), ForeignKey("model_versions.model_id", use_alter=True, name="fk_slacr_model"))
    sponsor_score             = Column(Numeric(5, 2))
    leverage_score            = Column(Numeric(5, 2))
    asset_quality_score       = Column(Numeric(5, 2))
    cash_flow_score           = Column(Numeric(5, 2))
    risk_score                = Column(Numeric(5, 2))
    composite_score           = Column(Numeric(5, 2))
    internal_rating           = Column(String(30), nullable=False)
    occ_classification        = Column(String(30), nullable=False)
    model_version             = Column(String(20))
    confidence_interval_low   = Column(Numeric(5, 2))
    confidence_interval_high  = Column(Numeric(5, 2))
    input_features_snapshot   = Column(JsonCol)
    shap_values               = Column(JsonCol)
    lime_values               = Column(JsonCol)
    computed_at               = Column(DateTime(timezone=True))


class FeatureStore(Base):
    __tablename__ = "feature_store"

    feature_snapshot_id  = Column(String(36), primary_key=True, default=_uuid)
    deal_id              = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id      = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    computed_at          = Column(DateTime(timezone=True), nullable=False)
    dscr_t0              = Column(Numeric(10, 4))
    dscr_t1              = Column(Numeric(10, 4))
    leverage_t0          = Column(Numeric(10, 4))
    ebitda_margin_t0     = Column(Numeric(8, 6))
    current_ratio_t0     = Column(Numeric(10, 4))
    industry_risk_tier   = Column(String(10))
    collateral_coverage  = Column(Numeric(8, 4))
    guarantor_net_worth  = Column(Numeric(18, 2))
    naics_code           = Column(String(10))
    years_in_business    = Column(Integer)
    revenue_cagr_3yr     = Column(Numeric(8, 6))

    __table_args__ = (
        UniqueConstraint("deal_id", "pipeline_run_id", name="uq_feature_store_deal_run"),
    )


class ModelOutcome(Base):
    __tablename__ = "model_outcomes"

    outcome_id        = Column(String(36), primary_key=True, default=_uuid)
    deal_id           = Column(String(36), ForeignKey("deals.deal_id", ondelete="SET NULL"))
    loan_terms_id     = Column(String(36), ForeignKey("loan_terms.loan_terms_id"))
    predicted_rating  = Column(String(30), nullable=False)
    predicted_at      = Column(DateTime(timezone=True), nullable=False)
    actual_outcome    = Column(String(30))
    outcome_date      = Column(Date)
    loss_given_default = Column(Numeric(18, 2))
    recorded_at       = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Group H — Auth, Access & Audit (4 tables)
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    user_id        = Column(String(36), primary_key=True, default=_uuid)
    email          = Column(String(255), unique=True, nullable=False)
    role           = Column(_enum(UserRole), nullable=False)
    institution_id = Column(String(36))
    password_hash  = Column(String(128))
    created_at     = Column(DateTime(timezone=True), nullable=False)
    last_login     = Column(DateTime(timezone=True))
    is_active      = Column(Boolean, default=True)


class Session(Base):
    __tablename__ = "sessions"

    session_id          = Column(String(36), primary_key=True, default=_uuid)
    user_id             = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"))
    issued_at           = Column(DateTime(timezone=True), nullable=False)
    expires_at          = Column(DateTime(timezone=True), nullable=False)
    refresh_token_hash  = Column(String(128))
    revoked             = Column(Boolean, default=False)
    ip_address          = Column(String(45))

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class DealAccess(Base):
    __tablename__ = "deal_access"

    access_id    = Column(String(36), primary_key=True, default=_uuid)
    user_id      = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"))
    deal_id      = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    access_level = Column(_enum(AccessLevel), nullable=False)
    granted_by   = Column(String(36), ForeignKey("users.user_id"))
    granted_at   = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "deal_id", name="uq_deal_access_user_deal"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id         = Column(String(36), primary_key=True, default=_uuid)
    user_id        = Column(String(36), ForeignKey("users.user_id"))
    deal_id        = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    session_id     = Column(String(128))
    actor_ip       = Column(String(45))
    action_type    = Column(String(30), nullable=False)
    route          = Column(Text)
    target_path    = Column(Text)
    target_table   = Column(String(50))
    agent_name     = Column(String(50))
    old_value      = Column(JsonCol)
    new_value      = Column(JsonCol)
    audit_metadata = Column("metadata", JsonCol)
    status_code    = Column(Integer)
    timestamp      = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_audit_log_timestamp_desc", "timestamp"),
        Index("ix_audit_log_session_timestamp", "session_id", "timestamp"),
        Index("ix_audit_log_deal_timestamp", "deal_id", "timestamp"),
    )


# ---------------------------------------------------------------------------
# Remaining tables (vector, financial ratios, forecasts, embeddings)
# ---------------------------------------------------------------------------

class FinancialRatio(Base):
    __tablename__ = "financial_ratios"

    ratio_id              = Column(String(36), primary_key=True, default=_uuid)
    entity_id             = Column(String(36), ForeignKey("entities.entity_id", ondelete="CASCADE"))
    pipeline_run_id       = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    fiscal_year           = Column(Integer, nullable=False)
    dscr                  = Column(Numeric(20, 4))
    fixed_charge_coverage = Column(Numeric(10, 4))
    leverage_ratio        = Column(Numeric(10, 4))
    funded_debt_to_ebitda = Column(Numeric(10, 4))
    current_ratio         = Column(Numeric(10, 4))
    quick_ratio           = Column(Numeric(10, 4))
    debt_to_equity        = Column(Numeric(10, 4))
    ebitda_margin         = Column(Numeric(8, 6))
    net_profit_margin     = Column(Numeric(8, 6))
    return_on_assets      = Column(Numeric(8, 6))
    interest_coverage     = Column(Numeric(20, 4))
    asset_turnover        = Column(Numeric(10, 4))
    computed_at           = Column(DateTime(timezone=True))


class Forecast(Base):
    __tablename__ = "forecasts"

    forecast_id      = Column(String(36), primary_key=True, default=_uuid)
    entity_id        = Column(String(36), ForeignKey("entities.entity_id"))
    pipeline_run_id  = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    metric           = Column(String(30))
    forecast_period  = Column(Date)
    forecast_value   = Column(Numeric(18, 2))
    confidence_lower = Column(Numeric(18, 2))
    confidence_upper = Column(Numeric(18, 2))
    model_version    = Column(String(50))
    computed_at      = Column(DateTime(timezone=True))


class Embedding(Base):
    """pgvector in PostgreSQL; ChromaDB handles local-mode vectors — this table stays empty locally."""
    __tablename__ = "embeddings"

    embedding_id  = Column(String(36), primary_key=True, default=_uuid)
    document_id   = Column(String(36), ForeignKey("documents.document_id"))
    deal_id       = Column(String(36))
    entity_id     = Column(String(36))
    document_type = Column(String(30))
    chunk_index   = Column(Integer, nullable=False)
    chunk_text    = Column(Text)
    embedding     = Column(Text)  # placeholder — overridden by vector(768) in PostgreSQL DDL
    model_name    = Column(String(100))
    created_at    = Column(DateTime(timezone=True))
