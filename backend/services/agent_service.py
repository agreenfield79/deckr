import json
import logging
import os
import time
from datetime import date
from pathlib import Path

from services import agent_registry, orchestrate_client, watsonx_client, workspace_service
from services.extraction_service import get_extracted_text

logger = logging.getLogger("deckr.agent_service")

# Agents executed in order by run_pipeline_stream()
PIPELINE_SEQUENCE = ["financial", "risk", "packaging", "review"]


def run(
    agent_name: str,
    message: str,
    session_id: str,
    messages: list[dict],
    save_to_workspace: bool,
    save_path: str | None,
    action_type: str | None = None,
) -> dict:
    agent = agent_registry.get_agent(agent_name)
    use_orchestrate = os.getenv("USE_ORCHESTRATE", "false").lower() == "true"

    logger.info(
        "agent_service.run: agent=%s session=%s mode=%s orchestrate=%s action=%s",
        agent_name, session_id, agent["mode"], use_orchestrate, action_type or "default",
    )

    if use_orchestrate:
        # Orchestrate's chat/completions API processes only the last message in the
        # messages array as the current user query — it does not use prior array items
        # for conversation continuity the way OpenAI-compatible APIs do.
        # X-IBM-THREAD-ID server-side memory is also unreliable across sessions.
        #
        # Solution: pack everything into a SINGLE human message:
        #   1. Workspace context (capped at 10,000 chars)
        #   2. Prior conversation turns formatted as inline text (capped at 4,000 chars)
        #   3. Current user request
        #
        # This is session-agnostic and guaranteed to work regardless of API memory behavior.
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

        # Build prior conversation block from messages (exclude last item = current message)
        prior_turns = messages[:-1] if messages else []
        history_block = ""
        if prior_turns:
            lines: list[str] = []
            for m in prior_turns:
                role_label = "User" if m.get("role") == "user" else "Assistant"
                content = m.get("content", "")
                # Truncate very long agent replies to keep the block manageable
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

        # Assemble the single message
        parts: list[str] = []
        if has_context:
            parts.append(f"--- WORKSPACE CONTEXT ---\n{context}")
        if history_block:
            parts.append(history_block.strip())
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

        result = orchestrate_client.invoke_agent(agent_name, orchestrate_messages, session_id)
        reply = result["reply"]

        # Save output to workspace with frontmatter — same behaviour as watsonx path
        effective_path = save_path or (agent["output_path"] if save_to_workspace else None)
        if save_to_workspace and effective_path:
            content = _wrap_with_frontmatter(reply, agent_name, effective_path)
            workspace_service.write_file(effective_path, content)
            logger.info("agent_service: output saved to %s (via orchestrate)", effective_path)

        return {"reply": reply, "saved_to": effective_path if save_to_workspace else None}

    context = _load_context(agent["context_folders"], message)

    if agent["mode"] == "generate":
        if action_type:
            prompt = _build_action_prompt(action_type, context, message)
        else:
            prompt = _build_prompt(agent, context, message)
        reply = watsonx_client.generate(prompt, agent["model"], {})
    else:
        reply = watsonx_client.chat(messages, agent["model"], {})

    effective_path = save_path or (agent["output_path"] if save_to_workspace else None)

    if save_to_workspace and effective_path:
        content = _wrap_with_frontmatter(reply, agent_name, effective_path)
        workspace_service.write_file(effective_path, content)
        logger.info("agent_service: output saved to %s", effective_path)

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
    return frontmatter + content


# ---------------------------------------------------------------------------
# Pipeline runner — Step 13.1
# ---------------------------------------------------------------------------

# Default run prompts for each pipeline step
_PIPELINE_PROMPTS: dict[str, str] = {
    "financial": (
        "Run Financial Analysis Agent — generate a comprehensive financial analysis of all "
        "uploaded documents including leverage, liquidity, collateral, and guarantor review."
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
        "Run Review Agent — review the complete credit package in the Deck folder for accuracy, "
        "completeness, and compliance; flag any gaps or inconsistencies."
    ),
}


def run_pipeline_stream(session_id: str, message: str = ""):
    """
    Generator that runs agents in sequence (Financial → Risk → Packaging → Review)
    and yields NDJSON progress events for FastAPI StreamingResponse.

    Event types:
      {"type": "pipeline_start", "total": 4}
      {"type": "step_start",  "agent": str, "display_name": str, "step": int, "total": int}
      {"type": "step_done",   "agent": str, "step": int, "saved_to": str|None, "elapsed_ms": int, "reply_preview": str}
      {"type": "step_error",  "agent": str, "step": int, "error": str, "elapsed_ms": int}
      {"type": "pipeline_complete", "steps_done": int, "steps_failed": int, "total_elapsed_ms": int}
    """
    total = len(PIPELINE_SEQUENCE)
    pipeline_start = time.time()
    steps_done = 0
    steps_failed = 0

    yield json.dumps({"type": "pipeline_start", "total": total}) + "\n"
    logger.info("agent_service.run_pipeline_stream: started session=%s", session_id)

    for i, agent_name in enumerate(PIPELINE_SEQUENCE):
        step_num = i + 1
        agent_cfg = agent_registry.get_agent(agent_name)
        display_name = agent_cfg["display_name"]

        yield json.dumps({
            "type": "step_start",
            "agent": agent_name,
            "display_name": display_name,
            "step": step_num,
            "total": total,
        }) + "\n"
        logger.info(
            "agent_service.run_pipeline_stream: step %d/%d agent=%s session=%s",
            step_num, total, agent_name, session_id,
        )

        step_start = time.time()
        try:
            prompt = message or _PIPELINE_PROMPTS.get(
                agent_name,
                f"Run {display_name} — generate comprehensive analysis.",
            )
            result = run(
                agent_name=agent_name,
                message=prompt,
                session_id=session_id,
                messages=[],        # standalone call — no conversation history
                save_to_workspace=True,
                save_path=None,
            )
            elapsed = int((time.time() - step_start) * 1000)
            reply_preview = (result["reply"] or "")[:200].replace("\n", " ")
            steps_done += 1
            logger.info(
                "agent_service.run_pipeline_stream: step %d done agent=%s elapsed=%dms saved_to=%s",
                step_num, agent_name, elapsed, result.get("saved_to"),
            )
            yield json.dumps({
                "type": "step_done",
                "agent": agent_name,
                "step": step_num,
                "saved_to": result.get("saved_to"),
                "elapsed_ms": elapsed,
                "reply_preview": reply_preview,
            }) + "\n"

        except Exception as exc:
            elapsed = int((time.time() - step_start) * 1000)
            steps_failed += 1
            logger.error(
                "agent_service.run_pipeline_stream: step %d failed agent=%s — %s",
                step_num, agent_name, exc,
            )
            yield json.dumps({
                "type": "step_error",
                "agent": agent_name,
                "step": step_num,
                "error": str(exc),
                "elapsed_ms": elapsed,
            }) + "\n"

    total_elapsed = int((time.time() - pipeline_start) * 1000)
    logger.info(
        "agent_service.run_pipeline_stream: complete session=%s done=%d failed=%d elapsed=%dms",
        session_id, steps_done, steps_failed, total_elapsed,
    )
    yield json.dumps({
        "type": "pipeline_complete",
        "steps_done": steps_done,
        "steps_failed": steps_failed,
        "total_elapsed_ms": total_elapsed,
    }) + "\n"
