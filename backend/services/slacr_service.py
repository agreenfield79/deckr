import json
import logging

from models.slacr import SlacrInput, SlacrOutput
from services import workspace_service

logger = logging.getLogger("deckr.slacr_service")

# Score: 1=best (Low Risk), 5=worst (Decline)
# Weights: S=0.20, L=0.20, A=0.25, C=0.15, R=0.20
_WEIGHTS = {
    "strength":        0.20,
    "leverage":        0.20,
    "ability_to_repay": 0.25,
    "collateral":      0.15,
    "risk_factors":    0.20,
}

# (upper_bound_inclusive, rating_label, decision_label)
_RATING_BANDS = [
    (1.75, "Low Risk",       "Approve"),
    (2.50, "Moderate Risk",  "Approve with conditions"),
    (3.25, "Elevated Risk",  "Further review required"),
    (4.00, "High Risk",      "Decline or restructure"),
    (5.00, "Decline",        "Reject"),
]

_MITIGANT_RULES: list[tuple[str, int, str]] = [
    ("strength",        4, "Require management experience documentation and personal financial guaranty"),
    ("leverage",        4, "Require equity injection to reduce leverage below policy threshold"),
    ("ability_to_repay", 4, "Require 6-month debt service reserve account funded at closing"),
    ("collateral",      4, "Require additional collateral pledge or personal unlimited guaranty"),
    ("risk_factors",    4, "Include industry-specific risk monitoring covenant and reporting requirements"),
]


def _get_rating(score: float) -> tuple[str, str]:
    for threshold, rating, decision in _RATING_BANDS:
        if score <= threshold:
            return rating, decision
    return "Decline", "Reject"


def compute(slacr_input: SlacrInput, ai_narrative: str = "") -> SlacrOutput:
    weighted_score = (
        slacr_input.strength        * _WEIGHTS["strength"]
        + slacr_input.leverage      * _WEIGHTS["leverage"]
        + slacr_input.ability_to_repay * _WEIGHTS["ability_to_repay"]
        + slacr_input.collateral    * _WEIGHTS["collateral"]
        + slacr_input.risk_factors  * _WEIGHTS["risk_factors"]
    )
    rating, decision = _get_rating(weighted_score)

    mitigants: list[str] = [
        msg
        for field, threshold, msg in _MITIGANT_RULES
        if getattr(slacr_input, field) >= threshold
    ]
    if not mitigants:
        mitigants = ["Standard monitoring and covenant compliance"]

    logger.info(
        "slacr.compute: score=%.2f rating=%s decision=%s",
        weighted_score, rating, decision,
    )
    return SlacrOutput(
        weighted_score=round(weighted_score, 2),
        rating=rating,
        decision=decision,
        mitigants=mitigants,
        ai_narrative=ai_narrative,
        input=slacr_input,
    )


def save(output: SlacrOutput) -> None:
    workspace_service.write_file("SLACR/slacr.json", output.model_dump_json(indent=2))
    logger.info("slacr.save: SLACR/slacr.json written (score=%.2f)", output.weighted_score)


def load() -> SlacrOutput | None:
    root = workspace_service._get_root()
    json_path = root / "SLACR" / "slacr.json"
    if not json_path.exists():
        return None
    try:
        return SlacrOutput(**json.loads(json_path.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.warning("slacr.load: failed to parse slacr.json: %s", exc)
        return None
