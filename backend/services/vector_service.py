"""
Vector Service — ChromaDB (local) / pgvector (cloud).

Local mode:  ChromaDB persists to backend/data/.chroma/
Cloud mode:  pgvector via SQLAlchemy Embeddings table (see sql_models.py)
D-3: all operations catch exceptions and return empty results / False.

Two separate embedding systems — do NOT conflate:
  vector_service.py  (this file) — document chunk ANN search from uploaded PDFs.
  embeddings_service.py          — workspace .md file semantic retrieval for agents.
"""

import logging
import os

logger = logging.getLogger("deckr.vector_service")

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()

# Required ChromaDB metadata fields per Phase 2 target schema (Section 2E).
_REQUIRED_META_FIELDS = ("deal_id", "entity_id", "document_type", "page_number", "chunk_type")

_chroma_client = None


def _get_chroma():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    try:
        import chromadb
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data", ".chroma")
        os.makedirs(data_dir, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=data_dir)
        logger.info("ChromaDB initialized at %s", data_dir)
        return _chroma_client
    except ImportError:
        logger.warning("chromadb not installed — vector search unavailable")
        return None
    except Exception as exc:
        logger.warning("ChromaDB init failed: %s", exc)
        return None


def _collection(name: str = "deckr_embeddings"):
    client = _get_chroma()
    if client is None:
        return None
    try:
        return client.get_or_create_collection(name)
    except Exception as exc:
        logger.warning("ChromaDB get_or_create_collection failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def upsert_embedding(document_id: str, chunk_index: int, chunk_text: str,
                     embedding: list[float],
                     model_name: str = "ibm/slate-125m-english-rtrvr-v2",
                     metadata: dict | None = None) -> bool:
    """
    Upsert a document chunk embedding.

    Local:  stores in ChromaDB (`deckr_embeddings` collection).
    Cloud:  inserts into SQL `embeddings` table (pgvector ANN search).

    ``metadata`` must contain: deal_id, entity_id, document_type,
    page_number, chunk_type.  Missing fields are warned but not raised (D-3).
    """
    if STORAGE_BACKEND == "cloud":
        return _upsert_pgvector(document_id, chunk_index, chunk_text,
                                embedding, model_name, metadata or {})
    return _upsert_chroma(document_id, chunk_index, chunk_text, embedding, metadata or {})


def _upsert_chroma(document_id: str, chunk_index: int, chunk_text: str,
                   embedding: list[float], metadata: dict) -> bool:
    # D-3 field enforcement — warn on missing or None required fields, do not raise.
    missing = [f for f in _REQUIRED_META_FIELDS if metadata.get(f) is None]
    if missing:
        logger.warning(
            "ChromaDB upsert: missing/None required metadata fields %s for document_id=%s",
            missing, document_id,
        )
    try:
        col = _collection()
        if col is None:
            return False
        doc_id = f"{document_id}_{chunk_index}"
        meta = {"document_id": document_id, "chunk_index": chunk_index, **metadata}
        col.upsert(ids=[doc_id], embeddings=[embedding],
                   documents=[chunk_text], metadatas=[meta])
        return True
    except Exception as exc:
        logger.warning("ChromaDB upsert failed: %s", exc)
        return False


def _upsert_pgvector(document_id: str, chunk_index: int, chunk_text: str,
                     embedding: list[float], model_name: str,
                     metadata: dict | None = None) -> bool:
    """
    Cloud path — insert into SQL `embeddings` table.
    Writes deal_id, entity_id, document_type from metadata dict (Phase 3F.2).
    """
    meta = metadata or {}
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Embedding
        from uuid import uuid4
        from datetime import datetime, timezone
        with next(get_sql_session()) as session:
            session.add(Embedding(
                embedding_id  = str(uuid4()),
                document_id   = document_id,
                chunk_index   = chunk_index,
                chunk_text    = chunk_text,
                model_name    = model_name,
                deal_id       = meta.get("deal_id"),
                entity_id     = meta.get("entity_id"),
                document_type = meta.get("document_type"),
                created_at    = datetime.now(timezone.utc),
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("pgvector upsert failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def similarity_search(query_embedding: list[float], n_results: int = 5,
                      where: dict | None = None,
                      deal_id: str | None = None) -> list[dict]:
    """
    ANN similarity search.

    Local:  ChromaDB.
    Cloud:  pgvector cosine similarity with optional deal_id scoping.

    ``deal_id`` is a convenience parameter: when provided, it is merged into
    the ``where`` dict as ``{"deal_id": deal_id}``.  The caller may also pass
    ``where`` directly for compound filters.
    """
    # Build effective where clause — deal_id shortcut merged with any explicit where.
    # ChromaDB requires compound filters to use the $and operator (flat multi-key dicts
    # are invalid and raise ValueError at query time).
    effective_where: dict | None = None
    if deal_id and where:
        # Merge: convert existing single-key where + deal_id into a $and compound filter.
        combined = [{"deal_id": {"$eq": deal_id}}]
        for k, v in where.items():
            combined.append({k: v if isinstance(v, dict) else {"$eq": v}})
        effective_where = {"$and": combined}
    elif deal_id:
        effective_where = {"deal_id": {"$eq": deal_id}}
    elif where:
        effective_where = where

    if STORAGE_BACKEND == "cloud":
        return _similarity_search_pgvector(query_embedding, n_results, effective_where)
    return _similarity_search_chroma(query_embedding, n_results, effective_where)


def _similarity_search_chroma(query_embedding: list[float], n_results: int,
                               where: dict | None) -> list[dict]:
    try:
        col = _collection()
        if col is None:
            return []
        kwargs: dict = {"query_embeddings": [query_embedding], "n_results": n_results}
        if where:
            kwargs["where"] = where
        result = col.query(**kwargs)
        docs      = result.get("documents", [[]])[0]
        metas     = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            {"text": d, "metadata": m, "distance": dist}
            for d, m, dist in zip(docs, metas, distances)
        ]
    except Exception as exc:
        logger.warning("ChromaDB similarity_search failed: %s", exc)
        return []


def _similarity_search_pgvector(query_embedding: list[float], n_results: int,
                                 where: dict | None) -> list[dict]:
    """
    pgvector cosine similarity search with optional deal_id scoping.
    Uses raw SQL so the vector <-> operator is available regardless of
    SQLAlchemy version.
    """
    try:
        from services.db_factory import get_sql_session
        import sqlalchemy as sa

        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        sql = (
            "SELECT chunk_text, document_id, chunk_index, deal_id, entity_id, "
            "       document_type, model_name, "
            "       embedding <-> CAST(:vec AS vector) AS distance "
            "FROM embeddings "
        )
        params: dict = {"vec": vec_str, "limit": n_results}
        if where and where.get("deal_id"):
            sql += "WHERE deal_id = :deal_id "
            params["deal_id"] = where["deal_id"]
        sql += "ORDER BY distance LIMIT :limit"

        with next(get_sql_session()) as session:
            rows = session.execute(sa.text(sql), params).fetchall()

        return [
            {
                "text": r.chunk_text,
                "metadata": {
                    "document_id":   r.document_id,
                    "chunk_index":   r.chunk_index,
                    "deal_id":       r.deal_id,
                    "entity_id":     r.entity_id,
                    "document_type": r.document_type,
                    "model_name":    r.model_name,
                },
                "distance": r.distance,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("pgvector similarity_search failed: %s", exc)
        return []
