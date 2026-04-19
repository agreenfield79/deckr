"""
interpret_service.py — Neural SLACR ML inference service.

Extracted from routers/interpret.py so the pipeline (agent_service.py) can
call the ML inference step directly without an HTTP round-trip and without
creating a circular import.

Public API
----------
run_neural_slacr_pipeline() -> dict
    Load SLACR scores + financial ratios, run the ML model, write both
    output files to the workspace, and return the result dict.
    Raises RuntimeError on ML model failure (allows callers to decide
    whether to skip downstream steps or abort).
"""

import json
import logging
from datetime import date

from ml import neural_slacr
from services import workspace_service

logger = logging.getLogger("deckr.interpret_service")

_OUTPUT_PATH   = "SLACR/neural_slacr_output.json"
_NARRATIVE_PATH = "Agent Notes/neural_slacr.md"

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


def parse_financial_ratios(inputs: dict) -> None:
    """
    Merge DSCR, D/E ratio, current ratio, and EBITDA margin from
    Financials/extracted_data.json into the inputs dict in-place.
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
        logger.warning("interpret_service: could not parse extracted_data.json — %s", e)


def generate_template_narrative(result: dict) -> str:
    """
    Build a structured Markdown narrative directly from NeuralSlacrOutput data.

    Written to Agent Notes/neural_slacr.md immediately after the ML run as a
    guaranteed baseline.  The interpreter agent may overwrite with a richer
    AI narrative if its save_to_workspace tool call succeeds.
    """
    rating       = result.get("predicted_rating", "Unknown")
    probability  = result.get("probability", 0.0)
    composite    = result.get("composite_score", 0.0)
    comp_band    = _composite_band(composite)
    shap         = result.get("shap_values", {})
    lime         = result.get("lime_coefficients", {})
    distribution = result.get("score_distribution", [])
    input_vals   = result.get("input_values", {})
    today        = date.today().strftime("%B %d, %Y")

    top_shap = sorted(shap.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    deal_band_row = next((d for d in distribution if d["rating"] == rating), None)
    deal_pct = deal_band_row["percentage"] if deal_band_row else 0.0
    divergence = comp_band != rating

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
            "The model's prediction aligns with the analyst composite band, providing "
            "independent ML validation of the SLACR score."
        )

    if top_shap and any(v != 0.0 for _, v in top_shap):
        shap_lines = []
        for feat, val in top_shap:
            direction = "increases predicted risk" if val > 0 else "reduces predicted risk"
            desc = _FEATURE_DESC.get(feat, feat.lower())
            shap_lines.append(
                f"**{feat}** (SHAP {val:+.4f}) — {desc}, which {direction}"
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
            "installed in the backend environment). Install with: pip install shap."
        )

    lime_nonzero = {k: v for k, v in lime.items() if v != 0.0}
    if lime_nonzero:
        top_lime = sorted(lime_nonzero.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        lime_desc = "; ".join(f"{feat} ({val:+.4f})" for feat, val in top_lime)
        p3 = (
            f"The LIME local linear approximation confirms the model's reasoning at this "
            f"specific operating point. The strongest local coefficients are: {lime_desc}. "
            f"Positive LIME coefficients reinforce the predicted class; negative coefficients "
            f"represent countervailing local factors."
        )
    else:
        p3 = (
            "LIME coefficients were not computed for this run (the lime package may not be "
            "installed). Install with: pip install lime."
        )

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

    if divergence:
        p5 = (
            f"The divergence between the ML-predicted **{rating}** and the analyst-composite "
            f"**{comp_band}** (composite score {composite:.2f}) warrants attention. "
            f"The SLACR composite is a purely linear weighted average of five dimension scores, "
            f"while the Random Forest model captures non-linear interactions between all nine "
            f"input features including the financial ratios (DSCR, D/E ratio, current ratio, "
            f"EBITDA margin). Review the SHAP waterfall above to identify which financial ratio "
            f"features are driving the ML prediction away from the composite."
        )
    else:
        p5 = (
            f"The ML model's **{rating}** prediction aligns with the analyst-scored composite "
            f"band ({comp_band}, composite {composite:.2f}), providing independent quantitative "
            f"support for the manual SLACR assessment. This convergence increases confidence in "
            f"the overall risk classification and supports the credit decision implied by the "
            f"SLACR composite."
        )

    lines = [
        "# Neural SLACR Model Interpretation",
        f"*Generated {today} · Predicted: {rating} ({probability * 100:.1f}%) · Composite: {composite:.2f} ({comp_band})*",
        "",
        p1, "",
        p2, "",
        p3, "",
        p4, "",
        p5, "",
        "---",
        "*Generated with AI assistance (IBM watsonx). "
        "All figures should be independently verified prior to "
        "credit committee submission or lender distribution.*",
    ]
    return "\n".join(lines)


def run_neural_slacr_pipeline() -> dict:
    """
    Run the full Neural SLACR inference pipeline synchronously.

    Steps:
      1. Load SLACR/slacr.json dimension scores
      2. Merge financial ratios from extracted_data.json
      3. Run neural_slacr.run(inputs)
      4. Write SLACR/neural_slacr_output.json
      4b. Write template narrative to Agent Notes/neural_slacr.md

    Returns the result dict on success.
    Raises RuntimeError if the ML model fails (callers skip the interpreter
    agent stage when this raises).

    Called by:
      - routers/interpret.py  (POST /api/interpret/run)
      - services/agent_service.py  (pipeline pre-hook before interpreter stage)
    """
    # 1. Load SLACR dimension scores
    inputs: dict[str, float] = {}
    try:
        raw = workspace_service.read_file("SLACR/slacr.json")
        slacr = json.loads(raw)
        inp = slacr.get("input", slacr)
        for field in ("strength", "leverage", "ability_to_repay", "collateral", "risk_factors"):
            if field in inp and inp[field] is not None:
                inputs[field] = float(inp[field])
    except Exception as e:
        logger.warning("interpret_service: SLACR/slacr.json not available — using defaults (%s)", e)

    # 2. Merge financial ratios
    parse_financial_ratios(inputs)
    logger.info("interpret_service: feature inputs resolved: %s", inputs)

    # 3. Run ML model
    try:
        result_dict = neural_slacr.run(inputs)
    except Exception as e:
        logger.error("interpret_service: neural_slacr.run failed — %s", e)
        raise RuntimeError(f"Neural SLACR model error: {e}") from e

    # 4. Persist ML output
    try:
        workspace_service.write_file(_OUTPUT_PATH, json.dumps(result_dict, indent=2))
        logger.info(
            "interpret_service: wrote %s — rating=%s prob=%.3f",
            _OUTPUT_PATH,
            result_dict.get("predicted_rating"),
            result_dict.get("probability", 0),
        )
    except Exception as e:
        logger.warning("interpret_service: could not write %s — %s", _OUTPUT_PATH, e)

    # 4b. Write guaranteed template narrative
    try:
        template_narrative = generate_template_narrative(result_dict)
        workspace_service.write_file(_NARRATIVE_PATH, template_narrative)
        logger.info("interpret_service: template narrative written → %s", _NARRATIVE_PATH)
    except Exception as e:
        logger.warning("interpret_service: could not write template narrative — %s", e)

    return result_dict
