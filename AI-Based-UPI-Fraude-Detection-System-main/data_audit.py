import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import matplotlib.pyplot as plt

# ================= CONFIG =================
DB_URL = "postgresql://admin:admin123@localhost:5432/fraud_db"

# ================= LOAD DATA =================
print("🔌 Connecting to DB...")
engine = create_engine(DB_URL)

df = pd.read_sql("SELECT * FROM transactions", engine)

print(f"\n✅ Loaded {len(df)} rows")

# ================= LABEL =================
df["label"] = (df["fraud_flag"] != "LEGIT").astype(int)

# ================= 1. CLASS DISTRIBUTION =================
print("\n📊 CLASS DISTRIBUTION")
dist = df["fraud_flag"].value_counts()
perc = df["fraud_flag"].value_counts(normalize=True) * 100

print(pd.concat([dist, perc], axis=1, keys=["Count", "%"]))

# ================= 2. BASIC STATS =================
print("\n📊 BASIC STATS (Fraud vs Legit)")
stats = df.groupby("label")[["amount", "txn_count_1min", "device_risk_score"]].mean()
print(stats)

# ================= 3. CORRELATION CHECK =================
print("\n📊 TOP CORRELATED FEATURES WITH TARGET")

corr = df.corr(numeric_only=True)["label"].sort_values(ascending=False)
print(corr.head(15))

print("\n⚠️ High correlation (>0.9) = LEAKAGE")

# ================= 4. RULE LEAKAGE CHECK =================
print("\n📊 RULE FEATURE CHECK")

def check_rule(col):
    res = df.groupby(col)["label"].mean()
    print(f"\n🔎 {col}")
    print(res)

rule_features = [
    "is_mule_account",
    "is_geo_impossible",
    "is_high_sender"
]

for col in rule_features:
    if col in df.columns:
        check_rule(col)

# ================= 5. BUCKET ANALYSIS =================
print("\n📊 DEVICE RISK BUCKET CHECK")

if "device_risk_score" in df.columns:
    df["risk_bucket"] = pd.cut(df["device_risk_score"], bins=5)
    print(df.groupby("risk_bucket")["label"].mean())

# ================= 6. RANGE OVERLAP =================
print("\n📊 RANGE OVERLAP CHECK")

features = ["amount", "txn_count_1min", "device_risk_score"]

for col in features:
    if col in df.columns:
        print(f"\n🔎 {col}")
        print(df.groupby("label")[col].agg(["min", "max"]))

# ================= 7. HISTOGRAMS =================
print("\n📊 PLOTTING DISTRIBUTIONS")

for col in features:
    if col in df.columns:
        plt.figure()
        df[df["label"] == 0][col].hist(alpha=0.5, label="Legit")
        df[df["label"] == 1][col].hist(alpha=0.5, label="Fraud")
        plt.title(col)
        plt.legend()
        plt.show()

# ================= 8. RANDOM SAMPLE =================
print("\n📊 RANDOM SAMPLE")
print(df.sample(10))

# ================= FINAL VERDICT =================
print("\n🚨 FINAL DIAGNOSIS CHECKLIST")

issues = []

if corr.iloc[1] > 0.9:
    issues.append("High correlation leakage")

if df.groupby("label")["amount"].mean().diff().abs().iloc[-1] > 10000:
    issues.append("Amount too separable")

if len(issues) == 0:
    print("✅ Dataset looks realistic")
else:
    print("❌ Issues detected:")
    for i in issues:
        print("-", i)