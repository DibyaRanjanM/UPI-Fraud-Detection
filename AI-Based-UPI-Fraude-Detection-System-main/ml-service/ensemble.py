import joblib
import numpy as np
import torch
import torch.nn as nn
import os
import time

from risk_tier import assign_tier

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# ================= FEATURES =================
CLEAN_FEATURE_COLS = [
    "txn_count_1min", "txn_count_5min", "txn_count_1hr",
    "amount_sum_1hr", "unique_receivers_1hr", "unique_devices_1hr",
    "amount", "amount_zscore", "amount_vs_daily_avg", "is_round_number",
    "hour_of_day", "day_of_week", "is_weekend", "is_night", "days_since_last_txn",
    "is_new_device", "device_txn_count", "device_vpa_count",
    "distance_from_last_txn_km", "txn_speed_kmph",
    "sender_degree_1hr", "receiver_degree_1hr", "chain_length",
    "vpa_similarity_score"
]

RULE_FEATURES = [
    "is_geo_impossible", "is_mule_account", "is_high_sender",
    "merchant_category_risk", "merchant_dispute_rate", "device_risk_score"
]

# Feature names for SHAP (clean + if_score + ae_score)
FUSION_FEATURE_NAMES = CLEAN_FEATURE_COLS + ["if_score", "ae_score"]


# ================= AUTOENCODER (PDF Section 3.2.2) =================
# Input → Dense(64, ReLU) → Dense(32, ReLU) → Dense(16, ReLU) [bottleneck]
#      → Dense(32, ReLU) → Dense(64, ReLU) → Output
class Autoencoder(nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.enc = nn.Sequential(
            nn.Linear(input_dim, 64), nn.ReLU(),
            nn.Linear(64, 32), nn.ReLU(),
            nn.Linear(32, 16), nn.ReLU(),
        )
        self.dec = nn.Sequential(
            nn.Linear(16, 32), nn.ReLU(),
            nn.Linear(32, 64), nn.ReLU(),
            nn.Linear(64, input_dim),
        )

    def forward(self, x):
        return self.dec(self.enc(x))


# ================= ENSEMBLE =================
class EnsembleScorer:

    # Ensemble weights per PDF spec (Section 3.2.3)
    W_IF  = 0.25
    W_AE  = 0.25
    W_XGB = 0.50

    def __init__(self):
        print("📦 Loading models from:", MODELS_DIR)

        self.scaler = joblib.load(f"{MODELS_DIR}/scaler.pkl")
        self._load_if()
        self._load_ae()
        self._load_xgb()

        try:
            self.shap_explainer = joblib.load(f"{MODELS_DIR}/shap_explainer_fusion.pkl")
            print("  ✅ SHAP explainer loaded")
        except Exception:
            self.shap_explainer = None
            print("  ⚠️  SHAP explainer not loaded (will skip per-prediction SHAP)")

        try:
            self.risk_threshold = joblib.load(f"{MODELS_DIR}/risk_threshold.pkl")
        except Exception:
            self.risk_threshold = 0.80

        print("✅ Ensemble Ready — weights: IF={}, AE={}, XGB={}".format(
            self.W_IF, self.W_AE, self.W_XGB))

    # ================= LOADERS =================
    def _load_if(self):
        d = joblib.load(f"{MODELS_DIR}/isolation_forest.pkl")
        self.iforest = d["model"]
        self.if_lo = d["lo"]
        self.if_hi = d["hi"]

    def _load_ae(self):
        meta = joblib.load(f"{MODELS_DIR}/autoencoder_meta.pkl")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.ae = Autoencoder(meta["input_dim"]).to(self.device)
        self.ae.load_state_dict(
            torch.load(f"{MODELS_DIR}/autoencoder.pt", map_location=self.device)
        )
        self.ae.eval()

        self.ae_p95 = meta["p95"]

    def _load_xgb(self):
        d = joblib.load(f"{MODELS_DIR}/xgboost_clean.pkl")
        self.xgb_model = d["model"]
        self.fusion_features = d["features"]

    # ================= FEATURE EXTRACTION =================
    def _extract(self, txn, cols):
        row = []
        for c in cols:
            val = txn.get(c, 0)
            try:
                row.append(float(val))
            except Exception:
                row.append(0.0)
        return np.array(row, dtype=np.float32).reshape(1, -1)

    # ================= SHAP EXTRACTION =================
    def _compute_shap_top5(self, fusion_vec):
        """Extract top-5 SHAP features from XGBoost model."""
        if self.shap_explainer is None:
            return []

        try:
            shap_values = self.shap_explainer.shap_values(fusion_vec)

            # Handle multi-output (binary classifier returns 2 arrays)
            if isinstance(shap_values, list):
                sv = shap_values[1][0]  # fraud class
            elif len(shap_values.shape) == 3:
                sv = shap_values[0, :, 1]
            else:
                sv = shap_values[0]

            # Get top-5 by absolute value
            abs_sv = np.abs(sv)
            top_indices = np.argsort(abs_sv)[-5:][::-1]

            result = []
            for idx in top_indices:
                if idx < len(FUSION_FEATURE_NAMES):
                    fname = FUSION_FEATURE_NAMES[idx]
                else:
                    fname = f"feature_{idx}"

                val = float(fusion_vec[0, idx]) if idx < fusion_vec.shape[1] else 0.0
                shap_val = float(sv[idx])

                result.append({
                    "feature": fname,
                    "value": round(val, 4),
                    "shap": round(shap_val, 4),
                    "direction": "increases_risk" if shap_val > 0 else "reduces_risk",
                })

            return result
        except Exception as e:
            return []

    # ================= MAIN SCORING =================
    def score(self, txn):

        start_time = time.time()
        reasons = []

        # ---------------- EXTRACT ----------------
        raw_clean = self._extract(txn, CLEAN_FEATURE_COLS)
        raw_rules = self._extract(txn, RULE_FEATURES)[0]

        # ---------------- SCALE ----------------
        scaled = self.scaler.transform(raw_clean)

        # ================= ISOLATION FOREST =================
        if_raw = float(-self.iforest.score_samples(scaled)[0])

        # Normalize IF score to [0, 1]
        norm_if = max(0.0, min(1.0,
            (if_raw - self.if_lo) / (self.if_hi - self.if_lo + 1e-8)
        ))

        # ================= AUTOENCODER =================
        latency_ms = (time.time() - start_time) * 1000

        if latency_ms > 40:
            ae_raw = 0.0
            reasons.append({
                "type": "system",
                "impact": "neutral",
                "desc": "Autoencoder skipped (latency guard)"
            })
        else:
            with torch.no_grad():
                t = torch.FloatTensor(scaled).to(self.device)
                recon = self.ae(t)
                ae_raw = float(torch.mean((recon - t) ** 2).item())

        # Normalize AE score against 95th percentile
        norm_ae = min(1.0, ae_raw / (self.ae_p95 + 1e-8))

        # ================= XGBOOST =================
        fusion = np.hstack([raw_clean, [[if_raw]], [[ae_raw]]])
        xgb_prob = float(self.xgb_model.predict_proba(fusion)[0][1])

        # ================= SHAP TOP-5 =================
        shap_top5 = self._compute_shap_top5(fusion)

        # ================= WEIGHTED ENSEMBLE (PDF Spec) =================
        # ensemble_score = 0.25 × IF + 0.25 × AE + 0.50 × XGB
        ensemble_raw = (
            self.W_IF  * norm_if +
            self.W_AE  * norm_ae +
            self.W_XGB * xgb_prob
        )

        # ================= RULE ENGINE (supplementary boost) =================
        is_geo, is_mule, is_high, merch_cat, merch_disp, dev_risk = raw_rules

        rule_boost = 0.0

        if is_mule and xgb_prob > 0.6:
            rule_boost += 0.10
            reasons.append({
                "type": "network",
                "impact": "critical",
                "desc": "Mule network pattern"
            })

        if dev_risk > 0.8 and xgb_prob > 0.5:
            rule_boost += 0.05
            reasons.append({
                "type": "device",
                "impact": "high",
                "desc": "High device risk"
            })

        if merch_disp > 0.7 and xgb_prob > 0.6:
            rule_boost += 0.05
            reasons.append({
                "type": "merchant",
                "impact": "medium",
                "desc": "Merchant dispute spike"
            })

        if is_geo:
            rule_boost += 0.10
            reasons.append({
                "type": "geo",
                "impact": "critical",
                "desc": "Geo impossible"
            })

        # velocity signal
        if txn.get("txn_count_1min", 0) > 10:
            reasons.append({
                "type": "velocity",
                "impact": "high",
                "desc": "High transaction velocity"
            })

        rule_boost = min(rule_boost, 0.20)

        # ================= FINAL SCORE =================
        final_score = min(1.0, float(ensemble_raw + rule_boost))

        # ================= RISK TIER (via risk_tier.py — PDF thresholds) =====
        is_night = bool(txn.get("is_night", 0))
        txn_type = txn.get("txn_type", "P2P")
        tier, threshold_set = assign_tier(final_score, is_night, txn_type)

        # ================= CONFIDENCE =================
        margin = abs(final_score - 0.5)
        if margin > 0.3:
            confidence = "HIGH"
        elif margin > 0.15:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # ================= LATENCY =================
        total_latency = round((time.time() - start_time) * 1000, 2)

        # ================= OUTPUT =================
        return {
            "ensemble_score": round(final_score, 4),
            "risk_tier": tier,
            "confidence": confidence,
            "threshold_set": threshold_set,

            # Flat model scores (frontend-friendly)
            "if_score": round(norm_if, 4),
            "ae_score": round(norm_ae, 4),
            "xgb_score": round(xgb_prob, 4),

            # Nested model scores (for detailed views)
            "model_scores": {
                "isolation_forest": round(norm_if, 4),
                "autoencoder": round(norm_ae, 4),
                "xgboost": round(xgb_prob, 4),
                "if_raw": round(if_raw, 4),
                "ae_raw": round(ae_raw, 4),
            },

            "shap_top5": shap_top5,
            "reasons": reasons,

            "latency_ms": total_latency
        }