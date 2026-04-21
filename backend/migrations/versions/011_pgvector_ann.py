"""011_pgvector_ann — ANN index on embeddings table (Cloud Track B only).

Revision: 011
Down-revision: 010

This migration creates an IVFFlat approximate-nearest-neighbour index on the
``embeddings.embedding`` column using pgvector's cosine operator class.

IMPORTANT — row-count gate:
  The IVFFlat index degrades for small tables (< 10,000 rows the centroid
  estimation is unreliable).  ``upgrade()`` checks the row count and skips
  index creation if the threshold is not yet met, printing a notice so the
  operator knows to re-run the migration once data volume grows.

Track A (SQLite) note:
  pgvector is not available in SQLite mode.  This migration is a no-op on
  SQLite and is intended only for the GCP Cloud SQL (PostgreSQL 15+) path.
  Run from the backend directory after connecting via Cloud SQL Auth Proxy:
      alembic upgrade head
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision      = "011"
down_revision = "010"
branch_labels = None
depends_on    = None

# Minimum row count before creating the IVFFlat index.
# Below this threshold centroid estimation is unreliable and the index
# adds overhead without benefit.  Per Phase 2 target schema (Section 2E).
_ANN_ROW_THRESHOLD = 10_000


def upgrade() -> None:
    bind = op.get_bind()

    # No-op on SQLite — pgvector is PostgreSQL-only.
    if bind.dialect.name != "postgresql":
        print(
            "[011_pgvector_ann] Skipping: dialect is "
            f"'{bind.dialect.name}' (PostgreSQL required for pgvector)."
        )
        return

    # Check current row count — skip if below threshold.
    result = bind.execute(sa.text("SELECT COUNT(*) FROM embeddings"))
    row_count = result.scalar() or 0
    if row_count < _ANN_ROW_THRESHOLD:
        print(
            f"[011_pgvector_ann] Skipping ANN index creation: "
            f"embeddings table has {row_count:,} rows "
            f"(threshold: {_ANN_ROW_THRESHOLD:,}). "
            "Re-run 'alembic upgrade head' once the table reaches the threshold."
        )
        return

    print(
        f"[011_pgvector_ann] Creating IVFFlat ANN index "
        f"({row_count:,} rows >= threshold {_ANN_ROW_THRESHOLD:,})."
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_embeddings_ann
        ON embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
    print("[011_pgvector_ann] ix_embeddings_ann created.")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_embeddings_ann")
