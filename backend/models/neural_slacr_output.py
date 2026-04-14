"""Pydantic output schema for the Neural SLACR model (backend/ml/neural_slacr.py).

Returned by POST /api/interpret/run and GET /api/interpret/output.
A sidecar JSON is written to SLACR/neural_slacr_output.json for workspace
persistence and context injection into the interpreter agent.
"""

from pydantic import BaseModel


class FeatureImportanceItem(BaseModel):
    feature: str
    importance: float
    direction: str  # "risk" — higher value = stronger predictor of risk tier


class ScoreBandItem(BaseModel):
    rating: str
    count: int
    percentage: float  # % of training set predicted in this band


class NeuralSlacrOutput(BaseModel):
    predicted_rating: str        # e.g. "Moderate Risk"
    probability: float           # confidence in predicted_rating (0–1)
    composite_score: float       # weighted SLACR composite from analyst scores

    shap_values: dict[str, float]       # feature → SHAP contribution for predicted class
    lime_coefficients: dict[str, float] # feature → LIME local linear coefficient

    feature_importances: list[FeatureImportanceItem]  # sorted by importance desc
    score_distribution: list[ScoreBandItem]           # training-set distribution by band
    correlation_matrix: list[list[float]]             # 9×9 Pearson correlation of inputs

    feature_names: list[str]            # ordered feature labels (length 9)
    input_values: dict[str, float]      # the 9 input values actually fed to the model
