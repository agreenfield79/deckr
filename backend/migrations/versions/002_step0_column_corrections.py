"""Step 0 — Column corrections to existing tables.

Phase 3B.0: ENUM drift fixes, wrong-tier column removals, type corrections,
FK additions, and missing column additions to all existing tables.

Revision ID: 002
Revises: 001
Create Date: 2026-04-20

Notes:
  - PostgreSQL ENUM value additions (ALTER TYPE ... ADD VALUE) cannot be rolled back
    without dropping/recreating the type. Those stmts are guarded by dialect check.
  - SQLite column renames use batch mode (render_as_batch=True in env.py).
  - All new columns are nullable — no default values required for existing rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # ── 3B.0.1 — ENUM drift fixes (PostgreSQL only) ──────────────────────────
    if _is_postgresql():
        op.execute("ALTER TYPE source_agent_type ADD VALUE IF NOT EXISTS 'financial'")
        op.execute("ALTER TYPE source_agent_type ADD VALUE IF NOT EXISTS 'collateral'")
        op.execute("ALTER TYPE source_agent_type ADD VALUE IF NOT EXISTS 'guarantor'")
        op.execute("ALTER TYPE source_agent_type ADD VALUE IF NOT EXISTS 'industry'")
        op.execute("ALTER TYPE source_agent_type ADD VALUE IF NOT EXISTS 'packaging'")
        op.execute("ALTER TYPE source_agent_type ADD VALUE IF NOT EXISTS 'extraction'")
        op.execute("ALTER TYPE deal_status ADD VALUE IF NOT EXISTS 'closed'")

    # ── 3B.0.2 — Remove wrong-tier columns ───────────────────────────────────
    with op.batch_alter_table("management_guidance") as batch_op:
        batch_op.drop_column("source_text")
        batch_op.add_column(sa.Column("source", sa.String(50), nullable=True))

    with op.batch_alter_table("income_statements") as batch_op:
        batch_op.drop_column("revenue_segments")
        batch_op.add_column(sa.Column("shares_outstanding", sa.BigInteger, nullable=True))
        batch_op.add_column(sa.Column("eps", sa.Numeric(10, 4), nullable=True))

    with op.batch_alter_table("loan_terms") as batch_op:
        batch_op.drop_column("covenant_definitions")

    # ── 3B.0.3 — Truncate Text → VARCHAR(255) ────────────────────────────────
    with op.batch_alter_table("covenants") as batch_op:
        batch_op.alter_column("description", type_=sa.String(255), existing_nullable=True)

    with op.batch_alter_table("collateral") as batch_op:
        batch_op.alter_column("description", type_=sa.String(255), existing_nullable=True)

    with op.batch_alter_table("covenant_compliance_projections") as batch_op:
        batch_op.alter_column("trigger_action", type_=sa.String(255), existing_nullable=True)

    # ── 3B.0.4 — FK corrections ───────────────────────────────────────────────
    # personal_financial_statements.entity_id — add ON DELETE CASCADE
    with op.batch_alter_table("personal_financial_statements") as batch_op:
        batch_op.drop_constraint("fk_pfs_entity", type_="foreignkey") if _is_postgresql() else None
        batch_op.alter_column("entity_id",
                              existing_type=sa.String(36),
                              nullable=True)
    # Note: batch mode recreates the table with the new FK for SQLite;
    # PostgreSQL uses an explicit ALTER TABLE.
    if _is_postgresql():
        op.execute(
            "ALTER TABLE personal_financial_statements "
            "ADD CONSTRAINT fk_pfs_entity_cascade "
            "FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE"
        )

    # covenants — add loan_terms_id FK column
    with op.batch_alter_table("covenants") as batch_op:
        batch_op.add_column(sa.Column("loan_terms_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("headroom_pct",   sa.Numeric(8, 4), nullable=True))
        batch_op.add_column(sa.Column("test_frequency", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("last_tested_at", sa.Date, nullable=True))
        batch_op.add_column(sa.Column("cure_period_days", sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("waiver_count",   sa.Integer, nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("status",         sa.String(20), nullable=True))
        batch_op.create_foreign_key(
            "fk_covenants_loan_terms", "loan_terms",
            ["loan_terms_id"], ["loan_terms_id"]
        )

    # covenant_compliance_projections — add covenant_id FK
    with op.batch_alter_table("covenant_compliance_projections") as batch_op:
        batch_op.add_column(sa.Column("covenant_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_ccp_covenant", "covenants",
            ["covenant_id"], ["covenant_id"]
        )

    # ── 3B.0.5 — Add missing columns to existing tables ──────────────────────

    # deals
    with op.batch_alter_table("deals") as batch_op:
        batch_op.add_column(sa.Column("pipeline_version", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("storage_backend",  sa.String(20), nullable=True, server_default="local"))

    # entities
    with op.batch_alter_table("entities") as batch_op:
        batch_op.add_column(sa.Column("role", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("dba",  sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("ein",  sa.String(15), nullable=True))

    # financial_ratios
    with op.batch_alter_table("financial_ratios") as batch_op:
        batch_op.add_column(sa.Column("interest_coverage", sa.Numeric(10, 4), nullable=True))
        batch_op.add_column(sa.Column("asset_turnover",    sa.Numeric(10, 4), nullable=True))

    # slacr_scores
    with op.batch_alter_table("slacr_scores") as batch_op:
        batch_op.add_column(sa.Column("entity_id",               sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("model_id",                sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("confidence_interval_low", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("confidence_interval_high",sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("input_features_snapshot", sa.JSON, nullable=True))
        batch_op.create_foreign_key("fk_slacr_entity", "entities", ["entity_id"], ["entity_id"])

    # loan_terms
    with op.batch_alter_table("loan_terms") as batch_op:
        batch_op.add_column(sa.Column("entity_id",            sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("loan_type",            sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("rate_index",           sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("spread_bps",           sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("balloon_payment",      sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("origination_fee_bps",  sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("prepayment_penalty",   sa.Boolean, nullable=True))
        batch_op.add_column(sa.Column("draw_period_months",   sa.Integer, nullable=True))
        batch_op.add_column(sa.Column("target_close_date",    sa.Date, nullable=True))
        batch_op.add_column(sa.Column("status",               sa.String(20), nullable=True, server_default="proposed"))
        batch_op.create_foreign_key("fk_loan_terms_entity", "entities", ["entity_id"], ["entity_id"])

    # collateral
    with op.batch_alter_table("collateral") as batch_op:
        batch_op.add_column(sa.Column("entity_id",      sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("appraiser_name", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("parcel_id",      sa.String(50), nullable=True))
        batch_op.create_foreign_key("fk_collateral_entity", "entities", ["entity_id"], ["entity_id"])

    # revenue_segments
    with op.batch_alter_table("revenue_segments") as batch_op:
        batch_op.add_column(sa.Column("segment_type",   sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("gross_profit",   sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("segment_margin", sa.Numeric(8, 6), nullable=True))

    # projections
    with op.batch_alter_table("projections") as batch_op:
        batch_op.add_column(sa.Column("assumptions_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("leverage_ratio", sa.Numeric(10, 4), nullable=True))
        batch_op.add_column(sa.Column("debt_balance",   sa.Numeric(18, 2), nullable=True))

    # pipeline_runs — rename total_duration_seconds → total_elapsed_ms + add columns
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.alter_column("total_duration_seconds", new_column_name="total_elapsed_ms")
        batch_op.add_column(sa.Column("triggered_by",    sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("pipeline_version",sa.String(20), nullable=True))

    # pipeline_stage_logs — rename duration_seconds → elapsed_ms + add error_code
    with op.batch_alter_table("pipeline_stage_logs") as batch_op:
        batch_op.alter_column("duration_seconds", new_column_name="elapsed_ms")
        batch_op.add_column(sa.Column("error_code", sa.String(30), nullable=True))

    # documents
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("extraction_run_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_documents_extraction_run", "pipeline_runs",
            ["extraction_run_id"], ["pipeline_run_id"]
        )

    # audit_log
    with op.batch_alter_table("audit_log") as batch_op:
        batch_op.add_column(sa.Column("user_id",   sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("old_value", sa.JSON, nullable=True))
        batch_op.add_column(sa.Column("new_value", sa.JSON, nullable=True))

    # embeddings
    with op.batch_alter_table("embeddings") as batch_op:
        batch_op.add_column(sa.Column("deal_id",       sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("entity_id",     sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("document_type", sa.String(30), nullable=True))


def downgrade() -> None:
    # embeddings
    with op.batch_alter_table("embeddings") as batch_op:
        batch_op.drop_column("document_type")
        batch_op.drop_column("entity_id")
        batch_op.drop_column("deal_id")

    # audit_log
    with op.batch_alter_table("audit_log") as batch_op:
        batch_op.drop_column("new_value")
        batch_op.drop_column("old_value")
        batch_op.drop_column("user_id")

    # documents
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("fk_documents_extraction_run", type_="foreignkey")
        batch_op.drop_column("extraction_run_id")

    # pipeline_stage_logs
    with op.batch_alter_table("pipeline_stage_logs") as batch_op:
        batch_op.drop_column("error_code")
        batch_op.alter_column("elapsed_ms", new_column_name="duration_seconds")

    # pipeline_runs
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.drop_column("pipeline_version")
        batch_op.drop_column("triggered_by")
        batch_op.alter_column("total_elapsed_ms", new_column_name="total_duration_seconds")

    # projections
    with op.batch_alter_table("projections") as batch_op:
        batch_op.drop_column("debt_balance")
        batch_op.drop_column("leverage_ratio")
        batch_op.drop_column("assumptions_id")

    # revenue_segments
    with op.batch_alter_table("revenue_segments") as batch_op:
        batch_op.drop_column("segment_margin")
        batch_op.drop_column("gross_profit")
        batch_op.drop_column("segment_type")

    # collateral
    with op.batch_alter_table("collateral") as batch_op:
        batch_op.drop_constraint("fk_collateral_entity", type_="foreignkey")
        batch_op.drop_column("parcel_id")
        batch_op.drop_column("appraiser_name")
        batch_op.drop_column("entity_id")

    # loan_terms
    with op.batch_alter_table("loan_terms") as batch_op:
        batch_op.drop_constraint("fk_loan_terms_entity", type_="foreignkey")
        batch_op.drop_column("status")
        batch_op.drop_column("target_close_date")
        batch_op.drop_column("draw_period_months")
        batch_op.drop_column("prepayment_penalty")
        batch_op.drop_column("origination_fee_bps")
        batch_op.drop_column("balloon_payment")
        batch_op.drop_column("spread_bps")
        batch_op.drop_column("rate_index")
        batch_op.drop_column("loan_type")
        batch_op.drop_column("entity_id")
        batch_op.add_column(sa.Column("covenant_definitions", sa.JSON, nullable=True))

    # slacr_scores
    with op.batch_alter_table("slacr_scores") as batch_op:
        batch_op.drop_constraint("fk_slacr_entity", type_="foreignkey")
        batch_op.drop_column("input_features_snapshot")
        batch_op.drop_column("confidence_interval_high")
        batch_op.drop_column("confidence_interval_low")
        batch_op.drop_column("model_id")
        batch_op.drop_column("entity_id")

    # financial_ratios
    with op.batch_alter_table("financial_ratios") as batch_op:
        batch_op.drop_column("asset_turnover")
        batch_op.drop_column("interest_coverage")

    # entities
    with op.batch_alter_table("entities") as batch_op:
        batch_op.drop_column("ein")
        batch_op.drop_column("dba")
        batch_op.drop_column("role")

    # deals
    with op.batch_alter_table("deals") as batch_op:
        batch_op.drop_column("storage_backend")
        batch_op.drop_column("pipeline_version")

    # covenants — covenant_compliance_projections covenant_id
    with op.batch_alter_table("covenant_compliance_projections") as batch_op:
        batch_op.drop_constraint("fk_ccp_covenant", type_="foreignkey")
        batch_op.drop_column("covenant_id")
        batch_op.alter_column("trigger_action", type_=sa.Text, existing_nullable=True)

    # covenants
    with op.batch_alter_table("covenants") as batch_op:
        batch_op.drop_constraint("fk_covenants_loan_terms", type_="foreignkey")
        batch_op.drop_column("status")
        batch_op.drop_column("waiver_count")
        batch_op.drop_column("cure_period_days")
        batch_op.drop_column("last_tested_at")
        batch_op.drop_column("test_frequency")
        batch_op.drop_column("headroom_pct")
        batch_op.drop_column("loan_terms_id")
        batch_op.alter_column("description", type_=sa.Text, existing_nullable=True)

    # collateral description restore
    with op.batch_alter_table("collateral") as batch_op:
        batch_op.alter_column("description", type_=sa.Text, existing_nullable=True)

    # management_guidance
    with op.batch_alter_table("management_guidance") as batch_op:
        batch_op.drop_column("source")
        batch_op.add_column(sa.Column("source_text", sa.Text, nullable=True))

    # income_statements
    with op.batch_alter_table("income_statements") as batch_op:
        batch_op.drop_column("eps")
        batch_op.drop_column("shares_outstanding")
        batch_op.add_column(sa.Column("revenue_segments", sa.JSON, nullable=True))

    # PostgreSQL ENUM values cannot be removed — note only, no downgrade action
