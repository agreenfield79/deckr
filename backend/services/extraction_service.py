"""
extraction_service.py — document text extraction (Step 14.1)

Activated when ENABLE_EXTRACTION=true in .env.

Supported file types:
  - PDF  → text extracted via pypdf (local bytes, no watsonx API call)
  - .txt / .md / .csv / .tsv → decoded directly from bytes

Sidecar format: {relative_path}.extracted.json
  {"source_path": "...", "text": "...", "char_count": N}
  Written to the same storage backend as the source file (local or COS).

The upload router passes raw content bytes so this service never needs to
re-read the file from storage on the happy path.
"""

import io
import json
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger("deckr.extraction_service")

_EXTRACTABLE_TEXT_EXT = {".txt", ".md", ".csv", ".tsv"}


def extract_document(relative_path: str, content: bytes | None = None) -> str | None:
    """
    Extract plain text from a document and persist a JSON sidecar.

    Args:
        relative_path: workspace-relative path (e.g. "Financials/report.pdf").
                       Determines file type and sidecar write destination.
        content:       raw file bytes — pass directly from upload router to avoid
                       a redundant re-read from disk or COS.

    Returns:
        Relative path of the sidecar file on success, or None if extraction is
        disabled, file type unsupported, or no text was found.
    """
    if os.getenv("ENABLE_EXTRACTION", "false").lower() != "true":
        return None

    ext = Path(relative_path).suffix.lower()
    text: str | None = None

    if ext == ".pdf":
        if content is None:
            content = _read_content(relative_path)
        if content:
            text = _extract_pdf(content)

    elif ext in _EXTRACTABLE_TEXT_EXT:
        if content is None:
            content = _read_content(relative_path)
        if content:
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1", errors="replace")

    else:
        logger.debug("extraction: unsupported type %s — %s", ext, relative_path)
        return None

    if not text or len(text.strip()) < 10:
        logger.warning("extraction: no usable text extracted from %s", relative_path)
        return None

    sidecar_rel = relative_path + ".extracted.json"
    sidecar_data = {
        "source_path": relative_path,
        "text": text.strip(),
        "char_count": len(text),
    }
    sidecar_json = json.dumps(sidecar_data, ensure_ascii=False, indent=2)

    # Write sidecar to the same storage backend as the source file
    use_cos = os.getenv("USE_COS", "false").lower() == "true"
    if use_cos:
        try:
            from services import cos_service
            cos_service.write_file(sidecar_rel, sidecar_json)
        except Exception as e:
            logger.error("extraction: COS sidecar write failed — %s", e)
            return None
    else:
        from services import workspace_service
        workspace_service.write_file(sidecar_rel, sidecar_json)

    logger.info(
        "extraction: %s → %d chars extracted, sidecar written to %s",
        relative_path, len(text), sidecar_rel,
    )

    # Push extracted text into the embeddings index immediately so the very
    # next agent call can retrieve it without waiting for a full COS rebuild.
    if os.getenv("ENABLE_EMBEDDINGS", "false").lower() == "true":
        try:
            from services import embeddings_service
            embeddings_service.update_file(relative_path, text.strip())
        except Exception as e:
            logger.debug("extraction: embeddings update skipped — %s", e)

    return sidecar_rel


def get_extracted_text(file_path: str) -> str | None:
    """
    Read {file_path}.extracted.json and return the plain text if it exists.

    Accepts an absolute local filesystem path (as produced by _load_context's
    Path.rglob() calls in agent_service.py).  Checks local disk first, then
    falls back to COS when USE_COS=true.

    Returns None (not an exception) when no sidecar is found — the caller
    then falls through to raw UTF-8 text reading.
    """
    sidecar_local = Path(file_path + ".extracted.json")

    # Fast path: local sidecar on disk
    if sidecar_local.exists():
        try:
            data = json.loads(sidecar_local.read_text(encoding="utf-8"))
            # Try multiple text keys — "text" is canonical, but "content" and
            # "raw_text" are acceptable alternates. Structured financial sidecars
            # (e.g. extracted_data.json) have no text key and return None, which
            # tells chunk_and_index_document to skip silently (correct behaviour).
            text = data.get("text") or data.get("content") or data.get("raw_text")
            if text and isinstance(text, str):
                return text
            logger.debug(
                "extraction.get_extracted_text: sidecar %s has no text key — skipping chunking",
                sidecar_local.name,
            )
            return None
        except Exception as e:
            logger.warning("extraction.get_extracted_text: local read failed — %s", e)

    # COS fallback: convert absolute path → workspace-relative key
    if os.getenv("USE_COS", "false").lower() == "true":
        try:
            from services import workspace_service, cos_service
            root = workspace_service._get_root()
            try:
                rel = str(Path(file_path).relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = Path(file_path).name
            sidecar_rel = rel + ".extracted.json"
            sidecar_content = cos_service.read_file(sidecar_rel)
            data = json.loads(sidecar_content)
            text = data.get("text") or data.get("content") or data.get("raw_text")
            if text and isinstance(text, str):
                return text
        except Exception:
            pass  # sidecar does not exist — normal for files not yet extracted

    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_content(relative_path: str) -> bytes | None:
    """Read file bytes from COS or local disk."""
    use_cos = os.getenv("USE_COS", "false").lower() == "true"
    if use_cos:
        try:
            from services import cos_service
            return cos_service.read_binary(relative_path)
        except Exception as e:
            logger.warning("extraction._read_content: COS read failed — %s", e)
            return None
    else:
        from services import workspace_service
        local_path = workspace_service.resolve_path(relative_path)
        if local_path.exists():
            return local_path.read_bytes()
        return None


def _extract_pdf(content: bytes) -> str | None:
    """
    Extract text from PDF bytes.

    Three-pass extraction:
      Pass 1 — pypdf         (fast; works on most standard text PDFs)
      Pass 2 — pdfminer.six  (better layout analysis and font encoding handling)
      Pass 3 — PyMuPDF/fitz  (MuPDF engine; handles compressed streams, CJK, custom encodings)

    If all three return empty, the PDF is almost certainly image-based (scanned)
    and will require OCR — planned for Phase 15 via watsonx Document Understanding.
    """
    # --- Pass 1: pypdf (fast) ---
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        if text:
            return text
        logger.debug("extraction._extract_pdf: pypdf found no text — trying pdfminer fallback")
    except ImportError:
        pass
    except Exception as e:
        logger.debug("extraction._extract_pdf: pypdf failed (%s) — trying pdfminer fallback", e)

    # --- Pass 2: pdfminer.six (better at complex layouts and unusual font encoding) ---
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(io.BytesIO(content))
        if text and text.strip():
            return text.strip()
        logger.debug("extraction._extract_pdf: pdfminer found no text — trying PyMuPDF fallback")
    except ImportError:
        logger.debug("extraction: pdfminer.six not installed — skipping pass 2")
    except Exception as e:
        logger.debug("extraction._extract_pdf: pdfminer error (%s) — trying PyMuPDF fallback", e)

    # --- Pass 3: PyMuPDF / fitz (MuPDF engine — handles compressed streams, CJK, custom encodings) ---
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=content, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        if text:
            return text
        logger.warning(
            "extraction._extract_pdf: all three local extractors found no text — "
            "PDF is likely image-based (scanned). Attempting WDU OCR (Pass 4)."
        )
    except ImportError:
        logger.warning(
            "extraction._extract_pdf: PyMuPDF not installed — run: pip install pymupdf. "
            "Falling through to WDU OCR pass."
        )
    except Exception as e:
        logger.error("extraction._extract_pdf: PyMuPDF error — %s", e)

    # --- Pass 4: IBM watsonx Document Understanding (OCR for scanned / image-based PDFs) ---
    # Triggered only when ENABLE_WDU=true and all three local passes returned empty.
    # Verify exact endpoint at provisioning time against the WDU API reference:
    #   POST {WDU_URL}/v2/analyze   (Bearer IAM token auth)
    if os.getenv("ENABLE_WDU", "false").lower() != "true":
        logger.warning(
            "extraction._extract_pdf: all extractors exhausted and ENABLE_WDU=false. "
            "PDF is unextractable without OCR. Set ENABLE_WDU=true after provisioning WDU."
        )
        return None

    wdu_url = os.getenv("WDU_URL", "").rstrip("/")
    wdu_key = os.getenv("WDU_API_KEY", "")
    if not wdu_url or not wdu_key:
        logger.error(
            "extraction._extract_pdf: ENABLE_WDU=true but WDU_URL or WDU_API_KEY not set."
        )
        return None

    try:
        from services.token_cache import TokenCache
        _wdu_token_cache = TokenCache(api_key_env_var="WDU_API_KEY")
        token = _wdu_token_cache.get_token()

        endpoint = f"{wdu_url}/v2/analyze"
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/pdf",
            },
            data=content,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # Parse elements array — WDU returns text spans and table cells
        parts: list[str] = []
        for element in data.get("elements", []):
            text_val = element.get("text", "")
            if text_val and text_val.strip():
                parts.append(text_val.strip())

        text = "\n".join(parts).strip()
        if text:
            logger.info(
                "extraction._extract_pdf: WDU OCR pass 4 extracted %d chars", len(text)
            )
            return text

        logger.warning(
            "extraction._extract_pdf: WDU OCR returned no text — "
            "document may be fully graphical or encrypted."
        )
        return None

    except Exception as e:
        logger.error("extraction._extract_pdf: WDU OCR pass 4 failed — %s", e)
        return None


# ---------------------------------------------------------------------------
# Canonical Chunker — 3E.5
# 1,200 char max per chunk, split on paragraph boundaries (\n\n).
# Falls back to hard-split if no paragraph boundary exists in the window.
# ---------------------------------------------------------------------------

_CHUNK_MAX_CHARS = 1_200


def _chunk_text(text: str) -> list[str]:
    """
    Split text into chunks of at most _CHUNK_MAX_CHARS characters.
    Prefers paragraph boundaries (\n\n); falls back to hard split.
    Returns a list of non-empty stripped chunk strings.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) <= _CHUNK_MAX_CHARS:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # Para itself may be longer than limit — hard-split it
            while len(para) > _CHUNK_MAX_CHARS:
                chunks.append(para[:_CHUNK_MAX_CHARS])
                para = para[_CHUNK_MAX_CHARS:]
            current = para
    if current:
        chunks.append(current)
    return chunks


def chunk_and_index_document(
    relative_path: str,
    document_id: str,
    deal_id: str,
    entity_id: str,
    document_type: str | None = None,
) -> int:
    """
    Read the extracted text sidecar for ``relative_path``, chunk it with the
    canonical chunker, persist each chunk to MongoDB (document_chunks), and
    upsert the embedding into the vector store.

    Returns the number of chunks written. Returns 0 (not an exception) on any
    failure — D-3 pattern.

    Callers
    -------
    * ``extraction_persistence_service.seed()`` (IP1) — called once per
      uploaded document after extraction is confirmed.
    * Any backfill script processing existing deals.
    """
    if not (document_id and deal_id and entity_id):
        logger.warning(
            "chunk_and_index_document: missing context — doc=%s deal=%s entity=%s — skipping",
            document_id, deal_id, entity_id,
        )
        return 0

    text = get_extracted_text(relative_path)
    if not text:
        logger.debug("chunk_and_index_document: no extracted text for %s — skipping", relative_path)
        return 0

    file_name = Path(relative_path).name
    # chunk_type describes content structure ("paragraph", "table", "header", "footnote").
    # The plain-text chunker only produces paragraph splits — other values require a
    # structured PDF block parser (out of scope).
    # document_type describes the file category ("bank_statement", "tax_return", "10k", etc.)
    # and must retain the original caller value, not be coerced to a content-structure term.
    _CHUNK_STRUCTURE_TYPES = ("paragraph", "table", "header", "footnote")
    chunk_type_val    = document_type if document_type in _CHUNK_STRUCTURE_TYPES else "paragraph"
    document_type_val = document_type or "other"
    chunks            = _chunk_text(text)
    written           = 0

    try:
        from services import mongo_service as _mongo_ch
        from services import vector_service as _vec_ch
    except Exception as exc:
        logger.warning("chunk_and_index_document: import failed — %s", exc)
        return 0

    for idx, chunk_text in enumerate(chunks):
        # MongoDB — document_chunks
        try:
            _mongo_ch.save_document_chunk(
                document_id  = document_id,
                deal_id      = deal_id,
                entity_id    = entity_id,
                file_name    = file_name,
                page_number  = None,
                chunk_index  = idx,
                chunk_type   = chunk_type_val,
                text         = chunk_text,
            )
        except Exception as exc:
            logger.warning(
                "chunk_and_index_document: save_document_chunk failed idx=%d — %s", idx, exc
            )
            continue

        # Vector store embedding — D-3: fail-silent
        try:
            from services import embeddings_service as _emb_svc
            embedding_vectors = _emb_svc._embed([chunk_text])
            embedding = embedding_vectors[0] if embedding_vectors else None
            if embedding:
                _vec_ch.upsert_embedding(
                    document_id  = document_id,
                    chunk_index  = idx,
                    chunk_text   = chunk_text,
                    embedding    = embedding,
                    metadata     = {
                        "deal_id":       deal_id or "",
                        "entity_id":     entity_id or "",
                        "document_type": document_type_val,
                        "page_number":   0,   # sentinel: page unknown (plain-text extraction)
                        "chunk_type":    chunk_type_val,
                    },
                )
        except Exception as exc:
            logger.warning(
                "chunk_and_index_document: upsert_embedding failed idx=%d — %s", idx, exc
            )

        written += 1

    logger.info(
        "chunk_and_index_document: %s → %d chunks written (doc=%s deal=%s)",
        relative_path, written, document_id, deal_id,
    )
    return written
