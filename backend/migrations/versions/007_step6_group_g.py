"""Step 6 — Create Group G tables: model_versions, feature_store, model_outcomes.

Also seeds the current neural SLACR model version and wires deferred FKs.

Revision ID: 007
Revises: 006
Create Date: 2026-04-20
"""
from typing import Sequence, Union
from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy import inspect, text
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEURAL_SLACR_MODEL_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("model_versions"):
        op.create_table(
            "model_versions",
            sa.Column("model_id",                sa.String(36), primary_key=True),
            sa.Column("model_name",              sa.String(100), nullable=False),
            sa.Column("version",                 sa.String(20), nullable=False),
            sa.Column("architecture",            sa.String(50)),
            sa.Column("deployed_at",             sa.DateTime(timezone=True), nullable=False),
            sa.Column("deprecated_at",           sa.DateTime(timezone=True)),
            sa.Column("training_dataset_hash",   sa.String(64)),
            sa.Column("validation_auc",          sa.Numeric(6, 4)),
            sa.Column("validation_ks_statistic", sa.Numeric(6, 4)),
            sa.Column("calibration_brier_score", sa.Numeric(6, 4)),
            sa.Column("feature_names",           sa.JSON),
            sa.Column("created_at",              sa.DateTime(timezone=True)),
            sa.UniqueConstraint("model_name", "version", name="uq_model_version_name_ver"),
        )

    if not insp.has_table("feature_store"):
        op.create_table(
            "feature_store",
            sa.Column("feature_snapshot_id", sa.String(36), primary_key=True),
            sa.Column("deal_id",             sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="CASCADE")),
            sa.Column("pipeline_run_id",     sa.String(36), sa.ForeignKey("pipeline_runs.pipeline_run_id")),
            sa.Column("computed_at",         sa.DateTime(timezone=True), nullable=False),
            sa.Column("dscr_t0",             sa.Numeric(10, 4)),
            sa.Column("dscr_t1",             sa.Numeric(10, 4)),
            sa.Column("leverage_t0",         sa.Numeric(10, 4)),
            sa.Column("ebitda_margin_t0",    sa.Numeric(8, 6)),
            sa.Column("current_ratio_t0",    sa.Numeric(10, 4)),
            sa.Column("industry_risk_tier",  sa.String(10)),
            sa.Column("collateral_coverage", sa.Numeric(8, 4)),
            sa.Column("guarantor_net_worth", sa.Numeric(18, 2)),
            sa.Column("naics_code",          sa.String(10)),
            sa.Column("years_in_business",   sa.Integer),
            sa.Column("revenue_cagr_3yr",    sa.Numeric(8, 6)),
            sa.UniqueConstraint("deal_id", "pipeline_run_id", name="uq_feature_store_deal_run"),
        )

    if not insp.has_table("model_outcomes"):
        op.create_table(
            "model_outcomes",
            sa.Column("outcome_id",         sa.String(36), primary_key=True),
            sa.Column("deal_id",            sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="SET NULL")),
            sa.Column("loan_terms_id",      sa.String(36), sa.ForeignKey("loan_terms.loan_terms_id")),
            sa.Column("predicted_rating",   sa.String(30), nullable=False),
            sa.Column("predicted_at",       sa.DateTime(timezone=True), nullable=False),
            sa.Column("actual_outcome",     sa.String(30)),
            sa.Column("outcome_date",       sa.Date),
            sa.Column("loss_given_default", sa.Numeric(18, 2)),
            sa.Column("recorded_at",        sa.DateTime(timezone=True)),
        )

    # Seed current neural SLACR model version (idempotent)
    now_str = datetime.now(timezone.utc).isoformat()
    existing = bind.execute(
        text("SELECT model_id FROM model_versions WHERE model_name='neural_slacr' AND version='1.0.0'")
    ).fetchone()
    if not existing:
        bind.execute(
            text(
                "INSERT INTO model_versions "
                "(model_id, model_name, version, architecture, deployed_at, created_at) "
                "VALUES (:model_id, :model_name, :version, :architecture, :deployed_at, :created_at)"
            ),
            {
                "model_id": _NEURAL_SLACR_MODEL_ID,
                "model_name": "neural_slacr",
                "version": "1.0.0",
                "architecture": "neural_slacr",
                "deployed_at": now_str,
                "created_at": now_str,
            }
        )

    # Wire deferred FKs — silently skip if already present (SQLite batch mode)
    try:
        with op.batch_alter_table("slacr_scores") as batch_op:
            batch_op.create_foreign_key(
                "fk_slacr_model", "model_versions", ["model_id"], ["model_id"]
            )
    except Exception:
        pass

    try:
        with op.batch_alter_table("projection_assumptions") as batch_op:
            batch_op.create_foreign_key(
                "fk_proj_assumptions_model", "model_versions", ["model_id"], ["model_id"]
            )
    except Exception:
        pass


def downgrade() -> None:
    try:
        with op.batch_alter_table("projection_assumptions") as batch_op:
            batch_op.drop_constraint("fk_proj_assumptions_model", type_="foreignkey")
    except Exception:
        pass
    try:
        with op.batch_alter_table("slacr_scores") as batch_op:
            batch_op.drop_constraint("fk_slacr_model", type_="foreignkey")
    except Exception:
        pass

    op.drop_table("model_outcomes")
    op.drop_table("feature_store")
    op.drop_table("model_versions")
