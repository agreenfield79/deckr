"""012 — Widen financial_ratios.interest_coverage and .dscr to NUMERIC(20, 4).

Root cause: NVIDIA pipeline run produced an interest_coverage of 1,303,870 —
seven digits before the decimal point — which exceeds the maximum representable
value of NUMERIC(10, 4) (six digits before the decimal, i.e. < 10^6).  The
resulting psycopg2.errors.NumericValueOutOfRange caused the entire INSERT to
roll back, writing 0 rows to financial_ratios and failing the IP2 gate.

Columns widened in this migration
  financial_ratios.interest_coverage  NUMERIC(10, 4) → NUMERIC(20, 4)
  financial_ratios.dscr               NUMERIC(10, 4) → NUMERIC(20, 4)

NUMERIC(20, 4) stores up to 16 digits before the decimal point
(max absolute value < 10^16), accommodating any plausible ratio produced
by a large-cap borrower without sacrificing the 4-decimal-place precision
used by the rest of the schema.

PostgreSQL note: ALTER COLUMN TYPE is blocked when any view selects the
column being changed.  v_ratio_dashboard selects both interest_coverage and
dscr; v_covenant_tracker, v_slacr_components, and v_deal_snapshot select dscr.
All seven views are therefore dropped before the ALTER and recreated afterwards,
identical to the pattern used in migration 010.

SQLite note: batch_alter_table(recreate="always") handles the column type
change without view interference (SQLite views are not validated on rename).

Revision ID: 012
Revises: 011
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WIDE = sa.Numeric(20, 4)
_NARROW = sa.Numeric(10, 4)

# ---------------------------------------------------------------------------
# View DDL — identical to migration 010 (must be re-applied after ALTER)
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
    for name in reversed(_VIEW_ORDER):
        op.execute(text(f"DROP VIEW IF EXISTS {name}"))


def _recreate_all_views() -> None:
    for name in _VIEW_ORDER:
        op.execute(text(_VIEWS[name]))


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgresql():
        _drop_all_views()

    recreate = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("financial_ratios", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "interest_coverage",
            existing_type=_NARROW,
            type_=_WIDE,
            nullable=True,
        )
        batch_op.alter_column(
            "dscr",
            existing_type=_NARROW,
            type_=_WIDE,
            nullable=True,
        )

    if _is_postgresql():
        _recreate_all_views()


def downgrade() -> None:
    if _is_postgresql():
        _drop_all_views()

    recreate = "never" if _is_postgresql() else "always"
    with op.batch_alter_table("financial_ratios", recreate=recreate) as batch_op:
        batch_op.alter_column(
            "interest_coverage",
            existing_type=_WIDE,
            type_=_NARROW,
            nullable=True,
        )
        batch_op.alter_column(
            "dscr",
            existing_type=_WIDE,
            type_=_NARROW,
            nullable=True,
        )

    if _is_postgresql():
        _recreate_all_views()
