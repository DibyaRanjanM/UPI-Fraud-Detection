# Deployment & Operations Guide — Sentinel Oversight

> Guide for deploying, operating, and troubleshooting the Sentinel Oversight platform.

---

## 1. System Requirements

### Hardware (Minimum)

| Resource | Minimum | Recommended |
|---|---|---|
| **RAM** | 4 GB free | 8 GB+ free |
| **CPU** | 4 cores | 8 cores |
| **Disk** | 10 GB free | 50 GB+ (for data retention) |
| **GPU** | Not required | Optional (CUDA for AE inference) |

### Software Dependencies

| Software | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Backend services |
| **Node.js** | 18+ | Frontend build |
| **Docker Desktop** | Latest | Infrastructure containers |
| **PowerShell** | 5.1+ | Start/stop scripts (Windows) |

---

## 2. Startup Procedure

### Automated Start (Recommended)

```powershell
# Full platform start
.\start.ps1

# Skip Docker (containers already running)
.\start.ps1 -NoDocker

# Minimal mode (skip simulator — low resource usage)
.\start.ps1 -Minimal
```

**Startup Sequence:**

| Phase | Service | Port | Dependencies |
|---|---|---|---|
| 1 | Docker (Kafka, Redis, PostgreSQL, Prometheus, Grafana) | 9092, 6379, 5432, 9090, 3001 | Docker Desktop |
| 2 | Gateway Simulator | 8001 | None |
| 3 | Feature Service | — | Kafka |
| 3 | Graph Service | — | Kafka, Redis |
| 3 | ML Service | 8002 | Kafka, model artifacts |
| 3 | DLQ Consumer | — | Kafka, Gateway |
| 3 | DB Consumer | — | Kafka, PostgreSQL |
| 4 | API Gateway | 8000 | Kafka, Redis |
| 5 | Simulator | — | Kafka |
| 6 | Frontend | 5173 | API Gateway |

**Safety Checks:**
- Minimum 2 GB free RAM required (auto-abort below 2 GB)
- Auto-enables Minimal mode below 2.5 GB free RAM
- Stale PID file from previous runs is cleaned automatically

### Shutdown

```powershell
# Graceful shutdown (tracked PIDs only)
.\stop.ps1

# Force shutdown (includes orphaned windows)
.\stop.ps1 -Force
```

**Shutdown Sequence:**
1. Kill all tracked child processes (via PID file)
2. Kill parent PowerShell windows (via PID file)
3. (If `-Force`) Kill any orphaned UPI-* titled windows
4. Stop Docker containers (`docker-compose down`)

---

## 3. Service Management

### Process Tracking

All service PIDs are stored in `.service_pids`:
```
12345|FeatureService
12346|MLService
12347|GraphService
...
```

### Individual Service Restart

To restart a single service without affecting others:

```powershell
# Find the service PID from .service_pids
Get-Content .service_pids

# Kill specific service
Stop-Process -Id <PID> -Force

# Restart it manually
cd ml-service
python app.py
```

### Service Health Checks

| Service | Health Check | Expected |
|---|---|---|
| API Gateway | `curl http://localhost:8000/health` | `{"status": "ok"}` |
| Gateway Sim | `curl http://localhost:8001/health` | `{"status": "ok"}` |
| ML Metrics | `curl http://localhost:8002/metrics` | Prometheus text |
| Kafka | `docker exec kafka kafka-topics --list --bootstrap-server localhost:29092` | Topic list |
| Redis | `docker exec redis redis-cli ping` | `PONG` |
| PostgreSQL | `docker exec postgres psql -U admin -d fraud_db -c "SELECT 1"` | `1` |
| Frontend | Open `http://localhost:5173` | Dashboard loads |

---

## 4. Monitoring & Alerting

### Prometheus Targets

Configuration in `observability/prometheus.yml`:

| Job | Target | Scrape Path |
|---|---|---|
| `api-gateway` | `host.docker.internal:8000` | `/prometheus` |
| `ml-service` | `host.docker.internal:8002` | `/metrics` |
| `gateway-simulator` | `host.docker.internal:8001` | *(default)* |

### Key Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold | Action |
|---|---|---|---|
| `inference_latency_ms` (p99) | > 150ms | > 200ms | Scale ML Service |
| `fraud_alerts_total` rate | > 20/min | > 50/min | Investigate fraud campaign |
| `gateway_webhook_failures_total` | > 5/min | > 20/min | Check gateway health |
| `false_positive_rate` | > 5% | > 10% | Retrain models |
| `kafka_consumer_lag` | > 1000 | > 5000 | Scale consumers |

### Grafana Access

- **URL:** `http://localhost:3001`
- **Credentials:** `admin` / `admin123`
- **Data Source:** Prometheus (`http://prometheus:9090`)

---

## 5. Kafka Operations

### Topic Management

```bash
# List topics
docker exec kafka kafka-topics --list --bootstrap-server localhost:29092

# Describe a topic
docker exec kafka kafka-topics --describe \
  --topic upi_transactions \
  --bootstrap-server localhost:29092

# Check consumer group lag
docker exec kafka kafka-consumer-groups \
  --describe --group ml-service-v1 \
  --bootstrap-server localhost:29092
```

### Expected Topics

| Topic | Partitions | Consumers |
|---|---|---|
| `upi_transactions` | 1 | feature-service-production |
| `upi_features` | 1 | ml-service-v1, db-consumer-live-v1 |
| `scored_transactions` | 1 | api-gw-scored, graph-service-v1 |
| `fraud_alerts` | 1 | api-gw-alerts |
| `risk_escalations` | 1 | api-gw-escalations |
| `gateway_dlq` | 1 | dlq-retry-v1 |
| `gateway_dlq_dead` | 1 | *(none — terminal storage)* |

---

## 6. Database Operations

### PostgreSQL Access

```bash
# Connect to fraud_db
docker exec -it postgres psql -U admin -d fraud_db

# Check transaction count
SELECT COUNT(*) FROM transactions;

# Check fraud distribution
SELECT fraud_flag, COUNT(*), ROUND(COUNT(*)::numeric / (SELECT COUNT(*) FROM transactions) * 100, 2) as pct
FROM transactions
GROUP BY fraud_flag
ORDER BY COUNT(*) DESC;

# Check recent transactions
SELECT txn_id, sender_vpa, receiver_vpa, amount, fraud_flag
FROM transactions
ORDER BY unix_timestamp DESC
LIMIT 10;

# Check analyst decisions
SELECT * FROM analyst_decisions ORDER BY decided_at DESC LIMIT 10;
```

### Schema Reference

See `init.sql` for complete schema definition. Key tables:

| Table | Purpose | Key Indexes |
|---|---|---|
| `transactions` | All enriched transactions | `sender_vpa`, `receiver_vpa`, `unix_timestamp`, `is_fraud` |
| `analyst_decisions` | Analyst decision log | `txn_id`, `decided_at` |

---

## 7. Troubleshooting

### Common Issues

#### Kafka Connection Failures

**Symptoms:** Services stuck at "Waiting for Kafka..." or "NoBrokersAvailable"

**Solution:**
```powershell
# Check if Kafka container is running
docker ps | findstr kafka

# If not running, restart Docker services
docker-compose up -d

# Wait 30 seconds for Kafka to initialize, then restart services
```

#### ML Service Model Loading Errors

**Symptoms:** "FileNotFoundError" or "Model loading failed"

**Solution:**
```powershell
# Check if model files exist
ls ml-service/models/

# If missing, run the training pipeline
cd notebooks
python 02_train_models.py
```

#### High Memory Usage

**Symptoms:** System slowdown, services crashing

**Solution:**
```powershell
# Use minimal mode
.\stop.ps1
.\start.ps1 -Minimal

# Or reduce simulator rate
# Edit simulator/producer.py: RATE_PER_SEC = 500
```

#### Frontend Not Loading

**Symptoms:** Blank page or connection error at localhost:5173

**Solution:**
```powershell
# Check if npm dependencies are installed
cd frontend
npm install

# Restart dev server
npm run dev
```

#### Redis Connection Issues

**Symptoms:** "Redis not available" warning in API Gateway

**Solution:**
```powershell
# Check Redis container
docker ps | findstr redis

# Test Redis connectivity
docker exec redis redis-cli ping

# If down, restart
docker-compose restart redis
```

#### Gateway Failures / DLQ Accumulation

**Symptoms:** `gateway_webhook_failures_total` increasing

**Solution:**
```powershell
# Check gateway simulator
curl http://localhost:8001/health

# If down, restart
cd gateway-simulator
uvicorn app:app --host 127.0.0.1 --port 8001
```

### Log Locations

All services log to stdout. When using `start.ps1`, each service runs in its own minimized PowerShell window. To view logs:

1. Find the service window in the taskbar
2. Click to restore the window
3. Logs are displayed in real-time

Service windows are titled:
- `UPI-FeatureService`
- `UPI-MLService`
- `UPI-GraphService`
- `UPI-APIGateway`
- `UPI-Simulator`
- `UPI-Frontend`
- `UPI-DLQConsumer`
- `UPI-DBConsumer`
- `UPI-GatewaySimulator`

---

## 8. Performance Tuning

### Feature Service

| Parameter | Default | Tuning Guide |
|---|---|---|
| `MAX_WORKERS` | 32 | Increase to 48–64 on 8+ core machines |
| `max_poll_records` | 1000 | Reduce to 500 if seeing memory pressure |
| `batch_size` | 65536 | Standard, rarely needs change |

### ML Service

| Parameter | Default | Tuning Guide |
|---|---|---|
| `max_poll_records` | 200 | Keep low — scoring is compute-intensive |
| Latency guard | 40ms | Raise to 60ms to allow more AE scoring |

### Simulator

| Parameter | Default | Tuning Guide |
|---|---|---|
| `RATE_PER_SEC` | 2000 | Reduce to 500 for development |
| `FRAUD_RATE` | 0.005 | Increase to 0.01 for testing fraud detection |

### Kafka

| Parameter | Default | Tuning Guide |
|---|---|---|
| `KAFKA_LOG_RETENTION_HOURS` | 2 | Increase for data replay scenarios |
| `compression_type` | gzip | Use lz4 for lower latency |

---

## 9. Backup & Recovery

### Model Artifacts

```powershell
# Backup model artifacts
Copy-Item -Recurse ml-service/models/ backup/models_$(Get-Date -Format "yyyyMMdd")/
```

### Database

```bash
# Backup PostgreSQL
docker exec postgres pg_dump -U admin fraud_db > backup_$(date +%Y%m%d).sql

# Restore PostgreSQL
docker exec -i postgres psql -U admin fraud_db < backup_20260407.sql
```

### Configuration

Key files to backup:
- `.env` — Environment variables
- `docker-compose.yml` — Infrastructure config
- `observability/prometheus.yml` — Monitoring config
- `fraud_patterns.json` — Fraud pattern catalog
- `ml-service/models/` — All model artifacts
