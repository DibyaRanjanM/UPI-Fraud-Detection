"""
DLQ Retry Consumer — retries failed gateway webhook calls.

Consumes from `gateway_dlq` topic and re-attempts the API call with
exponential backoff (max 3 retries).
"""
import json
import time
import os
import requests
from kafka import KafkaConsumer, KafkaProducer

KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
GATEWAY_BASE_URL = os.getenv("GATEWAY_URL", "http://localhost:8001")

MAX_RETRIES = 3
BASE_BACKOFF_S = 2

consumer = KafkaConsumer(
    "gateway_dlq",
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    group_id="dlq-retry-v1",
    auto_offset_reset="earliest",
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    acks=1,
)

print("DLQ Retry Consumer started — consuming gateway_dlq")


def retry_gateway_call(item: dict, attempt: int = 1) -> bool:
    """Retry a failed gateway webhook call with exponential backoff."""
    tier = item.get("tier", "High-Risk")
    txn_id = item.get("txn_id", "unknown")
    score = item.get("score", 0)
    reason = item.get("reason", "")

    endpoint = f"{GATEWAY_BASE_URL}/{'hold' if tier == 'High-Risk' else 'block'}"
    payload = {"txn_id": txn_id, "risk_score": score, "reason": reason}

    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        if resp.status_code == 200:
            print(f"  ✅ DLQ retry SUCCESS for {txn_id} (attempt {attempt})")
            return True
        else:
            print(f"  ⚠️  DLQ retry got {resp.status_code} for {txn_id} (attempt {attempt})")
            return False
    except Exception as e:
        print(f"  ❌ DLQ retry FAILED for {txn_id} (attempt {attempt}): {e}")
        return False


for msg in consumer:
    item = msg.value
    txn_id = item.get("txn_id", "?")
    retry_count = item.get("retry_count", 0)

    if retry_count >= MAX_RETRIES:
        # Permanent failure — log and discard
        print(f"  ☠️  DLQ PERMANENT FAILURE for {txn_id} after {MAX_RETRIES} retries. Discarding.")
        producer.send("gateway_dlq_dead", value={
            **item,
            "permanently_failed": True,
            "discarded_at": time.time(),
        })
        continue

    # Exponential backoff
    backoff = BASE_BACKOFF_S * (2 ** retry_count)
    print(f"DLQ: retrying {txn_id} (attempt {retry_count + 1}/{MAX_RETRIES}) after {backoff}s backoff...")
    time.sleep(backoff)

    success = retry_gateway_call(item, retry_count + 1)

    if not success:
        # Re-enqueue with incremented retry count
        item["retry_count"] = retry_count + 1
        item["last_retry_at"] = time.time()
        producer.send("gateway_dlq", value=item)
        print(f"  ↩️  Re-enqueued {txn_id} for retry {retry_count + 2}")
