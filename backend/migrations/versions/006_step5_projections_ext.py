"""Step 5 — Create projection_assumptions and sensitivity_analyses tables.

Revision ID: 006
Revises: 005
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if not inspect(bind).has_table("projection_assumptions"):
        op.create_table(
            "projection_assumptions",
            sa.Column("assumptions_id",           sa.String(36), primary_key=True),
            sa.Column("deal_id",                  sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="CASCADE")),
            sa.Column("pipeline_run_id",          sa.String(36), sa.ForeignKey("pipeline_runs.pipeline_run_id")),
            sa.Column("model_id",                 sa.String(36)),  # FK → model_versions wired in 007
            sa.Column("scenario",                 sa.String(10), nullable=False),
            sa.Column("revenue_growth_rate",      sa.Numeric(8, 6)),
            sa.Column("ebitda_margin_assumption", sa.Numeric(8, 6)),
            sa.Column("capex_pct_revenue",        sa.Numeric(8, 6)),
            sa.Column("interest_rate_assumption", sa.Numeric(8, 6)),
            sa.Column("debt_paydown_rate",        sa.Numeric(8, 6)),
            sa.Column("macro_scenario_tag",       sa.String(50)),
            sa.Column("created_at",               sa.DateTime(timezone=True)),
            sa.UniqueConstraint("deal_id", "pipeline_run_id", "scenario",
                                name="uq_proj_assumptions_deal_run_scenario"),
        )

    if not inspect(bind).has_table("sensitivity_analyses"):
        op.create_table(
            "sensitivity_analyses",
            sa.Column("sensitivity_id",       sa.String(36), primary_key=True),
            sa.Column("deal_id",              sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="CASCADE")),
            sa.Column("pipeline_run_id",      sa.String(36), sa.ForeignKey("pipeline_runs.pipeline_run_id")),
            sa.Column("variable_shocked",     sa.String(30), nullable=False),
            sa.Column("shock_magnitude_pct",  sa.Numeric(8, 4), nullable=False),
            sa.Column("resulting_dscr",       sa.Numeric(10, 4)),
            sa.Column("resulting_leverage",   sa.Numeric(10, 4)),
            sa.Column("resulting_fcf",        sa.Numeric(18, 2)),
            sa.Column("covenant_breach_year", sa.Integer),
            sa.Column("computed_at",          sa.DateTime(timezone=True)),
            sa.UniqueConstraint("deal_id", "pipeline_run_id", "variable_shocked", "shock_magnitude_pct",
                                name="uq_sensitivity_deal_run_variable_shock"),
        )

    # Wire projections.assumptions_id FK now that the table exists (only if column exists and FK not yet set)
    try:
        with op.batch_alter_table("projections") as batch_op:
            batch_op.create_foreign_key(
                "fk_projections_assumptions", "projection_assumptions",
                ["assumptions_id"], ["assumptions_id"]
            )
    except Exception:
        pass  # FK may already exist (SQLite batch recreate) or assumptions_id col missing


def downgrade() -> None:
    try:
        with op.batch_alter_table("projections") as batch_op:
            batch_op.drop_constraint("fk_projections_assumptions", type_="foreignkey")
    except Exception:
        pass

    op.drop_table("sensitivity_analyses")
    op.drop_table("projection_assumptions")
