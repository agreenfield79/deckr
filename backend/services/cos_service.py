"""
IBM Cloud Object Storage adapter for Deckr workspace operations.

Activated when USE_COS=true in .env. Mirrors the public interface of
workspace_service.py so callers require no changes.

COS key structure mirrors the local filesystem layout:
    {WORKSPACE_ROOT}/{relative_path}
    e.g. workspace_root/projects/default/Borrower/borrower_profile.md

All text objects are stored as UTF-8; binary objects are stored as-is.
Folder simulation: COS has no true directories — list operations use key
prefixes. "Folders" exist implicitly when any object shares their prefix.
"""

import io
import logging
import os

import ibm_boto3
from ibm_botocore.client import Config
from ibm_botocore.exceptions import ClientError
from fastapi import HTTPException

logger = logging.getLogger("deckr.cos_service")

_client = None  # lazy-initialised singleton


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key      = os.getenv("COS_API_KEY")
    instance_crn = os.getenv("COS_INSTANCE_CRN")
    endpoint_url = os.getenv("COS_ENDPOINT_URL")

    if not all([api_key, instance_crn, endpoint_url]):
        raise RuntimeError(
            "COS_API_KEY, COS_INSTANCE_CRN, and COS_ENDPOINT_URL must all be set "
            "when USE_COS=true"
        )

    _client = ibm_boto3.client(
        "s3",
        ibm_api_key_id=api_key,
        ibm_service_instance_id=instance_crn,
        config=Config(signature_version="oauth"),
        endpoint_url=endpoint_url,
    )
    logger.info("cos_service: COS client initialised (endpoint=%s)", endpoint_url)
    return _client


def _bucket() -> str:
    name = os.getenv("COS_BUCKET_NAME", "deckr-workspace")
    return name


def _workspace_root() -> str:
    """Return the key prefix that corresponds to WORKSPACE_ROOT."""
    root = os.getenv("WORKSPACE_ROOT", "./workspace_root/projects/default")
    # Strip leading ./ and normalise separators
    return root.lstrip("./").replace("\\", "/").strip("/")


def _key(relative_path: str) -> str:
    """Build the full COS object key for a workspace-relative path."""
    rel = relative_path.replace("\\", "/").lstrip("/")
    prefix = _workspace_root()
    return f"{prefix}/{rel}" if prefix else rel


def _rel_from_key(key: str) -> str:
    """Strip the workspace root prefix from a COS key to get a relative path."""
    prefix = _workspace_root()
    if prefix and key.startswith(prefix + "/"):
        return key[len(prefix) + 1:]
    return key


def _validate_relative_path(relative_path: str) -> str:
    """Block directory traversal attempts."""
    if ".." in relative_path.replace("\\", "/").split("/"):
        logger.warning("cos_service: path traversal attempt blocked: %s", relative_path)
        raise HTTPException(
            status_code=400,
            detail=f"Path '{relative_path}' escapes the workspace root",
        )
    return relative_path


# ---------------------------------------------------------------------------
# Public interface — mirrors workspace_service.py
# ---------------------------------------------------------------------------

def list_tree() -> dict:
    """List all objects under the workspace root, reconstructing a virtual tree."""
    client = _get_client()
    prefix = _workspace_root() + "/"

    paginator = client.get_paginator("list_objects_v2")
    all_keys: list[str] = []
    for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            all_keys.append(obj["Key"])

    logger.debug("cos_service.list_tree: %d objects found", len(all_keys))

    # Build a nested dict tree from flat key list
    root_node: dict = {}
    for key in sorted(all_keys):
        rel = _rel_from_key(key)
        parts = rel.split("/")
        node = root_node
        for part in parts[:-1]:  # folders
            node = node.setdefault(part, {})
        node[parts[-1]] = None  # file leaf

    def _to_items(node: dict, path_prefix: str) -> list:
        items = []
        for name, children in sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower())):
            rel_path = f"{path_prefix}/{name}" if path_prefix else name
            if children is None:
                items.append({"name": name, "path": rel_path, "type": "file"})
            else:
                items.append({
                    "name": name,
                    "path": rel_path,
                    "type": "folder",
                    "children": _to_items(children, rel_path),
                })
        return items

    return {"items": _to_items(root_node, "")}


def read_file(relative_path: str) -> str:
    _validate_relative_path(relative_path)
    client = _get_client()
    key = _key(relative_path)
    try:
        resp = client.get_object(Bucket=_bucket(), Key=key)
        data = resp["Body"].read()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=415,
                detail=f"'{relative_path}' is a binary file and cannot be displayed as text.",
            )
    except HTTPException:
        raise
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
        logger.error("cos_service.read_file: %s — %s", relative_path, e)
        raise HTTPException(status_code=500, detail="COS read error")


def read_binary(relative_path: str) -> bytes:
    """Read raw bytes from COS — used by extraction_service for PDFs."""
    _validate_relative_path(relative_path)
    client = _get_client()
    key = _key(relative_path)
    try:
        resp = client.get_object(Bucket=_bucket(), Key=key)
        return resp["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
        logger.error("cos_service.read_binary: %s — %s", relative_path, e)
        raise HTTPException(status_code=500, detail="COS read error")


def list_folder(relative_path: str) -> list[dict]:
    """
    List all non-sidecar files under a workspace folder prefix.
    Returns the same shape as upload.py's local list_uploads() for drop-in use.
    Includes extracted=True when a matching .extracted.json sidecar exists in COS.
    """
    _validate_relative_path(relative_path)
    client = _get_client()
    prefix = _key(relative_path) + "/"

    paginator = client.get_paginator("list_objects_v2")
    all_objects: dict[str, dict] = {}
    for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            all_objects[obj["Key"]] = obj

    results: list[dict] = []
    for key, obj in sorted(all_objects.items(), key=lambda kv: kv[0]):
        name = key.rsplit("/", 1)[-1]
        # Skip implicit "folder" markers and extraction sidecars
        if not name or name.endswith(".extracted.json"):
            continue
        rel = _rel_from_key(key)
        sidecar_key = key + ".extracted.json"
        extracted = sidecar_key in all_objects
        results.append({
            "name": name,
            "path": rel,
            "size": obj.get("Size", 0),
            "modified": obj["LastModified"].timestamp(),
            "extracted": extracted,
        })

    logger.debug("cos_service.list_folder: %s — %d files", relative_path, len(results))
    return results


def write_file(relative_path: str, content: str) -> None:
    _validate_relative_path(relative_path)
    client = _get_client()
    key = _key(relative_path)
    data = content.encode("utf-8")
    client.put_object(Bucket=_bucket(), Key=key, Body=data, ContentType="text/plain; charset=utf-8")
    logger.info("cos_service.write_file: %s (%d bytes)", relative_path, len(data))


def write_binary(relative_path: str, content: bytes) -> None:
    _validate_relative_path(relative_path)
    client = _get_client()
    key = _key(relative_path)
    client.put_object(Bucket=_bucket(), Key=key, Body=content)
    logger.info("cos_service.write_binary: %s (%d bytes)", relative_path, len(content))


def delete_file(relative_path: str) -> None:
    _validate_relative_path(relative_path)
    client = _get_client()
    key = _key(relative_path)
    # Verify exists first for a consistent 404 error
    try:
        client.head_object(Bucket=_bucket(), Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404", "403"):
            raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
        raise
    client.delete_object(Bucket=_bucket(), Key=key)
    logger.info("cos_service.delete_file: %s", relative_path)


def create_folder(relative_path: str) -> None:
    """COS has no real folders — this is a no-op (folders exist implicitly via key prefixes)."""
    _validate_relative_path(relative_path)
    logger.debug("cos_service.create_folder: %s (no-op in COS)", relative_path)


def rename_file(old_path: str, new_path: str) -> None:
    """COS has no rename — copy then delete."""
    _validate_relative_path(old_path)
    _validate_relative_path(new_path)
    client = _get_client()
    old_key = _key(old_path)
    new_key = _key(new_path)

    try:
        client.copy_object(
            Bucket=_bucket(),
            CopySource={"Bucket": _bucket(), "Key": old_key},
            Key=new_key,
        )
        client.delete_object(Bucket=_bucket(), Key=old_key)
        logger.info("cos_service.rename_file: %s → %s", old_path, new_path)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail=f"Source not found: {old_path}")
        logger.error("cos_service.rename_file: %s → %s — %s", old_path, new_path, e)
        raise HTTPException(status_code=500, detail="COS rename error")


def configured() -> bool:
    """Return True if all required COS env vars are set."""
    return all([
        os.getenv("COS_API_KEY"),
        os.getenv("COS_INSTANCE_CRN"),
        os.getenv("COS_ENDPOINT_URL"),
        os.getenv("COS_BUCKET_NAME"),
    ])
