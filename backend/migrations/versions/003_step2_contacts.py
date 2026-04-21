"""Step 2 — Create contacts table.

Revision ID: 003
Revises: 002
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("contacts"):
        op.create_table(
            "contacts",
            sa.Column("contact_id",   sa.String(36), primary_key=True),
            sa.Column("entity_id",    sa.String(36), sa.ForeignKey("entities.entity_id", ondelete="CASCADE")),
            sa.Column("deal_id",      sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="CASCADE")),
            sa.Column("name",         sa.String(255), nullable=False),
            sa.Column("title",        sa.String(100)),
            sa.Column("email",        sa.String(255)),
            sa.Column("phone",        sa.String(30)),
            sa.Column("contact_type", sa.String(30), nullable=False),
            sa.Column("created_at",   sa.DateTime(timezone=True)),
        )
    # Indexes are idempotent — create only if missing
    inspector = inspect(bind)
    existing_ix = [idx["name"] for idx in inspector.get_indexes("contacts")]
    if "ix_contacts_deal_id" not in existing_ix:
        op.create_index("ix_contacts_deal_id", "contacts", ["deal_id"])
    if "ix_contacts_entity_id" not in existing_ix:
        op.create_index("ix_contacts_entity_id", "contacts", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_entity_id", "contacts")
    op.drop_index("ix_contacts_deal_id",   "contacts")
    op.drop_table("contacts")
