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

    extraction_queued = False
    is_pdf = filename.lower().endswith(".pdf")
    if is_pdf and os.getenv("ENABLE_EXTRACTION", "false").lower() == "true":
        full_path = str(workspace_service.resolve_path(destination))
        background_tasks.add_task(extraction_service.extract_document, full_path)
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
    root = workspace_service._get_root()
    target = workspace_service.resolve_path(folder)

    if not target.exists() or not target.is_dir():
        return []

    results = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name):
        if not entry.is_file():
            continue
        # Skip extraction sidecar files from the listing
        if entry.name.endswith(".extracted.json"):
            continue
        extracted = (entry.parent / (entry.name + ".extracted.json")).exists()
        rel_path = str(entry.relative_to(root)).replace("\\", "/")
        results.append({
            "name": entry.name,
            "path": rel_path,
            "size": entry.stat().st_size,
            "modified": entry.stat().st_mtime,
            "extracted": extracted,
        })

    return results
