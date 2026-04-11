import logging

from fastapi import APIRouter, BackgroundTasks

from models.agent import AgentRequest, AgentResponse
from services import agent_registry, agent_service

logger = logging.getLogger("deckr.routers.agent")

router = APIRouter()


@router.get("/registry")
def get_registry():
    """Return all agent display names and capabilities."""
    return agent_registry.list_agents()


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

    all_files = ([save_path] + queued_paths) if queued_paths else None

    return AgentResponse(
        reply=result["reply"],
        agent_name=agent_name,
        session_id=body.session_id,
        saved_to=result.get("saved_to"),
        saved_files=all_files,
    )
