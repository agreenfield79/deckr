"""Step 7 — Create Group H tables: users, sessions, deal_access.

These tables remain unused until auth is activated (Phase 10C).

Revision ID: 008
Revises: 007
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy import inspect
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("users"):
        op.create_table(
            "users",
            sa.Column("user_id",        sa.String(36), primary_key=True),
            sa.Column("email",          sa.String(255), unique=True, nullable=False),
            sa.Column("role",           sa.String(20), nullable=False),
            sa.Column("institution_id", sa.String(36)),
            sa.Column("password_hash",  sa.String(128)),
            sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_login",     sa.DateTime(timezone=True)),
            sa.Column("is_active",      sa.Boolean, server_default="1"),
        )

    if not insp.has_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("session_id",         sa.String(36), primary_key=True),
            sa.Column("user_id",            sa.String(36), sa.ForeignKey("users.user_id", ondelete="CASCADE")),
            sa.Column("issued_at",          sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at",         sa.DateTime(timezone=True), nullable=False),
            sa.Column("refresh_token_hash", sa.String(128)),
            sa.Column("revoked",            sa.Boolean, server_default="0"),
            sa.Column("ip_address",         sa.String(45)),
        )
    sessions_ix = [idx["name"] for idx in insp.get_indexes("sessions")] if insp.has_table("sessions") else []
    if "ix_sessions_user_id" not in sessions_ix:
        op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    if "ix_sessions_expires_at" not in sessions_ix:
        op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    if not insp.has_table("deal_access"):
        op.create_table(
            "deal_access",
            sa.Column("access_id",    sa.String(36), primary_key=True),
            sa.Column("user_id",      sa.String(36), sa.ForeignKey("users.user_id", ondelete="CASCADE")),
            sa.Column("deal_id",      sa.String(36), sa.ForeignKey("deals.deal_id", ondelete="CASCADE")),
            sa.Column("access_level", sa.String(10), nullable=False),
            sa.Column("granted_by",   sa.String(36), sa.ForeignKey("users.user_id")),
            sa.Column("granted_at",   sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "deal_id", name="uq_deal_access_user_deal"),
        )

    # Wire audit_log.user_id FK now that users exists
    try:
        with op.batch_alter_table("audit_log") as batch_op:
            batch_op.create_foreign_key(
                "fk_audit_log_user", "users", ["user_id"], ["user_id"]
            )
    except Exception:
        pass


def downgrade() -> None:
    try:
        with op.batch_alter_table("audit_log") as batch_op:
            batch_op.drop_constraint("fk_audit_log_user", type_="foreignkey")
    except Exception:
        pass

    op.drop_table("deal_access")
    try:
        op.drop_index("ix_sessions_expires_at", "sessions")
        op.drop_index("ix_sessions_user_id",    "sessions")
    except Exception:
        pass
    op.drop_table("sessions")
    op.drop_table("users")
