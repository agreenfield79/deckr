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
