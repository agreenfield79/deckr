import logging

from fastapi import APIRouter

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
    """Invoke an agent — conversation turn or ad-hoc message."""
    logger.info(
        "POST /agent/%s session=%s msg_len=%d",
        agent_name, body.session_id, len(body.message),
    )
    result = agent_service.run(
        agent_name=agent_name,
        message=body.message,
        session_id=body.session_id,
        messages=body.messages,
        save_to_workspace=body.save_to_workspace,
        save_path=body.save_path,
    )
    return AgentResponse(
        reply=result["reply"],
        agent_name=agent_name,
        session_id=body.session_id,
        saved_to=result.get("saved_to"),
    )


@router.post("/{agent_name}/run")
def run_agent(agent_name: str, body: AgentRequest) -> AgentResponse:
    """Single-shot run — always saves output to the agent's registered output_path."""
    agent = agent_registry.get_agent(agent_name)
    save_path = body.save_path or agent["output_path"]
    logger.info(
        "POST /agent/%s/run session=%s → saved to %s",
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
    return AgentResponse(
        reply=result["reply"],
        agent_name=agent_name,
        session_id=body.session_id,
        saved_to=result.get("saved_to"),
    )
