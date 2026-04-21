"""
embeddings_service.py — semantic workspace retrieval (Step 14.2 / 14.3)

Activated when ENABLE_EMBEDDINGS=true in .env.

Architecture:
  - Embedding model: ibm/slate-125m-english-rtrvr-v2 via watsonx REST API
    (same auth as watsonx_client.py — uses token_cache, no SDK version quirks)
  - Index: in-memory dict, persisted to backend/.deckr_embeddings.json
    (local file, never uploaded to COS, excluded from git)
  - Chunking: paragraph-boundary split, max ~1,200 chars (~400 tokens)
  - Search: cosine similarity, top-20 candidates
  - Re-ranking: keyword overlap fallback; cross-encoder if sentence-transformers
    installed (optional heavy dependency — graceful fallback)

Public API (used by agent_service):
  update_file(rel_path, text)         — called by workspace_service.write_file()
  get_relevant_context(query, folders) — replaces _load_context() when enabled
  embed_query(text)                   — single-text embedding for cross-service use

DISTINCT FROM: vector_service.py + ChromaDB, which indexes uploaded financial
  document chunks for ANN similarity search. This file indexes workspace .md
  files only and never reads from or writes to ChromaDB or the SQL embeddings
  table. The two systems share no index stores:
    embeddings_service.py  -> backend/.deckr_embeddings.json
    vector_service.py      -> backend/data/.chroma/
"""

import json
import logging
import math
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger("deckr.embeddings_service")

EMBEDDING_MODEL  = "ibm/slate-125m-english-rtrvr-v2"   # v1 deprecated 2025
MAX_CHUNK_CHARS  = 1_200   # ~400 tokens; model hard-cap is 512 tokens
TOP_K_SEARCH     = 20      # candidates retrieved by cosine similarity
TOP_N_RERANK     = 5       # final chunks after re-ranking

# Index cache next to the backend package — never included in COS or the workspace tree
_INDEX_FILE = Path(__file__).parent.parent / ".deckr_embeddings.json"

# In-memory index:
#   {rel_path: {"mtime": float, "chunks": [str], "embeddings": [[float]]}}
_INDEX: dict | None = None
_INDEX_DIRTY = False
# Tracks whether a COS bucket scan has been done this process lifetime.
# Reset to False on each server start so the first agent call picks up any
# newly extracted sidecars that were written to COS since last restart.
_COS_SYNCED = False


# ---------------------------------------------------------------------------
# Index I/O
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    if _INDEX_FILE.exists():
        try:
            data = json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
            _INDEX = data.get("files", {})
            logger.info("embeddings_service: index loaded (%d files)", len(_INDEX))
            return _INDEX
        except Exception as e:
            logger.warning("embeddings_service: index load failed (%s) — rebuilding", e)
    _INDEX = {}
    return _INDEX


def _save_index() -> None:
    global _INDEX_DIRTY
    if _INDEX is None:
        return
    try:
        _INDEX_FILE.write_text(
            json.dumps({"version": 1, "files": _INDEX}, ensure_ascii=False),
            encoding="utf-8",
        )
        _INDEX_DIRTY = False
        logger.debug("embeddings_service: index saved (%d files)", len(_INDEX))
    except Exception as e:
        logger.warning("embeddings_service: index save failed — %s", e)


# ---------------------------------------------------------------------------
# Embedding API — direct REST (consistent with watsonx_client.py)
# ---------------------------------------------------------------------------

def _embed(texts: list[str]) -> list[list[float]]:
    """
    Batch-embed texts via the watsonx /text/embeddings REST endpoint.
    Uses token_cache for IAM auth — same as watsonx_client.generate().
    IBM model max: 512 tokens / input, 1,000 inputs / request.
    """
    from services.token_cache import token_cache

    base_url  = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    api_ver   = os.getenv("WATSONX_API_VERSION", "2024-05-31")
    project   = os.getenv("WATSONX_PROJECT_ID")

    if not project:
        raise RuntimeError("WATSONX_PROJECT_ID must be set for embeddings")

    token = token_cache.get_token()
    url   = f"{base_url}/ml/v1/text/embeddings?version={api_ver}"
    body  = {
        "model_id":   EMBEDDING_MODEL,
        "inputs":     texts,
        "parameters": {"truncate_input_tokens": 512},
        "project_id": project,
    }

    t0 = time.time()
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    elapsed = int((time.time() - t0) * 1000)
    vectors = [r["embedding"] for r in resp.json()["results"]]
    logger.debug("embeddings_service._embed: %d texts, %dms", len(texts), elapsed)
    return vectors


def embed_query(text: str) -> list[float] | None:
    """
    Public single-text embedding helper for cross-service use.

    Wraps ``_embed([text])`` with D-3 error handling.  Returns the embedding
    vector as a flat ``list[float]``, or ``None`` if the call fails (e.g.
    watsonx unavailable, ``ENABLE_EMBEDDINGS=false``).

    Used by ``tool_service.search_documents`` to generate query embeddings
    for ``vector_service.similarity_search()`` (document chunk ANN search).
    Both systems use the same model (ibm/slate-125m-english-rtrvr-v2) so the
    vectors are compatible.
    """
    try:
        vectors = _embed([text])
        return vectors[0] if vectors else None
    except Exception as exc:
        logger.warning("embeddings_service.embed_query failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Split text into chunks at paragraph boundaries, capped at max_chars each.
    Falls back to hard character splits for single very-long paragraphs.
    Drops chunks shorter than 20 characters.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            if current:
                chunks.append(current.strip())
            if len(para) > max_chars:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i : i + max_chars].strip())
                current = ""
            else:
                current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if len(c) >= 20]


# ---------------------------------------------------------------------------
# Index build & update
# ---------------------------------------------------------------------------

def update_file(rel_path: str, text: str) -> None:
    """
    Update the embedding index for a single file after a write.
    Called by workspace_service.write_file() — no-op when ENABLE_EMBEDDINGS=false
    or for non-text sidecar files.
    """
    if os.getenv("ENABLE_EMBEDDINGS", "false").lower() != "true":
        return
    if rel_path.endswith((".extracted.json", ".embeddings.json")):
        return

    try:
        index  = _load_index()
        chunks = chunk_text(text)
        if not chunks:
            return

        t0         = time.time()
        embeddings = _embed(chunks)
        elapsed    = int((time.time() - t0) * 1000)

        index[rel_path] = {
            "mtime":      time.time(),
            "chunks":     chunks,
            "embeddings": embeddings,
        }
        global _INDEX_DIRTY
        _INDEX_DIRTY = True
        _save_index()

        logger.info(
            "embeddings_service: indexed %s — %d chunks, %dms",
            rel_path, len(chunks), elapsed,
        )
    except Exception as e:
        logger.error("embeddings_service: failed to index %s — %s", rel_path, e)


def remove_file(rel_path: str) -> None:
    """
    Evict a file's chunks from the in-memory index and persist the change.

    Called by workspace_service.delete_file() so that stale indexed content
    from deleted files cannot be returned to agents in future context lookups.
    Also removes the sidecar path variant (rel_path + ".extracted.json") if
    the index entry was stored under the source key (COS sidecar convention).
    No-op when ENABLE_EMBEDDINGS=false or the path is not in the index.
    """
    if os.getenv("ENABLE_EMBEDDINGS", "false").lower() != "true":
        return

    index = _load_index()
    removed = False

    for key in [rel_path, rel_path + ".extracted.json"]:
        if key in index:
            del index[key]
            removed = True
            logger.info("embeddings_service.remove_file: evicted %s", key)

    if removed:
        global _INDEX_DIRTY
        _INDEX_DIRTY = True
        _save_index()


def build_index(force: bool = False) -> int:
    """
    Build or refresh the embedding index.

    When USE_COS=true: scans the COS bucket for .extracted.json sidecars (PDF
    text) and plain text/markdown files, embedding any that are new or changed.

    When USE_COS=false: scans the local workspace directory instead.

    Binary files (PDF, xlsx, etc.) are always skipped — their text is available
    via extraction sidecars.  Returns number of files newly embedded.
    """
    index   = _load_index()
    use_cos = os.getenv("USE_COS", "false").lower() == "true"

    if use_cos:
        return _build_index_cos(index, force)
    return _build_index_local(index, force)


def _build_index_cos(index: dict, force: bool = False) -> int:
    """
    COS-aware index bootstrap.

    Walks the COS bucket under the workspace key prefix and embeds:
      - *.extracted.json sidecars  → indexed under the source file path
        (e.g. "Financials/10K-NVDA.pdf") so agent_service context filtering works
      - *.md / *.txt text files    → indexed under their relative path

    Timestamp-based deduplication skips objects already in the index whose
    COS LastModified hasn't changed since the last build.
    """
    try:
        from services import cos_service
        client = cos_service._get_client()
        bucket = cos_service._bucket()
        prefix = cos_service._workspace_root() + "/"   # e.g. "workspace_root/projects/default/"
    except Exception as e:
        logger.error("embeddings_service._build_index_cos: COS init failed — %s", e)
        return 0

    files_to_embed: list[tuple[str, str]] = []   # (display_rel_path, text)

    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel = key[len(prefix):]   # strip workspace prefix → workspace-relative path

                last_mod    = obj.get("LastModified")
                last_mod_ts = last_mod.timestamp() if last_mod else 0

                if rel.endswith(".extracted.json"):
                    # Index as the SOURCE file path (sans sidecar suffix)
                    source_rel = rel[: -len(".extracted.json")]
                    cached     = index.get(source_rel)
                    if not force and cached and cached.get("mtime", 0) >= last_mod_ts:
                        continue
                    try:
                        raw  = cos_service.read_file(rel)
                        data = json.loads(raw)
                        text = data.get("text", "")
                        if len(text.strip()) >= 20:
                            files_to_embed.append((source_rel, text))
                    except Exception as e:
                        logger.warning("embeddings_service._build_index_cos: sidecar %s — %s", rel, e)

                elif rel.endswith((".md", ".txt")):
                    cached = index.get(rel)
                    if not force and cached and cached.get("mtime", 0) >= last_mod_ts:
                        continue
                    try:
                        text = cos_service.read_file(rel)
                        if len(text.strip()) >= 20:
                            files_to_embed.append((rel, text))
                    except Exception as e:
                        logger.warning("embeddings_service._build_index_cos: text %s — %s", rel, e)

    except Exception as e:
        logger.error("embeddings_service._build_index_cos: bucket listing failed — %s", e)
        return 0

    if not files_to_embed:
        logger.debug("embeddings_service._build_index_cos: no new/changed files to embed")
        return 0

    logger.info("embeddings_service._build_index_cos: embedding %d file(s)", len(files_to_embed))
    processed = 0

    for rel_path, text in files_to_embed:
        chunks = chunk_text(text)
        if not chunks:
            continue
        try:
            embeddings = _embed(chunks)
            index[rel_path] = {
                "mtime":      time.time(),
                "chunks":     chunks,
                "embeddings": embeddings,
            }
            processed += 1
            logger.info(
                "embeddings_service._build_index_cos: indexed %s (%d chunks)",
                rel_path, len(chunks),
            )
        except Exception as e:
            logger.error("embeddings_service._build_index_cos: %s — %s", rel_path, e)

    if processed > 0:
        _save_index()

    logger.info("embeddings_service._build_index_cos: %d file(s) newly indexed", processed)
    return processed


def _build_index_local(index: dict, force: bool = False) -> int:
    """Local-filesystem index build (used when USE_COS=false)."""
    from services import workspace_service

    root = workspace_service._get_root()

    _SKIP_SUFFIXES = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc",
                      ".png", ".jpg", ".jpeg", ".gif", ".zip"}

    files_to_embed: list[tuple[str, str]] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        if file_path.name.endswith((".extracted.json", ".embeddings.json")):
            continue

        rel   = str(file_path.relative_to(root)).replace("\\", "/")
        mtime = file_path.stat().st_mtime

        cached = index.get(rel)
        if not force and cached and cached.get("mtime", 0) >= mtime:
            continue

        try:
            text = file_path.read_text(encoding="utf-8")
            if len(text.strip()) < 20:
                continue
            files_to_embed.append((rel, text))
        except (UnicodeDecodeError, OSError):
            continue

    if not files_to_embed:
        logger.debug("embeddings_service.build_index: no new/changed files")
        return 0

    logger.info("embeddings_service.build_index: embedding %d file(s)", len(files_to_embed))
    processed = 0

    for rel_path, text in files_to_embed:
        chunks = chunk_text(text)
        if not chunks:
            continue
        try:
            embeddings = _embed(chunks)
            index[rel_path] = {
                "mtime":      time.time(),
                "chunks":     chunks,
                "embeddings": embeddings,
            }
            processed += 1
            logger.info(
                "embeddings_service.build_index: indexed %s (%d chunks)",
                rel_path, len(chunks),
            )
        except Exception as e:
            logger.error("embeddings_service.build_index: %s — %s", rel_path, e)

    if processed > 0:
        _save_index()

    return processed


# ---------------------------------------------------------------------------
# Search & re-ranking
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_score(query: str, text: str) -> float:
    """Lightweight keyword overlap — fallback re-ranker when cross-encoder unavailable."""
    terms     = set(query.lower().split())
    text_low  = text.lower()
    if not terms:
        return 0.0
    return sum(1 for t in terms if t in text_low) / len(terms)


def search(query: str, context_folders: list[str], top_k: int = TOP_K_SEARCH) -> list[dict]:
    """
    Embed the query and return top-k chunks by cosine similarity across relevant files.
    Returns a list of dicts: {file, chunk_idx, text, cosine_score}.
    """
    index = _load_index()
    if not index:
        return []

    # Determine the set of relevant files from context_folders
    if "all" in context_folders:
        relevant = set(index.keys())
    else:
        relevant = set()
        for folder in context_folders:
            folder_norm = folder.rstrip("/")
            for rel in index:
                if rel.startswith(folder_norm + "/") or rel == folder_norm:
                    relevant.add(rel)

    if not relevant:
        return []

    # Embed the query
    try:
        query_vec = _embed([query])[0]
    except Exception as e:
        logger.error("embeddings_service.search: query embed failed — %s", e)
        return []

    # Score all chunks
    candidates: list[dict] = []
    for rel_path in relevant:
        entry      = index.get(rel_path, {})
        chunks     = entry.get("chunks", [])
        embeddings = entry.get("embeddings", [])
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            candidates.append({
                "file":         rel_path,
                "chunk_idx":    i,
                "text":         chunk,
                "cosine_score": _cosine_similarity(query_vec, emb),
            })

    candidates.sort(key=lambda c: c["cosine_score"], reverse=True)
    return candidates[:top_k]


def rerank(query: str, candidates: list[dict], top_n: int = TOP_N_RERANK) -> list[dict]:
    """
    Re-rank candidates with a cross-encoder (sentence-transformers) when available,
    or with combined cosine + keyword overlap as a lightweight fallback.
    """
    if not candidates:
        return []

    # Optional: sentence-transformers cross-encoder (not in requirements.txt — user installs separately)
    try:
        from sentence_transformers import CrossEncoder
        enc    = CrossEncoder("cross-encoder/ms-marco-minilm-l-12-v2")
        pairs  = [[query, c["text"]] for c in candidates]
        scores = enc.predict(pairs)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        logger.debug("embeddings_service.rerank: cross-encoder (%d→%d)", len(candidates), top_n)
        return candidates[:top_n]
    except ImportError:
        pass   # sentence-transformers not installed — use keyword fallback
    except Exception as e:
        logger.warning("embeddings_service.rerank: cross-encoder failed (%s) — keyword fallback", e)

    # Keyword overlap fallback
    for c in candidates:
        c["rerank_score"] = 0.7 * c["cosine_score"] + 0.3 * _keyword_score(query, c["text"])
    candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
    logger.debug("embeddings_service.rerank: keyword fallback (%d→%d)", len(candidates), top_n)
    return candidates[:top_n]


# ---------------------------------------------------------------------------
# Main public API for agent_service
# ---------------------------------------------------------------------------

def get_relevant_context(query: str, context_folders: list[str]) -> str:
    """
    Retrieve and re-rank the most relevant workspace chunks for a query.

    Triggers build_index() when:
      - The in-memory index is empty (first ever call, or after cache delete)
      - USE_COS=true and no COS scan has been done this process lifetime
        (ensures newly extracted COS sidecars are picked up after each restart)

    Returns a formatted multi-file context string for injection into agent prompts,
    or a sentinel string when no documents are found.
    """
    global _COS_SYNCED
    index   = _load_index()
    use_cos = os.getenv("USE_COS", "false").lower() == "true"

    # Rebuild when index is empty OR when running COS mode and haven't synced yet
    if not index or (use_cos and not _COS_SYNCED):
        built = build_index()
        _COS_SYNCED = True   # mark done for this process lifetime
        if not _load_index():
            logger.info("embeddings_service: no files to index — returning empty context")
            return "[No workspace documents found]"

    candidates = search(query, context_folders)
    if not candidates:
        logger.info("embeddings_service: no relevant chunks found for query (len=%d)", len(query))
        return "[No relevant workspace documents found]"

    top = rerank(query, candidates)

    # Group retrieved chunks by source file for a clean prompt format
    grouped: dict[str, list[str]] = {}
    for item in top:
        grouped.setdefault(item["file"], []).append(item["text"])

    parts = [
        f"--- FILE: {rel_path} ---\n" + "\n\n".join(chunks)
        for rel_path, chunks in grouped.items()
    ]
    context = "\n\n".join(parts)

    logger.info(
        "embeddings_service: %d chunks from %d files returned (query_len=%d)",
        len(top), len(grouped), len(query),
    )
    return context
