# ML Pipeline Documentation — Sentinel Oversight

> Complete documentation of the machine learning pipeline including data collection, model training, ensemble strategy, explainability, drift monitoring, and experiment tracking.

---

## 1. Pipeline Overview

The ML pipeline consists of two phases:

```
OFFLINE PHASE (Training)
  PostgreSQL → Data Loading → Feature Selection → Scaling
       → Isolation Forest Training (clean data only)
       → Autoencoder Training (clean data only)
       → Feature Fusion (raw + IF + AE scores)
       → Stratified Downsampling (4:1 ratio)
       → Calibrated XGBoost Training
       → SHAP Explainer Generation
       → Model Artifact Serialization

ONLINE PHASE (Inference)
  Kafka[upi_features] → Feature Extraction → StandardScaler
       → Parallel Scoring (IF ∥ AE ∥ XGB)
       → Weighted Ensemble (0.25 IF + 0.25 AE + 0.50 XGB)
       → Rule Engine Boost
       → Risk Tier Classification
       → SHAP Top-5 Extraction
       → Kafka[scored_transactions]
```

---

## 2. Feature Engineering

### 2.1 Clean Features (24 dimensions)

These features are used as input to the Isolation Forest and Autoencoder:

| # | Feature | Type | Source Module | Description |
|---|---|---|---|---|
| 1 | `txn_count_1min` | int | velocity | Transactions in last 1 minute |
| 2 | `txn_count_5min` | int | velocity | Transactions in last 5 minutes |
| 3 | `txn_count_1hr` | int | velocity | Transactions in last 1 hour |
| 4 | `amount_sum_1hr` | float | velocity | Total amount in last 1 hour |
| 5 | `unique_receivers_1hr` | int | velocity | Unique receivers in last 1 hour |
| 6 | `unique_devices_1hr` | int | velocity | Unique devices in last 1 hour |
| 7 | `amount` | float | raw | Transaction amount (₹) |
| 8 | `amount_zscore` | float | amount | Z-score vs. sender's history |
| 9 | `amount_vs_daily_avg` | float | amount | Ratio to sender's daily average |
| 10 | `is_round_number` | int | amount | Whether amount is a round number |
| 11 | `hour_of_day` | int | temporal | Hour (0–23) |
| 12 | `day_of_week` | int | temporal | Day (0=Mon, 6=Sun) |
| 13 | `is_weekend` | int | temporal | Weekend indicator |
| 14 | `is_night` | int | temporal | Night hours (10 PM – 6 AM) |
| 15 | `days_since_last_txn` | float | temporal | Days since sender's last transaction |
| 16 | `is_new_device` | int | device | First-time device for this VPA |
| 17 | `device_txn_count` | int | device | Historical txn count for this device |
| 18 | `device_vpa_count` | int | device | Number of VPAs using this device |
| 19 | `distance_from_last_txn_km` | float | geo | Distance from sender's last transaction |
| 20 | `txn_speed_kmph` | float | geo | Implied travel speed (km/h) |
| 21 | `sender_degree_1hr` | int | graph | Sender's out-degree in 1 hour |
| 22 | `receiver_degree_1hr` | int | graph | Receiver's in-degree in 1 hour |
| 23 | `chain_length` | int | graph | Forwarding chain length |
| 24 | `vpa_similarity_score` | float | vpa | Cosine similarity to known brands |

### 2.2 Rule Features (6 dimensions)

Used only by the rule engine (not fed to unsupervised models):

| # | Feature | Type | Description |
|---|---|---|---|
| 1 | `is_geo_impossible` | int | Travel speed > 800 km/h |
| 2 | `is_mule_account` | int | Mule account pattern detected |
| 3 | `is_high_sender` | int | High-volume sender flag |
| 4 | `merchant_category_risk` | float | Merchant category risk score [0,1] |
| 5 | `merchant_dispute_rate` | float | Merchant dispute ratio [0,1] |
| 6 | `device_risk_score` | float | Device risk score [0,1] |

### 2.3 Fusion Features (26 dimensions)

Input to XGBoost meta-model:

```
fusion_vector = [clean_features(24)] + [if_raw_score(1)] + [ae_raw_error(1)]
```

---

## 3. Model Training

### 3.1 Data Preparation

```python
# Temporal split (85/15) — no data leakage
split_idx = int(len(df) * 0.85)
train_df = df.iloc[:split_idx]
test_df  = df.iloc[split_idx:]

# Further split training into train/validation (85/15, stratified)
train_df_tr, train_df_val = train_test_split(
    train_df, test_size=0.15, stratify=train_df["label"], random_state=42
)

# StandardScaler fitted on training data only
scaler = StandardScaler()
X_tr_sc = scaler.fit_transform(X_tr)
```

### 3.2 Model 1: Isolation Forest

**Architecture:** Unsupervised anomaly detector

| Hyperparameter | Value | Rationale |
|---|---|---|
| `n_estimators` | 200 | Sufficient for convergence |
| `contamination` | 0.003 | Matches 0.3% expected fraud rate |
| `n_jobs` | -1 | Full CPU parallelism |
| `random_state` | 42 | Reproducibility |

**Training Data:** Clean (legitimate) transactions only  
**Score Normalization:** Min-max scaling using the clean data's score range `[lo, hi]`

```python
norm_if = (raw_score - lo) / (hi - lo)  # clipped to [0, 1]
```

**Serialized Artifact:** `isolation_forest.pkl` — contains model, `lo`, and `hi` bounds

### 3.3 Model 2: PyTorch Autoencoder

**Architecture:** (per PDF Section 3.2.2)

```
Input(24) → Dense(64, ReLU) → Dense(32, ReLU) → Dense(16, ReLU) [bottleneck]
         → Dense(32, ReLU) → Dense(64, ReLU) → Output(24)
```

| Hyperparameter | Value | Rationale |
|---|---|---|
| Bottleneck dim | 16 | Sufficient compression for 24D input |
| Epochs | 30 | Convergence point based on loss monitoring |
| Batch size | 512 | Balanced memory/convergence |
| Learning rate | 1e-3 | Adam optimizer default |
| Loss function | MSELoss | Standard for reconstruction |

**Training Data:** Clean (legitimate) transactions only  
**Score Normalization:** Divided by 95th percentile of clean reconstruction errors

```python
norm_ae = min(1.0, raw_error / p95)
```

**Serialized Artifacts:**
- `autoencoder.pt` — PyTorch model weights
- `autoencoder_meta.pkl` — `p95` threshold and `input_dim`

### 3.4 Model 3: Calibrated XGBoost

**Architecture:** XGBoost classifier wrapped in `CalibratedClassifierCV`

| Hyperparameter | Value | Rationale |
|---|---|---|
| `n_estimators` | 400 | Higher for better performance with calibration |
| `max_depth` | 6 | Balance complexity vs. overfitting |
| `learning_rate` | 0.03 | Conservative for 400 trees |
| `subsample` | 0.8 | Regularization via bagging |
| `colsample_bytree` | 0.8 | Feature subsampling |
| `scale_pos_weight` | Auto (from data) | Class imbalance handling |
| `eval_metric` | logloss | Probability calibration focus |
| `tree_method` | hist | Fast histogram-based training |
| Calibration | Sigmoid, 3-fold CV | Ensures score ≈ true probability |

**Training Data:** Fusion features with stratified downsampling (4:1 legit:fraud ratio)

**Class Imbalance Strategy:**
1. **Stratified downsampling** — Reduce legitimate class to 4× fraud count
2. **`scale_pos_weight`** — Further balance within XGBoost
3. **Calibration** — Sigmoid isotonic calibration corrects any remaining bias

**Serialized Artifact:** `xgboost_clean.pkl` — contains calibrated model and feature list

---

## 4. Ensemble Strategy

### 4.1 Weighted Scoring Formula

```
ensemble_raw = 0.25 × IF_normalized + 0.25 × AE_normalized + 0.50 × XGB_probability
```

| Model | Weight | Rationale |
|---|---|---|
| Isolation Forest | 0.25 | Catches novel anomalies not in training data |
| Autoencoder | 0.25 | Captures complex non-linear reconstruction patterns |
| XGBoost | 0.50 | Highest weight — trained on fusion features with calibrated probabilities |

### 4.2 Rule Engine Boost

Additional score boost (capped at +0.20) for context-aware signals:

```python
rule_boost = 0.0

if is_mule and xgb_prob > 0.6:        rule_boost += 0.10  # Mule + ML agreement
if device_risk > 0.8 and xgb_prob > 0.5:  rule_boost += 0.05  # Risky device
if merchant_dispute > 0.7 and xgb_prob > 0.6: rule_boost += 0.05  # Bad merchant
if is_geo_impossible:                  rule_boost += 0.10  # Impossible travel

rule_boost = min(rule_boost, 0.20)     # Hard cap
final_score = min(1.0, ensemble_raw + rule_boost)
```

### 4.3 Online Latency Guard

To maintain <200ms SLA, the autoencoder is conditionally skipped:

```python
if elapsed_ms > 40:
    ae_score = 0.0  # Skip AE, use 0 contribution
    # Ensemble becomes: 0.25 × IF + 0.50 × XGB
```

---

## 5. Risk Tier Classification

### 5.1 Adaptive Thresholds

Three threshold sets are applied based on transaction context:

| Tier | Default | Night (1–4 AM) | P2M |
|---|---|---|---|
| Legitimate | < 0.30 | < 0.20 | < 0.35 |
| Suspicious | 0.30 – 0.55 | 0.20 – 0.40 | 0.35 – 0.60 |
| High-Risk | 0.55 – 0.80 | 0.40 – 0.65 | 0.60 – 0.82 |
| Block | ≥ 0.80 | ≥ 0.65 | ≥ 0.82 |

**Selection Logic:**
1. Night hours (`is_night=1`) → Night thresholds (more aggressive)
2. P2M transactions (`txn_type="P2M"`) → P2M thresholds (slightly relaxed)
3. Default → Standard thresholds

### 5.2 Tier Actions

| Tier | Alert | Gateway | Analyst Queue |
|---|---|---|---|
| Legitimate | ✗ | ✗ | ✗ |
| Suspicious | ✓ | ✗ | ✓ |
| High-Risk | ✓ | Hold (30 min) | ✓ |
| Block | ✓ | Block (permanent) | ✓ |

### 5.3 Confidence Scoring

```python
margin = abs(final_score - 0.5)
if margin > 0.30:   confidence = "HIGH"
elif margin > 0.15: confidence = "MEDIUM"
else:                confidence = "LOW"
```

---

## 6. Explainability

### 6.1 SHAP Feature Attribution

**Engine:** `shap.TreeExplainer` with interventional feature perturbation  
**Background:** 150-sample subsample from training data  
**Target:** Inner XGBoost model (extracted from calibration wrapper)

For each prediction, the top 5 SHAP features are extracted:

```json
{
  "shap_top5": [
    {
      "feature": "txn_count_1min",
      "value": 8.0,
      "shap": 0.1245,
      "direction": "increases_risk"
    },
    {
      "feature": "amount",
      "value": 85000.0,
      "shap": 0.0892,
      "direction": "increases_risk"
    }
  ]
}
```

### 6.2 GenAI Analyst Reports

The GenAI service generates structured 5-section fraud analyst reports by synthesizing:
- SHAP feature attributions
- Individual model scores (IF, AE, XGB)
- Matched fraud pattern from the catalog
- Graph network context (PageRank, chain length, fraud proximity)

---

## 7. Drift Monitoring

### 7.1 Population Stability Index (PSI)

Monitors 14 key features for distribution drift:

```python
FEATURE_COLS = [
    "txn_count_1min", "txn_count_5min", "txn_count_1hr",
    "amount_sum_1hr", "unique_receivers_1hr",
    "amount_zscore", "is_round_number",
    "hour_of_day", "day_of_week", "is_weekend", "is_night",
    "is_new_device", "device_txn_count",
    "amount",
]
```

**PSI Interpretation:**

| PSI | Status | Action |
|---|---|---|
| < 0.10 | Stable | No action |
| 0.10 – 0.20 | Moderate drift | Monitor closely |
| > 0.20 | Significant drift | Consider retraining |

### 7.2 Mean Shift Detection

In addition to PSI, a 40% mean shift threshold triggers immediate alerts:

```python
shift_ratio = abs(current_mean - baseline_mean) / baseline_mean
if shift_ratio > 0.40:
    print(f"⚠️ Drift detected on [{feature}] → retraining recommended")
```

### 7.3 Baseline Management

```python
# Save baseline after training
from drift_monitor import save_baseline
save_baseline(X_train)

# Check drift with recent production data
from drift_monitor import check_drift, drift_alerts
psi_scores = check_drift(recent_X)
alerts = drift_alerts(psi_scores)
```

---

## 8. MLflow Experiment Tracking

### 8.1 Experiment Structure

| Experiment | Models Logged | Key Metrics |
|---|---|---|
| `upi-fraud/isolation-forest` | IF model | lo, hi bounds, train samples |
| `upi-fraud/autoencoder` | AE model | p95 reconstruction error |
| `upi-fraud/xgboost-classifier` | XGBoost model | Validation AUC |
| `upi-fraud/ensemble` | Ensemble config | AUROC, PR-AUC, recall, precision, FPR |
| `upi-fraud/inference` | — | Runtime inference metrics |

### 8.2 Logged Parameters

Each training run logs:
- Model hyperparameters
- Ensemble weights
- Tier thresholds
- Performance metrics (AUROC, PR-AUC, recall, precision, FPR)
- Model artifacts

### 8.3 Usage

```python
# Enable MLflow tracking
export MLFLOW_TRACKING_URI=http://localhost:5000

# Run training with MLflow logging
python notebooks/02_train_models.py
```

---

## 9. Model Artifacts

All serialized models are stored in `ml-service/models/`:

| File | Size | Description |
|---|---|---|
| `scaler.pkl` | ~1 KB | StandardScaler fitted on training data |
| `isolation_forest.pkl` | ~2.5 MB | IF model + normalization bounds |
| `autoencoder.pt` | ~38 KB | PyTorch autoencoder weights |
| `autoencoder_meta.pkl` | ~45 B | AE p95 threshold + input dimension |
| `xgboost_clean.pkl` | ~3.6 MB | Calibrated XGBoost + feature list |
| `shap_explainer_fusion.pkl` | ~4.6 MB | Pre-computed SHAP TreeExplainer |
| `risk_threshold.pkl` | ~21 B | Operational risk threshold |

---

## 10. Performance Benchmarks

### Training Pipeline Results

```
AUROC:   0.98+
PR-AUC:  0.95+
Recall:  95%+
Precision: 90%+
FPR:     < 1%
```

### Inference Latency Breakdown

| Stage | Latency |
|---|---|
| Feature extraction + scaling | 1–5ms |
| Isolation Forest scoring | 2–10ms |
| Autoencoder inference | 5–20ms |
| XGBoost prediction | 3–15ms |
| SHAP extraction | 5–20ms |
| Rule engine | < 1ms |
| Risk tier assignment | < 1ms |
| **Total** | **20–80ms** |

---

## 11. Retraining Guide

### When to Retrain

1. **Drift Alert**: PSI > 0.20 on multiple features
2. **FPR Spike**: False positive rate exceeds 5% in analyst reviews
3. **Data Volume**: Significant increase in transaction volume/patterns
4. **Periodic**: Recommended monthly retraining cycle

### Retraining Steps

```bash
# 1. Ensure Docker + Kafka + PostgreSQL are running
docker-compose up -d

# 2. Generate fresh training data (or use production data)
cd simulator && python producer.py

# 3. Wait for sufficient data (recommended: 200K+ transactions)

# 4. Run training pipeline
cd notebooks && python 02_train_models.py

# 5. Verify model artifacts
ls -la ../ml-service/models/

# 6. Restart ML service to load new models
# (the ML service loads models at startup)
```
