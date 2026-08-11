# API Reference — Sentinel Oversight

> Complete REST API documentation for the API Gateway (`port 8000`) and Gateway Simulator (`port 8001`).

---

## Base URLs

| Service | Base URL |
|---|---|
| API Gateway | `http://localhost:8000` |
| Gateway Simulator | `http://localhost:8001` |
| ML Metrics | `http://localhost:8002` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3001` |

---

## API Gateway Endpoints (port 8000)

### Health & Status

#### `GET /health`

Returns the current system health status.

**Response:**
```json
{
  "status": "ok",
  "txns": 2500,
  "alerts": 45,
  "held": 3,
  "escalations": 12
}
```

---

### Transaction Data

#### `GET /transactions`

Returns recently scored transactions from the in-memory buffer.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 200 | Maximum number of transactions to return |

**Response:** Array of transaction objects

```json
[
  {
    "txn_id": "abc-123-def-456",
    "sender_vpa": "rahul123@oksbi",
    "receiver_vpa": "shop@ybl",
    "amount": 2500.00,
    "device_id": "DEV_A1B2C3D4E5F6",
    "timestamp": 1712534400.0,
    "risk_tier": "Suspicious",
    "ensemble_score": 0.4523,
    "if_score": 0.3210,
    "ae_score": 0.1854,
    "xgb_score": 0.5421,
    "confidence": "MEDIUM",
    "threshold_set": "default",
    "shap_top5": [
      {
        "feature": "txn_count_1min",
        "value": 8.0,
        "shap": 0.1245,
        "direction": "increases_risk"
      }
    ],
    "reasons": [
      {
        "type": "velocity",
        "impact": "high",
        "desc": "High transaction velocity"
      }
    ],
    "latency_ms": 85.3
  }
]
```

#### `GET /transaction/{txn_id}`

Lookup a single transaction by its ID.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `txn_id` | string | Transaction UUID |

**Response:** Transaction object (see above) or:
```json
{
  "error": "Transaction not found in buffer"
}
```

---

### Fraud Alerts

#### `GET /alerts`

Returns recent fraud alerts (non-legitimate tier transactions).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 100 | Maximum number of alerts to return |

**Response:** Array of enriched alert objects (same structure as transactions)

---

### Real-Time Streams (SSE)

All SSE endpoints use `text/event-stream` content type with JSON payloads.

#### `GET /stream/transactions`

Server-Sent Events stream of all scored transactions.

- **Initial burst:** Sends the 50 most recent transactions immediately
- **Heartbeat:** Sends `: heartbeat\n\n` every 30 seconds
- **Format:** `data: {json_object}\n\n`

**Usage:**
```javascript
const es = new EventSource('http://localhost:8000/stream/transactions');
es.onmessage = (event) => {
  const txn = JSON.parse(event.data);
  console.log(txn.risk_tier, txn.ensemble_score);
};
```

#### `GET /stream/alerts`

Server-Sent Events stream of fraud alerts only.

- **Initial burst:** Sends the 20 most recent alerts immediately
- **Heartbeat:** Every 30 seconds
- **Metrics:** Tracks `active_sse_connections` in Prometheus

#### `GET /stream/explain/{txn_id}`

Streaming GenAI fraud explanation for a specific transaction.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `txn_id` | string | Transaction UUID to explain |

**Response stream:**
```
data: {"token": "## 1. Fraud Summary\n"}

data: {"token": "Transaction abc-123 from ***@oksbi"}

data: {"token": " is classified as High-Risk..."}

data: {"done": true}
```

---

### System Metrics

#### `GET /metrics/system`

Comprehensive system performance metrics.

**Response:**
```json
{
  "tps": 42.5,
  "latency_ms": 85.3,
  "alerts_per_min": 12,
  "held": 3,
  "held_count": 3,
  "queue_size": 2500,
  "alert_queue_size": 45,
  "uptime": 3600,
  "uptime_seconds": 3600,
  "fpr": 4.2,
  "recall": 92.5,
  "sla_ok": true,
  "sla_breach_pct": 1.2,
  "drift_status": "Stable",
  "drift_psi": 0.0,
  "fraud_pressure": "MEDIUM",
  "kafka_lag": 250,
  "gateway_failures": 0,
  "genai_first_token_ms": 0,
  "active_sse_connections": 2,
  "latency": {
    "feature": 34.1,
    "model": 42.6,
    "api": 8.5
  }
}
```

**Fraud Pressure Levels:**

| Level | Condition | Description |
|---|---|---|
| `LOW` | ≤ 5 alerts/min | Normal operations |
| `MEDIUM` | 6–20 alerts/min | Elevated monitoring recommended |
| `HIGH` | > 20 alerts/min | Active fraud campaign suspected |

#### `GET /metrics/analytics`

Trend data, score distributions, and model averages.

**Response:**
```json
{
  "trend": [
    { "t": "14:00", "fraud": 2, "legit": 58 },
    { "t": "14:30", "fraud": 5, "legit": 45 }
  ],
  "histogram": [
    { "range": "0.0-0.1", "count": 892, "idx": 0 },
    { "range": "0.1-0.2", "count": 234, "idx": 1 }
  ],
  "model_scores": {
    "iso_avg": 0.1234,
    "ae_avg": 0.0567,
    "xgb_avg": 0.0891,
    "ensemble_avg": 0.0945
  }
}
```

#### `GET /metrics/model`

Confusion matrix and model performance from analyst decisions.

**Response:**
```json
{
  "true_positives": 45,
  "false_positives": 3,
  "false_negatives": 2,
  "true_negatives": 950,
  "total_reviewed": 48,
  "precision": 93.8,
  "recall": 95.7,
  "false_positive_rate": 0.31,
  "fraud_catch_rate": 95.7,
  "f2_score": 0.9523
}
```

---

### Graph Data

#### `GET /graph/data`

Returns network graph nodes and links for visualization.

**Data Source Priority:**
1. Redis cache (populated by Graph Service, TTL: 120s)
2. In-memory fallback (built from recent transactions)

**Response:**
```json
{
  "nodes": [
    {
      "id": "rahul123@oksbi",
      "label": "rah***@oksbi",
      "risk_tier": "Suspicious",
      "pagerank": 0.00234,
      "txn_count": 15,
      "community_id": 3,
      "chain_length": 2,
      "fraud_hop_count": 999,
      "is_star_receiver": false,
      "is_suspicious_cluster": true
    }
  ],
  "links": [
    {
      "source": "rahul123@oksbi",
      "target": "shop@ybl",
      "amount": 2500.00,
      "risk_tier": "Suspicious",
      "is_chain": false
    }
  ]
}
```

---

### Investigation

#### `GET /investigate/search`

Search transactions across multiple dimensions.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search_type` | string | `vpa` | Search type: `vpa`, `device`, `amount` |
| `query` | string | `""` | Search query (VPA or device ID) |
| `limit` | int | `50` | Maximum results |
| `min_amount` | float | `0` | Minimum amount (for `amount` search) |
| `max_amount` | float | `999999999` | Maximum amount (for `amount` search) |

**Example:**
```
GET /investigate/search?search_type=vpa&query=rahul123@oksbi&limit=20
```

**Response:**
```json
{
  "results": [ /* array of transaction objects */ ],
  "count": 15
}
```

#### `GET /investigate/timeline/{vpa}`

Get the transaction timeline for a specific VPA.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `vpa` | string (path) | — | VPA address |
| `limit` | int | `30` | Maximum timeline entries |

**Response:**
```json
{
  "timeline": [ /* transactions sorted by timestamp desc */ ],
  "vpa": "rahul123@oksbi"
}
```

---

### Analyst Decisions

#### `POST /decision/{txn_id}`

Record an analyst's decision on a flagged transaction.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `txn_id` | string | Transaction UUID |

**Request Body:**
```json
{
  "action": "confirm_fraud",
  "note": "Verified mule pattern via KYC records"
}
```

**Supported Actions:**

| Action | Effect | Confusion Matrix |
|---|---|---|
| `confirm_fraud` | Analyst confirms this IS fraud | TP += 1 |
| `mark_legitimate` | Analyst confirms this is NOT fraud | FP += 1 |
| `escalate` | Escalate for senior review | — |
| `note` | Add a note without changing status | — |

**Response:**
```json
{
  "status": "recorded",
  "txn_id": "abc-123",
  "action": "confirm_fraud",
  "confusion_matrix": {
    "tp": 45,
    "fp": 3,
    "fn": 2,
    "tn": 950
  }
}
```

---

### Prometheus Metrics

#### `GET /prometheus`

Standard Prometheus metrics endpoint (text format).

**Exposed Metrics:**

| Metric | Type | Labels | Description |
|---|---|---|---|
| `fraud_catch_rate` | Gauge | — | % of confirmed fraud caught |
| `false_positive_rate` | Gauge | — | % of false positives among reviewed |
| `active_sse_connections` | Gauge | — | Active SSE connections count |
| `genai_rationale_first_token_ms` | Gauge | — | GenAI first token latency |
| `analyst_decisions_total` | Counter | `decision` | Analyst decision counts |
| `kafka_consumer_lag` | Gauge | — | Consumer lag |

---

## Gateway Simulator Endpoints (port 8001)

### `POST /hold`

Place a transaction on hold (30-minute expiry).

**Request Body:**
```json
{
  "txn_id": "abc-123",
  "risk_score": 0.72,
  "reason": "Mule network pattern"
}
```

**Response:**
```json
{
  "status": "HELD",
  "txn_id": "abc-123",
  "hold_expires_at": "2026-04-07T23:00:00"
}
```

### `POST /block`

Permanently block a transaction.

**Request Body:** Same as `/hold`

**Response:**
```json
{
  "status": "BLOCKED",
  "txn_id": "abc-123",
  "reason_code": "FRAUD_MULE_NETWORK_PATT"
}
```

### `POST /release/{txn_id}`

Release a held transaction.

**Response:**
```json
{
  "status": "RELEASED",
  "txn_id": "abc-123"
}
```

### `GET /status/{txn_id}`

Check transaction status in the gateway.

**Response:** Hold/block details or `{"status": "NOT_FOUND"}`

### `GET /audit`

Get the gateway audit log.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 100 | Maximum audit entries |

### `GET /health`

Gateway health check.

**Response:**
```json
{
  "status": "ok",
  "held": 3,
  "blocked": 12
}
```

> **Note:** The gateway simulator has a 2% configurable failure rate to test the DLQ retry mechanism.

---

## ML Service Metrics (port 8002)

Standard Prometheus metrics endpoint at `/metrics`:

| Metric | Type | Buckets | Description |
|---|---|---|---|
| `inference_latency_ms` | Histogram | 10, 25, 50, 100, 150, 200, 300, 500, 1000 | Scoring latency |
| `ensemble_score` | Histogram | 0.1 – 1.0 (10 bins) | Score distribution |
| `fraud_alerts_total` | Counter | Label: `risk_tier` | Alert counts by tier |
| `gateway_webhook_latency_ms` | Histogram | 10, 50, 100, 200, 500, 1000, 2000 | Gateway API latency |
| `gateway_webhook_failures_total` | Counter | — | Failed gateway calls |
