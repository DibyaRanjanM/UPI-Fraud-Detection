"""
MLflow integration for UPI Fraud Detection System.

Logs training runs for all 3 models + ensemble to MLflow tracking server.
Supports model registry for production deployment tracking.
"""
import os
import time

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

try:
    import mlflow
    import mlflow.sklearn
    import mlflow.pytorch
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    print("Warning: mlflow not installed. Tracking disabled.")


def setup():
    """Initialize MLflow tracking URI."""
    if MLFLOW_AVAILABLE:
        mlflow.set_tracking_uri(MLFLOW_URI)
        print(f"MLflow tracking: {MLFLOW_URI}")


def log_isolation_forest(run_name: str, params: dict, metrics: dict, model=None):
    """Log Isolation Forest training run."""
    if not MLFLOW_AVAILABLE:
        return
    mlflow.set_experiment("upi-fraud/isolation-forest")
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        mlflow.set_tag("model_type", "isolation_forest")
        mlflow.set_tag("ensemble_weight", "0.25")
        if model is not None:
            mlflow.sklearn.log_model(model, "isolation_forest")


def log_autoencoder(run_name: str, params: dict, metrics: dict, model=None):
    """Log Autoencoder training run."""
    if not MLFLOW_AVAILABLE:
        return
    mlflow.set_experiment("upi-fraud/autoencoder")
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        mlflow.set_tag("model_type", "autoencoder")
        mlflow.set_tag("ensemble_weight", "0.25")
        mlflow.set_tag("architecture", params.get("architecture", "64-32-16-32-64"))
        if model is not None:
            try:
                mlflow.pytorch.log_model(model, "autoencoder")
            except Exception:
                pass  # PyTorch logging may not always work


def log_xgboost(run_name: str, params: dict, metrics: dict, model=None):
    """Log XGBoost Classifier training run."""
    if not MLFLOW_AVAILABLE:
        return
    mlflow.set_experiment("upi-fraud/xgboost-classifier")
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        mlflow.set_tag("model_type", "xgboost")
        mlflow.set_tag("ensemble_weight", "0.50")
        if model is not None:
            mlflow.sklearn.log_model(model, "xgboost_calibrated")


def log_ensemble(weights: dict, metrics: dict):
    """Log ensemble configuration and combined metrics."""
    if not MLFLOW_AVAILABLE:
        return
    mlflow.set_experiment("upi-fraud/ensemble")
    with mlflow.start_run(run_name=f"ensemble-v1-{int(time.time())}"):
        mlflow.log_params({
            "weight_isolation_forest": weights.get("if", 0.25),
            "weight_autoencoder": weights.get("ae", 0.25),
            "weight_xgboost": weights.get("xgb", 0.50),
            "tier_thresholds": "0.30/0.55/0.80",
            "rule_boost_cap": 0.20,
        })
        mlflow.log_metrics(metrics)
        mlflow.set_tag("model_type", "ensemble")
        mlflow.set_tag("formula", "0.25*IF + 0.25*AE + 0.50*XGB + rule_boost")


def log_inference_metrics(metrics: dict):
    """Log runtime inference metrics (called periodically by ML service)."""
    if not MLFLOW_AVAILABLE:
        return
    mlflow.set_experiment("upi-fraud/inference")
    with mlflow.start_run(run_name=f"inference-{int(time.time())}"):
        mlflow.log_metrics(metrics)