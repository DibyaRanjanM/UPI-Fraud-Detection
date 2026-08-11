import json
import time
import os
import requests
from kafka import KafkaConsumer, KafkaProducer
from ensemble import EnsembleScorer
from risk_tier import assign_tier, tier_requires_alert, tier_requires_gateway
from prometheus_client import start_http_server, Histogram, Gauge, Counter

KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
GATEWAY_BASE_URL = os.getenv("GATEWAY_URL", "http://localhost:8001")

# Prometheus metrics
INFERENCE_LATENCY = Histogram(
    "inference_latency_ms",
    "End-to-end latency from Kafka receive to risk tier assigned",
    buckets=[10, 25, 50, 100, 150, 200, 300, 500, 1000]
)
FRAUD_ALERT_RATE = Counter(
    "fraud_alerts_total",
    "Total fraud alerts by risk tier",
    ["risk_tier"]
)
ENSEMBLE_SCORE_DIST = Histogram(
    "ensemble_score",
    "Distribution of ensemble scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)
GATEWAY_LATENCY = Histogram(
    "gateway_webhook_latency_ms",
    "Round-trip time to gateway hold/block API",
    buckets=[10, 50, 100, 200, 500, 1000, 2000]
)
GATEWAY_FAILURES = Counter(
    "gateway_webhook_failures_total",
    "Gateway webhook call failures"
)

# Start Prometheus metrics server
start_http_server(8002)
print("Prometheus metrics on :8002")

# Load ensemble scorer (loads all 3 models)
scorer = EnsembleScorer()

consumer = KafkaConsumer(
    "upi_features",
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    group_id="ml-service-v1",
    auto_offset_reset="latest",
    max_poll_records=200,
)

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    compression_type="gzip",
    acks=1,
)


def call_gateway(tier: str, txn_id: str, score: float, reason: str):
    endpoint = f"{GATEWAY_BASE_URL}/{'hold' if tier == 'High-Risk' else 'block'}"
    payload  = {"txn_id": txn_id, "risk_score": score, "reason": reason}
    t0 = time.time()
    try:
        resp = requests.post(endpoint, json=payload, timeout=2)
        latency = (time.time() - t0) * 1000
        GATEWAY_LATENCY.observe(latency)
        return resp.json()
    except Exception as e:
        GATEWAY_FAILURES.inc()
        print(f"Gateway failed for {txn_id}: {e}")
        # Push to dead-letter queue
        producer.send("gateway_dlq", value={
            "txn_id": txn_id, "tier": tier,
            "score": score, "reason": reason,
            "failed_at": time.time()
        })
        return None


print("ML Scoring Service started")

for msg in consumer:
    t0  = time.time()
    txn = msg.value

    try:
        result = scorer.score(txn)
        txn.update(result)

        latency_ms = round((time.time() - t0) * 1000, 2)
        txn["total_latency_ms"] = latency_ms

        INFERENCE_LATENCY.observe(latency_ms)
        ENSEMBLE_SCORE_DIST.observe(result["ensemble_score"])

        # Publish to scored_transactions (all tiers)
        producer.send("scored_transactions", value=txn)

        tier = result["risk_tier"]

        # Publish alert for non-legitimate
        if tier_requires_alert(tier):
            FRAUD_ALERT_RATE.labels(risk_tier=tier).inc()
            # Include all enriched data in alert
            producer.send("fraud_alerts", value=txn)

        # Gateway webhook
        if tier_requires_gateway(tier):
            call_gateway(
                tier,
                txn["txn_id"],
                result["ensemble_score"],
                txn.get("fraud_flag", "UNKNOWN")
            )

        status = "BREACH" if latency_ms > 200 else "OK"
        print(f"[{status}][{tier}] {txn['txn_id'][:8]} "
              f"score={result['ensemble_score']:.3f} "
              f"latency={latency_ms}ms")

    except Exception as e:
        print(f"Scoring error for {txn.get('txn_id', '?')}: {e}")
        continue