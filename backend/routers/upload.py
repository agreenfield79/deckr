import logging
import os
import re

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from services import extraction_service, workspace_service
from services.limiter import limiter

logger = logging.getLogger("deckr.routers.upload")

router = APIRouter()

# Maps UI category label → workspace subfolder
CATEGORY_MAP: dict[str, str] = {
    "Financial Statements": "Financials",
    "Tax Returns": "Tax Returns",
    "Interim Financials": "Financials/interim",
    "Collateral Docs": "Collateral",
    "Guarantor Financials": "Guarantors",
    "Bank Statements": "Financials/bank_statements",
    "Rent Roll": "Collateral/rent_roll",
    "Other": "Other",
}

# Extensions routed to the extraction pipeline (unchanged from before)
_EXTRACTABLE_EXTS = {".pdf", ".txt", ".md", ".csv", ".tsv"}

# Security: allowed file types for upload (Step 30.3).
# Any extension not in this set is rejected before the file is written.
_ALLOWED_EXTS = {
    ".pdf", ".txt", ".md", ".csv", ".tsv",
    ".xlsx", ".xls", ".docx", ".doc",
    ".png", ".jpg", ".jpeg",
}

# Max upload size: 50 MB (Step 30.3 — guard before file.read())
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Safe filename pattern: letters, digits, dots, hyphens, underscores only.
# Rejects path separators, null bytes, and other shell-hostile characters.
_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-\s]*$")


def _sanitize_filename(filename: str) -> str:
    """
    Strip path separators and enforce a safe filename pattern.

    - Removes any directory component (basename only).
    - Replaces characters outside [a-zA-Z0-9._-] with '_'.
    - Ensures the result is non-empty.
    """
    # Take basename only — prevents ../Deck/memo.md traversal via filename
    name = os.path.basename(filename).strip()
    if not name:
        return "upload"
    # Replace unsafe characters with underscore
    safe = re.sub(r"[^\w.\-\s]", "_", name, flags=re.UNICODE)
    # Collapse repeated underscores/spaces
    safe = re.sub(r"[\s_]{2,}", "_", safe).strip("_")
    return safe or "upload"


@router.post("")
@limiter.limit("20/minute")
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(...),
):
    # --- Category validation ---
    folder = CATEGORY_MAP.get(category)
    if folder is None:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    # --- File size guard (Step 30.3): check Content-Length before reading ---
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    # --- Filename sanitization (Step 30.3) ---
    raw_filename = file.filename or "upload"
    filename = _sanitize_filename(raw_filename)
    if raw_filename != filename:
        logger.warning(
            "upload: filename sanitized '%s' → '%s'", raw_filename, filename
        )

    # --- File type allowlist (Step 30.3) ---
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTS:
        logger.warning(
            "upload: rejected file type '%s' (filename='%s')", ext, filename
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{ext}' is not allowed. "
                f"Accepted types: {', '.join(sorted(_ALLOWED_EXTS))}"
            ),
        )

    # --- Read and secondary size check (Content-Length may be absent) ---
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    destination = f"{folder}/{filename}"
    workspace_service.write_binary(destination, content)
    logger.info("upload: %s → %s (%d bytes)", filename, destination, len(content))

    extraction_queued = False
    if ext in _EXTRACTABLE_EXTS and os.getenv("ENABLE_EXTRACTION", "false").lower() == "true":
        background_tasks.add_task(extraction_service.extract_document, destination, content)
        extraction_queued = True
        logger.info("extraction queued for: %s", destination)

    return {
        "saved": True,
        "path": destination,
        "filename": filename,
        "extraction_queued": extraction_queued,
    }


@router.get("/list")
def list_uploads(folder: str):
    return workspace_service.list_folder(folder)
