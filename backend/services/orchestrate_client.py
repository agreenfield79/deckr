# orchestrate_client.py
# Phase 12 activation: set USE_ORCHESTRATE=true and install ibm-watsonx-orchestrate-adk
# pip install ibm-watsonx-orchestrate-adk (see requirements.txt comment)


def invoke_agent(agent_name: str, message: str, session_id: str) -> dict:
    raise NotImplementedError("Orchestrate client — activate USE_ORCHESTRATE=true in Phase 12")


def get_agent_memory(session_id: str) -> dict:
    raise NotImplementedError("Orchestrate memory — Phase 12")
