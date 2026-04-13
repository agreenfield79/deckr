import logging
import re

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from models.agent import AgentRequest, AgentResponse, PipelineRequest
from models.slacr import SlacrInput
from services import agent_registry, agent_service, slacr_service, workspace_service

logger = logging.getLogger("deckr.routers.agent")

router = APIRouter()


@router.get("/registry")
def get_registry():
    """Return all agent display names and capabilities.
    When USE_ORCHESTRATE=true, merges static registry with live Orchestrate agent list
    to annotate which agents are confirmed live in the Orchestrate instance.
    """
    import os
    static = agent_registry.list_agents()

    if os.getenv("USE_ORCHESTRATE", "false").lower() != "true":
        return static

    # Fetch live Orchestrate agents — falls back to [] on any error
    from services import orchestrate_client as oc
    live_agents = oc.list_agents()
    # Build a set of live agent names for fast lookup (Orchestrate uses display names)
    live_names = {a.get("name", "").lower() for a in live_agents}
    live_names |= {a.get("display_name", "").lower() for a in live_agents}

    # Annotate each static agent with orchestrate_live status
    for agent in static:
        display = agent.get("display_name", "").lower()
        name = agent.get("name", "").lower()
        agent["orchestrate_live"] = display in live_names or name in live_names

    logger.info(
        "registry: %d agents returned (%d confirmed live in Orchestrate)",
        len(static),
        sum(1 for a in static if a.get("orchestrate_live")),
    )
    return static


@router.post("/pipeline")
def run_pipeline(body: PipelineRequest) -> StreamingResponse:
    """
    Run the full analysis pipeline: Financial → Risk → Packaging → Review.
    Returns an NDJSON stream of progress events so the frontend can update
    progressively without waiting for all four agents to complete.
    """
    logger.info("POST /agent/pipeline session=%s", body.session_id)
    return StreamingResponse(
        agent_service.run_pipeline_stream(body.session_id, body.message),
        media_type="application/x-ndjson",
    )


@router.post("/{agent_name}")
def invoke_agent(agent_name: str, body: AgentRequest) -> AgentResponse:
    """Invoke an agent — conversation turn or ad-hoc action message."""
    logger.info(
        "POST /agent/%s session=%s msg_len=%d action=%s",
        agent_name, body.session_id, len(body.message), body.action_type or "chat",
    )

    # When action_type is set, auto-resolve save_path from agent's action_map
    save_path = body.save_path
    if body.action_type and not save_path:
        agent_cfg = agent_registry.get_agent(agent_name)
        action_map = agent_cfg.get("action_map", {})
        save_path = action_map.get(body.action_type, agent_cfg["output_path"])

    result = agent_service.run(
        agent_name=agent_name,
        message=body.message,
        session_id=body.session_id,
        messages=body.messages,
        save_to_workspace=body.save_to_workspace or bool(body.action_type),
        save_path=save_path,
        action_type=body.action_type,
        tools=body.tools,
    )
    return AgentResponse(
        reply=result["reply"],
        agent_name=agent_name,
        session_id=body.session_id,
        saved_to=result.get("saved_to"),
    )


@router.post("/{agent_name}/run")
def run_agent(
    agent_name: str,
    body: AgentRequest,
    background_tasks: BackgroundTasks,
) -> AgentResponse:
    """Single-shot run — always saves primary output; queues sub-saves for financial agent."""
    agent = agent_registry.get_agent(agent_name)
    save_path = body.save_path or agent["output_path"]
    logger.info(
        "POST /agent/%s/run session=%s → primary save: %s",
        agent_name, body.session_id, save_path,
    )

    result = agent_service.run(
        agent_name=agent_name,
        message=body.message or f"Run {agent['display_name']} — generate comprehensive analysis.",
        session_id=body.session_id,
        messages=body.messages,
        save_to_workspace=True,
        save_path=save_path,
        tools=body.tools,
    )

    # Financial agent: queue individual action analyses as background tasks
    queued_paths: list[str] = []
    if agent_name == "financial" and "action_map" in agent:
        for action_type, action_path in agent["action_map"].items():
            background_tasks.add_task(
                agent_service.run_action_save,
                agent_name,
                action_type,
                action_path,
                body.session_id,
            )
            queued_paths.append(action_path)
        logger.info(
            "POST /agent/%s/run: queued %d background action saves",
            agent_name, len(queued_paths),
        )

    # Risk agent: parse scores from narrative, compute SLACR JSON, save analysis
    if agent_name == "risk":
        narrative = result["reply"]
        parsed = _parse_slacr_scores(narrative)
        slacr_input = SlacrInput(**parsed, notes={})
        slacr_output = slacr_service.compute(slacr_input, ai_narrative=narrative)
        slacr_service.save(slacr_output)
        workspace_service.write_file("SLACR/slacr_analysis.md", narrative)
        logger.info(
            "POST /agent/risk/run: SLACR JSON + analysis saved (score=%.2f %s)",
            slacr_output.weighted_score, slacr_output.rating,
        )

    all_files = ([save_path] + queued_paths) if queued_paths else None

    return AgentResponse(
        reply=result["reply"],
        agent_name=agent_name,
        session_id=body.session_id,
        saved_to=result.get("saved_to"),
        saved_files=all_files,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLACR_DIMENSION_MAP = {
    r"[Ss]ponsor|[Mm]anagement [Qq]uality":       "strength",
    r"[Ll]everage|[Cc]apitalization":              "leverage",
    r"[Aa]sset [Qq]uality|[Cc]ollateral":          "collateral",
    r"[Cc]ash [Ff]low|[Rr]epayment [Cc]apacity":  "ability_to_repay",
    r"[Ii]ndustry|[Mm]arket [Rr]isk":             "risk_factors",
}


def _parse_slacr_scores(text: str) -> dict:
    """
    Parse dimension scores from SLACR agent output (agent scale: 5=best, 1=worst)
    and convert to service scale (1=best, 5=worst) via: service_score = 6 - agent_score.
    Falls back to 3 (neutral) for any dimension not found.
    """
    rows = re.findall(r"\|([^|]+)\|[^|]*\|\s*(\d)\s*\|", text)
    result: dict[str, int] = {}
    for label, score_str in rows:
        agent_score = int(score_str)
        service_score = max(1, min(5, 6 - agent_score))
        for pattern, field in _SLACR_DIMENSION_MAP.items():
            if field not in result and re.search(pattern, label, re.IGNORECASE):
                result[field] = service_score
                break
    for field in ("strength", "leverage", "ability_to_repay", "collateral", "risk_factors"):
        result.setdefault(field, 3)
    return result
