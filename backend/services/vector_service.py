"""
Vector Service — ChromaDB (local) / pgvector (cloud).

Local mode: ChromaDB persists to backend/data/.chroma/
Cloud mode: pgvector via SQLAlchemy Embeddings table (see sql_models.py)
D-3: all operations catch exceptions and return empty results.
"""

import logging
import os

logger = logging.getLogger("deckr.vector_service")

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
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
                     embedding: list[float], model_name: str = "ibm/slate-125m-english-rtrvr",
                     metadata: dict | None = None) -> bool:
    """
    Local: stores in ChromaDB.
    Cloud: insert into SQL Embeddings table (pgvector handles ANN search).
    """
    if STORAGE_BACKEND == "cloud":
        return _upsert_pgvector(document_id, chunk_index, chunk_text, embedding, model_name)
    return _upsert_chroma(document_id, chunk_index, chunk_text, embedding, metadata or {})


def _upsert_chroma(document_id: str, chunk_index: int, chunk_text: str,
                   embedding: list[float], metadata: dict) -> bool:
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
                     embedding: list[float], model_name: str) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Embedding
        from uuid import uuid4
        from datetime import datetime, timezone
        with next(get_sql_session()) as session:
            session.add(Embedding(
                embedding_id=str(uuid4()),
                document_id=document_id,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
                model_name=model_name,
                created_at=datetime.now(timezone.utc),
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
                      where: dict | None = None) -> list[dict]:
    """
    Local: ChromaDB ANN search.
    Cloud: pgvector cosine similarity (not yet implemented — returns empty list).
    """
    if STORAGE_BACKEND == "cloud":
        logger.warning("pgvector similarity_search not yet implemented")
        return []
    try:
        col = _collection()
        if col is None:
            return []
        kwargs: dict = {"query_embeddings": [query_embedding], "n_results": n_results}
        if where:
            kwargs["where"] = where
        result = col.query(**kwargs)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            {"text": d, "metadata": m, "distance": dist}
            for d, m, dist in zip(docs, metas, distances)
        ]
    except Exception as exc:
        logger.warning("similarity_search failed: %s", exc)
        return []
