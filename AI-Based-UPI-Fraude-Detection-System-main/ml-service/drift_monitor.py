import numpy as np
import joblib
import os
from typing import Dict

BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), "models", "baseline_stats.pkl"
)

FEATURE_COLS = [
    "txn_count_1min", "txn_count_5min", "txn_count_1hr",
    "amount_sum_1hr", "unique_receivers_1hr",
    "amount_zscore", "is_round_number",
    "hour_of_day", "day_of_week", "is_weekend", "is_night",
    "is_new_device", "device_txn_count",
    "amount",
]

def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Population Stability Index.
      PSI < 0.1  — no significant change
      PSI 0.1–0.2 — slight change, monitor
      PSI > 0.2  — significant shift, consider retraining
    """
    eps = 1e-8
    expected_hist, bin_edges = np.histogram(expected, bins=bins)
    actual_hist, _           = np.histogram(actual,   bins=bin_edges)

    expected_pct = expected_hist / (expected_hist.sum() + eps) + eps
    actual_pct   = actual_hist   / (actual_hist.sum()   + eps) + eps

    psi = float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))
    return psi

def save_baseline(X_train: np.ndarray):
    """Call once after training to persist the training distribution."""
    stats = {}
    for i, col in enumerate(FEATURE_COLS):
        col_data = X_train[:, i]
        stats[col] = {
            "mean":   float(np.mean(col_data)),
            "std":    float(np.std(col_data)),
            "p5":     float(np.percentile(col_data, 5)),
            "p95":    float(np.percentile(col_data, 95)),
            "values": col_data[:10000].tolist(),
        }
    joblib.dump(stats, BASELINE_PATH)
    print(f"Baseline saved → {BASELINE_PATH}")

def check_drift(recent_X: np.ndarray) -> Dict[str, float]:
    """
    Compare recent window against training baseline.
    Returns {feature_name: psi_score}.
    """
    if not os.path.exists(BASELINE_PATH):
        print("No baseline found. Run save_baseline() after training.")
        return {}

    baseline   = joblib.load(BASELINE_PATH)
    psi_scores = {}

    for i, col in enumerate(FEATURE_COLS):
        if col not in baseline:
            continue
            
        expected = np.array(baseline[col]["values"])
        actual   = recent_X[:, i]
        
        current_mean = float(np.mean(actual))
        baseline_mean = baseline[col]["mean"]
        
        # ⚠️ Active Drift Trigger: If severe mean shift is detected
        if baseline_mean > 0:
            shift_ratio = abs(current_mean - baseline_mean) / baseline_mean
            if shift_ratio > 0.40:  # 40% threshold for critical distribution drift
                print(f"⚠️ Drift detected on [{col}] → retraining recommended")

        try:
            psi_scores[col] = round(compute_psi(expected, actual), 4)
        except Exception as e:
            psi_scores[col] = 0.0

    return psi_scores

def drift_alerts(psi_scores: Dict[str, float]) -> list:
    """Return features with PSI > 0.2 — significant distribution shift."""
    return [
        {"feature": col, "psi": psi, "severity": "high" if psi > 0.25 else "medium"}
        for col, psi in psi_scores.items()
        if psi > 0.2
    ]

def drift_summary(psi_scores: Dict[str, float]) -> str:
    """Human-readable drift summary for the dashboard."""
    if not psi_scores:
        return "No drift data available."
    alerts = drift_alerts(psi_scores)
    if not alerts:
        return f"No drift detected across {len(psi_scores)} features."
    names = ", ".join(a["feature"] for a in alerts)
    return f"Drift detected in {len(alerts)} features: {names}"