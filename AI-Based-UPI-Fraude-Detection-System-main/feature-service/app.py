import json
import time
import os
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
from concurrent.futures import ThreadPoolExecutor

# ================= FEATURE MODULES =================
from velocity import update_velocity
from device import compute_device_features
from temporal import compute_temporal_features
from amount_features import compute_amount_features
from geo import compute_geo_features
from graph_features import compute_graph_features
from vpa import compute_vpa_features
from merchant import compute_merchant_features

# ================= CONFIG =================
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
GROUP_ID = "feature-service-production"
MAX_WORKERS = 32   # ⚠️ tuned for stability (not 50 to avoid CPU thrash)

print("🚀 Feature Service Starting...")
print(f"🧠 Group ID: {GROUP_ID}")

# ================= SAFE MERGE =================
def safe_merge(txn: dict, features: dict) -> dict:
    """
    Safe feature merge without bias.
    """
    if not features:
        return txn

    for k, v in features.items():
        txn[k] = v

    return txn


# ================= TIMESTAMP FIX =================
def normalize_timestamp(txn):
    raw_ts = txn.get("timestamp", time.time())

    try:
        ts = float(raw_ts)
    except:
        ts = time.time()

    txn["timestamp"] = ts
    txn["unix_timestamp"] = ts
    return ts


# ================= KAFKA CONNECT =================
while True:
    try:
        consumer = KafkaConsumer(
            "upi_transactions",
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            max_poll_records=1000,
        )

        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode(),
            compression_type="gzip",
            batch_size=65536,
            linger_ms=10,
            acks=1,
            retries=3,
        )

        print("✅ Connected to Kafka")
        break

    except NoBrokersAvailable:
        print("⏳ Waiting for Kafka...")
        time.sleep(3)

print("🔥 Feature Service Running (Optimized Mode)...")

# ================= PROCESS FUNCTION =================
def process_transaction(txn: dict):

    t_start = time.time()

    try:
        timestamp = normalize_timestamp(txn)

        sender   = txn.get("sender_vpa", "")
        receiver = txn.get("receiver_vpa", "")
        amount   = float(txn.get("amount", 0))
        device_id = txn.get("device_id", "")

        # ================= BASIC FEATURES =================
        velocity = update_velocity(sender, amount, receiver, device_id)
        temporal = compute_temporal_features(sender, timestamp)
        device   = compute_device_features(sender, device_id)
        amount_f = compute_amount_features(sender, amount)

        # ================= ADVANCED FEATURES =================
        try:
            geo      = compute_geo_features(sender, timestamp)
            graph    = compute_graph_features(sender, receiver, timestamp)
            vpa_feat = compute_vpa_features(sender, receiver, timestamp)
            merchant = compute_merchant_features(receiver, amount, timestamp)
        except Exception:
            geo, graph, vpa_feat, merchant = {}, {}, {}, {}

        # ================= MERGE =================
        txn = safe_merge(txn, velocity)
        txn = safe_merge(txn, temporal)
        txn = safe_merge(txn, device)
        txn = safe_merge(txn, amount_f)
        txn = safe_merge(txn, geo)
        txn = safe_merge(txn, graph)
        txn = safe_merge(txn, vpa_feat)
        txn = safe_merge(txn, merchant)

        # ================= LATENCY =================
        latency_ms = round((time.time() - t_start) * 1000, 2)
        txn["feature_latency_ms"] = latency_ms

        return txn, latency_ms

    except Exception as e:
        return None, 0


# ================= MAIN LOOP =================
latencies = []
count = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

    while True:
        try:
            msg_batch = consumer.poll(timeout_ms=1000, max_records=1000)

            if not msg_batch:
                continue

            futures = []

            for tp, records in msg_batch.items():
                for record in records:
                    futures.append(executor.submit(process_transaction, record.value))

            for f in futures:
                txn, lat = f.result()

                if txn is None:
                    continue

                try:
                    producer.send("upi_features",
                                  key=txn.get("sender_vpa", "unknown"),
                                  value=txn)
                except Exception:
                    continue

                latencies.append(lat)
                count += 1

                # ================= LOGGING =================
                if count % 2000 == 0:
                    producer.flush()

                    lat_sorted = sorted(latencies)
                    p50 = lat_sorted[len(lat_sorted)//2] if lat_sorted else 0
                    p99 = lat_sorted[int(len(lat_sorted)*0.99)] if lat_sorted else 0

                    print(f"📊 {count:,} txns | p50={p50:.1f}ms | p99={p99:.1f}ms")

                    latencies.clear()

            producer.flush()

        except Exception as e:
            print("❌ Main Loop Error:", e)
            time.sleep(1)