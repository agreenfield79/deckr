from pydantic import BaseModel


class AgentRequest(BaseModel):
    message: str
    agent_name: str
    session_id: str                   # UUID — required from Day 1; becomes Orchestrate memory scope in Phase 12
    messages: list[dict]              # full prior conversation history sent with every request
    save_to_workspace: bool = False
    save_path: str | None = None
    tools: list[dict] | None = None   # reserved for Phase 13 tool calling


class AgentResponse(BaseModel):
    reply: str
    agent_name: str
    session_id: str
    saved_to: str | None = None
