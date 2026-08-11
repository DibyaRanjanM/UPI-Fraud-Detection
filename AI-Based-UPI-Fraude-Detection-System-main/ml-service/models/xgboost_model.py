import numpy as np
import joblib
import os
import xgboost as xgb
import shap
from sklearn.metrics import fbeta_score
from imblearn.over_sampling import SMOTE

SAVE_PATH = os.path.join(os.path.dirname(__file__), "saved", "xgboost.pkl")
SHAP_PATH = os.path.join(os.path.dirname(__file__), "saved", "shap_explainer.pkl")

FEATURE_COLS = [
    "txn_count_1min", "txn_count_5min", "txn_count_1hr",
    "amount_sum_1hr", "unique_receivers_1hr",
    "amount_zscore", "is_round_number",
    "hour_of_day", "day_of_week", "is_weekend", "is_night",
    "is_new_device", "device_txn_count",
    "amount",
]


def train(X_train_scaled: np.ndarray, y_train: np.ndarray,
          X_val_scaled: np.ndarray,   y_val: np.ndarray) -> dict:

    print(f"  Before SMOTE — fraud: {y_train.sum():,} / legit: {(y_train==0).sum():,}")
    smote = SMOTE(sampling_strategy=0.1, random_state=42, k_neighbors=5)
    X_res, y_res = smote.fit_resample(X_train_scaled, y_train)
    print(f"  After SMOTE  — fraud: {y_res.sum():,} / legit: {(y_res==0).sum():,}")

    scale_pos_weight = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))

    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="aucpr",
        tree_method="hist",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(
        X_res, y_res,
        eval_set=[(X_val_scaled, y_val)],
        verbose=50,
    )

    # Threshold tuning — maximise F2 on validation set
    probs_val = model.predict_proba(X_val_scaled)[:, 1]
    best_thresh, best_f2 = 0.5, 0.0
    for t in np.arange(0.05, 0.95, 0.01):
        preds = (probs_val >= t).astype(int)
        f2    = fbeta_score(y_val, preds, beta=2, zero_division=0)
        if f2 > best_f2:
            best_f2     = f2
            best_thresh = float(t)

    print(f"  Best threshold: {best_thresh:.2f}   F2: {best_f2:.4f}")

    explainer = shap.TreeExplainer(model)
    joblib.dump(explainer, SHAP_PATH)

    artifact = {
        "model":        model,
        "threshold":    best_thresh,
        "feature_cols": FEATURE_COLS,
    }
    joblib.dump(artifact, SAVE_PATH)
    print(f"  XGBoost saved → {SAVE_PATH}")
    return artifact


def load() -> dict:
    return joblib.load(SAVE_PATH)


def score(model_artifact: dict, X_scaled: np.ndarray) -> np.ndarray:
    return model_artifact["model"].predict_proba(X_scaled)[:, 1]


def get_shap_top5(X_scaled: np.ndarray, feature_cols: list) -> list:
    explainer = joblib.load(SHAP_PATH)
    shap_vals = explainer.shap_values(X_scaled)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[1]
    row      = shap_vals[0]
    top5_idx = np.argsort(np.abs(row))[-5:][::-1]
    return [
        {
            "feature":   feature_cols[i],
            "value":     round(float(X_scaled[0][i]), 4),
            "shap":      round(float(row[i]), 4),
            "direction": "increases_risk" if row[i] > 0 else "decreases_risk",
        }
        for i in top5_idx
    ]