"""Neural SLACR — shallow scikit-learn Random Forest model for SLACR risk validation.

Inputs  : 9 features — 5 SLACR dimension scores (1–5 each) + 4 financial ratios
          (DSCR, D/E ratio, current ratio, EBITDA margin).
Output  : dict matching NeuralSlacrOutput schema — predicted_rating, probability,
          composite_score, shap_values, lime_coefficients, feature_importances,
          score_distribution, correlation_matrix, feature_names, input_values.

Architecture: RandomForestClassifier (200 estimators, max_depth=8) for fast SHAP
via TreeExplainer.  Model trains on 800 synthetic deal records on first startup;
weights are persisted to neural_slacr_weights.pkl — subsequent starts load from disk.

SHAP/LIME are imported defensively; if the packages are not installed the function
returns zero-filled placeholders and logs a warning so the rest of the pipeline
continues unaffected.  Install with: pip install shap lime
"""

from __future__ import annotations

import logging
import os
import pickle
from collections import Counter
from pathlib import Path

import numpy as np

logger = logging.getLogger("deckr.neural_slacr")

# ---------------------------------------------------------------------------
# Feature / class metadata
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    "Strength",
    "Leverage",
    "Ability to Repay",
    "Collateral",
    "Risk Factors",
    "DSCR",
    "D/E Ratio",
    "Current Ratio",
    "EBITDA Margin",
]

RATING_BANDS: list[str] = [
    "Low Risk",
    "Moderate Risk",
    "Elevated Risk",
    "High Risk",
    "Decline",
]

# SLACR composite weights: S=0.20, L=0.20, A=0.25, C=0.15, R=0.20
_WEIGHTS = np.array([0.20, 0.20, 0.25, 0.15, 0.20])

_WEIGHTS_FILE = Path(__file__).parent / "neural_slacr_weights.pkl"
_N_TRAIN = 800
_N_ESTIMATORS = 200
_RANDOM_STATE = 42

# ---------------------------------------------------------------------------
# Synthetic training data
# ---------------------------------------------------------------------------


def _composite_to_class(composite: float) -> int:
    if composite <= 1.75:
        return 0  # Low Risk
    if composite <= 2.50:
        return 1  # Moderate Risk
    if composite <= 3.25:
        return 2  # Elevated Risk
    if composite <= 4.00:
        return 3  # High Risk
    return 4  # Decline


def _generate_training_data(n: int = _N_TRAIN, seed: int = _RANDOM_STATE):
    """Generate synthetic deal data with financial ratios correlated to SLACR composites."""
    rng = np.random.default_rng(seed)

    # SLACR dimension scores — integers 1-5 with slight jitter for RF variation
    slacr_raw = rng.integers(1, 6, size=(n, 5)).astype(float)
    slacr_raw += rng.normal(0, 0.08, size=(n, 5))
    slacr_raw = np.clip(slacr_raw, 1.0, 5.0)

    composites = slacr_raw @ _WEIGHTS  # weighted composite for each deal

    # Financial ratios: each correlated inversely or directly with composite + noise
    # DSCR: higher composite → lower coverage (more risky)
    dscr = (5.2 - composites) * 0.55 + rng.normal(0, 0.28, n)
    dscr = np.clip(dscr, 0.30, 5.00)

    # D/E ratio: higher composite → more leveraged
    de_ratio = (composites - 1.0) * 1.85 + rng.normal(0, 0.55, n)
    de_ratio = np.clip(de_ratio, 0.0, 12.0)

    # Current ratio: higher composite → lower liquidity
    current_ratio = (5.5 - composites) * 0.52 + rng.normal(0, 0.22, n)
    current_ratio = np.clip(current_ratio, 0.40, 5.0)

    # EBITDA margin: higher composite → thinner / negative margins
    ebitda_margin = (5.0 - composites) * 0.068 - 0.05 + rng.normal(0, 0.045, n)
    ebitda_margin = np.clip(ebitda_margin, -0.25, 0.65)

    X = np.column_stack([slacr_raw, dscr, de_ratio, current_ratio, ebitda_margin])
    y = np.array([_composite_to_class(c) for c in composites])
    return X, y


# ---------------------------------------------------------------------------
# Model persistence
# ---------------------------------------------------------------------------


def _train_and_save():
    """Train RF on synthetic data and persist weights."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError as exc:
        raise RuntimeError(
            "scikit-learn is required. Install with: pip install scikit-learn"
        ) from exc

    logger.info("neural_slacr: training on %d synthetic records…", _N_TRAIN)
    X, y = _generate_training_data()

    clf = RandomForestClassifier(
        n_estimators=_N_ESTIMATORS,
        max_depth=8,
        min_samples_leaf=4,
        random_state=_RANDOM_STATE,
        n_jobs=-1,
    )
    clf.fit(X, y)

    try:
        with open(_WEIGHTS_FILE, "wb") as f:
            pickle.dump({"model": clf, "X_train": X, "y_train": y}, f)
        logger.info("neural_slacr: weights saved → %s", _WEIGHTS_FILE)
    except Exception as e:
        logger.warning("neural_slacr: could not save weights — %s", e)

    return clf, X


def _load_model():
    """Load persisted model or train-on-missing-file fallback."""
    if not _WEIGHTS_FILE.exists():
        return _train_and_save()
    try:
        with open(_WEIGHTS_FILE, "rb") as f:
            data = pickle.load(f)
        logger.info("neural_slacr: loaded weights from %s", _WEIGHTS_FILE)
        return data["model"], data["X_train"]
    except Exception as e:
        logger.warning("neural_slacr: weights load failed (%s) — retraining", e)
        return _train_and_save()


# Load at module import — one-time cost per process start
try:
    _model, _X_train = _load_model()
except Exception as _boot_err:
    logger.error("neural_slacr: model boot failed — %s", _boot_err)
    _model = None
    _X_train = None


# ---------------------------------------------------------------------------
# Explainability helpers
# ---------------------------------------------------------------------------


def _compute_shap(clf, x_instance: np.ndarray) -> dict[str, float]:
    try:
        import shap  # type: ignore[import]

        explainer = shap.TreeExplainer(clf)
        sv = explainer.shap_values(x_instance.reshape(1, -1))
        pred_class = int(clf.predict(x_instance.reshape(1, -1))[0])
        # shap.TreeExplainer returns list[ndarray] for multi-class RF
        if isinstance(sv, list):
            values = sv[pred_class][0]
        else:
            values = sv[0, :, pred_class]
        return {name: float(round(v, 4)) for name, v in zip(FEATURE_NAMES, values)}
    except ImportError:
        logger.warning("neural_slacr: shap not installed — pip install shap")
        return {name: 0.0 for name in FEATURE_NAMES}
    except Exception as e:
        logger.warning("neural_slacr: SHAP computation failed — %s", e)
        return {name: 0.0 for name in FEATURE_NAMES}


def _compute_lime(clf, X_train: np.ndarray, x_instance: np.ndarray) -> dict[str, float]:
    try:
        from lime.lime_tabular import LimeTabularExplainer  # type: ignore[import]

        explainer = LimeTabularExplainer(
            X_train,
            feature_names=FEATURE_NAMES,
            class_names=RATING_BANDS,
            mode="classification",
            random_state=_RANDOM_STATE,
        )
        pred_class = int(clf.predict(x_instance.reshape(1, -1))[0])
        exp = explainer.explain_instance(
            x_instance, clf.predict_proba, num_features=9, top_labels=1
        )
        raw = dict(exp.as_list(label=pred_class))
        coefs: dict[str, float] = {}
        for name in FEATURE_NAMES:
            # LIME formats keys as "FeatureName op value" — match by name substring
            matched = next(
                (v for k, v in raw.items() if name.lower() in k.lower()), 0.0
            )
            coefs[name] = round(float(matched), 4)
        return coefs
    except ImportError:
        logger.warning("neural_slacr: lime not installed — pip install lime")
        return {name: 0.0 for name in FEATURE_NAMES}
    except Exception as e:
        logger.warning("neural_slacr: LIME computation failed — %s", e)
        return {name: 0.0 for name in FEATURE_NAMES}


def _compute_feature_importances(clf) -> list[dict]:
    importances = clf.feature_importances_
    return [
        {
            "feature": name,
            "importance": round(float(imp), 4),
            "direction": "risk",
        }
        for name, imp in sorted(
            zip(FEATURE_NAMES, importances), key=lambda x: x[1], reverse=True
        )
    ]


def _compute_score_distribution(clf, X_train: np.ndarray) -> list[dict]:
    y_pred = clf.predict(X_train)
    counts = Counter(int(c) for c in y_pred)
    total = len(y_pred)
    return [
        {
            "rating": RATING_BANDS[i],
            "count": counts.get(i, 0),
            "percentage": round(counts.get(i, 0) / total * 100, 1),
        }
        for i in range(len(RATING_BANDS))
    ]


def _compute_correlation_matrix(X_train: np.ndarray) -> list[list[float]]:
    corr = np.corrcoef(X_train.T)
    return [[round(float(v), 3) for v in row] for row in corr]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(inputs: dict[str, float]) -> dict:
    """
    Run the Neural SLACR model on a single deal's feature vector.

    Args:
        inputs: dict with any subset of these keys (missing keys default to neutral):
                strength, leverage, ability_to_repay, collateral, risk_factors
                dscr, de_ratio, current_ratio, ebitda_margin

    Returns:
        dict matching NeuralSlacrOutput Pydantic schema — JSON-serializable.

    Raises:
        RuntimeError: if scikit-learn was never installed and training fails.
    """
    if _model is None or _X_train is None:
        raise RuntimeError(
            "Neural SLACR model failed to initialize. "
            "Ensure scikit-learn is installed: pip install scikit-learn"
        )

    x = np.array(
        [
            float(inputs.get("strength", 3.0)),
            float(inputs.get("leverage", 3.0)),
            float(inputs.get("ability_to_repay", 3.0)),
            float(inputs.get("collateral", 3.0)),
            float(inputs.get("risk_factors", 3.0)),
            float(inputs.get("dscr", 1.2)),
            float(inputs.get("de_ratio", 3.0)),
            float(inputs.get("current_ratio", 1.5)),
            float(inputs.get("ebitda_margin", 0.12)),
        ],
        dtype=float,
    )

    proba = _model.predict_proba(x.reshape(1, -1))[0]
    pred_class = int(np.argmax(proba))
    predicted_rating = RATING_BANDS[pred_class]
    probability = round(float(proba[pred_class]), 4)

    # Weighted SLACR composite from analyst dimension scores
    composite_score = round(float(x[:5] @ _WEIGHTS), 3)

    return {
        "predicted_rating": predicted_rating,
        "probability": probability,
        "composite_score": composite_score,
        "shap_values": _compute_shap(_model, x),
        "lime_coefficients": _compute_lime(_model, _X_train, x),
        "feature_importances": _compute_feature_importances(_model),
        "score_distribution": _compute_score_distribution(_model, _X_train),
        "correlation_matrix": _compute_correlation_matrix(_X_train),
        "feature_names": FEATURE_NAMES,
        "input_values": {
            name: round(float(v), 3) for name, v in zip(FEATURE_NAMES, x)
        },
    }
