"""
Collect enriched transactions from Kafka (upi_features) → PostgreSQL
Fully aligned with production schema
"""

import json
import os
import time
import signal
import sys
import psycopg2
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

# ================= CONFIG =================
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
POSTGRES_URL    = os.getenv("POSTGRES_URL", "postgresql://admin:admin123@localhost:5432/fraud_db")

TARGET_ROWS = 500_000
BATCH_SIZE  = 1000

print("🚀 Dataset Collector Starting...")

# ================= DB CONNECT =================
conn = psycopg2.connect(POSTGRES_URL)
conn.autocommit = False
cur = conn.cursor()

# ================= KAFKA CONNECT =================
while True:
    try:
        consumer = KafkaConsumer(
            "upi_features",
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            group_id="dataset-collector-v4",
            auto_offset_reset="earliest",
        )
        print("✅ Connected to Kafka")
        break
    except NoBrokersAvailable:
        print("⏳ Waiting for Kafka...")
        time.sleep(5)

# ================= INSERT SQL =================
INSERT_SQL = """
INSERT INTO transactions (
    txn_id, sender_vpa, receiver_vpa, amount, txn_type, device_id,
    unix_timestamp, occurred_at,

    txn_count_1min, txn_count_5min, txn_count_1hr,
    amount_sum_1hr, unique_receivers_1hr, unique_devices_1hr,

    amount_zscore, amount_vs_daily_avg, amount_vs_month_avg, is_round_number,

    hour_of_day, day_of_week, is_weekend, is_night,
    days_since_last_txn, is_first_txn_ever,

    is_new_device, device_txn_count, device_vpa_count,
    device_last_seen_hrs, device_risk_score,

    sender_vpa_age_days, receiver_vpa_age_days,
    sender_txn_history_size, receiver_txn_history_size,
    vpa_name_similarity,

    is_merchant_txn, merchant_category, merchant_risk_score,
    merchant_age_days, merchant_avg_amount,

    ip_state, ip_country, distance_from_last_km, is_geo_impossible,

    sender_pagerank, receiver_pagerank, community_id,
    is_suspicious_cluster, chain_length, fraud_hop_distance,

    anomaly_score, reconstruction_error, fraud_probability,
    risk_score, risk_tier,

    fraud_flag, is_fraud
) VALUES (
    %s,%s,%s,%s,%s,%s,
    %s,NOW(),

    %s,%s,%s,
    %s,%s,%s,

    %s,%s,%s,%s,

    %s,%s,%s,%s,
    %s,%s,

    %s,%s,%s,
    %s,%s,

    %s,%s,
    %s,%s,
    %s,

    %s,%s,%s,
    %s,%s,

    %s,%s,%s,%s,

    %s,%s,%s,
    %s,%s,%s,

    %s,%s,%s,
    %s,%s,

    %s,%s
)
ON CONFLICT (txn_id) DO NOTHING
"""

# ================= STATE =================
count = 0
fraud_count = 0
batch = []

print(f"📦 Collecting {TARGET_ROWS:,} transactions...")

# ================= SHUTDOWN =================
def shutdown(sig, frame):
    print("\n🛑 Shutting down...")
    flush_batch()
    cur.close()
    conn.close()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)

# ================= FLUSH =================
def flush_batch():
    global count, batch
    if not batch:
        return
    try:
        cur.executemany(INSERT_SQL, batch)
        conn.commit()
        count += len(batch)
    except Exception as e:
        print(f"\n❌ DB error: {e}")
        conn.rollback()
    batch.clear()

# ================= MAIN LOOP =================
for msg in consumer:
    try:
        t = msg.value

        row = (
            t.get("txn_id"),
            t.get("sender_vpa"),
            t.get("receiver_vpa"),
            float(t.get("amount", 0)),
            t.get("txn_type"),
            t.get("device_id"),

            float(t.get("unix_timestamp") or t.get("timestamp") or time.time()),

            int(t.get("txn_count_1min", 0)),
            int(t.get("txn_count_5min", 0)),
            int(t.get("txn_count_1hr", 0)),
            float(t.get("amount_sum_1hr", 0)),
            int(t.get("unique_receivers_1hr", 0)),
            int(t.get("unique_devices_1hr", 0)),

            float(t.get("amount_zscore", 0)),
            float(t.get("amount_vs_daily_avg", 0)),
            float(t.get("amount_vs_month_avg", 0)),
            int(t.get("is_round_number", 0)),

            int(t.get("hour_of_day", 0)),
            int(t.get("day_of_week", 0)),
            int(t.get("is_weekend", 0)),
            int(t.get("is_night", 0)),
            float(t.get("days_since_last_txn", 0)),
            int(t.get("is_first_txn_ever", 0)),

            int(t.get("is_new_device", 0)),
            int(t.get("device_txn_count", 1)),
            int(t.get("device_vpa_count", 0)),
            float(t.get("device_last_seen_hrs", 0)),
            float(t.get("device_risk_score", 0)),

            int(t.get("sender_vpa_age_days", 0)),
            int(t.get("receiver_vpa_age_days", 0)),
            int(t.get("sender_txn_history_size", 0)),
            int(t.get("receiver_txn_history_size", 0)),
            float(t.get("vpa_name_similarity", 0)),

            int(t.get("is_merchant_txn", 0)),
            t.get("merchant_category"),
            float(t.get("merchant_risk_score", 0)),
            int(t.get("merchant_age_days", 0)),
            float(t.get("merchant_avg_amount", 0)),

            t.get("ip_state"),
            t.get("ip_country", "India"),
            float(t.get("distance_from_last_km", 0)),
            int(t.get("is_geo_impossible", 0)),

            float(t.get("sender_pagerank", 0)),
            float(t.get("receiver_pagerank", 0)),
            int(t.get("community_id", 0)),
            int(t.get("is_suspicious_cluster", 0)),
            int(t.get("chain_length", 0)),
            int(t.get("fraud_hop_distance", 99)),

            float(t.get("anomaly_score", 0)),
            float(t.get("reconstruction_error", 0)),
            float(t.get("fraud_probability", 0)),

            float(t.get("risk_score", 0)),
            t.get("risk_tier", "LEGIT"),

            t.get("fraud_flag", "LEGIT"),
            int(t.get("is_fraud", 0)),
        )

        batch.append(row)

        if t.get("is_fraud", 0):
            fraud_count += 1

        if len(batch) >= BATCH_SIZE:
            flush_batch()
            pct = fraud_count / count * 100 if count else 0
            print(f"{count:,}/{TARGET_ROWS:,} | fraud: {fraud_count:,} ({pct:.2f}%)", end="\r")

        if count >= TARGET_ROWS:
            break

    except Exception as e:
        print(f"\n⚠️ Bad message: {e}")
        continue

# Final flush
flush_batch()

print("\n\n✅ Collection complete!")
print(f"Total: {count:,}")
print(f"Fraud: {fraud_count:,} ({fraud_count/count*100:.3f}%)")

cur.close()
conn.close()