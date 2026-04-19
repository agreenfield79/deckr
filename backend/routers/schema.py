"""
GET /api/schema — runtime schema introspection across all active DB stores.

Returns a structured payload describing the live schema for each store:
  sql:   table list with columns, types, PK, FK, and unique constraints
  neo4j: constraint/index Cypher statements from graph_models.CYPHER_SCHEMA
  mongo: active collection names
  chroma: ChromaDB collection names

All store sections degrade gracefully (return an error string) if the
store is offline or not installed, matching D-3 fail-silent convention.
"""

import logging
import os

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger("deckr.routers.schema")


@router.get("")
def get_schema():
    """Return live schema metadata for all configured database stores."""
    return {
        "storage_mode": os.getenv("STORAGE_BACKEND", "local"),
        "sql": _sql_schema(),
        "neo4j": _neo4j_schema(),
        "mongo": _mongo_schema(),
        "chroma": _chroma_schema(),
    }


# ---------------------------------------------------------------------------
# Per-store introspection helpers
# ---------------------------------------------------------------------------

def _sql_schema() -> list[dict]:
    """Inspect the live SQL engine and return table/column metadata."""
    try:
        from services.db_factory import get_sql_engine
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(get_sql_engine())
        tables = []
        for table_name in sorted(inspector.get_table_names()):
            columns = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "primary_key": bool(col.get("primary_key")),
                }
                for col in inspector.get_columns(table_name)
            ]
            pk = inspector.get_pk_constraint(table_name)
            fks = [
                {
                    "columns": fk["constrained_columns"],
                    "references": f"{fk['referred_table']}.{fk['referred_columns']}",
                }
                for fk in inspector.get_foreign_keys(table_name)
            ]
            uniques = [
                u["column_names"]
                for u in inspector.get_unique_constraints(table_name)
            ]
            tables.append({
                "table": table_name,
                "columns": columns,
                "primary_key": pk.get("constrained_columns", []),
                "foreign_keys": fks,
                "unique_constraints": uniques,
            })
        return tables
    except Exception as exc:
        logger.warning("SQL schema introspection failed: %s", exc)
        return [{"error": str(exc)}]


def _neo4j_schema() -> list[str]:
    """Return the Cypher schema statements defined in graph_models.CYPHER_SCHEMA."""
    try:
        from models.graph_models import CYPHER_SCHEMA
        return [
            line.strip()
            for line in CYPHER_SCHEMA.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
    except Exception as exc:
        logger.warning("Neo4j schema introspection failed: %s", exc)
        return [f"error: {exc}"]


def _mongo_schema() -> list[str]:
    """Return the names of all collections in the active MongoDB database."""
    try:
        from services.db_factory import get_mongo_db
        db = get_mongo_db()
        if db is None:
            return ["unavailable — MongoDB offline or not installed"]
        return sorted(db.list_collection_names())
    except Exception as exc:
        logger.warning("MongoDB schema introspection failed: %s", exc)
        return [f"error: {exc}"]


def _chroma_schema() -> list[str]:
    """Return the names of all ChromaDB collections."""
    try:
        from services.vector_service import _get_chroma
        client = _get_chroma()
        if client is None:
            return ["unavailable — ChromaDB offline or not installed"]
        return [c.name for c in client.list_collections()]
    except Exception as exc:
        logger.warning("ChromaDB schema introspection failed: %s", exc)
        return [f"error: {exc}"]
