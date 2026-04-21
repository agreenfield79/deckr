"""Step 3 — Create benchmarks table.

Revision ID: 004
Revises: 003
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("benchmarks"):
        op.create_table(
            "benchmarks",
            sa.Column("benchmark_id",  sa.String(36), primary_key=True),
            sa.Column("naics_code",    sa.String(10), nullable=False),
            sa.Column("metric_name",   sa.String(50), nullable=False),
            sa.Column("percentile_25", sa.Numeric(10, 4)),
            sa.Column("percentile_50", sa.Numeric(10, 4)),
            sa.Column("percentile_75", sa.Numeric(10, 4)),
            sa.Column("source",        sa.String(100)),
            sa.Column("as_of_year",    sa.Integer),
            sa.Column("created_at",    sa.DateTime(timezone=True)),
            sa.UniqueConstraint("naics_code", "metric_name", "as_of_year",
                                name="uq_benchmark_naics_metric_year"),
        )
    inspector = inspect(bind)
    existing_ix = [idx["name"] for idx in inspector.get_indexes("benchmarks")]
    if "ix_benchmarks_naics" not in existing_ix:
        op.create_index("ix_benchmarks_naics", "benchmarks", ["naics_code"])
    if "ix_benchmarks_metric" not in existing_ix:
        op.create_index("ix_benchmarks_metric", "benchmarks", ["metric_name"])


def downgrade() -> None:
    op.drop_index("ix_benchmarks_metric", "benchmarks")
    op.drop_index("ix_benchmarks_naics",  "benchmarks")
    op.drop_table("benchmarks")
