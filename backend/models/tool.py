from typing import Any

from pydantic import BaseModel


class ToolRequest(BaseModel):
    inputs: dict[str, Any] = {}   # tool_name comes from URL path, not body


class ToolResponse(BaseModel):
    tool_name: str
    result: Any = None
    error: str | None = None
