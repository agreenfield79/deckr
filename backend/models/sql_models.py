"""
SQLAlchemy ORM — all 22 Data Dictionary Layer 3 tables.

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
# Named ENUM types (Convention 2) — native_enum=False for SQLite compatibility
# ---------------------------------------------------------------------------

class DealStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    declined = "declined"


class ExtractionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    partial = "partial"
    failed = "failed"


class PipelineStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"
    partial = "partial"


class CovenantStatus(str, enum.Enum):
    compliant = "compliant"
    tight = "tight"
    breach = "breach"
    waived = "waived"


class SourceAgentType(str, enum.Enum):
    risk = "risk"
    review = "review"
    financial = "financial"
    collateral = "collateral"
    guarantor = "guarantor"
    industry = "industry"
    packaging = "packaging"
    extraction = "extraction"


def _enum(py_enum):
    """Return an Enum column type that is string-backed in all DB dialects."""
    return SAEnum(py_enum, native_enum=False)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class Workspace(Base):
    __tablename__ = "workspaces"

    workspace_id = Column(String(36), primary_key=True, default=_uuid)
    project_path = Column(Text, nullable=False, unique=True)
    borrower_name = Column(String(255))
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="SET NULL", use_alter=True, name="fk_workspaces_deal_id"), nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


class Deal(Base):
    __tablename__ = "deals"

    deal_id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.workspace_id"), nullable=False)
    borrower_entity_name = Column(String(255), nullable=False)
    entity_structure = Column(String(50))
    requested_loan_amount = Column(Numeric(18, 2))
    loan_purpose = Column(Text)
    naics_code = Column(String(10))
    status = Column(_enum(DealStatus), default=DealStatus.draft)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))


class Entity(Base):
    __tablename__ = "entities"

    entity_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(30), nullable=False)
    legal_name = Column(String(255), nullable=False)
    tax_id_masked = Column(String(20))
    state_of_incorporation = Column(String(2))
    years_in_business = Column(Integer)
    created_at = Column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"

    document_id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.workspace_id"))
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    file_name = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    document_type = Column(String(30), nullable=False)
    upload_timestamp = Column(DateTime(timezone=True), nullable=False)
    extraction_status = Column(_enum(ExtractionStatus), default=ExtractionStatus.pending)
    extracted_at = Column(DateTime(timezone=True))
    content_hash = Column(String(64))
    page_count = Column(Integer)
    file_size_bytes = Column(BigInteger)


class IncomeStatement(Base):
    __tablename__ = "income_statements"

    statement_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    fiscal_year = Column(Integer, nullable=False)
    fiscal_year_end = Column(Date)
    period_type = Column(String(10), default="annual")
    revenue = Column(Numeric(18, 2))
    revenue_segments = Column(JsonCol)
    cost_of_goods_sold = Column(Numeric(18, 2))
    cogs_product = Column(Numeric(18, 2))
    cogs_services = Column(Numeric(18, 2))
    gross_profit = Column(Numeric(18, 2))
    research_and_development = Column(Numeric(18, 2))
    selling_general_administrative = Column(Numeric(18, 2))
    stock_based_compensation = Column(Numeric(18, 2))
    restructuring_charges = Column(Numeric(18, 2))
    operating_expenses = Column(Numeric(18, 2))
    ebitda = Column(Numeric(18, 2))
    depreciation_amortization = Column(Numeric(18, 2))
    ebit = Column(Numeric(18, 2))
    interest_expense = Column(Numeric(18, 2))
    pre_tax_income = Column(Numeric(18, 2))
    effective_tax_rate = Column(Numeric(8, 6))
    tax_expense = Column(Numeric(18, 2))
    net_income = Column(Numeric(18, 2))
    extracted_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("entity_id", "fiscal_year", "period_type",
                         name="uq_income_statement_entity_year_period"),
    )


class BalanceSheet(Base):
    __tablename__ = "balance_sheets"

    balance_sheet_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    as_of_date = Column(Date, nullable=False)
    cash_and_equivalents = Column(Numeric(18, 2))
    accounts_receivable = Column(Numeric(18, 2))
    days_sales_outstanding = Column(Numeric(8, 2))
    inventory = Column(Numeric(18, 2))
    days_inventory_outstanding = Column(Numeric(8, 2))
    deferred_revenue = Column(Numeric(18, 2))
    accrued_liabilities = Column(Numeric(18, 2))
    other_current_assets = Column(Numeric(18, 2))
    total_current_assets = Column(Numeric(18, 2))
    pp_e_net = Column(Numeric(18, 2))
    other_long_term_assets = Column(Numeric(18, 2))
    total_assets = Column(Numeric(18, 2))
    accounts_payable = Column(Numeric(18, 2))
    days_payable_outstanding = Column(Numeric(8, 2))
    short_term_debt = Column(Numeric(18, 2))
    other_current_liabilities = Column(Numeric(18, 2))
    total_current_liabilities = Column(Numeric(18, 2))
    long_term_debt = Column(Numeric(18, 2))
    funded_debt_rate_type = Column(String(20))
    weighted_avg_interest_rate = Column(Numeric(8, 6))
    debt_maturity_schedule = Column(JsonCol)
    other_long_term_liabilities = Column(Numeric(18, 2))
    total_liabilities = Column(Numeric(18, 2))
    distributions = Column(Numeric(18, 2))
    retained_earnings = Column(Numeric(18, 2))
    total_equity = Column(Numeric(18, 2))
    extracted_at = Column(DateTime(timezone=True))


class CashFlowStatement(Base):
    __tablename__ = "cash_flow_statements"

    cashflow_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    fiscal_year = Column(Integer, nullable=False)
    operating_cash_flow = Column(Numeric(18, 2))
    stock_based_compensation = Column(Numeric(18, 2))
    working_capital_change = Column(Numeric(18, 2))
    working_capital_change_detail = Column(JsonCol)
    capital_expenditures = Column(Numeric(18, 2))
    maintenance_capex = Column(Numeric(18, 2))
    growth_capex = Column(Numeric(18, 2))
    acquisitions = Column(Numeric(18, 2))
    investing_cash_flow = Column(Numeric(18, 2))
    debt_repayment = Column(Numeric(18, 2))
    share_repurchases = Column(Numeric(18, 2))
    financing_cash_flow = Column(Numeric(18, 2))
    net_change_in_cash = Column(Numeric(18, 2))
    free_cash_flow = Column(Numeric(18, 2))
    normalized_free_cash_flow = Column(Numeric(18, 2))
    extracted_at = Column(DateTime(timezone=True))


class PersonalFinancialStatement(Base):
    __tablename__ = "personal_financial_statements"

    pfs_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    as_of_date = Column(Date)
    cash_savings = Column(Numeric(18, 2))
    real_estate_value = Column(Numeric(18, 2))
    retirement_accounts = Column(Numeric(18, 2))
    other_assets = Column(Numeric(18, 2))
    total_assets = Column(Numeric(18, 2))
    mortgage_balance = Column(Numeric(18, 2))
    auto_loans = Column(Numeric(18, 2))
    other_liabilities = Column(Numeric(18, 2))
    total_liabilities = Column(Numeric(18, 2))
    net_worth = Column(Numeric(18, 2))
    annual_income = Column(Numeric(18, 2))
    monthly_obligations = Column(Numeric(18, 2))
    extracted_at = Column(DateTime(timezone=True))
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)  # FK → deals, ON DELETE CASCADE, NULLABLE


class Collateral(Base):
    __tablename__ = "collateral"

    collateral_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    collateral_type = Column(String(30))
    description = Column(Text)
    appraised_value = Column(Numeric(18, 2))
    appraisal_date = Column(Date)
    ltv_ratio = Column(Numeric(5, 4))
    lien_position = Column(Integer)
    address = Column(Text)


class FinancialRatio(Base):
    __tablename__ = "financial_ratios"

    ratio_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    fiscal_year = Column(Integer, nullable=False)
    dscr = Column(Numeric)
    fixed_charge_coverage = Column(Numeric)
    leverage_ratio = Column(Numeric)
    funded_debt_to_ebitda = Column(Numeric)
    current_ratio = Column(Numeric)
    quick_ratio = Column(Numeric)
    debt_to_equity = Column(Numeric)
    ebitda_margin = Column(Numeric)
    net_profit_margin = Column(Numeric)
    return_on_assets = Column(Numeric)
    computed_at = Column(DateTime(timezone=True))


class SlacrScore(Base):
    __tablename__ = "slacr_scores"

    score_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    sponsor_score = Column(Numeric(5, 2))
    leverage_score = Column(Numeric(5, 2))
    asset_quality_score = Column(Numeric(5, 2))
    cash_flow_score = Column(Numeric(5, 2))
    risk_score = Column(Numeric(5, 2))
    composite_score = Column(Numeric(5, 2))
    internal_rating = Column(String(20), nullable=False)
    occ_classification = Column(String(30), nullable=False)
    model_version = Column(String(20))
    shap_values = Column(JsonCol)
    lime_values = Column(JsonCol)
    computed_at = Column(DateTime(timezone=True))


class Covenant(Base):
    __tablename__ = "covenants"

    covenant_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    covenant_type = Column(String(20))
    description = Column(Text)
    metric = Column(String(50))
    threshold_value = Column(Numeric(10, 4))
    actual_value = Column(Numeric(10, 4))
    unit = Column(String(20))
    pass_fail = Column(Boolean)
    source_agent = Column(_enum(SourceAgentType), nullable=False)


class Forecast(Base):
    __tablename__ = "forecasts"

    forecast_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    metric = Column(String(30))
    forecast_period = Column(Date)
    forecast_value = Column(Numeric(18, 2))
    confidence_lower = Column(Numeric(18, 2))
    confidence_upper = Column(Numeric(18, 2))
    model_version = Column(String(50))
    computed_at = Column(DateTime(timezone=True))


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    pipeline_run_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    workspace_id = Column(String(36), ForeignKey("workspaces.workspace_id"))  # denormalized for query perf
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    status = Column(_enum(PipelineStatus))
    stages_completed = Column(JsonCol)
    total_duration_seconds = Column(Integer)


class PipelineStageLog(Base):
    __tablename__ = "pipeline_stage_logs"

    log_id = Column(String(36), primary_key=True, default=_uuid)
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    agent_name = Column(String(50), nullable=False)
    stage_order = Column(Integer)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    output_file_path = Column(Text)
    status = Column(_enum(PipelineStatus))
    token_count_input = Column(Integer)
    token_count_output = Column(Integer)


class Embedding(Base):
    """pgvector in PostgreSQL; ChromaDB handles local-mode vectors — this table stays empty locally."""
    __tablename__ = "embeddings"

    embedding_id = Column(String(36), primary_key=True, default=_uuid)
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text)
    # embedding column: Vector(768) in PostgreSQL; omitted in SQLite (ChromaDB handles locally)
    embedding = Column(Text)  # placeholder — overridden by migration DDL in PostgreSQL
    model_name = Column(String(100))
    created_at = Column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    session_id = Column(String(128))
    actor_ip = Column(String(45))
    action_type = Column(String(30), nullable=False)
    route = Column(Text)
    target_path = Column(Text)
    target_table = Column(String(50))
    agent_name = Column(String(50))
    audit_metadata = Column("metadata", JsonCol)  # "metadata" reserved by SQLAlchemy; mapped via column()
    status_code = Column(Integer)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_audit_log_timestamp_desc", "timestamp"),
        Index("ix_audit_log_session_timestamp", "session_id", "timestamp"),
    )


class RevenueSegment(Base):
    __tablename__ = "revenue_segments"

    segment_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"), nullable=False)
    statement_id = Column(String(36), ForeignKey("income_statements.statement_id"))
    fiscal_year = Column(Integer, nullable=False)
    segment_name = Column(String(100), nullable=False)
    segment_revenue = Column(Numeric(18, 2))
    pct_of_total_revenue = Column(Numeric)
    yoy_growth = Column(Numeric)

    __table_args__ = (
        UniqueConstraint("entity_id", "fiscal_year", "segment_name",
                         name="uq_revenue_segment_entity_year_name"),
    )


class ManagementGuidance(Base):
    __tablename__ = "management_guidance"

    guidance_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    document_id = Column(String(36), ForeignKey("documents.document_id"))
    extracted_at = Column(DateTime(timezone=True))
    guidance_period = Column(String(20))
    next_year_revenue_low = Column(Numeric(18, 2))
    next_year_revenue_mid = Column(Numeric(18, 2))
    next_year_revenue_high = Column(Numeric(18, 2))
    next_year_ebitda_margin = Column(Numeric(8, 6))
    growth_drivers = Column(JsonCol)
    risk_factors = Column(JsonCol)
    source_text = Column(Text)


class LoanTerms(Base):
    __tablename__ = "loan_terms"

    loan_terms_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False)
    loan_amount = Column(Numeric(18, 2), nullable=False)
    interest_rate = Column(Numeric(8, 6))
    rate_type = Column(String(20))
    amortization_years = Column(Integer)
    term_months = Column(Integer)
    proposed_annual_debt_service = Column(Numeric(18, 2))
    covenant_definitions = Column(JsonCol)
    revolver_availability = Column(Numeric(18, 2))
    created_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("deal_id", name="uq_loan_terms_deal"),
    )


class Projection(Base):
    __tablename__ = "projections"

    projection_id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(String(36), ForeignKey("entities.entity_id"))
    deal_id = Column(String(36), ForeignKey("deals.deal_id"))  # denormalized for query perf
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    scenario = Column(String(10), nullable=False)
    projection_year = Column(Integer, nullable=False)
    projection_date = Column(Date)
    revenue = Column(Numeric(18, 2))
    ebitda = Column(Numeric(18, 2))
    ebit = Column(Numeric(18, 2))
    net_income = Column(Numeric(18, 2))
    operating_cash_flow = Column(Numeric(18, 2))
    capital_expenditures = Column(Numeric(18, 2))
    free_cash_flow = Column(Numeric(18, 2))
    dscr = Column(Numeric)
    funded_debt = Column(Numeric(18, 2))
    funded_debt_to_ebitda = Column(Numeric)
    ending_cash = Column(Numeric(18, 2))
    revenue_growth_assumption = Column(Numeric(8, 6))
    ebitda_margin_assumption = Column(Numeric(8, 6))
    computed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("entity_id", "pipeline_run_id", "scenario", "projection_year",
                         name="uq_projection_entity_run_scenario_year"),
    )


class CovenantComplianceProjection(Base):
    __tablename__ = "covenant_compliance_projections"

    compliance_id = Column(String(36), primary_key=True, default=_uuid)
    deal_id = Column(String(36), ForeignKey("deals.deal_id", ondelete="CASCADE"))
    pipeline_run_id = Column(String(36), ForeignKey("pipeline_runs.pipeline_run_id"))
    scenario = Column(String(10), nullable=False)
    projection_year = Column(Integer, nullable=False)
    covenant_type = Column(String(40), nullable=False)
    formula = Column(Text)
    threshold_value = Column(Numeric(10, 4))
    threshold_operator = Column(String(5))
    computed_value = Column(Numeric(10, 4))
    headroom_pct = Column(Numeric)
    status = Column(_enum(CovenantStatus))
    is_breach_year = Column(Boolean, default=False)
    trigger_action = Column(Text)

    __table_args__ = (
        UniqueConstraint("deal_id", "pipeline_run_id", "scenario", "projection_year",
                         "covenant_type", name="uq_covenant_compliance_projection"),
    )
