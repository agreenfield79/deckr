"""Step 4 — Create guarantees table.

Revision ID: 005
Revises: 004
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("guarantees"):
        op.create_table(
            "guarantees",
            sa.Column("guarantee_id",        sa.String(36), primary_key=True),
            sa.Column("deal_id",             sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="CASCADE"), nullable=False),
            sa.Column("guarantor_entity_id", sa.String(36), sa.ForeignKey("entities.entity_id", ondelete="CASCADE"), nullable=False),
            sa.Column("loan_terms_id",       sa.String(36), sa.ForeignKey("loan_terms.loan_terms_id")),
            sa.Column("guarantee_type",      sa.String(20), nullable=False),
            sa.Column("coverage_amount",     sa.Numeric(18, 2)),
            sa.Column("coverage_pct",        sa.Numeric(5, 4)),
            sa.Column("personal_net_worth",  sa.Numeric(18, 2)),
            sa.Column("liquid_assets",       sa.Numeric(18, 2)),
            sa.Column("executed_at",         sa.Date),
            sa.Column("expires_at",          sa.Date),
            sa.Column("created_at",          sa.DateTime(timezone=True)),
            sa.UniqueConstraint("deal_id", "guarantor_entity_id", name="uq_guarantee_deal_guarantor"),
        )
    inspector = inspect(bind)
    existing_ix = [idx["name"] for idx in inspector.get_indexes("guarantees")]
    if "ix_guarantees_deal_id" not in existing_ix:
        op.create_index("ix_guarantees_deal_id", "guarantees", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_guarantees_deal_id", "guarantees")
    op.drop_table("guarantees")
