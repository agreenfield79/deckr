"""
Interpret router — Neural SLACR model + Interpreter Agent.

POST /api/interpret/run
    1. Load SLACR/slacr.json   (5 SLACR dimension scores)
    2. Load Financials/extracted_data.json  (DSCR, D/E, current ratio, EBITDA margin)
    3. Run ml.neural_slacr.run(inputs) deterministically
    4. Write SLACR/neural_slacr_output.json (workspace sidecar for context injection)
    4b. Write template narrative to Agent Notes/neural_slacr.md (guaranteed baseline)
    5. Invoke interpreter agent via agent_service.run() — may overwrite with richer AI narrative
    6. Return NeuralSlacrOutput JSON for frontend chart rendering

GET /api/interpret/output
    Read SLACR/neural_slacr_output.json without re-triggering the model.
    Allows InterpretTab to display last-run results on mount.
"""

import json
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ml import neural_slacr
from models.neural_slacr_output import NeuralSlacrOutput
from services import agent_service, workspace_service
from services.limiter import limiter

router = APIRouter()
logger = logging.getLogger("deckr.routers.interpret")

_OUTPUT_PATH = "SLACR/neural_slacr_output.json"
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
    "Your ONLY tool call must be: save_to_workspace with path='Agent Notes/neural_slacr.md' "
    "and the complete narrative as the content argument. "
    "After saving, reply with one sentence confirming the file was saved."
)

# Feature descriptions for the template narrative
_FEATURE_DESC: dict[str, str] = {
    "Strength":          "sponsor / business strength",
    "Leverage":          "leverage position",
    "Ability to Repay":  "cash flow / ability to repay",
    "Collateral":        "collateral quality",
    "Risk Factors":      "external risk factors",
    "DSCR":              "debt service coverage ratio (higher = stronger coverage)",
    "D/E Ratio":         "debt-to-equity ratio (lower = less leveraged)",
    "Current Ratio":     "current ratio / short-term liquidity",
    "EBITDA Margin":     "EBITDA margin (higher = stronger profitability)",
}

_COMPOSITE_BANDS = [
    (1.75, "Low Risk"),
    (2.50, "Moderate Risk"),
    (3.25, "Elevated Risk"),
    (4.00, "High Risk"),
    (5.00, "Decline"),
]


def _composite_band(score: float) -> str:
    for threshold, label in _COMPOSITE_BANDS:
        if score <= threshold:
            return label
    return "Decline"


def _generate_template_narrative(result: dict) -> str:
    """
    Build a structured Markdown narrative directly from NeuralSlacrOutput data.

    This is written to Agent Notes/neural_slacr.md immediately after the ML run,
    guaranteeing content is always available even when the interpreter agent's
    save_to_workspace tool call fails (a known GPT-OSS-120B empty-arg pattern).
    The agent overwrites this file with a richer AI narrative if its tool call succeeds.
    """
    rating       = result.get("predicted_rating", "Unknown")
    probability  = result.get("probability", 0.0)
    composite    = result.get("composite_score", 0.0)
    comp_band    = _composite_band(composite)
    shap         = result.get("shap_values", {})
    lime         = result.get("lime_coefficients", {})
    importances  = result.get("feature_importances", [])
    distribution = result.get("score_distribution", [])
    input_vals   = result.get("input_values", {})
    today        = date.today().strftime("%B %d, %Y")

    # Top 3 SHAP contributors by absolute value
    top_shap = sorted(shap.items(), key=lambda x: abs(x[1]), reverse=True)[:3]

    # This deal's distribution band
    deal_band_row = next((d for d in distribution if d["rating"] == rating), None)
    deal_pct = deal_band_row["percentage"] if deal_band_row else 0.0

    # Divergence check
    divergence = comp_band != rating

    # --- Paragraph 1: Prediction summary ---
    p1 = (
        f"The Neural SLACR model predicts a **{rating}** classification for this deal "
        f"with **{probability * 100:.1f}% confidence** as of {today}. "
        f"The analyst-scored SLACR composite is **{composite:.2f}**, which falls in the "
        f"**{comp_band}** band under standard SLACR thresholds. "
    )
    if divergence:
        p1 += (
            f"The model's prediction ({rating}) diverges from the analyst composite band "
            f"({comp_band}), indicating that non-linear feature interactions or financial "
            f"ratio signals are shifting the ML assessment relative to the dimension-score-only composite."
        )
    else:
        p1 += (
            f"The model's prediction aligns with the analyst composite band, providing "
            f"independent ML validation of the SLACR score."
        )

    # --- Paragraph 2: SHAP drivers ---
    if top_shap and any(v != 0.0 for _, v in top_shap):
        shap_lines = []
        for feat, val in top_shap:
            direction = "increases predicted risk" if val > 0 else "reduces predicted risk"
            desc = _FEATURE_DESC.get(feat, feat.lower())
            shap_lines.append(
                f"**{feat}** (SHAP {val:+.4f}) — a positive contribution reflecting {desc}, "
                f"which {direction}"
            )
        p2 = (
            "The SHAP waterfall analysis identifies the three features with the greatest "
            f"influence on this prediction. {shap_lines[0]}. "
        )
        if len(shap_lines) > 1:
            p2 += f"{shap_lines[1]}. "
        if len(shap_lines) > 2:
            p2 += f"{shap_lines[2]}. "
        p2 += (
            "Features with negative SHAP values act as risk mitigants within the model's "
            "learned decision boundary, partially offsetting positive contributors."
        )
    else:
        p2 = (
            "SHAP values were not computed for this run (the shap package may not be "
            "installed in the backend environment). Install with: pip install shap. "
            "The global feature importances chart above shows the model's overall learned "
            "feature weights across the full training set."
        )

    # --- Paragraph 3: LIME ---
    lime_nonzero = {k: v for k, v in lime.items() if v != 0.0}
    if lime_nonzero:
        top_lime = sorted(lime_nonzero.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        lime_desc = "; ".join(
            f"{feat} ({val:+.4f})" for feat, val in top_lime
        )
        p3 = (
            f"The LIME local linear approximation confirms the model's reasoning at this "
            f"specific operating point. The strongest local coefficients are: {lime_desc}. "
            f"Positive LIME coefficients reinforce the predicted class; negative coefficients "
            f"represent countervailing local factors. Because LIME fits a surrogate linear model "
            f"in the neighborhood of this deal's feature vector, these coefficients reflect "
            f"how sensitive the prediction boundary is to small changes in each input."
        )
    else:
        p3 = (
            "LIME coefficients were not computed for this run (the lime package may not be "
            "installed). Install with: pip install lime. The SHAP values above provide the "
            "primary feature attribution signal for this analysis."
        )

    # --- Paragraph 4: Score distribution ---
    p4 = (
        f"Relative to the model's 800-record synthetic training distribution, the **{rating}** "
        f"band accounts for **{deal_pct:.1f}%** of all training predictions. "
    )
    other_bands = [d for d in distribution if d["rating"] != rating and d["count"] > 0]
    if other_bands:
        largest_other = max(other_bands, key=lambda x: x["count"])
        p4 += (
            f"The most populated band in the training set is **{largest_other['rating']}** "
            f"at {largest_other['percentage']:.1f}%. "
        )
    p4 += (
        "This deal's input feature vector — particularly the SLACR dimension scores of "
        + ", ".join(
            f"{feat}: {input_vals.get(feat, 'N/A')}"
            for feat in ["Strength", "Leverage", "Ability to Repay", "Collateral", "Risk Factors"]
        )
        + f" — places it {'firmly within' if probability > 0.65 else 'near the boundary of'} "
        f"the {rating} classification."
    )

    # --- Paragraph 5: Divergence analysis ---
    if divergence:
        p5 = (
            f"The divergence between the ML-predicted **{rating}** and the analyst-composite "
            f"**{comp_band}** (composite score {composite:.2f}) warrants attention. "
            f"The SLACR composite is a purely linear weighted average of five dimension scores, "
            f"while the Random Forest model captures non-linear interactions between all nine "
            f"input features including the financial ratios (DSCR, D/E ratio, current ratio, "
            f"EBITDA margin). When financial ratios signal stronger or weaker credit quality "
            f"than the analyst dimension scores alone, the model will produce a divergent rating. "
            f"Review the SHAP waterfall above to identify which financial ratio features are "
            f"driving the ML prediction away from the composite."
        )
    else:
        p5 = (
            f"The ML model's **{rating}** prediction aligns with the analyst-scored composite "
            f"band ({comp_band}, composite {composite:.2f}), providing independent quantitative "
            f"support for the manual SLACR assessment. The financial ratio inputs — where "
            f"available — are consistent with the dimension score profile. This convergence "
            f"increases confidence in the overall risk classification and supports the credit "
            f"decision implied by the SLACR composite."
        )

    lines = [
        f"# Neural SLACR Model Interpretation",
        f"*Generated {today} · Predicted: {rating} ({probability * 100:.1f}%) · Composite: {composite:.2f} ({comp_band})*",
        "",
        p1,
        "",
        p2,
        "",
        p3,
        "",
        p4,
        "",
        p5,
        "",
        "---",
        "*Generated with AI assistance (IBM watsonx). "
        "All figures should be independently verified prior to "
        "credit committee submission or lender distribution.*",
    ]
    return "\n".join(lines)


class RunRequest(BaseModel):
    session_id: str = "default"


def _parse_financial_ratios(inputs: dict) -> None:
    """
    Parse DSCR, D/E ratio, current ratio, and EBITDA margin from
    Financials/extracted_data.json and merge into the inputs dict in-place.
    Uses the latest fiscal year available.  Silently skips missing fields.
    """
    try:
        raw = workspace_service.read_file("Financials/extracted_data.json")
        fin = json.loads(raw)
        years = fin.get("fiscal_years", [])
        latest = years[-1] if years else None
        if not latest:
            return

        def _v(section: str, key: str) -> float | None:
            try:
                val = fin[section][key][latest]
                return float(val) if val is not None else None
            except Exception:
                return None

        op_cf      = _v("cash_flow_statement", "operating_cash_flow")
        interest   = _v("income_statement", "interest_expense")
        debt       = _v("balance_sheet", "total_debt")
        equity     = _v("balance_sheet", "total_equity")
        cur_assets = _v("balance_sheet", "current_assets")
        cur_liab   = _v("balance_sheet", "current_liabilities")
        revenue    = _v("income_statement", "revenue")
        ebitda     = _v("income_statement", "ebitda")

        if op_cf is not None and interest and interest != 0:
            inputs["dscr"] = round(op_cf / interest, 3)
        if debt is not None and equity and equity != 0:
            inputs["de_ratio"] = round(debt / equity, 3)
        if cur_assets is not None and cur_liab and cur_liab != 0:
            inputs["current_ratio"] = round(cur_assets / cur_liab, 3)
        if revenue and ebitda is not None and revenue != 0:
            inputs["ebitda_margin"] = round(ebitda / revenue, 4)

    except Exception as e:
        logger.warning("interpret: could not parse extracted_data.json — %s", e)


@router.post("/run", response_model=NeuralSlacrOutput)
@limiter.limit("2/minute")
def run_interpreter(request: Request, body: RunRequest):
    # --- 1. Load SLACR dimension scores ---
    inputs: dict[str, float] = {}
    try:
        raw = workspace_service.read_file("SLACR/slacr.json")
        slacr = json.loads(raw)
        inp = slacr.get("input", slacr)
        for field in ("strength", "leverage", "ability_to_repay", "collateral", "risk_factors"):
            if field in inp and inp[field] is not None:
                inputs[field] = float(inp[field])
    except Exception as e:
        logger.warning("interpret: SLACR/slacr.json not available — using defaults (%s)", e)

    # --- 2. Parse financial ratios ---
    _parse_financial_ratios(inputs)
    logger.info("interpret: feature inputs resolved: %s", inputs)

    # --- 3. Run ML model ---
    try:
        result_dict = neural_slacr.run(inputs)
    except Exception as e:
        logger.error("interpret: neural_slacr.run failed — %s", e)
        raise HTTPException(status_code=500, detail=f"Neural SLACR model error: {e}")

    # --- 4. Persist ML output to workspace ---
    try:
        workspace_service.write_file(_OUTPUT_PATH, json.dumps(result_dict, indent=2))
        logger.info(
            "interpret: wrote %s — rating=%s prob=%.3f",
            _OUTPUT_PATH,
            result_dict.get("predicted_rating"),
            result_dict.get("probability", 0),
        )
    except Exception as e:
        logger.warning("interpret: could not write %s — %s", _OUTPUT_PATH, e)

    # --- 4b. Write guaranteed template narrative ---
    # GPT-OSS-120B reliably calls save_to_workspace with empty args (documented Phase 27/28).
    # Writing a template-generated narrative here ensures the Interpret tab always has
    # content to display.  The agent call in step 5 may overwrite this with a richer version.
    try:
        template_narrative = _generate_template_narrative(result_dict)
        workspace_service.write_file(_NARRATIVE_PATH, template_narrative)
        logger.info("interpret: template narrative written → %s", _NARRATIVE_PATH)
    except Exception as e:
        logger.warning("interpret: could not write template narrative — %s", e)

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
