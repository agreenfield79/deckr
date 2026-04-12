import logging
import os
import time

import requests
from fastapi import HTTPException

from services.token_cache import TokenCache

logger = logging.getLogger("deckr.orchestrate_client")

# Independent token cache keyed to ORCHESTRATE_API_KEY.
# Completely separate from the watsonx.ai token_cache singleton in token_cache.py.
_orchestrate_token_cache = TokenCache(api_key_env_var="ORCHESTRATE_API_KEY")

# Agent ID map — populated from .env at startup.
# Values are the UUIDs assigned by Orchestrate when each agent is deployed.
# coordination is intentionally omitted — future Lender RFP agent, not yet deployed.
_AGENT_ID_MAP: dict[str, str | None] = {
    "packaging": os.getenv("ORCHESTRATE_AGENT_ID_PACKAGING"),
    "financial": os.getenv("ORCHESTRATE_AGENT_ID_FINANCIAL"),
    "risk":      os.getenv("ORCHESTRATE_AGENT_ID_RISK"),
    "review":    os.getenv("ORCHESTRATE_AGENT_ID_REVIEW"),
}


def _get_base_url() -> str:
    url = os.getenv("ORCHESTRATE_BASE_URL")
    if not url:
        raise RuntimeError(
            "ORCHESTRATE_BASE_URL is not set — required when USE_ORCHESTRATE=true"
        )
    return url.rstrip("/")


def invoke_agent(agent_name: str, messages: list[dict], session_id: str) -> dict:
    """
    Invoke a deployed Orchestrate agent via REST API.

    REST endpoint:
        POST {ORCHESTRATE_BASE_URL}/v1/orchestrate/{agent_id}/chat/completions

    Messages: full conversation history built by agent_service — context in first
    message, prior turns included, current message appended. This is more reliable
    than relying solely on X-IBM-THREAD-ID server-side thread memory.

    Memory: X-IBM-THREAD-ID = session_id is still sent for any supplemental
    server-side memory, but conversation continuity is ensured by the explicit
    messages array.
    """
    agent_id = _AGENT_ID_MAP.get(agent_name)
    if not agent_id:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Orchestrate agent '{agent_name}' is not configured. "
                f"Set ORCHESTRATE_AGENT_ID_{agent_name.upper()} in backend/.env."
            ),
        )

    base_url = _get_base_url()
    url = f"{base_url}/v1/orchestrate/{agent_id}/chat/completions"

    try:
        token = _orchestrate_token_cache.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-IBM-THREAD-ID": session_id,
            "Content-Type": "application/json",
        }
        payload = {
            "messages": messages,
            "stream": False,
        }

        t0 = time.time()
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        elapsed_ms = int((time.time() - t0) * 1000)
        resp.raise_for_status()

        data = resp.json()
        reply = data["choices"][0]["message"]["content"]

        logger.info(
            "orchestrate.invoke: agent=%s session=%s elapsed=%dms",
            agent_name, session_id, elapsed_ms,
        )
        return {"reply": reply}

    except HTTPException:
        raise
    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else "unknown"
        error_body = ""
        if e.response is not None:
            try:
                error_body = e.response.text[:600]
            except Exception:
                pass
        logger.error(
            "orchestrate.invoke: HTTP error agent=%s status=%s body=%s",
            agent_name, status_code, error_body,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Orchestrate upstream error (HTTP {status_code})",
        )
    except Exception as e:
        logger.error(
            "orchestrate.invoke: unexpected error agent=%s — %s",
            agent_name, type(e).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Orchestrate connection error — check ORCHESTRATE_BASE_URL and API key",
        )


def list_agents() -> list[dict]:
    """
    Fetch the live agent list from Orchestrate.

    GET {ORCHESTRATE_BASE_URL}/api/v1/orchestrate/agents

    Returns a list of Orchestrate agent objects. Falls back to an empty list on
    any error so the caller (registry endpoint) can merge safely with the static dict.
    """
    try:
        base_url = _get_base_url()
        url = f"{base_url}/v1/orchestrate/agents"
        token = _orchestrate_token_cache.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        agents = resp.json()
        result = agents if isinstance(agents, list) else []
        logger.info("orchestrate.list_agents: %d agents found", len(result))
        return result
    except Exception as e:
        logger.warning(
            "orchestrate.list_agents: failed (%s) — falling back to static registry",
            type(e).__name__,
        )
        return []


def configured_agent_ids() -> dict[str, bool]:
    """Return which agents have their IDs configured in .env."""
    return {name: bool(agent_id) for name, agent_id in _AGENT_ID_MAP.items()}
