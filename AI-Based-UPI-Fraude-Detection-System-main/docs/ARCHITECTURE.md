# System Architecture — Sentinel Oversight

> This document provides detailed architectural documentation for the Sentinel Oversight UPI Fraud Detection Platform.

---

## 1. High-Level Design Philosophy

Sentinel Oversight follows an **event-driven microservices architecture** with Apache Kafka as the central nervous system. Every service communicates asynchronously via Kafka topics, enabling:

- **Horizontal scalability** through Kafka consumer groups
- **Fault tolerance** via message persistence and DLQ retry mechanisms
- **Loose coupling** between services for independent deployment
- **Real-time processing** with sub-200ms end-to-end latency SLA

---

## 2. Data Flow Pipeline

### 2.1 Transaction Lifecycle

```
Phase 1: INGEST
  Producer → Kafka[upi_transactions]
  ↓
Phase 2: ENRICH
  Feature Service consumes upi_transactions
  → Computes 40+ features across 8 domains
  → Publishes to Kafka[upi_features]
  ↓
Phase 3: PERSIST (parallel branch)
  DB Consumer consumes upi_features
  → Cleans + adds chaos noise
  → Batch INSERT to PostgreSQL (1000/batch)
  ↓
Phase 4: SCORE
  ML Service consumes upi_features
  → 3-model ensemble (IF + AE + XGB)
  → Rule engine boost
  → Risk tier classification
  → Publishes to Kafka[scored_transactions]
  → If non-legitimate: publishes to Kafka[fraud_alerts]
  → If high-risk/block: calls Gateway (hold/block API)
  ↓
Phase 5: ANALYZE
  Graph Service consumes scored_transactions
  → Builds real-time directed graph (NetworkX)
  → Runs PageRank, Louvain, star/chain detection
  → Escalates risk tier if graph context warrants
  → Publishes to Kafka[risk_escalations]
  → Caches graph data to Redis
  ↓
Phase 6: SERVE
  API Gateway consumes scored_transactions, fraud_alerts, risk_escalations
  → Maintains in-memory buffers (5000 txns, 500 alerts)
  → Serves REST endpoints + SSE streams
  → Streams GenAI explanations on demand
  ↓
Phase 7: VISUALIZE
  Frontend (React) connects via SSE
  → Renders live dashboard with 5 tabs
  → Analyst decisions feedback to API Gateway
```

### 2.2 Kafka Topic Map

| Topic | Producer(s) | Consumer(s) | Retention | Description |
|---|---|---|---|---|
| `upi_transactions` | Simulator | Feature Service | 2 hours | Raw UPI transactions |
| `upi_features` | Feature Service | ML Service, DB Consumer | 2 hours | Enriched transactions with 40+ features |
| `scored_transactions` | ML Service | API Gateway, Graph Service | 2 hours | Scored transactions with risk tiers |
| `fraud_alerts` | ML Service | API Gateway | 2 hours | High-risk/block alerts only |
| `risk_escalations` | Graph Service | API Gateway | 2 hours | Graph-based risk tier upgrades |
| `gateway_dlq` | ML Service | DLQ Consumer | 24 hours | Failed gateway webhook calls |
| `gateway_dlq_dead` | DLQ Consumer | — (terminal) | 7 days | Permanently failed webhooks (exhausted retries) |

---

## 3. Service Architecture Details

### 3.1 Feature Service

**Pattern:** Stream processor (Kafka Consumer → Transform → Kafka Producer)  
**Concurrency:** ThreadPoolExecutor (32 workers)  
**Throughput:** Batch polling (1000 records/poll) with gzip compression

```
┌─────────────────────────────────────────────────────┐
│                  Feature Service                     │
│                                                      │
│  KafkaConsumer(upi_transactions)                    │
│       │                                              │
│       ▼                                              │
│  ThreadPoolExecutor(32)                              │
│       │                                              │
│  ┌────┴────┬────────┬──────────┬─────────┐          │
│  │velocity │ device │temporal  │amount   │          │
│  │ module  │ module │ module   │ module  │          │
│  └────┬────┴────┬───┴────┬─────┴────┬────┘          │
│       │         │        │          │                │
│  ┌────┴────┬────┴───┬────┴─────┬────┴────┐          │
│  │  geo    │ graph  │  vpa     │merchant│          │
│  │ module  │ module │ module   │ module  │          │
│  └────┬────┴────┬───┴────┬─────┴────┬────┘          │
│       │         │        │          │                │
│       └─────────┴────────┴──────────┘                │
│                    │                                  │
│              safe_merge()                            │
│                    │                                  │
│       KafkaProducer(upi_features)                   │
└─────────────────────────────────────────────────────┘
```

### 3.2 ML Service

**Pattern:** Streaming inference engine  
**Latency Guard:** Autoencoder skipped if >40ms already elapsed  
**SLA Target:** < 200ms total (ingest to tier assigned)

### 3.3 Graph Service

**Pattern:** Streaming graph builder with periodic analytics  
**Graph Engine:** NetworkX DiGraph (in-memory)  
**Edge TTL:** 30 minutes (auto-pruned every 500 txns)  
**PageRank:** Recomputed every 100 transactions  
**Communities:** Recomputed every 200 transactions  
**Escalation:** Published to Kafka for API Gateway consumption

### 3.4 API Gateway

**Pattern:** Aggregator + SSE gateway  
**Framework:** FastAPI with async support  
**Background:** 3 daemon threads consuming Kafka topics  
**Memory Buffers:**
- Transactions: 5,000 most recent
- Alerts: 500 most recent
- Escalations: 200 most recent

### 3.5 GenAI Service

**Pattern:** Async streaming LLM client  
**Providers:** Anthropic Claude Sonnet 4 / OpenAI GPT-4o  
**Fallback:** Deterministic local report generator (no API required)  
**Integration:** Invoked on-demand via API Gateway SSE endpoint

---

## 4. Infrastructure Layer

### 4.1 Docker Compose Services

```yaml
Services:
  - Zookeeper (Confluent 7.5)    # Kafka coordination
  - Kafka (Confluent 7.5)        # Message broker
  - Redis 7 (Alpine)             # Graph cache + fraud VPA tracking
  - PostgreSQL 15 (Alpine)       # Transaction persistence
  - Prometheus                   # Metrics collection
  - Grafana                      # Metrics visualization
```

### 4.2 Network Architecture

All Docker services communicate on a shared `fraud-net` bridge network. Application services run on the host and connect to Docker containers via localhost ports.

### 4.3 Data Persistence

| Store | Data | Retention | Volume |
|---|---|---|---|
| Kafka | Event streams | 2 hours | Ephemeral |
| PostgreSQL | Transaction records | Persistent | Named volume (`postgres_data`) |
| Redis | Graph cache, fraud VPAs | Ephemeral (LRU, 512MB cap) | None |
| File System | Model artifacts | Persistent | `ml-service/models/` |

---

## 5. Reliability Patterns

### 5.1 Dead-Letter Queue (DLQ)

When a gateway webhook call fails:
1. ML Service pushes the failed payload to `gateway_dlq` Kafka topic
2. DLQ Consumer picks it up and retries with exponential backoff (2s, 4s, 8s)
3. Max 3 retries before moving to `gateway_dlq_dead` (permanent failure)
4. Permanent failures are logged for manual investigation

### 5.2 Graceful Degradation

| Component Failure | System Behavior |
|---|---|
| LLM API unavailable | Deterministic local fallback explanation |
| Redis down | API Gateway falls back to in-memory graph builder |
| Gateway API failure | DLQ retry mechanism activates |
| Kafka temporarily unavailable | Consumers reconnect with 3-second backoff loops |
| High latency | Autoencoder scoring skipped (latency guard) |
| Low memory | Start script auto-enables Minimal mode |

### 5.3 Resilient Kafka Consumers

All Kafka consumers (API Gateway, Graph Service) are wrapped in `while True` loops with exception handling and 3-second reconnect delays, ensuring automatic recovery from broker restarts.

---

## 6. Performance Characteristics

| Metric | Target | Typical |
|---|---|---|
| End-to-end latency | < 200ms | 50–150ms |
| Transaction throughput | 2,000 TPS | 2,000+ TPS |
| Feature computation | < 50ms | 10–30ms |
| ML inference | < 100ms | 20–80ms |
| Graph analytics | < 50ms per txn | 5–20ms |
| GenAI first token | < 2,000ms | 500–1,500ms |
| Kafka consumer lag | < 1,000 msgs | < 500 msgs |

---

## 7. Security Considerations

> ⚠️ This is a demonstration platform. Production deployments must address:

- **API Keys**: Stored in environment variables, not committed to source control
- **VPA Masking**: All VPAs are masked (`rah***@oksbi`) in GenAI prompts and graph exports
- **CORS**: Currently open (`allow_origins=["*"]`) — restrict in production
- **Database**: Uses default credentials — change in production
- **Network**: No TLS between services — add in production
- **Authentication**: No auth on API endpoints — implement OAuth2/JWT in production
