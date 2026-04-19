"""Initial schema — all 22 Data Dictionary Layer 3 tables.

Revision ID: 001
Revises: None
Create Date: 2026-04-18

Creates every table defined in models/sql_models.py in dependency order.
Safe to run against both SQLite (local) and PostgreSQL (cloud).
For PostgreSQL: ENUMs, pgvector, and JSONB are handled via init_schema.sql
(see migrations/init_schema.sql); this migration uses string-backed enums
and JSON columns for cross-dialect compatibility.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Tier 1: root tables (no FK deps) ─────────────────────────────────────

    op.create_table(
        "workspaces",
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("project_path", sa.Text, nullable=False, unique=True),
        sa.Column("borrower_name", sa.String(255)),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "deals",
        sa.Column("deal_id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("borrower_entity_name", sa.String(255), nullable=False),
        sa.Column("entity_structure", sa.String(50)),
        sa.Column("requested_loan_amount", sa.Numeric(18, 2)),
        sa.Column("loan_purpose", sa.Text),
        sa.Column("naics_code", sa.String(10)),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # ── Tier 2: depends on deals / workspaces ─────────────────────────────────

    op.create_table(
        "entities",
        sa.Column("entity_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("tax_id_masked", sa.String(20)),
        sa.Column("state_of_incorporation", sa.String(2)),
        sa.Column("years_in_business", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "documents",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("file_name", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("upload_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_status", sa.String(20), server_default="pending"),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("page_count", sa.Integer),
        sa.Column("file_size_bytes", sa.BigInteger),
    )

    op.create_table(
        "loan_terms",
        sa.Column("loan_terms_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36), nullable=False),
        sa.Column("loan_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("interest_rate", sa.Numeric(8, 6)),
        sa.Column("rate_type", sa.String(20)),
        sa.Column("amortization_years", sa.Integer),
        sa.Column("term_months", sa.Integer),
        sa.Column("proposed_annual_debt_service", sa.Numeric(18, 2)),
        sa.Column("covenant_definitions", sa.JSON),
        sa.Column("revolver_availability", sa.Numeric(18, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("deal_id", name="uq_loan_terms_deal"),
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("pipeline_run_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20)),
        sa.Column("stages_completed", sa.JSON),
        sa.Column("total_duration_seconds", sa.Integer),
    )

    # ── Tier 3: depends on entities ───────────────────────────────────────────

    op.create_table(
        "income_statements",
        sa.Column("statement_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36)),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("fiscal_year_end", sa.Date),
        sa.Column("period_type", sa.String(10), server_default="annual"),
        sa.Column("revenue", sa.Numeric(18, 2)),
        sa.Column("revenue_segments", sa.JSON),
        sa.Column("cost_of_goods_sold", sa.Numeric(18, 2)),
        sa.Column("cogs_product", sa.Numeric(18, 2)),
        sa.Column("cogs_services", sa.Numeric(18, 2)),
        sa.Column("gross_profit", sa.Numeric(18, 2)),
        sa.Column("research_and_development", sa.Numeric(18, 2)),
        sa.Column("selling_general_administrative", sa.Numeric(18, 2)),
        sa.Column("stock_based_compensation", sa.Numeric(18, 2)),
        sa.Column("restructuring_charges", sa.Numeric(18, 2)),
        sa.Column("operating_expenses", sa.Numeric(18, 2)),
        sa.Column("ebitda", sa.Numeric(18, 2)),
        sa.Column("depreciation_amortization", sa.Numeric(18, 2)),
        sa.Column("ebit", sa.Numeric(18, 2)),
        sa.Column("interest_expense", sa.Numeric(18, 2)),
        sa.Column("pre_tax_income", sa.Numeric(18, 2)),
        sa.Column("effective_tax_rate", sa.Numeric(8, 6)),
        sa.Column("tax_expense", sa.Numeric(18, 2)),
        sa.Column("net_income", sa.Numeric(18, 2)),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "entity_id", "fiscal_year", "period_type",
            name="uq_income_statement_entity_year_period",
        ),
    )

    op.create_table(
        "balance_sheets",
        sa.Column("balance_sheet_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("cash_and_equivalents", sa.Numeric(18, 2)),
        sa.Column("accounts_receivable", sa.Numeric(18, 2)),
        sa.Column("days_sales_outstanding", sa.Numeric(8, 2)),
        sa.Column("inventory", sa.Numeric(18, 2)),
        sa.Column("days_inventory_outstanding", sa.Numeric(8, 2)),
        sa.Column("deferred_revenue", sa.Numeric(18, 2)),
        sa.Column("accrued_liabilities", sa.Numeric(18, 2)),
        sa.Column("other_current_assets", sa.Numeric(18, 2)),
        sa.Column("total_current_assets", sa.Numeric(18, 2)),
        sa.Column("pp_e_net", sa.Numeric(18, 2)),
        sa.Column("other_long_term_assets", sa.Numeric(18, 2)),
        sa.Column("total_assets", sa.Numeric(18, 2)),
        sa.Column("accounts_payable", sa.Numeric(18, 2)),
        sa.Column("days_payable_outstanding", sa.Numeric(8, 2)),
        sa.Column("short_term_debt", sa.Numeric(18, 2)),
        sa.Column("other_current_liabilities", sa.Numeric(18, 2)),
        sa.Column("total_current_liabilities", sa.Numeric(18, 2)),
        sa.Column("long_term_debt", sa.Numeric(18, 2)),
        sa.Column("funded_debt_rate_type", sa.String(20)),
        sa.Column("weighted_avg_interest_rate", sa.Numeric(8, 6)),
        sa.Column("debt_maturity_schedule", sa.JSON),
        sa.Column("other_long_term_liabilities", sa.Numeric(18, 2)),
        sa.Column("total_liabilities", sa.Numeric(18, 2)),
        sa.Column("distributions", sa.Numeric(18, 2)),
        sa.Column("retained_earnings", sa.Numeric(18, 2)),
        sa.Column("total_equity", sa.Numeric(18, 2)),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "cash_flow_statements",
        sa.Column("cashflow_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("operating_cash_flow", sa.Numeric(18, 2)),
        sa.Column("stock_based_compensation", sa.Numeric(18, 2)),
        sa.Column("working_capital_change", sa.Numeric(18, 2)),
        sa.Column("working_capital_change_detail", sa.JSON),
        sa.Column("capital_expenditures", sa.Numeric(18, 2)),
        sa.Column("maintenance_capex", sa.Numeric(18, 2)),
        sa.Column("growth_capex", sa.Numeric(18, 2)),
        sa.Column("acquisitions", sa.Numeric(18, 2)),
        sa.Column("investing_cash_flow", sa.Numeric(18, 2)),
        sa.Column("debt_repayment", sa.Numeric(18, 2)),
        sa.Column("share_repurchases", sa.Numeric(18, 2)),
        sa.Column("financing_cash_flow", sa.Numeric(18, 2)),
        sa.Column("net_change_in_cash", sa.Numeric(18, 2)),
        sa.Column("free_cash_flow", sa.Numeric(18, 2)),
        sa.Column("normalized_free_cash_flow", sa.Numeric(18, 2)),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "personal_financial_statements",
        sa.Column("pfs_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("as_of_date", sa.Date),
        sa.Column("cash_savings", sa.Numeric(18, 2)),
        sa.Column("real_estate_value", sa.Numeric(18, 2)),
        sa.Column("retirement_accounts", sa.Numeric(18, 2)),
        sa.Column("other_assets", sa.Numeric(18, 2)),
        sa.Column("total_assets", sa.Numeric(18, 2)),
        sa.Column("mortgage_balance", sa.Numeric(18, 2)),
        sa.Column("auto_loans", sa.Numeric(18, 2)),
        sa.Column("other_liabilities", sa.Numeric(18, 2)),
        sa.Column("total_liabilities", sa.Numeric(18, 2)),
        sa.Column("net_worth", sa.Numeric(18, 2)),
        sa.Column("annual_income", sa.Numeric(18, 2)),
        sa.Column("monthly_obligations", sa.Numeric(18, 2)),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.Column("deal_id", sa.String(36)),
    )

    op.create_table(
        "collateral",
        sa.Column("collateral_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("collateral_type", sa.String(30)),
        sa.Column("description", sa.Text),
        sa.Column("appraised_value", sa.Numeric(18, 2)),
        sa.Column("appraisal_date", sa.Date),
        sa.Column("ltv_ratio", sa.Numeric(5, 4)),
        sa.Column("lien_position", sa.Integer),
        sa.Column("address", sa.Text),
    )

    op.create_table(
        "management_guidance",
        sa.Column("guidance_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.Column("guidance_period", sa.String(20)),
        sa.Column("next_year_revenue_low", sa.Numeric(18, 2)),
        sa.Column("next_year_revenue_mid", sa.Numeric(18, 2)),
        sa.Column("next_year_revenue_high", sa.Numeric(18, 2)),
        sa.Column("next_year_ebitda_margin", sa.Numeric(8, 6)),
        sa.Column("growth_drivers", sa.JSON),
        sa.Column("risk_factors", sa.JSON),
        sa.Column("source_text", sa.Text),
    )

    # ── Tier 4: depends on entities + pipeline_runs ───────────────────────────

    op.create_table(
        "financial_ratios",
        sa.Column("ratio_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("dscr", sa.Numeric),
        sa.Column("fixed_charge_coverage", sa.Numeric),
        sa.Column("leverage_ratio", sa.Numeric),
        sa.Column("funded_debt_to_ebitda", sa.Numeric),
        sa.Column("current_ratio", sa.Numeric),
        sa.Column("quick_ratio", sa.Numeric),
        sa.Column("debt_to_equity", sa.Numeric),
        sa.Column("ebitda_margin", sa.Numeric),
        sa.Column("net_profit_margin", sa.Numeric),
        sa.Column("return_on_assets", sa.Numeric),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "slacr_scores",
        sa.Column("score_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("sponsor_score", sa.Numeric(5, 2)),
        sa.Column("leverage_score", sa.Numeric(5, 2)),
        sa.Column("asset_quality_score", sa.Numeric(5, 2)),
        sa.Column("cash_flow_score", sa.Numeric(5, 2)),
        sa.Column("risk_score", sa.Numeric(5, 2)),
        sa.Column("composite_score", sa.Numeric(5, 2)),
        sa.Column("internal_rating", sa.String(20), nullable=False),
        sa.Column("occ_classification", sa.String(30), nullable=False),
        sa.Column("model_version", sa.String(20)),
        sa.Column("shap_values", sa.JSON),
        sa.Column("lime_values", sa.JSON),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "covenants",
        sa.Column("covenant_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("covenant_type", sa.String(20)),
        sa.Column("description", sa.Text),
        sa.Column("metric", sa.String(50)),
        sa.Column("threshold_value", sa.Numeric(10, 4)),
        sa.Column("actual_value", sa.Numeric(10, 4)),
        sa.Column("unit", sa.String(20)),
        sa.Column("pass_fail", sa.Boolean),
        sa.Column("source_agent", sa.String(20), nullable=False),
    )

    op.create_table(
        "forecasts",
        sa.Column("forecast_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("metric", sa.String(30)),
        sa.Column("forecast_period", sa.Date),
        sa.Column("forecast_value", sa.Numeric(18, 2)),
        sa.Column("confidence_lower", sa.Numeric(18, 2)),
        sa.Column("confidence_upper", sa.Numeric(18, 2)),
        sa.Column("model_version", sa.String(50)),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "pipeline_stage_logs",
        sa.Column("log_id", sa.String(36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("stage_order", sa.Integer),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("output_file_path", sa.Text),
        sa.Column("status", sa.String(20)),
        sa.Column("token_count_input", sa.Integer),
        sa.Column("token_count_output", sa.Integer),
    )

    op.create_table(
        "embeddings",
        sa.Column("embedding_id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36)),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text),
        sa.Column("embedding", sa.Text),   # Text placeholder; overridden by vector(768) in PostgreSQL
        sa.Column("model_name", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("session_id", sa.String(128)),
        sa.Column("actor_ip", sa.String(45)),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("route", sa.Text),
        sa.Column("target_path", sa.Text),
        sa.Column("target_table", sa.String(50)),
        sa.Column("agent_name", sa.String(50)),
        sa.Column("metadata", sa.JSON),
        sa.Column("status_code", sa.Integer),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_timestamp_desc", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_session_timestamp", "audit_log", ["session_id", "timestamp"])

    # ── Tier 5: depends on income_statements + entities ───────────────────────

    op.create_table(
        "revenue_segments",
        sa.Column("segment_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("statement_id", sa.String(36)),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("segment_name", sa.String(100), nullable=False),
        sa.Column("segment_revenue", sa.Numeric(18, 2)),
        sa.Column("pct_of_total_revenue", sa.Numeric),
        sa.Column("yoy_growth", sa.Numeric),
        sa.UniqueConstraint(
            "entity_id", "fiscal_year", "segment_name",
            name="uq_revenue_segment_entity_year_name",
        ),
    )

    # ── Tier 6: projections + covenant compliance ─────────────────────────────

    op.create_table(
        "projections",
        sa.Column("projection_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("scenario", sa.String(10), nullable=False),
        sa.Column("projection_year", sa.Integer, nullable=False),
        sa.Column("projection_date", sa.Date),
        sa.Column("revenue", sa.Numeric(18, 2)),
        sa.Column("ebitda", sa.Numeric(18, 2)),
        sa.Column("ebit", sa.Numeric(18, 2)),
        sa.Column("net_income", sa.Numeric(18, 2)),
        sa.Column("operating_cash_flow", sa.Numeric(18, 2)),
        sa.Column("capital_expenditures", sa.Numeric(18, 2)),
        sa.Column("free_cash_flow", sa.Numeric(18, 2)),
        sa.Column("dscr", sa.Numeric),
        sa.Column("funded_debt", sa.Numeric(18, 2)),
        sa.Column("funded_debt_to_ebitda", sa.Numeric),
        sa.Column("ending_cash", sa.Numeric(18, 2)),
        sa.Column("revenue_growth_assumption", sa.Numeric(8, 6)),
        sa.Column("ebitda_margin_assumption", sa.Numeric(8, 6)),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "entity_id", "pipeline_run_id", "scenario", "projection_year",
            name="uq_projection_entity_run_scenario_year",
        ),
    )

    op.create_table(
        "covenant_compliance_projections",
        sa.Column("compliance_id", sa.String(36), primary_key=True),
        sa.Column("deal_id", sa.String(36)),
        sa.Column("pipeline_run_id", sa.String(36)),
        sa.Column("scenario", sa.String(10), nullable=False),
        sa.Column("projection_year", sa.Integer, nullable=False),
        sa.Column("covenant_type", sa.String(40), nullable=False),
        sa.Column("formula", sa.Text),
        sa.Column("threshold_value", sa.Numeric(10, 4)),
        sa.Column("threshold_operator", sa.String(5)),
        sa.Column("computed_value", sa.Numeric(10, 4)),
        sa.Column("headroom_pct", sa.Numeric),
        sa.Column("status", sa.String(20)),
        sa.Column("is_breach_year", sa.Boolean, server_default="0"),
        sa.Column("trigger_action", sa.Text),
        sa.UniqueConstraint(
            "deal_id", "pipeline_run_id", "scenario", "projection_year", "covenant_type",
            name="uq_covenant_compliance_projection",
        ),
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_table("covenant_compliance_projections")
    op.drop_table("projections")
    op.drop_table("revenue_segments")
    op.drop_index("ix_audit_log_session_timestamp", "audit_log")
    op.drop_index("ix_audit_log_timestamp_desc", "audit_log")
    op.drop_table("audit_log")
    op.drop_table("embeddings")
    op.drop_table("pipeline_stage_logs")
    op.drop_table("forecasts")
    op.drop_table("covenants")
    op.drop_table("slacr_scores")
    op.drop_table("financial_ratios")
    op.drop_table("management_guidance")
    op.drop_table("collateral")
    op.drop_table("personal_financial_statements")
    op.drop_table("cash_flow_statements")
    op.drop_table("balance_sheets")
    op.drop_table("income_statements")
    op.drop_table("pipeline_runs")
    op.drop_table("loan_terms")
    op.drop_table("documents")
    op.drop_table("entities")
    op.drop_table("deals")
    op.drop_table("workspaces")
