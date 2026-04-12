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
            return data.get("text")
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
            return data.get("text")
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
            "extraction._extract_pdf: all three extractors found no text — "
            "PDF is likely image-based (scanned). OCR required (Phase 15: watsonx Document Understanding)."
        )
        return None
    except ImportError:
        logger.warning(
            "extraction._extract_pdf: PyMuPDF not installed — run: pip install pymupdf. "
            "All text extractors exhausted; PDF may be image-based."
        )
        return None
    except Exception as e:
        logger.error("extraction._extract_pdf: PyMuPDF error — %s", e)
        return None
