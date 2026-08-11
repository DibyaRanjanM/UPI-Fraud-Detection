import json
import time
import psycopg2
from kafka import KafkaConsumer
import uuid
import signal
import sys
import os

# ================= CONFIG =================
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = "upi_features"

DB_CONFIG = {
    "host": "localhost",
    "database": "fraud_db",
    "user": "admin",
    "password": "admin123",
    "port": 5432
}

BATCH_SIZE = 1000

# ================= GLOBAL =================
conn = None
cursor = None
batch = []
count = 0
fraud_count = 0
start_time = time.time()


# ================= DB CONNECT =================
def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.autocommit = False
            print("✅ Connected to Postgres")
            return conn
        except Exception as e:
            print("⏳ Waiting for DB...", e)
            time.sleep(3)


# ================= KAFKA CONSUMER =================
def get_kafka_consumer():
    while True:
        try:
            consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                group_id="db-consumer-live-v1",
                auto_offset_reset="latest",
                enable_auto_commit=True,
                max_poll_records=500
            )
            print("✅ Connected to Kafka")
            return consumer
        except Exception as e:
            print("⏳ Waiting for Kafka...", e)
            time.sleep(3)


# ================= INSERT QUERY =================
INSERT_QUERY = """
INSERT INTO transactions (
    txn_id, sender_vpa, receiver_vpa, amount, device_id,
    unix_timestamp,

    txn_count_1min, txn_count_5min, txn_count_1hr,
    amount_sum_1hr, unique_receivers_1hr, unique_devices_1hr,

    amount_zscore, amount_vs_daily_avg, history_size, is_round_number,

    hour_of_day, day_of_week, is_weekend, is_night,
    days_since_last_txn, is_first_txn_ever,

    is_new_device, device_txn_count, device_vpa_count,
    device_last_seen_hours_ago, device_risk_score, sender_device_count,

    distance_from_last_txn_km, txn_speed_kmph, is_geo_impossible,

    sender_degree_1hr, receiver_degree_1hr,
    is_mule_account, is_high_sender, chain_length,

    sender_vpa_age_days, receiver_vpa_age_days,
    sender_txn_count_total, receiver_txn_count_total,
    vpa_similarity_score,

    is_merchant_txn, merchant_avg_txn_amount,
    merchant_txn_count, merchant_category_risk,
    merchant_age_days, merchant_dispute_rate,

    fraud_flag, is_fraud
)
VALUES (
    %(txn_id)s, %(sender_vpa)s, %(receiver_vpa)s, %(amount)s, %(device_id)s,
    %(unix_timestamp)s,

    %(txn_count_1min)s, %(txn_count_5min)s, %(txn_count_1hr)s,
    %(amount_sum_1hr)s, %(unique_receivers_1hr)s, %(unique_devices_1hr)s,

    %(amount_zscore)s, %(amount_vs_daily_avg)s, %(history_size)s, %(is_round_number)s,

    %(hour_of_day)s, %(day_of_week)s, %(is_weekend)s, %(is_night)s,
    %(days_since_last_txn)s, %(is_first_txn_ever)s,

    %(is_new_device)s, %(device_txn_count)s, %(device_vpa_count)s,
    %(device_last_seen_hours_ago)s, %(device_risk_score)s, %(sender_device_count)s,

    %(distance_from_last_txn_km)s, %(txn_speed_kmph)s, %(is_geo_impossible)s,

    %(sender_degree_1hr)s, %(receiver_degree_1hr)s,
    %(is_mule_account)s, %(is_high_sender)s, %(chain_length)s,

    %(sender_vpa_age_days)s, %(receiver_vpa_age_days)s,
    %(sender_txn_count_total)s, %(receiver_txn_count_total)s,
    %(vpa_similarity_score)s,

    %(is_merchant_txn)s, %(merchant_avg_txn_amount)s,
    %(merchant_txn_count)s, %(merchant_category_risk)s,
    %(merchant_age_days)s, %(merchant_dispute_rate)s,

    %(fraud_flag)s, %(is_fraud)s
)
ON CONFLICT (txn_id) DO NOTHING;
"""


# ================= INSERT BATCH =================
def insert_batch():
    global batch, count, fraud_count

    if not batch:
        return

    try:
        cursor.executemany(INSERT_QUERY, batch)
        conn.commit()

        count += len(batch)
        fraud_count += sum(x["is_fraud"] for x in batch)

        batch.clear()

        if count % 5000 == 0:
            elapsed = time.time() - start_time
            rate = count / elapsed
            fraud_pct = (fraud_count / count) * 100 if count else 0

            print(f"[{count:,} rows | {rate:.0f}/sec | fraud: {fraud_pct:.2f}%]")

    except Exception as e:
        print("❌ Insert error:", e)
        conn.rollback()


# ================= CLEAN DATA (WITH CHAOS INJECTION) =================
def clean_data(data):
    import random
    import numpy as np

    # 1. Base Assignment
    txn_id = data.get("txn_id")
    label = int(data.get("is_fraud", 0))
    fraud_flag = data.get("fraud_flag", "LEGIT")
    amount = float(data.get("amount", 0))
    
    txn_count_1hr = int(data.get("txn_count_1hr", 0))
    dev_risk = float(data.get("device_risk_score", 0))
    is_mule = int(data.get("is_mule_account", 0))
    dist_km = float(data.get("distance_from_last_txn_km", 0))
    
    # 🔥 WEAK STRUCTURAL SIGNALS (Applied just before noise to guarantee survival)
    if label == 1:
        amount *= random.uniform(1.3, 1.8)
        txn_count_1hr += random.randint(3, 7)
        dev_risk = min(1.0, dev_risk + random.uniform(0.1, 0.3))

    # 2. Chaos Injection Simulator (Tier-1 Boundary Blur)
    # a. Continuous Boundary Blur (Gaussian Noise)
    amount = max(0.0, amount + np.random.normal(0, amount * 0.05)) # Reduced noise to preserve subtle patterns
    dist_km = max(0.0, dist_km + np.random.normal(0, 50))

    r_num = random.random()
    # b. False Positives (~4% of legit txns behave wildly in velocity)
    if label == 0 and r_num < 0.04:
        txn_count_1hr += random.randint(5, 20)
    
    # c. False Negatives (~6% of fraud txns behave cleanly)
    elif label == 1 and r_num < 0.06:
        dev_risk = random.uniform(0.0, 0.2)
        is_mule = 0
        
    # d. True Target Random Flips (~0.5% unexplainable noise)
    if random.random() < 0.005:
        label = 1 - label

    return {
        "txn_id": txn_id,
        "sender_vpa": data.get("sender_vpa"),
        "receiver_vpa": data.get("receiver_vpa"),
        "amount": float(amount),
        "device_id": data.get("device_id"),

        "unix_timestamp": float(data.get("unix_timestamp") or data.get("timestamp") or time.time()),

        "txn_count_1min": int(data.get("txn_count_1min", 0)),
        "txn_count_5min": int(data.get("txn_count_5min", 0)),
        "txn_count_1hr": int(txn_count_1hr),

        "amount_sum_1hr": float(data.get("amount_sum_1hr", 0)),
        "unique_receivers_1hr": int(data.get("unique_receivers_1hr", 0)),
        "unique_devices_1hr": int(data.get("unique_devices_1hr", 0)),

        "amount_zscore": float(data.get("amount_zscore", 0)),
        "amount_vs_daily_avg": float(data.get("amount_vs_daily_avg", 0)),
        "history_size": int(data.get("history_size", 0)),
        "is_round_number": int(data.get("is_round_number", 0)),

        "hour_of_day": int(data.get("hour_of_day", 0)),
        "day_of_week": int(data.get("day_of_week", 0)),
        "is_weekend": int(data.get("is_weekend", 0)),
        "is_night": int(data.get("is_night", 0)),
        "days_since_last_txn": float(data.get("days_since_last_txn", 0)),
        "is_first_txn_ever": int(data.get("is_first_txn_ever", 0)),

        "is_new_device": int(data.get("is_new_device", 0)),
        "device_txn_count": int(data.get("device_txn_count", 0)),
        "device_vpa_count": int(data.get("device_vpa_count", 0)),
        "device_last_seen_hours_ago": float(data.get("device_last_seen_hours_ago", 0)),
        "device_risk_score": float(dev_risk),
        "sender_device_count": int(data.get("sender_device_count", 0)),

        "distance_from_last_txn_km": float(dist_km),
        "txn_speed_kmph": float(data.get("txn_speed_kmph", 0)),
        "is_geo_impossible": int(data.get("is_geo_impossible", 0)),

        "sender_degree_1hr": int(data.get("sender_degree_1hr", 0)),
        "receiver_degree_1hr": int(data.get("receiver_degree_1hr", 0)),
        "is_mule_account": int(is_mule),
        "is_high_sender": int(data.get("is_high_sender", 0)),
        "chain_length": int(data.get("chain_length", 0)),

        "sender_vpa_age_days": float(data.get("sender_vpa_age_days", 0)),
        "receiver_vpa_age_days": float(data.get("receiver_vpa_age_days", 0)),
        "sender_txn_count_total": int(data.get("sender_txn_count_total", 0)),
        "receiver_txn_count_total": int(data.get("receiver_txn_count_total", 0)),
        "vpa_similarity_score": float(data.get("vpa_similarity_score", 0)),

        "is_merchant_txn": int(data.get("is_merchant_txn", 0)),
        "merchant_avg_txn_amount": float(data.get("merchant_avg_txn_amount", 0)),
        "merchant_txn_count": int(data.get("merchant_txn_count", 0)),
        "merchant_category_risk": float(data.get("merchant_category_risk", 0)),
        "merchant_age_days": float(data.get("merchant_age_days", 0)),
        "merchant_dispute_rate": float(data.get("merchant_dispute_rate", 0)),

        "fraud_flag": fraud_flag,
        "is_fraud": int(label),
    }


# ================= SHUTDOWN =================
def shutdown(sig, frame):
    print("\n🛑 Shutting down...")
    insert_batch()
    cursor.close()
    conn.close()
    sys.exit(0)


# ================= MAIN =================
def main():
    global conn, cursor

    print("🚀 DB Consumer Starting...")

    conn = get_db_connection()
    cursor = conn.cursor()

    consumer = get_kafka_consumer()

    signal.signal(signal.SIGINT, shutdown)

    for msg in consumer:
        try:
            data = clean_data(msg.value)
            batch.append(data)

            if len(batch) >= BATCH_SIZE:
                insert_batch()

        except Exception as e:
            print("❌ Processing error:", e)


if __name__ == "__main__":
    main()