import concurrent.futures
import json
import logging
import os
import re
import time
import uuid
from datetime import date
from pathlib import Path

from services import agent_registry, event_bus, interpret_service, orchestrate_client, watsonx_client, workspace_service
from services.extraction_service import get_extracted_text

logger = logging.getLogger("deckr.agent_service")

# Pipeline execution plan — list of stages, each stage a list of agents.
# Single-agent stages run sequentially; multi-agent stages run in parallel
# via ThreadPoolExecutor, each agent on its own isolated Orchestrate thread.
#
# Architecture (Phase 20+):
#   1. Extraction  — sequential, context-injection path (no Orchestrate thread needed)
#   2. Analysis    — PARALLEL isolated threads: financial + industry
#                    (Phase 21: add collateral; Phase 22: add guarantor)
#                    Each reads uploaded docs from embeddings/workspace independently.
#                    No inter-agent dependency — all self-sufficient from raw uploads.
#   3. Risk        — sequential, isolated thread; reads all analysis outputs from
#                    workspace via tool calls (no thread history required).
#   4. Interpreter — ML inference pre-hook (interpret_service.run_neural_slacr_pipeline)
#                    fires first (synchronous, fast), writes neural_slacr_output.json +
#                    template narrative. Interpreter agent then enriches the narrative.
#                    If ML inference fails the agent stage is skipped gracefully.
#   5. Packaging   — sequential, isolated thread; assembles deck from workspace files;
#                    reads Agent Notes/neural_slacr.md for Section 11 ML validation.
#   6. Review      — sequential, ISOLATED thread (see comment in loop below).
#   7. Deckr       — sequential, isolated thread; borrower-facing deal sheet.
#
# Phase 21 expansion: replace ["financial", "industry"] with
#   ["financial", "industry", "collateral"]
# Phase 22 expansion: replace with
#   ["financial", "industry", "collateral", "guarantor"]
# — one line change here; no other code changes required.
PIPELINE_STAGES: list[list[str]] = [
    ["extraction"],
    ["financial", "industry", "collateral", "guarantor"],   # parallel isolated threads — final pipeline shape
    ["risk"],
    ["interpreter"],  # ML inference pre-hook runs first, then agent enriches narrative
    ["packaging"],
    ["review"],
    ["deckr"],    # Stage 7 — borrower-facing advocacy deal sheet
]

# Flat sequence derived from stages — used for _PIPELINE_PROMPTS lookup and display
PIPELINE_SEQUENCE = [agent for stage in PIPELINE_STAGES for agent in stage]


def run(
    agent_name: str,
    message: str,
    session_id: str,
    messages: list[dict],
    save_to_workspace: bool,
    save_path: str | None,
    action_type: str | None = None,
    tools: list[dict] | None = None,
    thread_id: str | None = None,
) -> dict:
    agent = agent_registry.get_agent(agent_name)
    use_orchestrate = os.getenv("USE_ORCHESTRATE", "false").lower() == "true"

    logger.info(
        "agent_service.run: agent=%s session=%s mode=%s orchestrate=%s action=%s tools=%d",
        agent_name, session_id, agent["mode"], use_orchestrate,
        action_type or "default", len(tools) if tools else 0,
    )

    _run_start = time.time()
    event_bus.publish({"type": "agent_start", "agent_name": agent_name, "session_id": session_id})

    if use_orchestrate:
        _MAX_CONTEXT_CHARS  = 10_000
        _MAX_HISTORY_CHARS  = 4_000

        context = _load_context(agent["context_folders"], message)
        if len(context) > _MAX_CONTEXT_CHARS:
            context = (
                context[:_MAX_CONTEXT_CHARS]
                + "\n\n[... workspace context truncated ...]"
            )
            logger.warning(
                "agent_service: context truncated to %d chars for Orchestrate payload (agent=%s)",
                _MAX_CONTEXT_CHARS, agent_name,
            )
        has_context = bool(context and context != "[No workspace documents found]")

        prior_turns = messages[:-1] if messages else []
        history_block = ""
        if prior_turns:
            lines: list[str] = []
            for m in prior_turns:
                role_label = "User" if m.get("role") == "user" else "Assistant"
                content = m.get("content", "")
                if role_label == "Assistant" and len(content) > 800:
                    content = content[:800] + "\n[... reply truncated ...]"
                lines.append(f"{role_label}: {content}")
            raw_history = "\n\n".join(lines)
            if len(raw_history) > _MAX_HISTORY_CHARS:
                raw_history = raw_history[-_MAX_HISTORY_CHARS:] + "\n[... earlier turns omitted ...]"
            history_block = f"\n\n--- PRIOR CONVERSATION ---\n{raw_history}"
            logger.info(
                "agent_service: %d prior turns included in Orchestrate payload (agent=%s)",
                len(prior_turns), agent_name,
            )

        parts: list[str] = []
        if has_context:
            parts.append(f"--- WORKSPACE CONTEXT ---\n{context}")
        if history_block:
            parts.append(history_block.strip())
        # Financial agent: pre-inject the complete extracted JSON and summary so
        # GPT-OSS-120B always has the full structured data, even when it
        # non-deterministically skips the get_file_content tool call.
        if agent_name == "financial":
            fin_ctx = _inject_financial_context()
            if fin_ctx:
                parts.append(fin_ctx)
                logger.info(
                    "agent_service: financial context pre-injected (%d chars) for agent=%s",
                    len(fin_ctx), agent_name,
                )
        # Deckr agent: pre-inject memo.md and financial_analysis.md so the model
        # does not need any get_file_content tool calls.  Its only remaining
        # tool call is save_to_workspace — eliminating the repeated empty-arg
        # get_file_content errors seen in Phase 27 pipeline runs.
        elif agent_name == "deckr":
            deckr_ctx = _inject_deckr_context()
            if deckr_ctx:
                parts.append(deckr_ctx)
                logger.info(
                    "agent_service: deckr context pre-injected (%d chars) for agent=%s",
                    len(deckr_ctx), agent_name,
                )
        # Interpreter agent: pre-inject neural_slacr_output.json so the model
        # does not need get_file_content tool calls.  Its only remaining tool
        # call is save_to_workspace("Agent Notes/neural_slacr.md").
        elif agent_name == "interpreter":
            interp_ctx = _inject_interpreter_context()
            if interp_ctx:
                parts.append(interp_ctx)
                logger.info(
                    "agent_service: interpreter context pre-injected (%d chars) for agent=%s",
                    len(interp_ctx), agent_name,
                )
        parts.append(f"--- CURRENT REQUEST ---\n{message}")
        full_message = "\n\n".join(parts)

        orchestrate_messages = [{"role": "human", "content": full_message}]
        logger.info(
            "agent_service: single-message payload built for Orchestrate — "
            "context=%s prior_turns=%d current_msg_len=%d (agent=%s)",
            "yes" if has_context else "no",
            len(prior_turns),
            len(message),
            agent_name,
        )

        result = orchestrate_client.invoke_agent(agent_name, orchestrate_messages, session_id, thread_id)
        reply = result["reply"]

        # Tool dispatch loop — Orchestrate path
        tool_calls = result.get("tool_calls") or []
        if tool_calls:
            reply = _run_tool_dispatch(
                agent_name=agent_name,
                session_id=session_id,
                messages=orchestrate_messages,
                result=result,
                invoke_fn=lambda msgs: orchestrate_client.invoke_agent(agent_name, msgs, session_id, thread_id),
            )

        effective_path = save_path or (agent["output_path"] if save_to_workspace else None)
        # When orchestrate_tool_save=True the agent is instructed to call the
        # save_to_workspace tool internally (Orchestrate's tool loop).  Suppress the
        # backend auto-save here so the brief confirmation reply the agent returns
        # does not overwrite the full content already written by the tool.
        tool_handles_save = agent.get("orchestrate_tool_save", False)
        if save_to_workspace and effective_path and not tool_handles_save:
            content = _wrap_with_frontmatter(reply, agent_name, effective_path)
            workspace_service.write_file(effective_path, content)
            logger.info("agent_service: output saved to %s (via orchestrate)", effective_path)
            event_bus.publish({"type": "agent_saved", "agent_name": agent_name, "saved_to": effective_path, "session_id": session_id})
        elif tool_handles_save and save_to_workspace:
            logger.info(
                "agent_service: backend auto-save suppressed for agent=%s (orchestrate_tool_save=True) — "
                "save_to_workspace tool is responsible for persisting output",
                agent_name,
            )
            # Fallback: if the agent did not call save_to_workspace (e.g. model
            # omitted the tool call or called it with missing args), the output file
            # will not exist yet.  In that case, persist the agent's full reply text
            # so downstream agents are not blocked by a missing file.
            if effective_path and reply and len(reply.strip()) > 80:
                file_missing = False
                try:
                    workspace_service.read_file(effective_path)
                except Exception:
                    file_missing = True
                if file_missing:
                    logger.warning(
                        "agent_service: %s did not save via tool — "
                        "falling back to saving reply (%d chars) to %s",
                        agent_name, len(reply), effective_path,
                    )
                    workspace_service.write_file(effective_path, reply)
                    event_bus.publish({
                        "type": "agent_saved",
                        "agent_name": agent_name,
                        "saved_to": effective_path,
                        "session_id": session_id,
                    })

        _elapsed = int((time.time() - _run_start) * 1000)
        event_bus.publish({"type": "agent_done", "agent_name": agent_name, "elapsed_ms": _elapsed, "session_id": session_id})
        return {"reply": reply, "saved_to": effective_path if (save_to_workspace and not tool_handles_save) else None}

    # --- Direct watsonx.ai path ---
    context = _load_context(agent["context_folders"], message)

    if agent["mode"] == "generate" and not tools:
        # Standard generation — no tool calling
        if action_type:
            prompt = _build_action_prompt(action_type, context, message)
        else:
            prompt = _build_prompt(agent, context, message)
        reply = watsonx_client.generate(prompt, agent["model"], {})

    else:
        # Chat path — required for tool calling; also used for mode=chat agents
        # When tools are provided with a generate-mode agent, we switch to the
        # /text/chat endpoint which supports function calling.
        chat_messages = list(messages) if messages else []
        if not chat_messages:
            system_prompt_path = agent.get("system_prompt", "")
            from pathlib import Path as _Path
            sp = _Path(system_prompt_path)
            system_content = sp.read_text(encoding="utf-8") if sp.exists() else (
                f"You are the {agent['display_name']}. "
                "Assist with commercial loan underwriting analysis."
            )
            if context and context != "[No workspace documents found]":
                system_content += f"\n\n--- WORKSPACE CONTEXT ---\n{context}"
            chat_messages = [
                {"role": "system", "content": system_content},
                {"role": "user",   "content": message},
            ]

        result = watsonx_client.chat(chat_messages, agent["model"], {}, tools=tools or None)
        reply = result["reply"]

        # Tool dispatch loop — direct path
        tool_calls = result.get("tool_calls") or []
        if tool_calls:
            reply = _run_tool_dispatch(
                agent_name=agent_name,
                session_id=session_id,
                messages=chat_messages,
                result=result,
                invoke_fn=lambda msgs: watsonx_client.chat(msgs, agent["model"], {}, tools=tools),
            )

    effective_path = save_path or (agent["output_path"] if save_to_workspace else None)

    if save_to_workspace and effective_path:
        content = _wrap_with_frontmatter(reply, agent_name, effective_path)
        workspace_service.write_file(effective_path, content)
        logger.info("agent_service: output saved to %s", effective_path)
        event_bus.publish({"type": "agent_saved", "agent_name": agent_name, "saved_to": effective_path, "session_id": session_id})

    _elapsed = int((time.time() - _run_start) * 1000)
    event_bus.publish({"type": "agent_done", "agent_name": agent_name, "elapsed_ms": _elapsed, "session_id": session_id})
    return {"reply": reply, "saved_to": effective_path if save_to_workspace else None}


def run_action_save(
    agent_name: str,
    action_type: str,
    save_path: str,
    session_id: str,
) -> None:
    """Background task: run a single action prompt and save output to workspace."""
    try:
        agent = agent_registry.get_agent(agent_name)
        context = _load_context(agent["context_folders"], action_type)
        prompt = _build_action_prompt(action_type, context, "")
        reply = watsonx_client.generate(prompt, agent["model"], {})
        content = _wrap_with_frontmatter(reply, agent_name, save_path)
        workspace_service.write_file(save_path, content)
        logger.info(
            "agent_service: background action '%s' saved to %s (session=%s)",
            action_type, save_path, session_id,
        )
    except Exception as e:
        logger.error(
            "agent_service: background action '%s' failed — %s",
            action_type, type(e).__name__,
        )


def _run_tool_dispatch(
    agent_name: str,
    session_id: str,
    messages: list[dict],
    result: dict,
    invoke_fn,
    max_iterations: int = 5,
) -> str:
    """
    Execute the tool dispatch loop shared by both Orchestrate and direct watsonx paths.

    For each tool_calls entry in `result`:
      1. Route to tool_service.dispatch()
      2. Append assistant message (with tool_calls) + tool result messages
      3. Re-invoke the agent
      4. Repeat until no tool_calls remain or max_iterations reached

    Returns the final plain-text reply.
    """
    import json as _json
    from services import tool_service

    current_result = result
    current_messages = list(messages)
    iteration = 0

    while True:
        tool_calls = current_result.get("tool_calls") or []
        if not tool_calls or iteration >= max_iterations:
            break
        iteration += 1

        # Append assistant's tool-call message to the conversation
        current_messages.append({
            "role":       "assistant",
            "content":    current_result.get("reply") or "",
            "tool_calls": tool_calls,
        })

        # Execute each tool call and collect results
        tool_result_msgs: list[dict] = []
        for tc in tool_calls:
            fn        = tc.get("function", {})
            tool_name = fn.get("name", "")
            call_id   = tc.get("id", "")
            try:
                args        = _json.loads(fn.get("arguments", "{}"))
                tool_output = tool_service.dispatch(tool_name, args)
                content     = _json.dumps(tool_output) if not isinstance(tool_output, str) else tool_output
                logger.info(
                    "agent_service: tool '%s' dispatched (iter=%d agent=%s result_len=%d)",
                    tool_name, iteration, agent_name, len(content),
                )
            except Exception as e:
                content = f"Error executing tool '{tool_name}': {e}"
                logger.warning(
                    "agent_service: tool '%s' failed (iter=%d agent=%s) — %s",
                    tool_name, iteration, agent_name, e,
                )

            tool_result_msgs.append({
                "role":         "tool",
                "tool_call_id": call_id,
                "content":      content,
            })

        current_messages.extend(tool_result_msgs)

        # Re-invoke agent with updated conversation
        current_result = invoke_fn(current_messages)

    if iteration >= max_iterations:
        logger.warning(
            "agent_service: tool dispatch reached max iterations (%d) for agent=%s session=%s",
            max_iterations, agent_name, session_id,
        )

    return current_result.get("reply") or ""


# ---------------------------------------------------------------------------
# Extraction pipeline — context-injection path (no tool calls)
# ---------------------------------------------------------------------------

_EXTRACTION_FOLDERS = ["Financials", "Tax Returns", "Guarantors"]

# Total character budget across ALL documents combined.
# GPT-OSS 120B supports ~128k tokens ≈ 500k chars.
# 450k leaves ~50k for the system prompt + JSON schema instructions.
# Individual documents are never truncated in the middle — each is included
# in full until the budget is exhausted, at which point the remaining
# document is truncated from the bottom (tail cut, not head+tail split).
# This correctly handles any document type: 4-page QuickBooks export,
# 30-page tax return, 10-K, or any combination thereof.
_EXTRACTION_TOTAL_BUDGET = 450_000

_NULL_SCHEMA: dict = {
    "company": None,
    "document_type": None,
    "fiscal_years": [],
    "income_statement": {
        "revenue":                        {},
        "gross_profit":                   {},
        "ebitda":                         {},
        "operating_income":               {},
        "net_income":                     {},
        "interest_expense":               {},
        "depreciation_amortization":      {},
        "cogs_product":                   {},
        "cogs_services":                  {},
        "research_and_development":       {},
        "selling_general_administrative": {},
        "stock_based_compensation":       {},
        "restructuring_charges":          {},
        "effective_tax_rate":             {},
    },
    "balance_sheet": {
        "total_assets":                   {},
        "total_liabilities":              {},
        "total_equity":                   {},
        "cash":                           {},
        "current_assets":                 {},
        "current_liabilities":            {},
        "total_debt":                     {},
        "long_term_debt":                 {},
        "days_sales_outstanding":         {},
        "days_inventory_outstanding":     {},
        "deferred_revenue":               {},
        "accrued_liabilities":            {},
        "days_payable_outstanding":       {},
        "funded_debt_rate_type":          {},
        "weighted_avg_interest_rate":     {},
        "debt_maturity_schedule":         {},
    },
    "cash_flow_statement": {
        "operating_cash_flow":            {},
        "capex":                          {},
        "free_cash_flow":                 {},
        "stock_based_compensation":       {},
        "maintenance_capex":              {},
        "growth_capex":                   {},
        "working_capital_change_detail":  {},
        "acquisitions":                   {},
        "debt_repayment":                 {},
        "share_repurchases":              {},
    },
    "revenue_segments": {},
    "management_guidance": {
        "guidance_period": None,
        "next_year_revenue_low": None,
        "next_year_revenue_mid": None,
        "next_year_revenue_high": None,
        "next_year_ebitda_margin": None,
        "growth_drivers": [],
        "risk_factors": [],
        "source_text": None,
    },
    "metadata": {
        "source_files":   [],
        "missing_fields": ["all — no documents uploaded"],
        "extracted_at":   date.today().isoformat(),
        "schema_version": "v2",
    },
}


def _build_extraction_context() -> tuple[str, list[str]]:
    """
    Read sidecar files (.extracted.json) for all documents in the three
    financial document folders.  COS-aware via workspace_service.

    Each document is included in full. Once the combined text approaches
    _EXTRACTION_TOTAL_BUDGET, the current document is truncated from the
    bottom — never split head+tail — and no further documents are added.

    This correctly handles any document type: a 4-page QuickBooks export
    (~10k chars), a 30-page tax return (~60k chars), a 10-K (~350k chars),
    or any combination, without ever omitting sections from the middle of
    a document.

    Returns (context_string, source_file_paths).
    Returns ("", []) when no documents are found.
    """
    parts: list[str] = []
    source_files: list[str] = []
    budget_used = 0

    for folder in _EXTRACTION_FOLDERS:
        try:
            files = workspace_service.list_folder(folder)
        except Exception as e:
            logger.warning("_build_extraction_context: list_folder('%s') failed — %s", folder, e)
            continue

        for f in files:
            if budget_used >= _EXTRACTION_TOTAL_BUDGET:
                logger.warning(
                    "_build_extraction_context: budget exhausted (%d chars) — skipping %s",
                    _EXTRACTION_TOTAL_BUDGET, f["path"],
                )
                continue

            path = f["path"]          # e.g. "Financials/10K-NVDA.pdf"
            sidecar = path + ".extracted.json"
            text = ""

            # Primary: sidecar pre-extracted text
            try:
                raw  = workspace_service.read_file(sidecar)
                data = json.loads(raw)
                text = data.get("text", "")
            except Exception:
                pass

            # Fallback: direct read (plain-text uploads without a sidecar)
            if not text:
                try:
                    text = workspace_service.read_file(path)
                except Exception:
                    pass

            if not text or not text.strip():
                logger.debug("_build_extraction_context: no text for %s — skipping", path)
                continue

            remaining = _EXTRACTION_TOTAL_BUDGET - budget_used
            if len(text) > remaining:
                logger.warning(
                    "_build_extraction_context: %s truncated from %d to %d chars (budget)",
                    path, len(text), remaining,
                )
                text = text[:remaining]

            parts.append(f"--- FILE: {path} ---\n{text}")
            source_files.append(path)
            budget_used += len(text)
            logger.info(
                "_build_extraction_context: loaded %s (%d chars, budget used %d/%d)",
                path, len(text), budget_used, _EXTRACTION_TOTAL_BUDGET,
            )

    context = "\n\n".join(parts)
    logger.info(
        "_build_extraction_context: %d document(s) loaded, total context %d chars",
        len(source_files), len(context),
    )
    return context, source_files


def _build_extraction_markdown(data: dict, source_files: list[str]) -> str:
    """
    Generate financial_data_summary.md deterministically from the parsed
    extraction JSON.  Pure Python — no AI call.
    """
    company       = data.get("company") or "Unknown"
    doc_type      = data.get("document_type") or "Unknown"
    fiscal_years  = data.get("fiscal_years") or []
    extracted_at  = (data.get("metadata") or {}).get("extracted_at", date.today().isoformat())
    missing       = (data.get("metadata") or {}).get("missing_fields") or []

    sources = ", ".join(source_files) if source_files else "None"

    def _val(section: str, field: str, fy: str) -> str:
        v = (data.get(section) or {}).get(field, {})
        if isinstance(v, dict):
            raw = v.get(fy)
        else:
            raw = None
        if raw is None:
            return "—"
        # Format large numbers with commas; keep small decimals as-is
        try:
            n = float(raw)
            return f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
        except (TypeError, ValueError):
            return str(raw)

    # Build header row and separator dynamically from fiscal_years
    fy_header = " | ".join(fiscal_years) if fiscal_years else "N/A"
    fy_sep    = " | ".join(["---"] * len(fiscal_years)) if fiscal_years else "---"

    def _row(label: str, section: str, field: str) -> str:
        vals = " | ".join(_val(section, field, fy) for fy in fiscal_years) if fiscal_years else "—"
        return f"| {label} | {vals} |"

    lines = [
        "## Financial Data Summary",
        f"**Company:** {company}",
        f"**Document Type:** {doc_type}",
        f"**Source Documents:** {sources}",
        f"**Extracted:** {extracted_at}",
        "",
        "### Income Statement",
        f"| Metric | {fy_header} |",
        f"|---|{fy_sep}|",
        _row("Revenue",             "income_statement", "revenue"),
        _row("Gross Profit",        "income_statement", "gross_profit"),
        _row("EBITDA",              "income_statement", "ebitda"),
        _row("Operating Income",    "income_statement", "operating_income"),
        _row("Net Income",          "income_statement", "net_income"),
        _row("Interest Expense",    "income_statement", "interest_expense"),
        _row("D&A",                 "income_statement", "depreciation_amortization"),
        "",
        "### Balance Sheet",
        f"| Metric | {fy_header} |",
        f"|---|{fy_sep}|",
        _row("Total Assets",        "balance_sheet", "total_assets"),
        _row("Total Liabilities",   "balance_sheet", "total_liabilities"),
        _row("Total Equity",        "balance_sheet", "total_equity"),
        _row("Cash",                "balance_sheet", "cash"),
        _row("Current Assets",      "balance_sheet", "current_assets"),
        _row("Current Liabilities", "balance_sheet", "current_liabilities"),
        _row("Total Debt",          "balance_sheet", "total_debt"),
        _row("Long-Term Debt",      "balance_sheet", "long_term_debt"),
        "",
        "### Cash Flow Statement",
        f"| Metric | {fy_header} |",
        f"|---|{fy_sep}|",
        _row("Operating Cash Flow", "cash_flow_statement", "operating_cash_flow"),
        _row("CapEx",               "cash_flow_statement", "capex"),
        _row("Free Cash Flow",      "cash_flow_statement", "free_cash_flow"),
        "",
        f"**Missing Fields:** {', '.join(missing) if missing else 'None'}",
    ]
    return "\n".join(lines)


def run_extraction(session_id: str, thread_id: str | None = None) -> dict:
    """
    Context-injection extraction path (Orchestrate, no tool calls).

    1. Backend pre-loads sidecar text from the three financial folders.
    2. Injects it as workspace context into the Orchestrate message.
    3. GPT-OSS 120B parses the text and returns the canonical JSON schema.
    4. Backend generates the markdown summary in Python.
    5. Backend saves both output files directly — no save_to_workspace tool call needed.
    """
    event_bus.publish({"type": "agent_start", "agent_name": "extraction", "session_id": session_id})
    _start = time.time()

    context, source_files = _build_extraction_context()

    # --- No documents: write null schema so downstream agents never 404 ---
    if not context:
        logger.warning("run_extraction: no financial documents found — writing null schema")
        null_data = dict(_NULL_SCHEMA)
        null_data["metadata"] = {
            "source_files":   [],
            "missing_fields": ["all — no documents uploaded"],
            "extracted_at":   date.today().isoformat(),
        }
        workspace_service.write_file(
            "Financials/extracted_data.json",
            json.dumps(null_data, indent=2),
        )
        workspace_service.write_file(
            "Financials/financial_data_summary.md",
            "## Financial Data Summary\n\nNo financial documents have been uploaded.",
        )
        event_bus.publish({"type": "agent_done", "agent_name": "extraction",
                           "elapsed_ms": int((time.time() - _start) * 1000), "session_id": session_id})
        return {
            "reply": "No financial documents found. Null schema written.",
            "saved_to": "Financials/extracted_data.json",
        }

    # --- Build Orchestrate message with pre-injected context ---
    prompt_path = Path("prompts/extraction_agent.txt")
    instructions = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else (
        "Parse the financial document text provided and return ONLY the canonical JSON schema populated "
        "with figures found in the documents. No markdown fences, no explanation."
    )

    full_message = (
        f"--- WORKSPACE CONTEXT ---\n{context}\n\n"
        f"--- CURRENT REQUEST ---\n{instructions}"
    )
    orchestrate_messages = [{"role": "human", "content": full_message}]

    logger.info(
        "run_extraction: invoking Orchestrate — context=%d chars, docs=%d",
        len(context), len(source_files),
    )
    result = orchestrate_client.invoke_agent("extraction", orchestrate_messages, session_id, thread_id)
    reply  = result.get("reply") or ""

    # --- Parse JSON from response ---
    extracted_data: dict | None = None
    # Strip markdown fences if the model added them despite instructions
    clean = re.sub(r"```(?:json)?\s*", "", reply).strip().rstrip("`").strip()
    match = re.search(r"\{[\s\S]+\}", clean)
    if match:
        try:
            extracted_data = json.loads(match.group(0))
            logger.info("run_extraction: JSON parsed successfully")
        except json.JSONDecodeError as e:
            logger.warning("run_extraction: JSON parse failed (%s) — falling back to null schema", e)

    if extracted_data is None:
        logger.warning("run_extraction: no valid JSON in response — writing null schema")
        extracted_data = dict(_NULL_SCHEMA)
        extracted_data["metadata"] = {
            "source_files":   source_files,
            "missing_fields": ["all — JSON parse failed; check model response"],
            "extracted_at":   date.today().isoformat(),
        }

    # Ensure metadata fields are populated from what we know
    if "metadata" not in extracted_data or not isinstance(extracted_data.get("metadata"), dict):
        extracted_data["metadata"] = {}
    extracted_data["metadata"].setdefault("source_files", source_files)
    extracted_data["metadata"].setdefault("extracted_at", date.today().isoformat())

    # --- Save JSON ---
    json_text = json.dumps(extracted_data, indent=2)
    workspace_service.write_file("Financials/extracted_data.json", json_text)
    logger.info("run_extraction: saved Financials/extracted_data.json (%d bytes)", len(json_text))

    # --- Generate and save markdown summary (pure Python — no AI call) ---
    markdown_text = _build_extraction_markdown(extracted_data, source_files)
    workspace_service.write_file("Financials/financial_data_summary.md", markdown_text)
    logger.info("run_extraction: saved Financials/financial_data_summary.md")

    _elapsed = int((time.time() - _start) * 1000)
    event_bus.publish({"type": "agent_done", "agent_name": "extraction",
                       "elapsed_ms": _elapsed, "session_id": session_id})
    event_bus.publish({"type": "agent_saved", "agent_name": "extraction",
                       "saved_to": "Financials/extracted_data.json", "session_id": session_id})

    fy_str = ", ".join(extracted_data.get("fiscal_years") or []) or "unknown fiscal years"
    missing_count = len((extracted_data.get("metadata") or {}).get("missing_fields") or [])
    confirmation = (
        f"Processed {len(source_files)} document(s). "
        f"Extracted fiscal years: {fy_str}. "
        f"Missing fields: {missing_count}."
    )
    return {"reply": confirmation, "saved_to": "Financials/extracted_data.json"}


def _load_context(context_folders: list[str], query: str = "") -> str:
    """
    Load workspace context for agent prompts.

    When ENABLE_EMBEDDINGS=true and a query is provided, uses semantic retrieval
    (embeddings_service) to select the most relevant chunks for that specific query.
    Falls back to full-file loading when embeddings are disabled or fail.
    """
    # Semantic retrieval path — replaces the 10k-char full-context dump
    if query and os.getenv("ENABLE_EMBEDDINGS", "false").lower() == "true":
        try:
            from services import embeddings_service
            ctx = embeddings_service.get_relevant_context(query, context_folders)
            if ctx and ctx not in (
                "[No workspace documents found]",
                "[No relevant workspace documents found]",
            ):
                logger.info(
                    "context: embeddings retrieval succeeded (query_len=%d, context_len=%d)",
                    len(query), len(ctx),
                )
                return ctx
            logger.info("context: embeddings returned no results — falling back to full load")
        except Exception as e:
            logger.warning("context: embeddings retrieval failed (%s) — falling back to full load", e)

    # Full-file loading fallback (original behaviour)
    root = workspace_service._get_root()
    parts: list[str] = []
    file_count = 0

    if "all" in context_folders:
        folders_to_scan = [root]
    else:
        folders_to_scan = [root / f.rstrip("/") for f in context_folders]

    for folder_path in folders_to_scan:
        label = (
            str(folder_path.relative_to(root)).replace("\\", "/")
            if folder_path != root
            else "workspace"
        )
        if not folder_path.exists() or not folder_path.is_dir():
            logger.warning("context: folder missing or empty — %s", label)
            parts.append(
                f"[MISSING: {label} — no documents have been uploaded to this category]"
            )
            continue

        folder_files = [p for p in folder_path.rglob("*") if p.is_file()]
        folder_files = [p for p in folder_files if not p.name.endswith(".extracted.json")]

        if not folder_files:
            logger.warning("context: folder missing or empty — %s", label)
            parts.append(
                f"[MISSING: {label} — no documents have been uploaded to this category]"
            )
            continue

        for file_path in sorted(folder_files):
            rel = str(file_path.relative_to(root)).replace("\\", "/")
            text = get_extracted_text(str(file_path))
            if text is None:
                try:
                    text = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
            parts.append(f"--- FILE: {rel} ---\n{text}")
            file_count += 1

    logger.info("context loaded: %d files from %s", file_count, context_folders)
    return "\n\n".join(parts) if parts else "[No workspace documents found]"


def _inject_deckr_context() -> str:
    """
    Pre-load Deck/memo.md and Agent Notes/financial_analysis.md for the deckr agent.

    GPT-OSS-120B non-deterministically calls get_file_content without the required
    'path' argument, causing repeated tool errors and an incomplete pipeline run.
    Pre-injecting both source files eliminates all get_file_content dependency —
    the agent's only remaining tool call is save_to_workspace.

    Returns an empty string when the files do not yet exist, which is a safe no-op.
    """
    blocks: list[str] = []
    for path, label in [
        ("Deck/memo.md",                        "CREDIT MEMORANDUM (Deck/memo.md)"),
        ("Agent Notes/financial_analysis.md",   "FINANCIAL ANALYSIS (Agent Notes/financial_analysis.md)"),
    ]:
        try:
            content = workspace_service.read_file(path)
            if content and content.strip():
                blocks.append(f"--- {label} ---\n{content.strip()}")
                logger.info(
                    "_inject_deckr_context: loaded %s (%d chars)", path, len(content)
                )
        except Exception as exc:
            logger.warning(
                "_inject_deckr_context: could not load %s — %s", path, exc
            )
    return "\n\n".join(blocks)


def _inject_interpreter_context() -> str:
    """
    Pre-load SLACR/neural_slacr_output.json for the interpreter agent.

    The Neural SLACR router writes this file before invoking the agent, so it
    always contains fresh model output.  Pre-injecting it eliminates the
    get_file_content empty-argument failure pattern documented in Phases 27/28.
    The agent's only remaining tool call is save_to_workspace.
    """
    try:
        content = workspace_service.read_file("SLACR/neural_slacr_output.json")
        if content and content.strip():
            logger.info(
                "_inject_interpreter_context: loaded SLACR/neural_slacr_output.json (%d chars)",
                len(content),
            )
            return (
                "--- NEURAL SLACR OUTPUT (SLACR/neural_slacr_output.json) ---\n"
                + content.strip()
            )
    except Exception as exc:
        logger.warning(
            "_inject_interpreter_context: could not load neural_slacr_output.json — %s", exc
        )
    return ""


def _inject_financial_context() -> str:
    """
    Pre-load the full extracted financial JSON and narrative summary for the
    financial agent.

    GPT-OSS-120B non-deterministically skips the mandatory get_file_content
    call when embeddings chunks of extracted_data.json are already present in
    the injected context.  Providing the complete file verbatim here guarantees
    the agent always has the full structured data, regardless of which tool
    calls it chooses to make.

    Returns an empty string when the files do not yet exist (e.g. extraction
    has not run), which is a safe no-op — the agent falls back to tool calls.
    """
    blocks: list[str] = []
    for path, label in [
        ("Financials/extracted_data.json", "EXTRACTED FINANCIAL DATA (JSON)"),
        ("Financials/financial_data_summary.md", "FINANCIAL DATA SUMMARY"),
    ]:
        try:
            content = workspace_service.read_file(path)
            if content and content.strip():
                blocks.append(f"--- {label} ---\n{content.strip()}")
                logger.info(
                    "_inject_financial_context: loaded %s (%d chars)", path, len(content)
                )
        except Exception as exc:
            logger.debug(
                "_inject_financial_context: could not load %s — %s", path, exc
            )

    return "\n\n".join(blocks)


def _build_prompt(agent: dict, context: str, message: str) -> str:
    prompt_path = Path(agent["system_prompt"])
    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = (
            f"You are the {agent['display_name']}. "
            "Assist with commercial loan underwriting analysis."
        )
    return (
        f"{system_prompt}\n\n"
        f"--- CONTEXT ---\n{context}\n\n"
        f"--- REQUEST ---\n{message}"
    )


def _build_action_prompt(action_type: str, context: str, message: str) -> str:
    """Build a prompt from a specific action template file."""
    prompt_path = Path(f"prompts/{action_type}.txt")
    if prompt_path.exists():
        action_template = prompt_path.read_text(encoding="utf-8")
    else:
        action_template = (
            f"Perform {action_type.replace('_', ' ')} analysis "
            "based on the provided workspace data."
        )
    request = message or "Analyze all available data and provide comprehensive findings."
    return (
        f"{action_template}\n\n"
        f"--- CONTEXT ---\n{context}\n\n"
        f"--- REQUEST ---\n{request}"
    )


_AI_DISCLOSURE = (
    "\n\n---\n"
    "*Generated with AI assistance (IBM watsonx). "
    "All figures should be independently verified prior to "
    "credit committee submission or lender distribution.*"
)


def _wrap_with_frontmatter(content: str, agent_name: str, output_path: str) -> str:
    frontmatter = (
        f"---\n"
        f"type: agent_output\n"
        f"agent_source: {agent_name}\n"
        f"output_path: {output_path}\n"
        f"project: default\n"
        f"created: {date.today().isoformat()}\n"
        f"---\n\n"
    )
    # Append AI disclosure to Markdown outputs only — skip JSON files so that
    # extracted_data.json and neural_slacr_output.json remain machine-parseable.
    disclosure = _AI_DISCLOSURE if output_path.endswith(".md") else ""
    return frontmatter + content + disclosure


# ---------------------------------------------------------------------------
# Integration Point helpers (IP1 / IP2 / IP3)
# ---------------------------------------------------------------------------

def _safe_int_local(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _fire_ip2_hook(agent_name: str, pipeline_state: dict) -> None:
    """
    D-3: dispatch to per-agent IP2 hook. All exceptions logged as warnings — never raises.
    Each hook is conditional on a structured sidecar file written by the agent.
    """
    try:
        if agent_name == "financial":
            _ip2_financial(pipeline_state)
        elif agent_name == "industry":
            _ip2_industry(pipeline_state)
        elif agent_name == "collateral":
            _ip2_collateral(pipeline_state)
        elif agent_name == "guarantor":
            _ip2_guarantor(pipeline_state)
    except Exception as exc:
        logger.warning("IP2[%s] hook raised unexpectedly: %s", agent_name, exc)


def _ip2_financial(pipeline_state: dict) -> None:
    """
    D-4: read Agent Notes/financial_ratios.json sidecar written by the financial agent.
    Skip gracefully if absent — hook becomes fully active once D-4 is deployed.
    Expected sidecar shape: { "<fiscal_year>": { "dscr": ..., "leverage": ..., ... }, ... }
    """
    try:
        raw = workspace_service.read_file("Agent Notes/financial_ratios.json")
        ratios: dict = json.loads(raw)
    except Exception:
        logger.debug(
            "IP2[financial]: Agent Notes/financial_ratios.json absent — "
            "D-4 sidecar not yet written by financial agent; skipping SQL write"
        )
        return

    from services import sql_service
    entity_id = pipeline_state.get("entity_id") or ""
    pipeline_run_id = pipeline_state.get("pipeline_run_id") or ""
    wrote = 0
    for year_str, year_data in ratios.items():
        year = _safe_int_local(year_str.replace("FY", "").replace("fy", "")) or _safe_int_local(year_str)
        if year is None or not isinstance(year_data, dict):
            continue
        ok = sql_service.write_financial_ratios(entity_id, pipeline_run_id, year, year_data)
        if ok:
            wrote += 1
    logger.info(
        "IP2[financial]: wrote %d financial_ratio row(s) entity_id=%s", wrote, entity_id
    )


def _ip2_industry(pipeline_state: dict) -> None:
    """
    Update Neo4j Industry node with enrichment properties.
    Reads Agent Notes/industry_enrichment.json sidecar if available; otherwise
    the Industry node was already created at IP1 via write_operates_in_relationship
    and no additional write is needed until the structured sidecar exists.
    """
    from services import graph_service
    try:
        raw = workspace_service.read_file("Agent Notes/industry_enrichment.json")
        enrichment: dict = json.loads(raw)
        naics_code = enrichment.get("naics_code") or pipeline_state.get("naics_code")
        if naics_code:
            graph_service.write_industry_enrichment(
                naics_code=naics_code,
                macro_risk_tier=enrichment.get("macro_risk_tier"),
                geopolitical_risk_tier=enrichment.get("geopolitical_risk_tier"),
                geopolitical_risk_factors=enrichment.get("geopolitical_risk_factors"),
            )
            logger.info("IP2[industry]: Industry node enriched naics_code=%s", naics_code)
    except Exception:
        logger.debug(
            "IP2[industry]: Agent Notes/industry_enrichment.json absent — "
            "Industry node already seeded at IP1; no enrichment update"
        )


def _ip2_collateral(pipeline_state: dict) -> None:
    """
    Update Neo4j Collateral node with appraiser findings.
    Reads Agent Notes/collateral_enrichment.json sidecar if available; otherwise
    the Collateral node was already seeded from extracted_data.json at IP1.
    """
    from services import graph_service
    try:
        raw = workspace_service.read_file("Agent Notes/collateral_enrichment.json")
        enrichment: dict = json.loads(raw)
        graph_service.write_collateral_node(
            deal_id=pipeline_state.get("deal_id") or "",
            collateral_id=enrichment.get("collateral_id", ""),
            collateral_type=enrichment.get("collateral_type", "unknown"),
            appraised_value=enrichment.get("appraised_value"),
        )
        logger.info("IP2[collateral]: Collateral node updated from sidecar")
    except Exception:
        logger.debug(
            "IP2[collateral]: Agent Notes/collateral_enrichment.json absent — "
            "Collateral node already seeded at IP1; no update"
        )


def _ip2_guarantor(pipeline_state: dict) -> None:
    """
    Write GUARANTEES edges in Neo4j.
    Guarantor Individual nodes were created at IP1. The GUARANTEES relationship
    requires individual entity_ids + loan_terms_id; these are queried from SQL
    via the deal_id so no additional sidecar is needed.
    """
    from services import graph_service
    deal_id = pipeline_state.get("deal_id") or ""
    loan_terms_id = pipeline_state.get("loan_terms_id") or ""
    if not deal_id or not loan_terms_id:
        logger.debug(
            "IP2[guarantor]: deal_id or loan_terms_id missing in pipeline_state — "
            "GUARANTEES edges deferred"
        )
        return
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Entity
        with next(get_sql_session()) as session:
            rows = session.query(Entity).filter_by(
                deal_id=deal_id, entity_type="guarantor_individual"
            ).all()
        for row in rows:
            graph_service.write_guarantees_relationship(
                entity_id=str(row.entity_id),
                loan_terms_id=loan_terms_id,
            )
        if rows:
            logger.info(
                "IP2[guarantor]: wrote %d GUARANTEES edge(s) deal_id=%s", len(rows), deal_id
            )
    except Exception as exc:
        logger.warning("IP2[guarantor]: GUARANTEES edge write failed — %s", exc)


def _fire_ip3_hook(pipeline_state: dict) -> None:
    """
    IP3: read SLACR/slacr.json after the risk agent completes.
    Applies OCC mapping deterministically (never by the LLM) and writes slacr_scores.
    Also reads SLACR/neural_slacr_output.json for SHAP/LIME if available.
    D-3: all exceptions logged as warnings — never raises.
    """
    try:
        raw = workspace_service.read_file("SLACR/slacr.json")
        slacr: dict = json.loads(raw)
    except Exception as exc:
        logger.warning("IP3: SLACR/slacr.json not found or not parseable — %s", exc)
        return

    try:
        from services import sql_service

        deal_id = pipeline_state.get("deal_id") or ""
        pipeline_run_id = pipeline_state.get("pipeline_run_id") or ""
        internal_rating = (
            slacr.get("rating") or slacr.get("internal_rating") or ""
        )

        shap_values: dict | None = None
        lime_values: dict | None = None
        try:
            ns_raw = workspace_service.read_file("SLACR/neural_slacr_output.json")
            ns: dict = json.loads(ns_raw)
            shap_values = ns.get("shap_values")
            lime_values = ns.get("lime_values")
        except Exception:
            pass

        # Pull DSCR from financial_ratios.json sidecar for OCC band tightening
        dscr: float | None = None
        try:
            fr_raw = workspace_service.read_file("Agent Notes/financial_ratios.json")
            fr: dict = json.loads(fr_raw)
            for year_data in fr.values():
                if isinstance(year_data, dict) and "dscr" in year_data:
                    try:
                        dscr = float(year_data["dscr"])
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass

        # Map slacr.json fields → SlacrScore ORM column names.
        # slacr.json is a SlacrOutput model dump: top-level has weighted_score,
        # rating, decision; dimension scores live under the "input" sub-dict.
        inp = slacr.get("input") or slacr
        scores = {
            "sponsor_score":       inp.get("strength"),
            "leverage_score":      inp.get("leverage"),
            "asset_quality_score": inp.get("collateral"),
            "cash_flow_score":     inp.get("ability_to_repay"),
            "risk_score":          inp.get("risk_factors"),
            "composite_score":     slacr.get("weighted_score") or slacr.get("score"),
        }
        scores = {k: float(v) for k, v in scores.items() if v is not None}

        ok = sql_service.write_slacr_score(
            deal_id=deal_id,
            pipeline_run_id=pipeline_run_id,
            scores=scores,
            internal_rating=internal_rating,
            dscr=dscr,
            shap_values=shap_values,
            lime_values=lime_values,
        )
        if ok:
            logger.info(
                "IP3: slacr_scores written deal_id=%s internal_rating=%s",
                deal_id, internal_rating,
            )
        else:
            logger.warning("IP3: write_slacr_score returned False for deal_id=%s", deal_id)
    except Exception as exc:
        logger.warning("IP3: hook failed — %s", exc)


# ---------------------------------------------------------------------------
# Pipeline runner — Step 13.1
# ---------------------------------------------------------------------------

# Default run prompts for each pipeline step
_PIPELINE_PROMPTS: dict[str, str] = {
    "extraction": (
        "Run Financial Data Extraction Agent — read all uploaded financial documents from the "
        "Financials, Tax Returns, and Guarantors folders, parse every financial line item into "
        "the canonical schema, and save structured output to Financials/extracted_data.json and "
        "Financials/financial_data_summary.md for use by all downstream analysis agents."
    ),
    "industry": (
        "Run Industry Analysis Agent — research the borrower's industry using web search and save "
        "a complete industry and market analysis to Agent Notes/industry_analysis.md for use by "
        "the Packaging Agent."
    ),
    "collateral": (
        "Run Collateral Agent — analyze all uploaded collateral documents, calculate LTV and lien "
        "positions, supplement with market comparables where appraisals are absent, and save a "
        "complete collateral schedule and narrative to Agent Notes/collateral_analysis.md."
    ),
    "guarantor": (
        "Run Guarantor Agent — analyze all uploaded guarantor financial documents, perform an "
        "online background check on each guarantor, calculate net worth, liquidity, and guarantee "
        "coverage ratios, and save a complete per-guarantor analysis to Agent Notes/guarantor_analysis.md."
    ),
    "financial": (
        "Run Financial Analysis Agent — generate a comprehensive financial analysis of all "
        "uploaded documents including leverage, liquidity, collateral, and guarantor review. "
        "Return your COMPLETE analysis as your reply text. Do NOT replace it with a brief "
        "save confirmation — the pipeline requires the full output in the reply."
    ),
    "risk": (
        "Run SLACR Risk Agent — score this deal using the SLACR framework, produce a risk "
        "narrative, and incorporate the financial analysis already saved to the workspace."
    ),
    "packaging": (
        "Run Packaging Agent — assemble the full credit memorandum using the financial analysis, "
        "SLACR risk narrative, and all uploaded borrower documents in the workspace."
    ),
    "review": (
        "Run Review Agent — two-level credit memo reconciliation. "
        "STEP 0: Call get_file_content('Deck/memo.md'). "
        "STEP 1: Call get_file_content for each agent note that is available — attempt each in "
        "sequence and SKIP silently if a file is not found (do not stop): "
        "'Agent Notes/financial_analysis.md', 'Agent Notes/industry_analysis.md', "
        "'Agent Notes/collateral_analysis.md', 'Agent Notes/guarantor_analysis.md', "
        "'SLACR/slacr_analysis.md'. "
        "STEP 2: Call get_file_content('Financials/extracted_data.json') — verify every "
        "financial figure in financial_analysis.md traces back to a non-null value in this JSON. "
        "STEP 3: Call search_workspace with queries 'revenue EBITDA net income operating income', "
        "'DSCR debt service coverage interest expense', 'collateral LTV lien appraisal', "
        "'guarantor net worth personal assets liquidity' to spot-check claims against source documents. "
        "STEP 4: Document all discrepancies, completeness gaps, and narrative concerns in structured format. "
        "STEP 5: You MUST call save_to_workspace — this step is mandatory regardless of which files "
        "were available. Call save_to_workspace with path='Agent Notes/review_notes.md' and your "
        "complete structured review as content. Do not skip this step even if some source files "
        "were missing. Chat reply must be a 1-2 sentence overall assessment only."
    ),
    "deckr": (
        "Run Deckr Agent. "
        "The Credit Memorandum and financial analysis are already pre-loaded in your context "
        "under '--- CREDIT MEMORANDUM (Deck/memo.md) ---' and "
        "'--- FINANCIAL ANALYSIS (Agent Notes/financial_analysis.md) ---'. "
        "DO NOT call get_file_content — those files are already in your context above. "
        "Using only the figures and facts from the pre-loaded content, produce a concise "
        "borrower-facing deal sheet with advocacy framing (lead with strengths; convert "
        "risk+mitigant pairs into stand-alone affirmative attributes; cite actual figures). "
        "Output sections using ## N. Section Name format: "
        "## 1. Header, ## 2. Company Overview & History, ## 3. Performance Summary, "
        "## 4. Ability to Repay, ## 5. Bidding Instructions. "
        "Your ONLY tool call must be: save_to_workspace with path='Deck/deckr.md' and "
        "the complete deal sheet text as the content argument. "
        "After saving, reply with one sentence confirming the file was saved."
    ),
    # Interpreter runs after the ML inference pre-hook in the pipeline.
    # The pre-hook writes neural_slacr_output.json and a template narrative;
    # this prompt drives the agent to enrich it with AI-generated prose.
    "interpreter": (
        "Run Interpreter Agent. "
        "The Neural SLACR model output JSON is already pre-loaded in your context "
        "under '--- NEURAL SLACR OUTPUT (SLACR/neural_slacr_output.json) ---'. "
        "DO NOT call get_file_content — the model output is already in your context above. "
        "Write a plain-language narrative (4–6 prose paragraphs) interpreting the ML results: "
        "(1) predicted risk rating and confidence, "
        "(2) top 3 SHAP drivers by name and sign, "
        "(3) LIME local explanation insights, "
        "(4) how this deal's band compares to the training distribution (cite percentages), "
        "(5) divergence analysis between ML prediction and analyst-scored composite. "
        "Write in prose only — no bullets, headers, or tables. Cite actual numbers. "
        "Your ONLY tool call must be save_to_workspace. "
        "Provide inputs.path = 'Agent Notes/neural_slacr.md' "
        "and inputs.content = your complete narrative text. "
        "If the tool returns an error, retry once with the correct arguments. "
        "Do not call save_to_workspace more than once. "
        "After saving, reply with one sentence confirming the file was saved."
    ),
}


def run_pipeline_stream(session_id: str, message: str = ""):
    """
    Generator that runs pipeline stages in sequence, yielding NDJSON progress
    events for FastAPI StreamingResponse.

    Stages are defined in PIPELINE_STAGES (list of lists).  Single-agent stages
    run sequentially.  Multi-agent stages (e.g. financial + collateral + guarantor
    at Phase 22) run in parallel via ThreadPoolExecutor — all agents in the stage
    start simultaneously; the next stage does not begin until every agent in the
    current stage has completed or errored.

    Event types:
      {"type": "pipeline_start",    "total": int}
      {"type": "step_start",        "agent": str, "display_name": str, "step": int, "total": int}
      {"type": "step_done",         "agent": str, "step": int, "saved_to": str|None, "elapsed_ms": int, "reply_preview": str}
      {"type": "step_error",        "agent": str, "step": int, "error": str, "elapsed_ms": int}
      {"type": "pipeline_complete", "steps_done": int, "steps_failed": int, "total_elapsed_ms": int}
    """
    total = len(PIPELINE_SEQUENCE)
    pipeline_start = time.time()
    steps_done = 0
    steps_failed = 0

    # Fresh thread ID per pipeline run prevents Orchestrate server-side thread
    # accumulation across multiple runs sharing the same user session ID.
    pipeline_thread_id = str(uuid.uuid4())

    # Carries IP1 seed result through to IP2/IP3 hooks.
    # Populated after extraction succeeds; read by parallel + risk stage hooks.
    _pipeline_state: dict = {"pipeline_run_id": str(uuid.uuid4())}

    yield json.dumps({"type": "pipeline_start", "total": total}) + "\n"
    logger.info(
        "agent_service.run_pipeline_stream: started session=%s thread=%s stages=%d agents=%d",
        session_id, pipeline_thread_id, len(PIPELINE_STAGES), total,
    )

    step_num = 0  # global step counter across all stages

    for stage in PIPELINE_STAGES:
        # ── emit step_start for every agent in this stage ────────────────────
        stage_step_nums: dict[str, int] = {}
        for agent_name in stage:
            step_num += 1
            stage_step_nums[agent_name] = step_num
            agent_cfg = agent_registry.get_agent(agent_name)
            yield json.dumps({
                "type":         "step_start",
                "agent":        agent_name,
                "display_name": agent_cfg["display_name"],
                "step":         step_num,
                "total":        total,
            }) + "\n"

        logger.info(
            "agent_service.run_pipeline_stream: stage [%s] starting session=%s",
            ", ".join(stage), session_id,
        )

        # ── helper: run one agent and return (agent_name, result_or_exc, elapsed) ─
        def _run_agent(agent_name: str, thread_id: str) -> tuple[str, dict | Exception, int]:
            agent_cfg = agent_registry.get_agent(agent_name)
            t0 = time.time()
            try:
                if agent_name == "extraction":
                    result = run_extraction(session_id, thread_id=thread_id)
                else:
                    prompt = message or _PIPELINE_PROMPTS.get(
                        agent_name,
                        f"Run {agent_cfg['display_name']} — generate comprehensive analysis.",
                    )
                    result = run(
                        agent_name=agent_name,
                        message=prompt,
                        session_id=session_id,
                        messages=[],
                        save_to_workspace=True,
                        save_path=None,
                        thread_id=thread_id,
                    )
                return agent_name, result, int((time.time() - t0) * 1000)
            except Exception as exc:
                return agent_name, exc, int((time.time() - t0) * 1000)

        # ── execute stage (parallel if >1 agent, sequential if single) ───────
        pending_events: list[str] = []

        if len(stage) == 1:
            # Single-agent stage — run inline, no thread overhead.
            #
            # Thread strategy:
            #   - Sequential analysis agents (extraction → financial → industry →
            #     risk → packaging) share pipeline_thread_id so that each agent
            #     benefits from the accumulated conversation context built by the
            #     agents that ran before it on the same Orchestrate thread.
            #     (Industry needs financial context; packaging needs everything.)
            #   - The review agent is isolated on its own thread
            #     (pipeline_thread_id + "-review") to prevent the ~30-message
            #     accumulation from the five prior agents from overwhelming it.
            #     Review retrieves everything it needs via explicit tool calls.
            agent_name = stage[0]

            # ── ML inference pre-hook (interpreter stage only) ────────────────
            # Runs synchronously before the Orchestrate agent is invoked.
            # Writes SLACR/neural_slacr_output.json and a template narrative to
            # Agent Notes/neural_slacr.md.  If it fails, emit a step_error and
            # skip the agent invocation — packaging will still run (no slacr.md).
            if agent_name == "interpreter":
                yield json.dumps({
                    "type":  "ml_inference_start",
                    "agent": "interpreter",
                }) + "\n"
                try:
                    interpret_service.run_neural_slacr_pipeline()
                    yield json.dumps({
                        "type":  "ml_inference_done",
                        "agent": "interpreter",
                    }) + "\n"
                    logger.info(
                        "agent_service.run_pipeline_stream: ML pre-hook complete session=%s",
                        session_id,
                    )
                except Exception as ml_exc:
                    logger.warning(
                        "agent_service.run_pipeline_stream: ML pre-hook failed — %s. "
                        "Skipping interpreter agent stage. session=%s",
                        ml_exc, session_id,
                    )
                    yield json.dumps({
                        "type":      "step_error",
                        "agent":     "interpreter",
                        "step":      stage_step_nums["interpreter"],
                        "error":     f"ML inference failed — interpreter stage skipped: {ml_exc}",
                        "elapsed_ms": 0,
                    }) + "\n"
                    steps_failed += 1
                    continue  # skip to the next pipeline stage (packaging)

            if agent_name == "review":
                # Review runs on its own isolated thread (Bug 3e fix).
                # Sharing packaging's thread was unreliable — packaging's thread
                # weight varies with deal complexity (2–5 tool calls + 13K deck).
                # When packaging's thread is heavy, review's additional tool
                # results push the combined context past GPT-OSS-120B's effective
                # reasoning threshold, triggering the "I am sorry" fallback.
                # The correct fix: isolated thread + explicit step-by-step prompt
                # listing every file to read.  All files are already saved to the
                # workspace by the time review runs, so tool calls are sufficient.
                agent_thread_id = f"{pipeline_thread_id}-review"
            elif agent_name in ("packaging", "risk", "deckr", "interpreter"):
                # packaging: assembles the deck from workspace files; does not
                #   need thread history from the analysis chain.
                # risk: reads all four analysis agent outputs from workspace via
                #   tool calls; does not need prior thread context.
                # deckr: reads memo.md and financial_analysis.md via tool calls;
                #   must not carry 30+ turns of prior agent history.
                # interpreter: reads pre-injected neural_slacr_output.json; must
                #   not carry risk-agent thread history.
                # All get their own isolated threads.
                agent_thread_id = f"{pipeline_thread_id}-{agent_name}"
            else:
                # extraction: the only remaining sequential pre-parallel stage.
                # Uses shared pipeline_thread_id (context-injection path — the
                # thread content is largely irrelevant for extraction).
                agent_thread_id = pipeline_thread_id
            agent_name_out, result_or_exc, elapsed = _run_agent(agent_name, agent_thread_id)
        else:
            # Multi-agent stage — run concurrently.
            # Parallel agents cannot share a thread (concurrent writes would
            # conflict), so each gets its own isolated thread ID.  They do not
            # need prior-stage thread context because the workspace files written
            # by earlier stages (extracted_data.json, etc.) are available via
            # tool calls.
            futures: dict[concurrent.futures.Future, str] = {}
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(stage))
            for agent_name in stage:
                agent_thread_id = f"{pipeline_thread_id}-{agent_name}"
                fut = executor.submit(_run_agent, agent_name, agent_thread_id)
                futures[fut] = agent_name

            # Collect results as they complete; buffer events for yielding below
            results_map: dict[str, tuple[dict | Exception, int]] = {}
            for fut in concurrent.futures.as_completed(futures):
                agent_name_out, result_or_exc, elapsed = fut.result()
                results_map[agent_name_out] = (result_or_exc, elapsed)

            executor.shutdown(wait=False)

            # ── IP2 persistence hooks (fail-silent per D-3) ──────────────────
            # Fire after collecting all parallel results; skip if IP1 did not seed
            if _pipeline_state.get("deal_id"):
                for _pname in stage:
                    _pr_exc, _ = results_map[_pname]
                    if not isinstance(_pr_exc, Exception):
                        _fire_ip2_hook(_pname, _pipeline_state)

            # Yield events for all agents in stage order for consistent UI rendering
            for agent_name in stage:
                result_or_exc, elapsed = results_map[agent_name]
                sn = stage_step_nums[agent_name]
                if isinstance(result_or_exc, Exception):
                    steps_failed += 1
                    logger.error(
                        "agent_service.run_pipeline_stream: step %d failed agent=%s — %s",
                        sn, agent_name, result_or_exc,
                    )
                    pending_events.append(json.dumps({
                        "type":       "step_error",
                        "agent":      agent_name,
                        "step":       sn,
                        "error":      str(result_or_exc),
                        "elapsed_ms": elapsed,
                    }) + "\n")
                else:
                    steps_done += 1
                    reply_preview = (result_or_exc.get("reply") or "")[:200].replace("\n", " ")
                    logger.info(
                        "agent_service.run_pipeline_stream: step %d done agent=%s elapsed=%dms saved_to=%s",
                        sn, agent_name, elapsed, result_or_exc.get("saved_to"),
                    )
                    pending_events.append(json.dumps({
                        "type":         "step_done",
                        "agent":        agent_name,
                        "step":         sn,
                        "saved_to":     result_or_exc.get("saved_to"),
                        "elapsed_ms":   elapsed,
                        "reply_preview": reply_preview,
                    }) + "\n")

            for ev in pending_events:
                yield ev
            continue  # skip the single-agent path below

        # ── single-agent path: emit done/error event ──────────────────────────
        sn = stage_step_nums[agent_name_out]
        if isinstance(result_or_exc, Exception):
            steps_failed += 1
            logger.error(
                "agent_service.run_pipeline_stream: step %d failed agent=%s — %s",
                sn, agent_name_out, result_or_exc,
            )
            yield json.dumps({
                "type":       "step_error",
                "agent":      agent_name_out,
                "step":       sn,
                "error":      str(result_or_exc),
                "elapsed_ms": elapsed,
            }) + "\n"
        else:
            steps_done += 1
            reply_preview = (result_or_exc.get("reply") or "")[:200].replace("\n", " ")
            logger.info(
                "agent_service.run_pipeline_stream: step %d done agent=%s elapsed=%dms saved_to=%s",
                sn, agent_name_out, elapsed, result_or_exc.get("saved_to"),
            )
            yield json.dumps({
                "type":         "step_done",
                "agent":        agent_name_out,
                "step":         sn,
                "saved_to":     "Agent Notes/neural_slacr.md" if agent_name_out == "interpreter" else result_or_exc.get("saved_to"),
                "elapsed_ms":   elapsed,
                "reply_preview": reply_preview,
            }) + "\n"

            # ── IP1: seed SQL + Neo4j after extraction ────────────────────────
            if agent_name_out == "extraction":
                try:
                    from services import extraction_persistence_service
                    _ws_root = str(workspace_service._get_root())
                    _seed = extraction_persistence_service.seed(
                        workspace_root=_ws_root,
                        deal_id=None,
                        workspace_id=None,
                    )
                    _pipeline_state.update({
                        "deal_id":       _seed.deal_id,
                        "entity_id":     _seed.entity_id,
                        "workspace_id":  _seed.workspace_id,
                    })
                    logger.info(
                        "IP1 gate passed: sql_rows=%d neo4j_nodes=%d deal_id=%s session=%s",
                        _seed.sql_row_count, _seed.neo4j_nodes_created,
                        _seed.deal_id, session_id,
                    )
                    # Register pipeline run row now that we have a deal_id
                    try:
                        from services import sql_service as _sql
                        _sql.insert_pipeline_run(
                            _pipeline_state["pipeline_run_id"],
                            _seed.deal_id or "",
                            _seed.workspace_id or "",
                        )
                    except Exception as _pr_exc:
                        logger.warning("IP1: insert_pipeline_run failed — %s", _pr_exc)
                    yield json.dumps({
                        "type":          "ip1_seeded",
                        "deal_id":       _seed.deal_id,
                        "sql_row_count": _seed.sql_row_count,
                    }) + "\n"
                except extraction_persistence_service.ExtractionSeedError as _e:
                    logger.error("IP1 gate FAILED session=%s — %s", session_id, _e)
                    yield json.dumps({
                        "type":       "step_error",
                        "agent":      "ip1_gate",
                        "step":       sn,
                        "error":      str(_e),
                        "elapsed_ms": 0,
                    }) + "\n"
                    steps_failed += 1
                    return  # halt the generator — parallel stage must not start
                except Exception as _e:
                    # Infrastructure issue — warn but do not halt (D-3)
                    logger.warning("IP1 seed failed non-fatally session=%s — %s", session_id, _e)

            # ── IP3: persist SLACR scores + OCC mapping after risk ────────────
            elif agent_name_out == "risk":
                _fire_ip3_hook(_pipeline_state)

    total_elapsed = int((time.time() - pipeline_start) * 1000)
    logger.info(
        "agent_service.run_pipeline_stream: complete session=%s done=%d failed=%d elapsed=%dms",
        session_id, steps_done, steps_failed, total_elapsed,
    )
    yield json.dumps({
        "type":              "pipeline_complete",
        "steps_done":        steps_done,
        "steps_failed":      steps_failed,
        "total_elapsed_ms":  total_elapsed,
    }) + "\n"
