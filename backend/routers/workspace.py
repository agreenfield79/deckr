import io
import logging
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import workspace_service
from services.limiter import limiter

logger = logging.getLogger("deckr.routers.workspace")

router = APIRouter()


class WriteFileRequest(BaseModel):
    path: str
    content: str


class CreateFolderRequest(BaseModel):
    path: str


@router.get("/tree")
def get_tree():
    return workspace_service.list_tree()


@router.get("/file")
def get_file(path: str):
    content = workspace_service.read_file(path)
    return {"content": content}


@router.post("/file")
def post_file(body: WriteFileRequest):
    workspace_service.write_file(body.path, body.content)
    return {"saved": True, "path": body.path}


@router.delete("/file")
def delete_file(path: str):
    workspace_service.delete_file(path)
    return {"deleted": True, "path": path}


@router.delete("/clear")
def clear_workspace():
    """Delete all files in the workspace, preserving folder structure."""
    root = workspace_service._get_root()
    deleted = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(root)).replace("\\", "/")
            try:
                workspace_service.delete_file(rel)
                deleted.append(rel)
            except Exception as e:
                logger.warning("clear_workspace: failed to delete %s — %s", rel, e)
    logger.info("clear_workspace: deleted %d files", len(deleted))
    return {"cleared": True, "deleted_count": len(deleted), "files": deleted}


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


@router.patch("/rename")
def rename_file(body: RenameRequest):
    workspace_service.rename_file(body.old_path, body.new_path)
    return {"renamed": True, "old": body.old_path, "new": body.new_path}


@router.post("/folder")
def post_folder(body: CreateFolderRequest):
    workspace_service.create_folder(body.path)
    return {"created": True, "path": body.path}


@router.get("/export")
@limiter.limit("3/minute")
def export_workspace(request: Request):
    """ZIP the full workspace tree and stream it as a download. Rate-limited: 3/minute per IP."""
    root = workspace_service._get_root()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                arcname = str(path.relative_to(root)).replace("\\", "/")
                zf.write(path, arcname)
    buffer.seek(0)
    logger.info("export_workspace: zipped %d files", sum(1 for _ in root.rglob("*") if _.is_file()))
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="workspace-export.zip"'},
    )


@router.get("/current-deal")
def get_current_deal():
    """
    Return the deal_id + workspace_id for the active workspace.
    Reads from Financials/extracted_data.json (written by IP1).
    Returns {deal_id: null, workspace_id: null} if not yet seeded.
    """
    try:
        import json as _json
        raw = workspace_service.read_file("Financials/extracted_data.json")
        data = _json.loads(raw) if raw else {}
        deal_id      = data.get("deal_id") or None
        workspace_id = data.get("workspace_id") or None
        # Fallback: try to read from SQL most-recent pipeline run
        if not deal_id:
            try:
                from services.db_factory import get_sql_session
                from models.sql_models import PipelineRun
                from sqlalchemy import select
                with next(get_sql_session()) as session:
                    row = session.execute(
                        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
                    ).scalar_one_or_none()
                    if row:
                        deal_id      = row.deal_id
                        workspace_id = row.workspace_id
            except Exception:
                pass
        return {"deal_id": deal_id, "workspace_id": workspace_id}
    except Exception as exc:
        logger.warning("get_current_deal failed: %s", exc)
        return {"deal_id": None, "workspace_id": None}


@router.get("/document-metadata")
def get_document_metadata(deal_id: str | None = None):
    """
    Return MongoDB document_index metadata (with agents_read badges).
    Falls back to empty list if MongoDB is offline.
    """
    try:
        from services import mongo_service
        docs = mongo_service.get_document_metadata(deal_id=deal_id)
        return {"documents": docs, "count": len(docs)}
    except Exception as exc:
        logger.warning("get_document_metadata failed: %s", exc)
        return {"documents": [], "count": 0, "error": str(exc)}
