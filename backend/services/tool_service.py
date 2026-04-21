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


def store_extraction(deal_id: str = None, workspace_id: str = None, **kwargs) -> dict:
    """
    IP1 tool — Trigger extraction persistence: read extracted_data.json from the
    workspace and seed all SQL financial tables + Neo4j anchor nodes.

    Parameters
    ----------
    deal_id      : optional; auto-generated if omitted.
    workspace_id : optional; resolved from workspace_root if omitted.
    """
    if kwargs:
        logger.debug("tool_service.store_extraction: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import workspace_service
    from services.extraction_persistence_service import seed, ExtractionSeedError

    workspace_root = str(workspace_service._get_root())
    try:
        result = seed(workspace_root=workspace_root, deal_id=deal_id, workspace_id=workspace_id)
        logger.info(
            "tool_service.store_extraction: sql_rows=%d neo4j_nodes=%d errors=%d",
            result.sql_row_count, result.neo4j_node_count, len(result.errors),
        )
        return {
            "seeded": True,
            "sql_rows": result.sql_row_count,
            "neo4j_nodes": result.neo4j_node_count,
            "errors": result.errors,
        }
    except ExtractionSeedError as exc:
        logger.warning("tool_service.store_extraction: seed failed — %s", exc)
        return {"seeded": False, "error": str(exc)}


def query_financials(
    deal_id: str = None,
    statement_type: str = "income_statement",
    entity_id: str = None,
    fiscal_year: int | None = None,
    **kwargs,
) -> list[dict]:
    """
    IP2 tool — Query structured financial data from SQL for a given deal.

    Parameters
    ----------
    deal_id        : deal identifier (used to resolve entity_id if not provided).
    entity_id      : entity identifier (overrides deal_id lookup).
    statement_type : one of "income_statement", "balance_sheet", "cash_flow",
                     "loan_terms", "management_guidance".
    fiscal_year    : optional year filter (e.g. 2024).
    """
    if not deal_id and not entity_id:
        raise ValueError("Either 'deal_id' or 'entity_id' must be provided.")
    if kwargs:
        logger.debug("tool_service.query_financials: ignoring extra kwargs %s", list(kwargs.keys()))

    from services import sql_service

    eid = entity_id
    if not eid and deal_id:
        eid = sql_service.get_entity_id_for_deal(deal_id)
    if not eid:
        return []

    stmt = statement_type.lower()
    if stmt == "income_statement":
        rows = sql_service.get_income_statements(eid)
    elif stmt == "balance_sheet":
        rows = sql_service.get_balance_sheets(eid)
    elif stmt == "cash_flow":
        rows = sql_service.get_cash_flow_statements(eid)
    elif stmt == "loan_terms":
        lt = sql_service.get_loan_terms(deal_id or eid)
        rows = [lt] if lt else []
    elif stmt == "management_guidance":
        mg = sql_service.get_management_guidance(eid)
        rows = [mg] if mg else []
    else:
        raise ValueError(
            f"Unknown statement_type '{stmt}'. Valid options: income_statement, "
            "balance_sheet, cash_flow, loan_terms, management_guidance."
        )

    if fiscal_year is not None:
        rows = [r for r in rows if r.get("fiscal_year") == fiscal_year]

    logger.info(
        "tool_service.query_financials: stmt=%s entity_id=%s rows=%d",
        stmt, eid, len(rows),
    )
    return rows


def log_pipeline_run(
    pipeline_run_id: str = None,
    deal_id: str = None,
    workspace_id: str = None,
    status: str = "complete",
    stages_completed: list | None = None,
    total_elapsed_ms: int | None = None,
    **kwargs,
) -> dict:
    """
    IP2 tool — Insert or update a pipeline_run record in SQL.

    If the pipeline_run_id already exists, updates its status, stages_completed,
    and total_elapsed_ms. Otherwise, inserts a new record.
    """
    if not pipeline_run_id:
        raise ValueError("'pipeline_run_id' is required.")
    if not deal_id:
        raise ValueError("'deal_id' is required.")
    if kwargs:
        logger.debug("tool_service.log_pipeline_run: ignoring extra kwargs %s", list(kwargs.keys()))

    from services import sql_service

    ws_id = workspace_id or "default"
    ok = sql_service.insert_pipeline_run(
        pipeline_run_id=pipeline_run_id,
        deal_id=deal_id,
        workspace_id=ws_id,
    )
    # If insert failed (likely already exists), try update instead.
    if not ok:
        ok = sql_service.update_pipeline_run(
            pipeline_run_id=pipeline_run_id,
            status=status,
            stages_completed=stages_completed,
            total_elapsed_ms=total_elapsed_ms,
        )
    else:
        # Row freshly inserted; stamp final status.
        sql_service.update_pipeline_run(
            pipeline_run_id=pipeline_run_id,
            status=status,
            stages_completed=stages_completed,
            total_elapsed_ms=total_elapsed_ms,
        )

    logger.info(
        "tool_service.log_pipeline_run: run_id=%s status=%s ok=%s",
        pipeline_run_id, status, ok,
    )
    return {"logged": ok, "pipeline_run_id": pipeline_run_id, "status": status}


def get_entity_graph(deal_id: str = None, **kwargs) -> dict:
    """
    IP3 tool — Return the deal knowledge graph (nodes + relationships) from Neo4j.

    Falls back to an empty graph if Neo4j is unavailable.
    """
    if not deal_id:
        raise ValueError("'deal_id' is required.")
    if kwargs:
        logger.debug("tool_service.get_entity_graph: ignoring extra kwargs %s", list(kwargs.keys()))

    from services import graph_service

    try:
        graph = graph_service.get_deal_graph(deal_id)
        nodes = len(graph.get("nodes") or [])
        rels  = len(graph.get("relationships") or [])
        logger.info(
            "tool_service.get_entity_graph: deal_id=%s nodes=%d relationships=%d",
            deal_id, nodes, rels,
        )
        return graph
    except Exception as exc:
        logger.warning("tool_service.get_entity_graph: failed — %s", exc)
        return {"nodes": [], "relationships": [], "error": str(exc)}


def search_documents(query: str = None, top_k: int = 5, deal_id: str | None = None,
                     folders: list[str] | None = None, **kwargs) -> list[dict]:
    """
    IP3 tool — Vector ANN similarity search across indexed document chunks.

    Searches the document chunk vector store (vector_service / ChromaDB or
    pgvector) for chunks semantically similar to ``query``.  Results are
    optionally scoped to a specific deal via ``deal_id``.

    Falls back to keyword-based workspace search if embeddings are unavailable.

    Note: ``folders`` is accepted for backwards-compatibility with System 1
    (embeddings_service.get_relevant_context) call patterns but is NOT forwarded
    to the vector store — ChromaDB metadata uses ``deal_id`` for scoping, not
    folder paths.  Pass ``deal_id`` to scope results to a specific borrower.
    """
    if not query:
        raise ValueError(
            "'query' is required. Provide a natural language search string, "
            "e.g. 'EBITDA margin trend over last 3 years'."
        )
    if kwargs:
        logger.debug("tool_service.search_documents: ignoring extra kwargs %s", list(kwargs.keys()))

    if os.getenv("ENABLE_EMBEDDINGS", "false").lower() == "true":
        try:
            from services import embeddings_service, vector_service
            embedding = embeddings_service.embed_query(query)
            if embedding:
                results = vector_service.similarity_search(
                    query_embedding=embedding,
                    n_results=top_k,
                    deal_id=deal_id,
                )
                logger.info(
                    "tool_service.search_documents: vector search — query_len=%d deal_id=%s hits=%d",
                    len(query), deal_id, len(results),
                )
                return results
        except Exception as exc:
            logger.warning("tool_service.search_documents: vector search failed (%s) — falling back", exc)

    # Fallback: text-based search via search_workspace
    text_results = search_workspace(query=query, folders=folders)
    return [{"text": text_results, "metadata": {}, "distance": None}]


def search_web(query: str = None, inputs: dict = None, max_results: int = 5, **kwargs) -> str:
    """
    Live web search via SerpAPI (Google Search results).

    Returns a formatted string of search results with titles, URLs, and snippets.
    Requires SERPAPI_KEY in environment.  Free tier: 100 searches/month.
    Sign up at serpapi.com.

    ``inputs`` handles the double-wrapped payload Orchestrate sometimes sends when the
    model fires the tool before deciding on a query string.
    **kwargs absorbs any remaining extra metadata fields Orchestrate may inject.
    """
    # Unwrap nested inputs dict if Orchestrate double-wraps the payload
    if not query and isinstance(inputs, dict):
        query = inputs.get("query")
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


# ---------------------------------------------------------------------------
# SQL View Query Handlers — 3E.8
# These wrap the read-only SQL views added in Phase 3B.8.
# ---------------------------------------------------------------------------

def query_ratios(deal_id: str = None, entity_id: str = None, **kwargs) -> list[dict]:
    """
    Query v_ratio_dashboard — DSCR, leverage, and coverage ratios per year.
    Returns a list of rows sorted by fiscal_year ascending.
    """
    if not deal_id and not entity_id:
        raise ValueError("Either 'deal_id' or 'entity_id' must be provided.")
    if kwargs:
        logger.debug("tool_service.query_ratios: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import sql_service
    eid = entity_id
    if not eid and deal_id:
        eid = sql_service.get_entity_id_for_deal(deal_id)
    if not eid:
        return []
    try:
        from services.db_factory import get_sql_session
        from sqlalchemy import text as _t
        with next(get_sql_session()) as session:
            rows = session.execute(
                _t("SELECT * FROM v_ratio_dashboard WHERE entity_id = :eid ORDER BY fiscal_year"),
                {"eid": eid},
            ).mappings().all()
        result = [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("tool_service.query_ratios failed: %s", exc)
        result = []
    logger.info("tool_service.query_ratios: entity_id=%s rows=%d", eid, len(result))
    return result


def query_deal_snapshot(deal_id: str = None, **kwargs) -> dict | None:
    """
    Query v_deal_snapshot for a single deal's latest SLACR score, ratios, and pipeline metadata.
    Returns a single dict or None if the deal does not exist.
    """
    if not deal_id:
        raise ValueError("'deal_id' is required.")
    if kwargs:
        logger.debug("tool_service.query_deal_snapshot: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import sql_service
    result = sql_service.get_deal_snapshot(deal_id)
    logger.info("tool_service.query_deal_snapshot: deal_id=%s found=%s", deal_id, result is not None)
    return result


def query_projection_stress(
    deal_id: str = None,
    pipeline_run_id: str = None,
    **kwargs,
) -> list[dict]:
    """
    Query v_projection_stress — scenario × year covenant heat map for a deal + pipeline run.
    Returns a list of rows (one row per scenario × projection year).
    """
    if not deal_id:
        raise ValueError("'deal_id' is required.")
    if not pipeline_run_id:
        raise ValueError("'pipeline_run_id' is required.")
    if kwargs:
        logger.debug("tool_service.query_projection_stress: ignoring extra kwargs %s", list(kwargs.keys()))
    from services import sql_service
    result = sql_service.get_projection_stress(deal_id, pipeline_run_id)
    logger.info(
        "tool_service.query_projection_stress: deal_id=%s run=%s rows=%d",
        deal_id, pipeline_run_id, len(result),
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
    # Phase 5B — Storage integration tools (IP1/IP2/IP3)
    "store_extraction":        store_extraction,
    "query_financials":        query_financials,
    "query_ratios":            query_ratios,
    "query_deal_snapshot":     query_deal_snapshot,
    "query_projection_stress": query_projection_stress,
    "log_pipeline_run":        log_pipeline_run,
    "get_entity_graph":        get_entity_graph,
    "search_documents":        search_documents,
}
