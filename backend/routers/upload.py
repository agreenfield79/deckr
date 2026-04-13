import logging
import os

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from services import extraction_service, workspace_service

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

_EXTRACTABLE_EXTS = {".pdf", ".txt", ".md", ".csv", ".tsv"}


@router.post("")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(...),
):
    folder = CATEGORY_MAP.get(category)
    if folder is None:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")

    content = await file.read()
    filename = file.filename or "upload"
    destination = f"{folder}/{filename}"

    workspace_service.write_binary(destination, content)
    logger.info("upload: %s → %s (%d bytes)", filename, destination, len(content))

    ext = os.path.splitext(filename)[1].lower()
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
