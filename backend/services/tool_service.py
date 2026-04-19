"""
tool_service.py — agent-callable tool handlers (Phase 15)

Each function corresponds to a tool an agent can invoke via tool calling.
All handlers are thin wrappers around existing services; only search_web
adds a new external integration (SerpAPI via requests, no SDK required).

dispatch() is the single entry point used by agent_service and routers/tools.py.
"""

import json
import logging
import os

import requests
from fastapi import HTTPException

logger = logging.getLogger("deckr.tool_service")

# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, callable] = {}


def dispatch(tool_name: str, inputs: dict) -> str | dict:
    """Route a tool call to the appropriate handler. Raises ValueError for unknown tools."""
    handler = _HANDLERS.get(tool_name)
    if not handler:
        raise ValueError(
            f"Unknown tool '{tool_name}'. Available: {sorted(_HANDLERS.keys())}"
        )
    logger.info("tool_service.dispatch: tool=%s inputs_keys=%s", tool_name, list(inputs.keys()))
    return handler(**inputs)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def save_to_workspace(path: str = None, content: str = None, **kwargs) -> dict:
    """
    Agent-initiated file save to workspace.

    Unlike the backend's automatic save_to_workspace=True path (which always
    saves agent output), this is explicitly invoked by the agent to persist
    a specific piece of content at a specific path.

    **kwargs absorbs extra metadata fields Orchestrate may inject (e.g. tool_name)
    so the handler does not raise on unexpected keyword arguments.
    """
    if path is None or content is None:
        missing = [f for f, v in [('path', path), ('content', content)] if v is None]
        msg = (
            f'Missing required parameter(s): {missing}. '
            f'Call save_to_workspace again with both '
            f'"inputs.path" (workspace-relative file path, e.g. "Agent Notes/neural_slacr.md") '
            f'and "inputs.content" (the full text to write).'
        )
        logger.warning("tool_service.save_to_workspace: missing required args %s", missing)
        raise HTTPException(status_code=422, detail=msg)
    if kwargs:
        logger.debug("tool_service.save_to_workspace: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import workspace_service
    workspace_service.write_file(path, content)
    logger.info("tool_service.save_to_workspace: wrote %d chars to %s", len(content), path)
    return {"saved": True, "path": path, "bytes": len(content)}


def get_file_content(path: str = None, **kwargs) -> str:
    """Read a workspace file and return its text content."""
    if path is None:
        msg = (
            'Missing required parameter: path. '
            'Call get_file_content again with '
            '"inputs.path" set to the workspace-relative file path '
            '(e.g. "Agent Notes/neural_slacr.md").'
        )
        logger.warning("tool_service.get_file_content: missing required arg 'path'")
        raise HTTPException(status_code=422, detail=msg)
    if kwargs:
        logger.debug("tool_service.get_file_content: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import workspace_service
    try:
        content = workspace_service.read_file(path)
        logger.info("tool_service.get_file_content: read %d chars from %s", len(content), path)
        return content
    except HTTPException as e:
        raise ValueError(f"Cannot read '{path}': {e.detail}") from e


def list_uploaded_documents(folder: str = "Financials", **kwargs) -> list[dict]:
    """List files in a workspace folder. Returns [{name, path, size, modified, extracted}]."""
    if kwargs:
        logger.debug("tool_service.list_uploaded_documents: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import workspace_service
    results = workspace_service.list_folder(folder)
    logger.info("tool_service.list_uploaded_documents: %d files in '%s'", len(results), folder)
    return results


def compute_slacr_score(
    strength: int,
    leverage: int,
    ability_to_repay: int,
    collateral: int,
    risk_factors: int,
    **kwargs,
) -> dict:
    """
    Compute a SLACR risk score from five dimension scores (each 1–5, where 1=best).

    Returns weighted_score, rating, decision, and mitigants.
    """
    from models.slacr import SlacrInput
    from services import slacr_service

    slacr_input = SlacrInput(
        strength=strength,
        leverage=leverage,
        ability_to_repay=ability_to_repay,
        collateral=collateral,
        risk_factors=risk_factors,
    )
    output = slacr_service.compute(slacr_input)
    slacr_service.save(output)
    result = {
        "weighted_score": output.weighted_score,
        "rating": output.rating,
        "decision": output.decision,
        "mitigants": output.mitigants,
    }
    if kwargs:
        logger.debug("tool_service.compute_slacr_score: ignoring extra kwargs %s", list(kwargs.keys()))
    logger.info(
        "tool_service.compute_slacr_score: score=%.2f rating=%s",
        output.weighted_score, output.rating,
    )
    return result


def search_workspace(query: str = None, folders: list[str] | None = None, **kwargs) -> str:
    """
    Semantic search across workspace documents using the embeddings index.

    Returns the most relevant document chunks for the given query.
    Defaults to searching all workspace folders.

    **kwargs absorbs extra metadata fields Orchestrate may inject.
    """
    if not query:
        logger.warning("tool_service.search_workspace: 'query' argument missing — returning guidance")
        return (
            'ERROR: Required parameter "query" was not provided. '
            'Call this tool again and include the query field. '
            'Example: {"query": "revenue EBITDA net income industry sector"}'
        )
    if kwargs:
        logger.debug("tool_service.search_workspace: ignoring extra kwargs %s", list(kwargs.keys()))
    context_folders = folders or ["all"]
    if os.getenv("ENABLE_EMBEDDINGS", "false").lower() == "true":
        try:
            from services import embeddings_service
            result = embeddings_service.get_relevant_context(query, context_folders)
            logger.info(
                "tool_service.search_workspace: embeddings retrieval — query_len=%d result_len=%d",
                len(query), len(result),
            )
            return result
        except Exception as e:
            logger.warning("tool_service.search_workspace: embeddings failed (%s) — falling back", e)

    # Fallback: full-file load via workspace_service
    from services import workspace_service
    from services.extraction_service import get_extracted_text
    root = workspace_service._get_root()
    parts: list[str] = []

    scan_paths = [root] if "all" in context_folders else [
        root / f.rstrip("/") for f in context_folders
    ]
    for folder_path in scan_paths:
        if not folder_path.exists():
            continue
        for file_path in sorted(folder_path.rglob("*")):
            if not file_path.is_file() or file_path.name.endswith(".extracted.json"):
                continue
            text = get_extracted_text(str(file_path))
            if text is None:
                try:
                    text = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
            rel = str(file_path.relative_to(root)).replace("\\", "/")
            parts.append(f"--- FILE: {rel} ---\n{text}")

    return "\n\n".join(parts) if parts else "[No workspace documents found]"


def search_web(query: str = None, max_results: int = 5, **kwargs) -> str:
    """
    Live web search via SerpAPI (Google Search results).

    Returns a formatted string of search results with titles, URLs, and snippets.
    Requires SERPAPI_KEY in environment.  Free tier: 100 searches/month.
    Sign up at serpapi.com.

    **kwargs absorbs extra metadata fields Orchestrate may inject.
    """
    if not query:
        logger.warning("tool_service.search_web: 'query' argument missing — returning guidance")
        return (
            'ERROR: Required parameter "query" was not provided. '
            'Call this tool again and include the query field. '
            'Example: {"query": "semiconductor industry market size 2026 global CAGR"}'
        )
    if kwargs:
        logger.debug("tool_service.search_web: ignoring extra kwargs %s", list(kwargs.keys()))
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise ValueError(
            "SERPAPI_KEY is not set. Sign up free at serpapi.com and add the key to backend/.env."
        )

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "api_key": api_key,
                "q":       query,
                "num":     max_results,
                "engine":  "google",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("tool_service.search_web: SerpAPI request failed — %s", e)
        raise ValueError(f"Web search failed: {e}") from e

    lines: list[str] = []
    for r in data.get("organic_results", []):
        title   = r.get("title", "")
        url     = r.get("link", "")
        snippet = (r.get("snippet") or "")[:400]
        lines.append(f"[{title}]({url})\n{snippet}")

    result = "\n\n".join(lines) if lines else "[No results found]"
    logger.info(
        "tool_service.search_web: query='%s' results=%d",
        query[:60], len(data.get("organic_results", [])),
    )
    return result


# Register all handlers after they are defined
_HANDLERS = {
    "save_to_workspace":       save_to_workspace,
    "get_file_content":        get_file_content,
    "list_uploaded_documents": list_uploaded_documents,
    "compute_slacr_score":     compute_slacr_score,
    "search_workspace":        search_workspace,
    "search_web":              search_web,
}
