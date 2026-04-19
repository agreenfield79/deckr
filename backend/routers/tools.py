import logging

from fastapi import APIRouter, HTTPException

from models.tool import ToolRequest, ToolResponse
from services import tool_service

logger = logging.getLogger("deckr.routers.tools")

router = APIRouter()


@router.post("/{tool_name}")
def invoke_tool(tool_name: str, body: ToolRequest) -> ToolResponse:
    """
    Invoke a named tool with the provided inputs dict.

    Used both by agents (via tool dispatch loop in agent_service) and directly
    for testing individual tool endpoints via PowerShell / Postman.

    Available tools: save_to_workspace, get_file_content, list_uploaded_documents,
                     compute_slacr_score, search_workspace, search_web
    """
    logger.info("POST /tools/%s inputs_keys=%s", tool_name, list(body.inputs.keys()))
    try:
        result = tool_service.dispatch(tool_name, body.inputs)
        return ToolResponse(tool_name=tool_name, result=result)
    except HTTPException:
        raise  # Let 422 (missing save_to_workspace args) propagate so Orchestrate signals the model to retry
    except ValueError as e:
        logger.warning("tools.invoke: bad request for '%s' — %s", tool_name, e)
        return ToolResponse(tool_name=tool_name, result=None, error=str(e))
    except Exception as e:
        logger.error("tools.invoke: '%s' execution failed — %s", tool_name, e)
        return ToolResponse(
            tool_name=tool_name,
            result=None,
            error=f"Tool execution failed: {type(e).__name__}: {e}",
        )
