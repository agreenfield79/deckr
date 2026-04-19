"""
Interpret router — Neural SLACR model + Interpreter Agent.

POST /api/interpret/run
    1. Calls interpret_service.run_neural_slacr_pipeline() which:
       a. Loads SLACR/slacr.json and Financials/extracted_data.json
       b. Runs ml.neural_slacr.run(inputs) deterministically
       c. Writes SLACR/neural_slacr_output.json (workspace sidecar for context injection)
       d. Writes template narrative to Agent Notes/neural_slacr.md (guaranteed baseline)
    2. Invokes interpreter agent via agent_service.run() — may overwrite with richer AI narrative
    3. Returns NeuralSlacrOutput JSON for frontend chart rendering

    Note: the same run_neural_slacr_pipeline() is called as a pre-hook by the pipeline
    (agent_service.py) when the interpreter stage runs automatically after the risk agent.

GET /api/interpret/output
    Read SLACR/neural_slacr_output.json without re-triggering the model.
    Allows InterpretTab to display last-run results on mount.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from models.neural_slacr_output import NeuralSlacrOutput
from services import agent_service, workspace_service
from services.interpret_service import run_neural_slacr_pipeline
from services.limiter import limiter

router = APIRouter()
logger = logging.getLogger("deckr.routers.interpret")

_OUTPUT_PATH    = "SLACR/neural_slacr_output.json"
_NARRATIVE_PATH = "Agent Notes/neural_slacr.md"

_INTERPRET_PROMPT = (
    "Run Interpreter Agent. "
    "The Neural SLACR model output JSON is already pre-loaded in your context "
    "under '--- NEURAL SLACR OUTPUT (SLACR/neural_slacr_output.json) ---'. "
    "DO NOT call get_file_content — the model output is already in your context above. "
    "Your task: write a clear, plain-language narrative (4–6 prose paragraphs) that "
    "interprets these ML results for a credit analyst. Address: "
    "(1) the predicted risk rating and the model's confidence level, "
    "(2) which input features most drive the prediction — cite the top 3 SHAP contributors "
    "by name and sign (positive = risk-increasing, negative = risk-reducing), "
    "(3) what the LIME local explanation reveals about this deal's feature profile, "
    "(4) how this deal's predicted band compares to the overall training distribution "
    "(e.g., 'this deal falls in the Moderate Risk band, which represents N% of training records'), "
    "and (5) any notable divergence between the model's predicted rating and the analyst-scored "
    "SLACR composite score — explain possible causes. "
    "Write in prose paragraphs only — no bullet lists, no headers, no markdown tables. "
    "Cite actual numbers from the pre-loaded JSON. "
    "Your ONLY tool call must be save_to_workspace. "
    "Provide inputs.path = 'Agent Notes/neural_slacr.md' "
    "and inputs.content = your complete narrative text. "
    "If the tool returns an error, retry once with the correct arguments. "
    "Do not call save_to_workspace more than once. "
    "After saving, reply with one sentence confirming the file was saved."
)


class RunRequest(BaseModel):
    session_id: str = "default"


@router.post("/run", response_model=NeuralSlacrOutput)
@limiter.limit("2/minute")
def run_interpreter(request: Request, body: RunRequest):
    # --- 1–4b. Run ML inference + write output files ---
    try:
        result_dict = run_neural_slacr_pipeline()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # --- 5. Invoke interpreter agent (best-effort AI enrichment) ---
    # Agent may overwrite the template narrative with a richer AI version.
    # Non-fatal: template narrative is already in place if this fails.
    try:
        agent_service.run(
            agent_name="interpreter",
            message=_INTERPRET_PROMPT,
            session_id=body.session_id,
            messages=[],
            save_to_workspace=True,
            save_path=_NARRATIVE_PATH,
        )
        logger.info("interpret: interpreter agent completed → %s", _NARRATIVE_PATH)
    except Exception as e:
        logger.warning("interpret: interpreter agent failed (non-fatal, template in place) — %s", e)

    # --- 6. Return structured output ---
    return NeuralSlacrOutput(**result_dict)


@router.get("/output", response_model=NeuralSlacrOutput)
def get_output():
    """
    Return the last-run SLACR/neural_slacr_output.json without re-triggering the model.
    InterpretTab calls this on mount to restore state from a prior run.

    Fix: workspace_service raises HTTPException(404) — not FileNotFoundError — when the
    file doesn't exist. Re-raise HTTPException directly so the 404 propagates to the
    frontend (instead of being caught by the generic Exception handler and re-raised as 500).
    """
    try:
        raw = workspace_service.read_file(_OUTPUT_PATH)
        data = json.loads(raw)
        return NeuralSlacrOutput(**data)
    except HTTPException:
        # Let workspace_service's 404 propagate as-is to the frontend
        raise
    except Exception as e:
        logger.error("interpret/output: could not read %s — %s", _OUTPUT_PATH, e)
        raise HTTPException(status_code=500, detail=f"Could not read output: {e}")
