import json
import asyncio
import time
import os
import redis
import httpx
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from kafka import KafkaConsumer
from prometheus_client import make_asgi_app
from pydantic import BaseModel
from typing import Optional
import threading

from metrics import (
    ACTIVE_SSE_CONNECTIONS, GENAI_FIRST_TOKEN_MS,
    ANALYST_DECISIONS, FALSE_POSITIVE_RATE, FRAUD_CATCH_RATE, KAFKA_LAG
)

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'genai-service'))
from explainer import stream_fraud_explanation

# ================= CONFIG =================
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
POSTGRES_URL    = os.getenv("POSTGRES_URL", "postgresql://admin:admin123@localhost:5432/fraud_db")
ML_METRICS_URL  = os.getenv("ML_METRICS_URL", "http://localhost:8002/metrics")
REDIS_HOST      = os.getenv("REDIS_HOST", "localhost")

app = FastAPI(title="UPI Fraud Detection API Gateway")
APP_START_TS = time.time()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus
metrics_app = make_asgi_app()
app.mount("/prometheus", metrics_app)

# Redis (for graph data from graph-service)
try:
    rdb = redis.Redis(host=REDIS_HOST, port=6379, db=1, decode_responses=True)
    rdb.ping()
    print("✅ Connected to Redis")
except Exception:
    rdb = None
    print("⚠️  Redis not available — graph endpoint will return empty")

# ================= GLOBAL MEMORY =================
_alerts = []
_txns = []
_sse_queues = []
_txn_sse_queues = []
_held_txns = {}
_alert_rate = []
_escalations = []

# Analyst decision tracking for confusion matrix
_decisions = {
    "confirm_fraud": [],     # analyst confirmed this IS fraud
    "mark_legitimate": [],   # analyst confirmed this is NOT fraud (false positive)
    "escalate": [],
    "notes": {},             # txn_id -> note text
}
_confusion = {
    "tp": 0,   # model said fraud, analyst confirmed fraud
    "fp": 0,   # model said fraud, analyst said legitimate
    "fn": 0,   # model said legitimate, but was fraud (estimated)
    "tn": 0,   # model said legitimate, was legitimate
}

# ================= TIER NORMALISATION =================
TIER_MAP = {
    "BLOCK": "Block", "Block": "Block",
    "HIGH": "High-Risk", "HIGH-RISK": "High-Risk", "High-Risk": "High-Risk",
    "SUSPICIOUS": "Suspicious", "Suspicious": "Suspicious",
    "SAFE": "Legitimate", "LEGITIMATE": "Legitimate", "Legitimate": "Legitimate",
}

def normalize_risk_tier(tier: str) -> str:
    return TIER_MAP.get((tier or "").strip(), "Legitimate")


def enrich_txn(txn: dict):
    txn["risk_tier"] = normalize_risk_tier(txn.get("risk_tier"))
    txn["risk_score"] = txn.get("ensemble_score", 0)

    # Flatten model scores if nested
    ms = txn.get("model_scores", {})
    if ms and "if_score" not in txn:
        txn["if_score"] = ms.get("isolation_forest", 0)
        txn["ae_score"] = ms.get("autoencoder", 0)
        txn["xgb_score"] = ms.get("xgboost", 0)

    txn["latency_ms"] = txn.get("total_latency_ms", txn.get("latency_ms", 0))
    txn["explainability"] = txn.get("shap_top5", [])
    return txn


# ================= RESILIENT KAFKA CONSUMERS =================
def _consume_scored():
    while True:
        try:
            consumer = KafkaConsumer(
                "scored_transactions",
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="api-gw-scored",
                auto_offset_reset="latest",
            )

            print("✅ Connected to Kafka (scored_transactions)")

            while True:
                msgs = consumer.poll(timeout_ms=1000)

                if not msgs:
                    continue

                for tp, records in msgs.items():
                    for msg in records:
                        txn = enrich_txn(msg.value)

                        _txns.insert(0, txn)
                        if len(_txns) > 5000:
                            _txns.pop()

                        for q in _txn_sse_queues:
                            try:
                                q.put_nowait(txn)
                            except Exception:
                                pass

        except Exception as e:
            print(f"🔥 Scored consumer crashed: {e}")
            time.sleep(3)


def _consume_alerts():
    while True:
        try:
            consumer = KafkaConsumer(
                "fraud_alerts",
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="api-gw-alerts",
                auto_offset_reset="latest",
            )

            print("✅ Connected to Kafka (fraud_alerts)")

            while True:
                msgs = consumer.poll(timeout_ms=1000)

                if not msgs:
                    continue

                for tp, records in msgs.items():
                    for msg in records:
                        alert = enrich_txn(msg.value)

                        _alerts.insert(0, alert)
                        if len(_alerts) > 500:
                            _alerts.pop()

                        if alert["risk_tier"] in ["High-Risk", "Block"]:
                            _held_txns[alert.get("txn_id", "")] = time.time()

                        _alert_rate.append(time.time())

                        for q in _sse_queues:
                            try:
                                q.put_nowait(alert)
                            except Exception:
                                pass

        except Exception as e:
            print(f"🔥 Alerts consumer crashed: {e}")
            time.sleep(3)


def _consume_escalations():
    """Consume risk_escalations from graph service."""
    while True:
        try:
            consumer = KafkaConsumer(
                "risk_escalations",
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="api-gw-escalations",
                auto_offset_reset="latest",
            )

            print("✅ Connected to Kafka (risk_escalations)")

            while True:
                msgs = consumer.poll(timeout_ms=1000)

                if not msgs:
                    continue

                for tp, records in msgs.items():
                    for msg in records:
                        esc = msg.value
                        _escalations.insert(0, esc)
                        if len(_escalations) > 200:
                            _escalations.pop()

                        # Update the original transaction's tier in memory
                        txn_id = esc.get("txn_id")
                        new_tier = normalize_risk_tier(esc.get("new_tier", ""))
                        for t in _txns:
                            if t.get("txn_id") == txn_id:
                                t["risk_tier"] = new_tier
                                t["escalated"] = True
                                t["escalation_reason"] = esc.get("reason", "")
                                break

                        # Also push to alert stream
                        for q in _sse_queues:
                            try:
                                q.put_nowait(esc)
                            except Exception:
                                pass

        except Exception as e:
            print(f"🔥 Escalations consumer crashed: {e}")
            time.sleep(3)


# Start background consumers
threading.Thread(target=_consume_scored, daemon=True).start()
threading.Thread(target=_consume_alerts, daemon=True).start()
threading.Thread(target=_consume_escalations, daemon=True).start()


# ================= BASIC API =================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "txns": len(_txns),
        "alerts": len(_alerts),
        "held": len(_held_txns),
        "escalations": len(_escalations),
    }


@app.get("/transactions")
def get_txns(limit: int = 200):
    return _txns[:limit]


@app.get("/alerts")
def get_alerts(limit: int = 100):
    return _alerts[:limit]


# ================= SSE STREAMS =================
@app.get("/stream/transactions")
async def stream_txns(request: Request):
    queue = asyncio.Queue(maxsize=200)
    _txn_sse_queues.append(queue)

    async def gen():
        try:
            for txn in _txns[:50]:
                yield f"data: {json.dumps(txn)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    txn = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(txn)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _txn_sse_queues.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/stream/alerts")
async def stream_alerts(request: Request):
    queue = asyncio.Queue(maxsize=100)
    _sse_queues.append(queue)
    ACTIVE_SSE_CONNECTIONS.inc()

    async def gen():
        try:
            for alert in _alerts[:20]:
                yield f"data: {json.dumps(alert)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    alert = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(alert)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _sse_queues.remove(queue)
            ACTIVE_SSE_CONNECTIONS.dec()

    return StreamingResponse(gen(), media_type="text/event-stream")


# ================= SYSTEM METRICS =================
@app.get("/metrics/system")
def metrics_system():
    now = time.time()

    recent_txns = [
        t for t in _txns[:500]
        if t.get("timestamp") and t.get("timestamp") > now - 60
    ]

    tps = len(recent_txns) / 60 if recent_txns else 0

    latencies = [t.get("latency_ms", 0) for t in _txns[:200]]
    avg_lat = sum(latencies) / len(latencies) if latencies else 0

    alerts_last_min = sum(1 for t in _alert_rate if t > now - 60)

    # SLA breach calculation
    sla_breaches = sum(1 for lat in latencies if lat > 200)
    sla_breach_pct = round(sla_breaches / max(len(latencies), 1) * 100, 1)

    # FPR & Recall from analyst decisions
    total_reviewed = _confusion["tp"] + _confusion["fp"]
    fpr = round(_confusion["fp"] / max(total_reviewed, 1) * 100, 2)
    recall = round(_confusion["tp"] / max(_confusion["tp"] + _confusion["fn"], 1) * 100, 1)

    # Drift indicators
    drift_status = "Stable"
    drift_psi = 0.0

    # Fraud pressure (based on alert rate)
    if alerts_last_min > 20:
        fraud_pressure = "HIGH"
    elif alerts_last_min > 5:
        fraud_pressure = "MEDIUM"
    else:
        fraud_pressure = "LOW"

    return {
        "tps": round(tps, 2),
        "latency_ms": round(avg_lat, 2),
        "alerts_per_min": alerts_last_min,
        "held": len(_held_txns),
        "held_count": len(_held_txns),
        "queue_size": len(_txns),
        "alert_queue_size": len(_alerts),
        "uptime": int(time.time() - APP_START_TS),
        "uptime_seconds": int(time.time() - APP_START_TS),
        "fpr": fpr,
        "recall": recall,
        "sla_ok": sla_breach_pct < 5,
        "sla_breach_pct": sla_breach_pct,
        "drift_status": drift_status,
        "drift_psi": drift_psi,
        "fraud_pressure": fraud_pressure,
        "kafka_lag": len(_txns),
        "gateway_failures": 0,
        "genai_first_token_ms": 0,
        "active_sse_connections": len(_sse_queues) + len(_txn_sse_queues),
        "latency": {
            "feature": round(avg_lat * 0.4, 2),
            "model": round(avg_lat * 0.5, 2),
            "api": round(avg_lat * 0.1, 2),
        },
    }


# ================= ANALYTICS METRICS =================
@app.get("/metrics/analytics")
def metrics_analytics():
    """Trend data, histogram, and model score averages for the dashboard."""
    now = time.time()

    # --- Trend (last 20 time windows of 30s each) ---
    trend = []
    for i in range(20):
        t_start = now - (20 - i) * 30
        t_end = t_start + 30
        window_txns = [t for t in _txns if t.get("timestamp") and t_start <= t.get("timestamp") < t_end]
        fraud = sum(1 for t in window_txns if t.get("risk_tier") in ["Suspicious", "High-Risk", "Block"])
        legit = len(window_txns) - fraud
        label = time.strftime("%H:%M", time.localtime(t_start))
        trend.append({"t": label, "fraud": fraud, "legit": legit})

    # --- Score Histogram (10 bins, 0.0-1.0) ---
    histogram = []
    for i in range(10):
        lo = i / 10
        hi = (i + 1) / 10
        count = sum(1 for t in _txns[:1000] if lo <= (t.get("ensemble_score") or 0) < hi)
        histogram.append({
            "range": f"{lo:.1f}-{hi:.1f}",
            "count": count,
            "idx": i,
        })

    # --- Model score averages ---
    recent = _txns[:1000]
    n = max(len(recent), 1)
    model_scores = {
        "iso_avg": round(sum(t.get("if_score", 0) for t in recent) / n, 4),
        "ae_avg": round(sum(t.get("ae_score", 0) for t in recent) / n, 4),
        "xgb_avg": round(sum(t.get("xgb_score", 0) for t in recent) / n, 4),
        "ensemble_avg": round(sum(t.get("ensemble_score", 0) for t in recent) / n, 4),
    }

    return {
        "trend": trend,
        "histogram": histogram,
        "model_scores": model_scores,
    }


# ================= MODEL PERFORMANCE METRICS =================
@app.get("/metrics/model")
def metrics_model():
    """Confusion matrix and performance metrics from analyst decisions."""
    tp = _confusion["tp"]
    fp = _confusion["fp"]
    fn = _confusion["fn"]
    tn = _confusion["tn"]
    total = tp + fp

    precision = round(tp / max(tp + fp, 1) * 100, 1)
    recall = round(tp / max(tp + fn, 1) * 100, 1)
    fpr = round(fp / max(fp + tn, 1) * 100, 2)

    # F2-score (recall-weighted)
    beta = 2
    if precision + recall > 0:
        f2 = round((1 + beta**2) * (precision/100 * recall/100) /
                    (beta**2 * precision/100 + recall/100), 4)
    else:
        f2 = 0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "total_reviewed": total,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": fpr,
        "fraud_catch_rate": recall,
        "f2_score": f2,
    }


# ================= GRAPH DATA =================
@app.get("/graph/data")
def graph_data():
    """Return graph nodes and links for the network visualisation."""
    # Try Redis first (populated by graph-service)
    if rdb is not None:
        try:
            nodes_raw = rdb.get("graph:nodes")
            links_raw = rdb.get("graph:links")

            if nodes_raw and links_raw:
                nodes = json.loads(nodes_raw)
                links = json.loads(links_raw)
                if nodes:  # Only return if we actually have data
                    return {"nodes": nodes, "links": links}
        except Exception:
            pass  # Fall through to memory fallback

    # Fallback: build from in-memory transactions
    return _build_graph_from_memory()


def _build_graph_from_memory():
    """Fallback graph builder from in-memory transactions."""
    node_map = {}
    links = []

    for txn in _txns[:500]:
        sender = txn.get("sender_vpa", "")
        receiver = txn.get("receiver_vpa", "")
        tier = txn.get("risk_tier", "Legitimate")
        amount = txn.get("amount", 0)

        for vpa in [sender, receiver]:
            if vpa and vpa not in node_map:
                node_map[vpa] = {
                    "id": vpa,
                    "label": _mask_vpa(vpa),
                    "risk_tier": tier,
                    "pagerank": txn.get("sender_pagerank", 0) if vpa == sender else txn.get("receiver_pagerank", 0),
                    "txn_count": 1,
                    "community_id": txn.get("community_id"),
                    "chain_length": txn.get("chain_length", 0),
                    "fraud_hop_count": txn.get("fraud_hop_count", 999),
                    "is_star_receiver": txn.get("is_star_receiver", False),
                    "is_suspicious_cluster": False,
                }
            elif vpa in node_map:
                node_map[vpa]["txn_count"] += 1
                # Keep worst tier
                if _tier_severity(tier) > _tier_severity(node_map[vpa]["risk_tier"]):
                    node_map[vpa]["risk_tier"] = tier

        if sender and receiver:
            links.append({
                "source": sender,
                "target": receiver,
                "amount": amount,
                "risk_tier": tier,
                "is_chain": txn.get("chain_length", 0) >= 4,
            })

    return {
        "nodes": list(node_map.values())[:300],
        "links": links[:500],
    }


def _tier_severity(tier):
    return {"Legitimate": 0, "Suspicious": 1, "High-Risk": 2, "Block": 3}.get(tier, 0)


def _mask_vpa(vpa: str) -> str:
    if not vpa or "@" not in vpa:
        return "***"
    parts = vpa.split("@", 1)
    return f"{parts[0][:3]}***@{parts[1]}"


# ================= TRANSACTION LOOKUP =================
@app.get("/transaction/{txn_id}")
def get_transaction(txn_id: str):
    """Lookup a single transaction by ID from in-memory buffer."""
    txn = next((t for t in _txns if t.get("txn_id") == txn_id), None)
    if not txn:
        txn = next((a for a in _alerts if a.get("txn_id") == txn_id), None)
    if txn:
        return txn
    return {"error": "Transaction not found in buffer"}


# ================= INVESTIGATION ENDPOINTS =================
@app.get("/investigate/search")
def investigate_search(
    search_type: str = "vpa",
    query: str = "",
    limit: int = 50,
    min_amount: float = 0,
    max_amount: float = 999999999,
):
    """Search transactions by VPA, device ID, or amount range."""
    results = []

    for txn in _txns:
        if len(results) >= limit:
            break

        if search_type == "vpa":
            if query and (query in (txn.get("sender_vpa") or "") or query in (txn.get("receiver_vpa") or "")):
                results.append(txn)
        elif search_type == "device":
            if query and query in (txn.get("device_id") or ""):
                results.append(txn)
        elif search_type == "amount":
            amt = float(txn.get("amount", 0))
            if min_amount <= amt <= max_amount:
                results.append(txn)

    return {"results": results, "count": len(results)}


@app.get("/investigate/timeline/{vpa}")
def investigate_timeline(vpa: str, limit: int = 30):
    """Get transaction timeline for a specific VPA."""
    matches = [
        t for t in _txns
        if t.get("sender_vpa") == vpa or t.get("receiver_vpa") == vpa
    ]
    # Sort by timestamp descending
    matches.sort(key=lambda t: t.get("timestamp", 0), reverse=True)
    return {"timeline": matches[:limit], "vpa": vpa}


# ================= ANALYST DECISIONS =================
class DecisionRequest(BaseModel):
    action: str        # "confirm_fraud", "mark_legitimate", "escalate"
    note: Optional[str] = ""


@app.post("/decision/{txn_id}")
def analyst_decision(txn_id: str, req: DecisionRequest):
    """Record analyst decision and update confusion matrix."""
    action = req.action.lower().replace(" ", "_")

    # Find the transaction
    txn = next((t for t in _txns if t.get("txn_id") == txn_id), None)
    if not txn:
        txn = next((a for a in _alerts if a.get("txn_id") == txn_id), None)

    tier = txn.get("risk_tier", "Legitimate") if txn else "Unknown"

    decision_record = {
        "txn_id": txn_id,
        "action": action,
        "tier": tier,
        "timestamp": time.time(),
        "note": req.note,
    }

    if action == "confirm_fraud":
        _decisions["confirm_fraud"].append(decision_record)
        _confusion["tp"] += 1
        ANALYST_DECISIONS.labels(decision="confirm_fraud").inc()
    elif action == "mark_legitimate":
        _decisions["mark_legitimate"].append(decision_record)
        _confusion["fp"] += 1  # model said fraud (alert) but analyst says legit
        ANALYST_DECISIONS.labels(decision="mark_legitimate").inc()
    elif action == "escalate":
        _decisions["escalate"].append(decision_record)
        ANALYST_DECISIONS.labels(decision="escalate").inc()
    elif action == "note":
        _decisions["notes"][txn_id] = req.note

    # Update Prometheus gauges
    total_reviewed = _confusion["tp"] + _confusion["fp"]
    if total_reviewed > 0:
        fpr = _confusion["fp"] / total_reviewed * 100
        FALSE_POSITIVE_RATE.set(fpr)
        catch_rate = _confusion["tp"] / max(_confusion["tp"] + _confusion["fn"], 1) * 100
        FRAUD_CATCH_RATE.set(catch_rate)

    return {
        "status": "recorded",
        "txn_id": txn_id,
        "action": action,
        "confusion_matrix": _confusion,
    }


# ================= GENAI STREAMING =================
@app.get("/stream/explain/{txn_id}")
async def explain(txn_id: str, request: Request):

    txn = next((t for t in _txns if t.get("txn_id") == txn_id), None)
    if not txn:
        txn = next((a for a in _alerts if a.get("txn_id") == txn_id), None)

    async def gen():
        if not txn:
            yield f"data: {json.dumps({'token': 'Transaction not found in buffer. '})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        t0 = time.time()
        first_token = True
        async for token in stream_fraud_explanation(txn):
            if await request.is_disconnected():
                break
            if first_token:
                GENAI_FIRST_TOKEN_MS.set(round((time.time() - t0) * 1000))
                first_token = False
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")