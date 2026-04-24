"""Step 10 — Phase 3B.10 schema discrepancy corrections.

Addresses 8 gaps identified between Phase 2 Target Schema and the actual ORM:
  1. covenants.threshold_operator column added (was missing entirely)
  2. covenants.covenant_type converted to ENUM (financial/affirmative/negative/reporting)
  3. financial_ratios.entity_id FK gets ON DELETE CASCADE
  4. financial_ratios — precision added to 10 pre-existing plain-Numeric columns
  5. slacr_scores.internal_rating widened VARCHAR(20) → VARCHAR(30)
  6. revenue_segments.pct_of_total_revenue + yoy_growth get NUMERIC(8,6)
  7. projections.dscr + funded_debt_to_ebitda get NUMERIC(10,4)
  8. audit_log — index added on (deal_id, timestamp)

SQLite note: batch_alter_table(recreate="always") temporarily drops and renames the
target table. SQLite validates all views that reference that table during the rename
step, which causes OperationalError if the views still exist. All 7 views are therefore
dropped at the top of upgrade() and recreated at the bottom, identical to migration 009.

Revision ID: 010
Revises: 009
Create Date: 2026-04-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# View DDL — identical to migration 009 (must be re-applied after batch ops)
# ---------------------------------------------------------------------------

_VIEWS = {
    "v_financial_summary": """
CREATE VIEW v_financial_summary AS
SELECT
    is2.entity_id,
    e.deal_id,
    e.legal_name,
    is2.fiscal_year,
    is2.period_type,
    is2.revenue,
    is2.ebitda,
    is2.ebit,
    is2.net_income,
    bs.total_assets,
    bs.total_liabilities,
    bs.total_equity,
    cf.operating_cash_flow,
    cf.free_cash_flow,
    cf.capital_expenditures
FROM income_statements is2
JOIN entities e ON e.entity_id = is2.entity_id
LEFT JOIN balance_sheets bs
    ON bs.entity_id = is2.entity_id
    AND bs.as_of_date = is2.fiscal_year_end
LEFT JOIN cash_flow_statements cf
    ON cf.entity_id = is2.entity_id
    AND cf.fiscal_year = is2.fiscal_year
""".strip(),

    "v_ratio_dashboard": """
CREATE VIEW v_ratio_dashboard AS
SELECT
    fr.ratio_id,
    fr.entity_id,
    fr.fiscal_year,
    fr.pipeline_run_id,
    fr.dscr,
    fr.fixed_charge_coverage,
    fr.leverage_ratio,
    fr.funded_debt_to_ebitda,
    fr.current_ratio,
    fr.quick_ratio,
    fr.ebitda_margin,
    fr.interest_coverage,
    fr.computed_at,
    d.deal_id,
    d.borrower_entity_name,
    d.naics_code,
    b25.percentile_25 AS dscr_p25,
    b50.percentile_50 AS dscr_p50,
    b75.percentile_75 AS dscr_p75
FROM financial_ratios fr
JOIN entities e ON e.entity_id = fr.entity_id
JOIN deals d    ON d.deal_id = e.deal_id
LEFT JOIN benchmarks b25 ON b25.naics_code = d.naics_code AND b25.metric_name = 'dscr'
LEFT JOIN benchmarks b50 ON b50.naics_code = d.naics_code AND b50.metric_name = 'dscr'
LEFT JOIN benchmarks b75 ON b75.naics_code = d.naics_code AND b75.metric_name = 'dscr'
""".strip(),

    "v_covenant_tracker": """
CREATE VIEW v_covenant_tracker AS
SELECT
    c.covenant_id,
    c.deal_id,
    c.loan_terms_id,
    c.pipeline_run_id,
    c.covenant_type,
    c.metric,
    c.description,
    c.threshold_value,
    c.threshold_operator,
    c.actual_value,
    c.pass_fail,
    c.headroom_pct,
    c.status,
    c.source_agent,
    lt.loan_amount,
    lt.proposed_annual_debt_service,
    fr.dscr AS financial_ratio_dscr
FROM covenants c
LEFT JOIN loan_terms lt ON lt.deal_id = c.deal_id
LEFT JOIN entities e    ON e.deal_id = c.deal_id AND e.entity_type = 'borrower'
LEFT JOIN financial_ratios fr
    ON fr.entity_id = e.entity_id
    AND fr.pipeline_run_id = c.pipeline_run_id
""".strip(),

    "v_slacr_components": """
CREATE VIEW v_slacr_components AS
SELECT
    ss.score_id,
    ss.deal_id,
    ss.entity_id,
    ss.pipeline_run_id,
    ss.sponsor_score,
    ss.leverage_score,
    ss.asset_quality_score,
    ss.cash_flow_score,
    ss.risk_score,
    ss.composite_score,
    ss.internal_rating,
    ss.occ_classification,
    ss.confidence_interval_low,
    ss.confidence_interval_high,
    ss.shap_values,
    ss.computed_at,
    fr.dscr                  AS historical_dscr,
    fr.funded_debt_to_ebitda AS historical_leverage
FROM slacr_scores ss
LEFT JOIN financial_ratios fr
    ON fr.entity_id = ss.entity_id
    AND fr.pipeline_run_id = ss.pipeline_run_id
""".strip(),

    "v_pipeline_history": """
CREATE VIEW v_pipeline_history AS
SELECT
    pr.pipeline_run_id,
    pr.deal_id,
    pr.started_at,
    pr.completed_at,
    pr.status,
    pr.total_elapsed_ms,
    pr.pipeline_version,
    pr.triggered_by,
    d.borrower_entity_name,
    COUNT(psl.log_id) AS stages_total,
    SUM(CASE WHEN psl.status = 'complete' THEN 1 ELSE 0 END) AS stages_complete
FROM pipeline_runs pr
JOIN deals d ON d.deal_id = pr.deal_id
LEFT JOIN pipeline_stage_logs psl ON psl.pipeline_run_id = pr.pipeline_run_id
GROUP BY pr.pipeline_run_id, pr.deal_id, pr.started_at, pr.completed_at,
         pr.status, pr.total_elapsed_ms, pr.pipeline_version, pr.triggered_by,
         d.borrower_entity_name
""".strip(),

    "v_projection_stress": """
CREATE VIEW v_projection_stress AS
SELECT
    p.deal_id,
    p.entity_id,
    p.pipeline_run_id,
    p.scenario,
    p.projection_year,
    p.revenue,
    p.ebitda,
    p.dscr,
    p.leverage_ratio,
    p.free_cash_flow,
    ccp.covenant_type,
    ccp.threshold_value,
    ccp.computed_value,
    ccp.headroom_pct,
    ccp.status        AS covenant_status,
    ccp.is_breach_year
FROM projections p
LEFT JOIN covenant_compliance_projections ccp
    ON ccp.deal_id = p.deal_id
    AND ccp.pipeline_run_id = p.pipeline_run_id
    AND ccp.scenario = p.scenario
    AND ccp.projection_year = p.projection_year
""".strip(),

    "v_deal_snapshot": """
CREATE VIEW v_deal_snapshot AS
SELECT
    d.deal_id,
    d.borrower_entity_name,
    d.naics_code,
    d.status              AS deal_status,
    d.pipeline_version,
    d.storage_backend,
    d.created_at          AS deal_created_at,
    lt.loan_amount,
    lt.loan_type,
    lt.term_months,
    lt.rate_type,
    lt.status             AS loan_status,
    ss.composite_score    AS slacr_score,
    ss.internal_rating,
    ss.occ_classification,
    fr.dscr               AS latest_dscr,
    fr.funded_debt_to_ebitda AS latest_leverage,
    pr.pipeline_run_id    AS latest_run_id,
    pr.status             AS pipeline_status,
    pr.completed_at       AS pipeline_completed_at,
    COUNT(DISTINCT doc.document_id) AS document_count,
    COUNT(DISTINCT e.entity_id)     AS entity_count
FROM deals d
LEFT JOIN loan_terms lt ON lt.deal_id = d.deal_id
LEFT JOIN pipeline_runs pr ON pr.deal_id = d.deal_id
    AND pr.started_at = (
        SELECT MAX(pr2.started_at) FROM pipeline_runs pr2 WHERE pr2.deal_id = d.deal_id
    )
LEFT JOIN slacr_scores ss ON ss.deal_id = d.deal_id AND ss.pipeline_run_id = pr.pipeline_run_id
LEFT JOIN entities e      ON e.deal_id = d.deal_id
LEFT JOIN financial_ratios fr
    ON fr.entity_id = e.entity_id
    AND fr.pipeline_run_id = pr.pipeline_run_id
    AND e.entity_type = 'borrower'
LEFT JOIN documents doc ON doc.deal_id = d.deal_id
GROUP BY d.deal_id, d.borrower_entity_name, d.naics_code, d.status,
         d.pipeline_version, d.storage_backend, d.created_at,
         lt.loan_amount, lt.loan_type, lt.term_months, lt.rate_type, lt.status,
         ss.composite_score, ss.internal_rating, ss.occ_classification,
         fr.dscr, fr.funded_debt_to_ebitda,
         pr.pipeline_run_id, pr.status, pr.completed_at
""".strip(),
}

_VIEW_ORDER = [
    "v_financial_summary",
    "v_ratio_dashboard",
    "v_covenant_tracker",
    "v_slacr_components",
    "v_pipeline_history",
    "v_projection_stress",
    "v_deal_snapshot",
]


def _drop_all_views() -> None:
    """Drop all 7 views so SQLite batch_alter_table can rename temp tables freely."""
    for name in reversed(_VIEW_ORDER):
        op.execute(text(f"DROP VIEW IF EXISTS {name}"))


def _recreate_all_views() -> None:
    """Recreate all 7 views after batch operations complete."""
    for name in _VIEW_ORDER:
        op.execute(text(_VIEWS[name]))


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _existing_indexes(table_name: str):
    return {ix["name"] for ix in inspect(op.get_bind()).get_indexes(table_name)}


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # STEP 0a — clean up any orphaned temp tables from a prior failed run #
    # (batch_alter_table leaves _alembic_tmp_<table> if it crashes mid-op)#
    # ------------------------------------------------------------------ #
    for tmp in [
        "_alembic_tmp_covenants",
        "_alembic_tmp_financial_ratios",
        "_alembic_tmp_slacr_scores",
        "_alembic_tmp_revenue_segments",
        "_alembic_tmp_projections",
    ]:
        op.execute(text(f"DROP TABLE IF EXISTS {tmp}"))

    # ------------------------------------------------------------------ #
    # STEP 0b — drop all views so SQLite batch-rename doesn't fail        #
    # ------------------------------------------------------------------ #
    _drop_all_views()

    # ------------------------------------------------------------------ #
    # 1 & 2 — covenants: add threshold_operator + ENUM covenant_type      #
    # ------------------------------------------------------------------ #
    cov_cols = {col["name"] for col in inspect(op.get_bind()).get_columns("covenants")}

    # recreate="never" for PostgreSQL: fk_ccp_covenant (covenant_compliance_projections
    # → covenants) is created in migration 002. Recreating covenants would require
    # dropping covenants_pkey, which PostgreSQL blocks due to that FK dependency.
    # PostgreSQL supports ADD COLUMN and ALTER COLUMN TYPE natively without recreation.
    _rb10 = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("covenants", recreate=_rb10) as batch_op:
        if "threshold_operator" not in cov_cols:
            batch_op.add_column(sa.Column("threshold_operator", sa.String(5), nullable=True))
        # Re-declare covenant_type to align DDL with ORM (storage unchanged in SQLite)
        batch_op.alter_column(
            "covenant_type",
            existing_type=sa.String(20),
            type_=sa.String(20),
            nullable=True,
        )

    # PostgreSQL: create native ENUM type and cast the column
    if _is_postgresql():
        op.execute(text(
            "DO $$ BEGIN "
            "  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'covenanttype') THEN "
            "    CREATE TYPE covenanttype AS ENUM "
            "      ('financial', 'affirmative', 'negative', 'reporting'); "
            "  END IF; "
            "END $$;"
        ))
        op.execute(text(
            "ALTER TABLE covenants "
            "ALTER COLUMN covenant_type TYPE covenanttype "
            "USING covenant_type::covenanttype;"
        ))

    # ------------------------------------------------------------------ #
    # 3 & 4 — financial_ratios: CASCADE FK + precision on 10 columns      #
    # ------------------------------------------------------------------ #
    # Drop any pre-existing unnamed FK outside the batch (IF EXISTS).
    # Migration 001 created financial_ratios with no ForeignKey() on entity_id,
    # so this constraint never exists on Alembic-only deployments. The try/except
    # inside a batch block does NOT catch errors raised during flush() at __exit__,
    # so the drop must happen here via raw SQL to be safely idempotent.
    if _is_postgresql():
        op.execute(text(
            "ALTER TABLE financial_ratios "
            "DROP CONSTRAINT IF EXISTS financial_ratios_entity_id_fkey"
        ))
    # recreate="never": use direct ALTER TABLE on PostgreSQL to avoid table
    # recreation, which could silently drop outbound FKs added in prior migrations.
    _rb_fr = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("financial_ratios", recreate=_rb_fr) as batch_op:
        batch_op.create_foreign_key(
            "fk_financial_ratios_entity_cascade",
            "entities",
            ["entity_id"],
            ["entity_id"],
            ondelete="CASCADE",
        )
        for col, new_type in [
            ("dscr",                  sa.Numeric(10, 4)),
            ("fixed_charge_coverage", sa.Numeric(10, 4)),
            ("leverage_ratio",        sa.Numeric(10, 4)),
            ("funded_debt_to_ebitda", sa.Numeric(10, 4)),
            ("current_ratio",         sa.Numeric(10, 4)),
            ("quick_ratio",           sa.Numeric(10, 4)),
            ("debt_to_equity",        sa.Numeric(10, 4)),
            ("ebitda_margin",         sa.Numeric(8, 6)),
            ("net_profit_margin",     sa.Numeric(8, 6)),
            ("return_on_assets",      sa.Numeric(8, 6)),
        ]:
            batch_op.alter_column(col, type_=new_type, existing_type=sa.Numeric())

    # ------------------------------------------------------------------ #
    # 5 — slacr_scores.internal_rating: VARCHAR(20) → VARCHAR(30)         #
    # ------------------------------------------------------------------ #
    # recreate="never": slacr_scores has outbound FKs added in migrations 002
    # and 007 (fk_slacr_entity, fk_slacr_model). Using direct ALTER COLUMN TYPE
    # avoids risking their loss during full table recreation.
    _rb_ss = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("slacr_scores", recreate=_rb_ss) as batch_op:
        batch_op.alter_column(
            "internal_rating",
            existing_type=sa.String(20),
            type_=sa.String(30),
            nullable=False,
        )

    # ------------------------------------------------------------------ #
    # 6 — revenue_segments: NUMERIC(8,6) precision                        #
    # ------------------------------------------------------------------ #
    _rb_rseg = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("revenue_segments", recreate=_rb_rseg) as batch_op:
        batch_op.alter_column(
            "pct_of_total_revenue",
            existing_type=sa.Numeric(),
            type_=sa.Numeric(8, 6),
            nullable=True,
        )
        batch_op.alter_column(
            "yoy_growth",
            existing_type=sa.Numeric(),
            type_=sa.Numeric(8, 6),
            nullable=True,
        )

    # ------------------------------------------------------------------ #
    # 7 — projections: NUMERIC(10,4) precision on dscr + funded_debt      #
    # ------------------------------------------------------------------ #
    # recreate="never": projections has outbound FK fk_projections_assumptions
    # added in migration 006. Direct ALTER COLUMN TYPE avoids recreation risk.
    _rb_proj = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("projections", recreate=_rb_proj) as batch_op:
        batch_op.alter_column(
            "dscr",
            existing_type=sa.Numeric(),
            type_=sa.Numeric(10, 4),
            nullable=True,
        )
        batch_op.alter_column(
            "funded_debt_to_ebitda",
            existing_type=sa.Numeric(),
            type_=sa.Numeric(10, 4),
            nullable=True,
        )

    # ------------------------------------------------------------------ #
    # 8 — audit_log: index on (deal_id, timestamp)                        #
    # ------------------------------------------------------------------ #
    if "ix_audit_log_deal_timestamp" not in _existing_indexes("audit_log"):
        op.create_index(
            "ix_audit_log_deal_timestamp",
            "audit_log",
            ["deal_id", "timestamp"],
        )

    # ------------------------------------------------------------------ #
    # STEP LAST — recreate all 7 views                                    #
    # ------------------------------------------------------------------ #
    _recreate_all_views()


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    _drop_all_views()

    # 8
    op.drop_index("ix_audit_log_deal_timestamp", table_name="audit_log")

    # 7
    _rb_proj_dg = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("projections", recreate=_rb_proj_dg) as batch_op:
        batch_op.alter_column("dscr",               existing_type=sa.Numeric(10, 4), type_=sa.Numeric())
        batch_op.alter_column("funded_debt_to_ebitda", existing_type=sa.Numeric(10, 4), type_=sa.Numeric())

    # 6
    _rb_rseg_dg = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("revenue_segments", recreate=_rb_rseg_dg) as batch_op:
        batch_op.alter_column("pct_of_total_revenue", existing_type=sa.Numeric(8, 6), type_=sa.Numeric())
        batch_op.alter_column("yoy_growth",           existing_type=sa.Numeric(8, 6), type_=sa.Numeric())

    # 5
    _rb_ss_dg = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("slacr_scores", recreate=_rb_ss_dg) as batch_op:
        batch_op.alter_column("internal_rating", existing_type=sa.String(30), type_=sa.String(20), nullable=False)

    # 4 & 3
    if _is_postgresql():
        op.execute(text(
            "ALTER TABLE financial_ratios "
            "DROP CONSTRAINT IF EXISTS fk_financial_ratios_entity_cascade"
        ))
    _rb_fr_dg = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("financial_ratios", recreate=_rb_fr_dg) as batch_op:
        batch_op.create_foreign_key(
            "fk_financial_ratios_entity_orig",
            "entities",
            ["entity_id"],
            ["entity_id"],
        )
        for col, old_type in [
            ("dscr",                  sa.Numeric(10, 4)),
            ("fixed_charge_coverage", sa.Numeric(10, 4)),
            ("leverage_ratio",        sa.Numeric(10, 4)),
            ("funded_debt_to_ebitda", sa.Numeric(10, 4)),
            ("current_ratio",         sa.Numeric(10, 4)),
            ("quick_ratio",           sa.Numeric(10, 4)),
            ("debt_to_equity",        sa.Numeric(10, 4)),
            ("ebitda_margin",         sa.Numeric(8, 6)),
            ("net_profit_margin",     sa.Numeric(8, 6)),
            ("return_on_assets",      sa.Numeric(8, 6)),
        ]:
            batch_op.alter_column(col, existing_type=old_type, type_=sa.Numeric())

    # 1 & 2
    if _is_postgresql():
        op.execute(text(
            "ALTER TABLE covenants ALTER COLUMN covenant_type TYPE VARCHAR(20) "
            "USING covenant_type::VARCHAR;"
        ))

    with op.batch_alter_table("covenants", recreate="always") as batch_op:
        batch_op.drop_column("threshold_operator")
        batch_op.alter_column(
            "covenant_type",
            existing_type=sa.String(20),
            type_=sa.String(20),
            nullable=True,
        )

    # Restore views as they were in migration 009
    _recreate_all_views()
