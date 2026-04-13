import logging
import os
import time

import requests
from fastapi import HTTPException

from services.token_cache import token_cache

logger = logging.getLogger("deckr.watsonx_client")

SUPPORTED_MODELS = {
    "granite":   "ibm/granite-3-8b-instruct",
    "llama-70b": "meta-llama/llama-3-3-70b-instruct",
    "mistral":   "mistralai/mistral-large",
    "llama-3b":  "meta-llama/llama-3-2-3b-instruct",
}


def _base_url() -> str:
    return os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")


def _api_version() -> str:
    return os.getenv("WATSONX_API_VERSION", "2024-05-31")


def _project_id() -> str:
    pid = os.getenv("WATSONX_PROJECT_ID")
    if not pid:
        raise HTTPException(status_code=500, detail="WATSONX_PROJECT_ID not configured")
    return pid


def _resolve_model(model_key: str) -> str:
    return SUPPORTED_MODELS.get(model_key, SUPPORTED_MODELS["granite"])


def chat(messages: list[dict], model_key: str, params: dict, tools: list[dict] | None = None) -> dict:
    """
    Multi-turn conversation via the watsonx /text/chat endpoint.

    When `tools` is provided the request includes tool definitions and the raw
    response is returned as a dict so the caller can inspect tool_calls.
    When `tools` is None the plain reply string is returned inside {"reply": ...}.
    """
    token = token_cache.get_token()
    url = f"{_base_url()}/ml/v1/text/chat?version={_api_version()}"
    body = {
        "model_id": _resolve_model(model_key),
        "project_id": _project_id(),
        "messages": messages,
        "parameters": {
            "max_new_tokens": params.get("max_new_tokens", 1000),
            "time_limit": params.get("time_limit", 30000),
        },
    }
    if tools:
        body["tools"] = tools
    t0 = time.time()
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        elapsed = int((time.time() - t0) * 1000)
        resp.raise_for_status()
        data = resp.json()
        logger.info("watsonx.chat: model=%s elapsed=%dms", model_key, elapsed)
        choice_msg = data["choices"][0]["message"]
        return {
            "reply":      choice_msg.get("content") or "",
            "tool_calls": choice_msg.get("tool_calls") or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        logger.error("watsonx.chat: upstream error — %s elapsed=%dms", type(e).__name__, elapsed)
        raise HTTPException(
            status_code=502,
            detail="AI service temporarily unavailable. Please try again.",
        )


def generate(prompt: str, model_key: str, params: dict) -> str:
    """Single-shot generation via the watsonx /text/generation endpoint."""
    token = token_cache.get_token()
    url = f"{_base_url()}/ml/v1/text/generation?version={_api_version()}"
    # Full-deck generation needs a larger token budget
    is_full_package = params.get("action_type") == "full_package"
    max_new_tokens = 4000 if is_full_package else params.get("max_new_tokens", 1500)
    body = {
        "model_id": _resolve_model(model_key),
        "project_id": _project_id(),
        "input": prompt,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "time_limit": params.get("time_limit", 30000),
        },
    }
    t0 = time.time()
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
        elapsed = int((time.time() - t0) * 1000)
        resp.raise_for_status()
        logger.info(
            "watsonx.generate: model=%s max_tokens=%d elapsed=%dms",
            model_key, max_new_tokens, elapsed,
        )
        return resp.json()["results"][0]["generated_text"]
    except HTTPException:
        raise
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        logger.error("watsonx.generate: upstream error — %s elapsed=%dms", type(e).__name__, elapsed)
        raise HTTPException(
            status_code=502,
            detail="AI service temporarily unavailable. Please try again.",
        )


def generate_stream(prompt: str, model_key: str, params: dict):
    """
    Stream text generation token-by-token via the ibm-watsonx-ai SDK.
    Uses ModelInference.generate_text_stream() which returns a generator of text chunks.
    Falls back gracefully if the SDK is unavailable.

    Intended use: wrap in FastAPI StreamingResponse for real-time output,
    e.g. for the pipeline endpoint when USE_ORCHESTRATE=false.
    """
    api_key = os.getenv("IBMCLOUD_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="IBMCLOUD_API_KEY not configured")

    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference
    except ImportError:
        logger.error("watsonx.generate_stream: ibm-watsonx-ai SDK not installed — run pip install ibm-watsonx-ai")
        raise HTTPException(
            status_code=500,
            detail="Streaming SDK not installed. Run: pip install ibm-watsonx-ai",
        )

    max_new_tokens = params.get("max_new_tokens", 1500)
    t0 = time.time()
    try:
        model = ModelInference(
            model_id=_resolve_model(model_key),
            credentials=Credentials(api_key=api_key, url=_base_url()),
            project_id=_project_id(),
            params={"max_new_tokens": max_new_tokens},
        )
        logger.info("watsonx.generate_stream: model=%s max_tokens=%d (streaming)", model_key, max_new_tokens)
        for chunk in model.generate_text_stream(prompt=prompt):
            yield chunk
        elapsed = int((time.time() - t0) * 1000)
        logger.info("watsonx.generate_stream: complete model=%s elapsed=%dms", model_key, elapsed)
    except HTTPException:
        raise
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        logger.error("watsonx.generate_stream: upstream error — %s elapsed=%dms", type(e).__name__, elapsed)
        raise HTTPException(
            status_code=502,
            detail="AI streaming service temporarily unavailable. Please try again.",
        )
