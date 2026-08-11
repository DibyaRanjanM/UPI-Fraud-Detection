import joblib
import numpy as np
import os
from sklearn.ensemble import IsolationForest

SAVE_PATH = os.path.join(os.path.dirname(__file__), "saved", "isolation_forest.pkl")

def train(X_legit_scaled: np.ndarray) -> dict:
    """Train Isolation Forest on legitimate transactions only."""
    model = IsolationForest(
        n_estimators=200,
        contamination=0.003,
        max_features=0.8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_legit_scaled)

    # Calibrate normalisation bounds on training data itself
    raw_scores = -model.score_samples(X_legit_scaled)
    lo = float(np.percentile(raw_scores, 1))
    hi = float(np.percentile(raw_scores, 99))

    artifact = {"model": model, "lo": lo, "hi": hi}
    joblib.dump(artifact, SAVE_PATH)
    print(f"Isolation Forest saved → {SAVE_PATH}")
    return artifact


def load() -> dict:
    return joblib.load(SAVE_PATH)


def score(model_artifact: dict, X_scaled: np.ndarray) -> np.ndarray:
    """Return normalised anomaly scores in [0, 1]. Higher = more anomalous."""
    raw = -model_artifact["model"].score_samples(X_scaled)
    lo, hi = model_artifact["lo"], model_artifact["hi"]
    return np.clip((raw - lo) / (hi - lo + 1e-8), 0, 1)