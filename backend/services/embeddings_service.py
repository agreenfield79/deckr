"""
embeddings_service.py — semantic workspace retrieval (Step 14.2 / 14.3)

Activated when ENABLE_EMBEDDINGS=true in .env.

Architecture:
  - Embedding model: ibm/slate-125m-english-rtrvr via watsonx REST API
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
"""

import json
import logging
import math
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger("deckr.embeddings_service")

EMBEDDING_MODEL  = "ibm/slate-125m-english-rtrvr"
MAX_CHUNK_CHARS  = 1_200   # ~400 tokens; model hard-cap is 512 tokens
TOP_K_SEARCH     = 20      # candidates retrieved by cosine similarity
TOP_N_RERANK     = 5       # final chunks after re-ranking

# Index cache next to the backend package — never included in COS or the workspace tree
_INDEX_FILE = Path(__file__).parent.parent / ".deckr_embeddings.json"

# In-memory index:
#   {rel_path: {"mtime": float, "chunks": [str], "embeddings": [[float]]}}
_INDEX: dict | None = None
_INDEX_DIRTY = False


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


def build_index(force: bool = False) -> int:
    """
    Scan all local workspace text files and embed any that are new or modified.
    Skips binary files (PDF, xlsx, etc.) — they must go through extraction first.
    Returns number of files newly embedded.
    """
    from services import workspace_service

    root  = workspace_service._get_root()
    index = _load_index()

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
            continue   # up to date

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

    Lazily triggers build_index() on first call when the in-memory index is empty
    so that the context is always populated even before any file write hooks fire.

    Returns a formatted multi-file context string for injection into agent prompts,
    or a sentinel string when no documents are found.
    """
    index = _load_index()

    # Lazy rebuild on first call or if index is empty
    if not index:
        built = build_index()
        if built == 0 and not index:
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
