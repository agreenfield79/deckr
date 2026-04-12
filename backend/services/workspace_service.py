import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("deckr.workspace_service")

_WORKSPACE_ROOT: str = os.getenv("WORKSPACE_ROOT", "./workspace_root/projects/default")


def _use_cos() -> bool:
    return os.getenv("USE_COS", "false").lower() == "true"


def _get_root() -> Path:
    root = Path(_WORKSPACE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_path(relative_path: str) -> Path:
    """Resolve a relative path under WORKSPACE_ROOT, blocking directory traversal."""
    root = _get_root()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        logger.warning("Path traversal attempt blocked: %s", relative_path)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Path '{relative_path}' escapes the workspace root",
        )
    return candidate


def _build_node(path: Path, root: Path) -> dict:
    rel = str(path.relative_to(root)).replace("\\", "/")
    if path.is_dir():
        children = sorted(
            [_build_node(child, root) for child in path.iterdir()],
            key=lambda n: (n["type"] == "file", n["name"].lower()),
        )
        return {"name": path.name, "path": rel, "type": "folder", "children": children}
    return {"name": path.name, "path": rel, "type": "file"}


def list_tree() -> dict:
    if _use_cos():
        from services import cos_service
        return cos_service.list_tree()
    root = _get_root()
    items = sorted(
        [_build_node(child, root) for child in root.iterdir()],
        key=lambda n: (n["type"] == "file", n["name"].lower()),
    )
    file_count = sum(1 for p in root.rglob("*") if p.is_file())
    logger.debug("list_tree: %d files found", file_count)
    return {"items": items}


def read_file(relative_path: str) -> str:
    if _use_cos():
        from services import cos_service
        return cos_service.read_file(relative_path)
    path = resolve_path(relative_path)
    if not path.exists() or not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
    return path.read_text(encoding="utf-8")


def write_file(relative_path: str, content: str) -> None:
    if _use_cos():
        from services import cos_service
        return cos_service.write_file(relative_path, content)
    path = resolve_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("write_file: %s (%d bytes)", relative_path, len(content))


def write_binary(relative_path: str, content: bytes) -> None:
    if _use_cos():
        from services import cos_service
        return cos_service.write_binary(relative_path, content)
    path = resolve_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    logger.info("write_binary: %s (%d bytes)", relative_path, len(content))


def delete_file(relative_path: str) -> None:
    if _use_cos():
        from services import cos_service
        return cos_service.delete_file(relative_path)
    path = resolve_path(relative_path)
    if not path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
    path.unlink()
    logger.info("delete_file: %s", relative_path)


def create_folder(relative_path: str) -> None:
    if _use_cos():
        from services import cos_service
        return cos_service.create_folder(relative_path)
    path = resolve_path(relative_path)
    path.mkdir(parents=True, exist_ok=True)
    logger.info("create_folder: %s", relative_path)


def rename_file(old_path: str, new_path: str) -> None:
    if _use_cos():
        from services import cos_service
        return cos_service.rename_file(old_path, new_path)
    src = resolve_path(old_path)
    dst = resolve_path(new_path)
    if not src.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Source not found: {old_path}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    logger.info("rename_file: %s → %s", old_path, new_path)
