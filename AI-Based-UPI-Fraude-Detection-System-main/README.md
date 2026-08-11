<p align="center">
  <h1 align="center">🛡️ Sentinel Oversight</h1>
  <p align="center">
    <strong>Real-Time UPI Fraud Detection & Intelligence Platform</strong>
  </p>
  <p align="center">
    A production-grade, event-driven fraud detection system for India's Unified Payments Interface (UPI) featuring ensemble ML scoring, real-time graph analytics, GenAI-powered explainability, and a live analyst command center.
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react" alt="React" />
  <img src="https://img.shields.io/badge/Kafka-Streaming-231F20?logo=apache-kafka" alt="Kafka" />
  <img src="https://img.shields.io/badge/PyTorch-AE-EE4C2C?logo=pytorch" alt="PyTorch" />
  <img src="https://img.shields.io/badge/XGBoost-Classifier-F76900" alt="XGBoost" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
</p>

---

## 📑 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Manual Setup](#manual-setup)
- [Service Documentation](#service-documentation)
  - [Transaction Simulator](#1-transaction-simulator)
  - [Feature Engineering Service](#2-feature-engineering-service)
  - [ML Scoring Service](#3-ml-scoring-service)
  - [Graph Analytics Service](#4-graph-analytics-service)
  - [GenAI Explainability Service](#5-genai-explainability-service)
  - [API Gateway](#6-api-gateway)
  - [Gateway Simulator](#7-gateway-simulator)
  - [Database Consumer](#8-database-consumer)
  - [Frontend Dashboard](#9-frontend-dashboard)
- [ML Pipeline](#ml-pipeline)
  - [Data Collection](#data-collection)
  - [Model Training](#model-training)
  - [Ensemble Strategy](#ensemble-strategy)
  - [Risk Tier Classification](#risk-tier-classification)
- [Fraud Detection Patterns](#fraud-detection-patterns)
- [API Reference](#api-reference)
- [Observability & Monitoring](#observability--monitoring)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**Sentinel Oversight** is an end-to-end, real-time fraud detection platform purpose-built for India's UPI transaction ecosystem. The system processes high-velocity transaction streams through a multi-stage pipeline:

1. **Ingest** — Simulated (or live) UPI transactions are published to Apache Kafka
2. **Enrich** — 40+ features are computed in real-time (velocity, device, geo, graph, temporal, VPA, merchant)
3. **Score** — A 3-model ensemble (Isolation Forest · Autoencoder · XGBoost) produces calibrated fraud scores
4. **Classify** — Context-aware risk tiers with adaptive thresholds (night-mode, P2M-relaxed)
5. **Act** — Gateway hold/block webhooks, dead-letter retry, analyst alerts
6. **Explain** — SHAP top-5 features + LLM-generated fraud analyst reports (Anthropic/OpenAI)
7. **Monitor** — Live graph analytics, drift detection, Prometheus/Grafana observability

The platform achieves **sub-200ms end-to-end latency** at **2,000+ transactions/second** throughput.

---

## Key Features

| Category | Capabilities |
|---|---|
| **ML Ensemble** | Isolation Forest (anomaly) + PyTorch Autoencoder (reconstruction) + Calibrated XGBoost (supervised) |
| **Feature Engineering** | 40+ real-time features across 8 domains with parallelized computation |
| **Graph Analytics** | PageRank, Louvain community detection, star pattern detection, forwarding chain BFS, fraud proximity |
| **Explainability** | SHAP top-5 feature attribution + streaming GenAI fraud analyst reports |
| **Risk Tiers** | Adaptive 4-tier classification (Legitimate → Suspicious → High-Risk → Block) with context-specific thresholds |
| **Gateway Integration** | Automated hold/block with DLQ retry (exponential backoff, max 3 retries) |
| **Analyst Workflow** | Decision queue, confirm/dismiss/escalate actions, confusion matrix feedback loop |
| **Observability** | Prometheus metrics, Grafana dashboards, SLA tracking, drift monitoring (PSI) |
| **Live Dashboard** | React 19 command center with SSE real-time streams, force-directed graph, recharts analytics |
| **Simulation** | Realistic UPI transaction generator with 9 fraud pattern injectors and behavioral user profiles |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          SENTINEL OVERSIGHT ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────┐      ┌───────────────────┐      ┌──────────────────┐         │
│  │  Transaction  │─────▶│  Kafka: topic      │─────▶│  Feature         │         │
│  │  Simulator    │      │  upi_transactions  │      │  Engineering     │         │
│  │  (producer)   │      └───────────────────┘      │  Service         │         │
│  └──────────────┘                                   │  (8 modules)     │         │
│                                                      └────────┬─────────┘        │
│                                                               │                  │
│                                                               ▼                  │
│                                                      ┌─────────────────┐        │
│                                                      │  Kafka: topic    │        │
│                                                      │  upi_features    │        │
│                                                      └────────┬────────┘        │
│                                                               │                  │
│                              ┌─────────────────────────┬──────┴──────┐           │
│                              │                         │             │           │
│                              ▼                         ▼             ▼           │
│                    ┌──────────────────┐    ┌──────────────┐  ┌─────────────┐    │
│                    │  ML Scoring      │    │  DB Consumer  │  │  DLQ        │    │
│                    │  Service         │    │  (PostgreSQL) │  │  Consumer   │    │
│                    │  ┌────────────┐  │    └──────────────┘  └─────────────┘    │
│                    │  │ Isolation   │  │                                         │
│                    │  │ Forest     │  │                                         │
│                    │  ├────────────┤  │                                         │
│                    │  │ Autoencoder│  │                                         │
│                    │  │ (PyTorch)  │  │                                         │
│                    │  ├────────────┤  │                                         │
│                    │  │ XGBoost    │  │                                         │
│                    │  │ (Calibr.)  │  │                                         │
│                    │  ├────────────┤  │                                         │
│                    │  │ Rule Engine│  │                                         │
│                    │  └────────────┘  │                                         │
│                    └────────┬─────────┘                                         │
│                             │                                                    │
│                    ┌────────┴────────┐                                           │
│                    ▼                 ▼                                           │
│          ┌─────────────────┐ ┌─────────────────┐                               │
│          │ scored_txns     │ │ fraud_alerts     │                               │
│          └────────┬────────┘ └────────┬────────┘                               │
│                   │                   │                                          │
│         ┌────────┬┴──────────────────┬┘                                         │
│         ▼        ▼                   ▼                                          │
│  ┌────────────┐ ┌──────────────┐  ┌──────────────┐                             │
│  │ Graph      │ │ API Gateway  │  │ Gateway      │                             │
│  │ Service    │ │ (FastAPI)    │  │ Simulator    │                             │
│  │ (NetworkX) │ │ + SSE Stream │  │ (hold/block) │                             │
│  └──────┬─────┘ └──────┬───────┘  └──────────────┘                             │
│         │              │                                                        │
│         │        ┌─────┴──────┐                                                │
│         │        │ GenAI      │                                                │
│         │        │ Explainer  │                                                │
│         │        │ (LLM)      │                                                │
│         │        └─────┬──────┘                                                │
│         │              │                                                        │
│         │              ▼                                                        │
│         │     ┌──────────────────┐                                             │
│         └────▶│  React Dashboard │◀── SSE real-time streams                    │
│               │  (Vite + React)  │                                             │
│               └──────────────────┘                                             │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐       │
│  │  Infrastructure: Kafka · Redis · PostgreSQL · Prometheus · Grafana  │       │
│  └──────────────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Message Broker** | Apache Kafka (Confluent 7.5) | Event streaming backbone |
| **ML Framework** | PyTorch, XGBoost, scikit-learn | Model training & inference |
| **Explainability** | SHAP, Anthropic Claude / OpenAI GPT-4o | Feature attribution & natural language reports |
| **Graph Analytics** | NetworkX, python-louvain | Real-time network analysis |
| **API Layer** | FastAPI, Uvicorn | Async REST + SSE gateway |
| **Database** | PostgreSQL 15 | Transaction persistence |
| **Cache** | Redis 7 | Graph data caching, fraud VPA tracking |
| **Frontend** | React 19, Vite 8, Recharts, Zustand | Live analyst command center |
| **Monitoring** | Prometheus, Grafana | Metrics collection & dashboarding |
| **Experiment Tracking** | MLflow | Model versioning & metrics |
| **Containerization** | Docker Compose | Infrastructure orchestration |

---

## Project Structure

```
upi_fraud_detection/
│
├── simulator/                      # Transaction data generator
│   ├── producer.py                 # Kafka-connected UPI transaction producer
│   ├── fraud_injector.py           # 9-scenario fraud pattern injector
│   └── vpa_generator.py            # Realistic VPA address generator
│
├── feature-service/                # Real-time feature engineering (8 modules)
│   ├── app.py                      # Main Kafka consumer + parallel processing
│   ├── velocity.py                 # Velocity features (1min/5min/1hr windows)
│   ├── device.py                   # Device fingerprinting & risk scoring
│   ├── temporal.py                 # Time-of-day, weekend, dormancy features
│   ├── amount_features.py          # Z-score, daily average, round number
│   ├── geo.py                      # Geolocation & impossible travel detection
│   ├── graph_features.py           # Degree centrality, mule detection, chains
│   ├── vpa.py                      # VPA age, similarity, impersonation
│   └── merchant.py                 # Merchant category risk, dispute rate
│
├── ml-service/                     # ML scoring & inference
│   ├── app.py                      # Kafka scoring loop + Prometheus metrics
│   ├── ensemble.py                 # 3-model ensemble scorer (IF+AE+XGB)
│   ├── risk_tier.py                # Adaptive risk tier classifier
│   ├── drift_monitor.py            # PSI-based feature drift detection
│   ├── mlflow_client.py            # MLflow experiment tracking integration
│   ├── dlq_consumer.py             # Dead-letter queue retry consumer
│   └── models/                     # Serialized model artifacts
│       ├── autoencoder.pt          # PyTorch autoencoder weights
│       ├── autoencoder_meta.pkl    # AE metadata (p95, input_dim)
│       ├── isolation_forest.pkl    # Isolation Forest + normalization bounds
│       ├── xgboost_clean.pkl       # Calibrated XGBoost classifier
│       ├── scaler.pkl              # StandardScaler for feature normalization
│       ├── shap_explainer_fusion.pkl # Pre-computed SHAP TreeExplainer
│       └── risk_threshold.pkl      # Operational risk threshold
│
├── graph-service/                  # Real-time graph analytics
│   ├── app.py                      # Kafka consumer + graph processing loop
│   ├── community.py                # PageRank, Louvain, star/chain detection
│   └── escalator.py                # Risk tier escalation publisher
│
├── genai-service/                  # LLM-powered fraud explainer
│   ├── explainer.py                # Streaming fraud explanation generator
│   ├── pattern_matcher.py          # Rule-based fraud pattern matching
│   └── prompts.py                  # Structured analyst prompt builder
│
├── api-gateway/                    # Central API gateway
│   ├── main.py                     # FastAPI app (REST + SSE + WebSocket)
│   ├── metrics.py                  # Prometheus metric definitions
│   └── requirements.txt            # Python dependencies
│
├── gateway-simulator/              # UPI gateway mock (hold/block/release)
│   ├── app.py                      # FastAPI gateway simulator
│   └── failure_sim.py              # Configurable failure injection
│
├── frontend/                       # React analyst dashboard
│   ├── src/
│   │   ├── App.jsx                 # Main app with tab navigation
│   │   ├── components/
│   │   │   ├── FraudOpsCenter.jsx          # Alert queue & analyst decisions
│   │   │   ├── TransactionInvestigator.jsx # Search, timeline, GenAI explain
│   │   │   ├── NetworkGraph.jsx            # Force-directed graph visualization
│   │   │   ├── ModelPerformance.jsx        # Confusion matrix, AUROC, trends
│   │   │   └── SystemHealth.jsx            # SLA, latency, drift monitoring
│   │   └── store/                  # Zustand state management
│   ├── package.json
│   └── vite.config.js
│
├── notebooks/                      # Training & experimentation
│   ├── 01_collect_dataset.py       # Data collection pipeline
│   └── 02_train_models.py          # Full 3-model training pipeline
│
├── observability/                  # Monitoring configuration
│   ├── prometheus.yml              # Prometheus scrape targets
│   └── grafana/                    # Grafana dashboard provisioning
│
├── tests/                          # Integration & smoke tests
│   ├── live_stack_verification.py  # Full stack health check
│   └── explainer_smoke_test.py     # GenAI explainer validation
│
├── docker-compose.yml              # Infrastructure services definition
├── init.sql                        # PostgreSQL schema initialization
├── db_consumer.py                  # Kafka → PostgreSQL persistence consumer
├── fraud_patterns.json             # Fraud pattern catalog (9 patterns)
├── start.ps1                       # One-command platform launcher (Windows)
├── stop.ps1                        # Graceful platform shutdown
├── .env.example                    # Environment variable template
└── README.md                       # This file
```

---

## Getting Started

### Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Backend services |
| **Node.js** | 18+ | Frontend development |
| **Docker Desktop** | Latest | Infrastructure containers |
| **Git** | Latest | Version control |

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/<your-org>/upi-fraud-detection.git
cd upi-fraud-detection
```

**2. Create environment file**

```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

**3. Install Python dependencies**

```bash
# Install per-service dependencies
pip install kafka-python psycopg2-binary redis fastapi uvicorn httpx prometheus_client
pip install torch xgboost scikit-learn shap joblib networkx python-louvain
pip install pydantic numpy pandas sqlalchemy imblearn mlflow
```

**4. Install frontend dependencies**

```bash
cd frontend
npm install
cd ..
```

### Quick Start

The simplest way to launch the entire platform:

```powershell
# Start all services (Docker + backend + frontend)
.\start.ps1

# Start without Docker (if Docker containers are already running)
.\start.ps1 -NoDocker

# Start minimal (skip simulator — useful for low-memory machines)
.\start.ps1 -Minimal
```

The start script will:
1. Check available RAM (minimum 2 GB required)
2. Launch Docker infrastructure (Kafka, Redis, PostgreSQL, Prometheus, Grafana)
3. Start the gateway simulator on port 8001
4. Start backend services (Feature Service, Graph Service, ML Service, DLQ Consumer, DB Consumer)
5. Start the API gateway on port 8000
6. Start the transaction simulator
7. Launch the frontend dev server on port 5173
8. Open the dashboard in your default browser

**To stop all services:**

```powershell
.\stop.ps1           # Stop tracked services
.\stop.ps1 -Force    # Also kill orphaned UPI windows
```

### Manual Setup

For more control, start services individually:

```bash
# Step 1: Infrastructure
docker-compose up -d

# Step 2: Gateway Simulator (port 8001)
cd gateway-simulator && uvicorn app:app --host 127.0.0.1 --port 8001

# Step 3: Feature Engineering
cd feature-service && python app.py

# Step 4: ML Scoring Service
cd ml-service && python app.py

# Step 5: Graph Analytics
cd graph-service && python app.py

# Step 6: DLQ Consumer
cd ml-service && python dlq_consumer.py

# Step 7: DB Consumer
python db_consumer.py

# Step 8: API Gateway (port 8000)
cd api-gateway && uvicorn main:app --host 127.0.0.1 --port 8000

# Step 9: Transaction Simulator
cd simulator && python producer.py

# Step 10: Frontend (port 5173)
cd frontend && npm run dev
```

---

## Service Documentation

### 1. Transaction Simulator

**Location:** `simulator/`  
**Entry Point:** `producer.py`  
**Kafka Topic (out):** `upi_transactions`

The simulator generates realistic UPI transactions at configurable throughput (default: 2,000 TPS). It models behavioral user profiles with:

- **User Profiles**: Each VPA has consistent devices (1–3), spending patterns, favorite merchants, friend networks, and home states
- **Amount Distribution**: Log-normal distribution (`μ=8.0, σ=1.0`) capped at ₹200,000, with 30% variance injection
- **Transaction Mix**: 40% P2P / 60% P2M with 80% preference for known contacts/merchants
- **Fraud Injection**: 0.5% base fraud rate across 9 distinct fraud scenarios

#### Fraud Scenarios Injected

| Scenario | Description | Key Feature Modifications |
|---|---|---|
| `VELOCITY_SPIKE` | 50+ txns from one VPA in 10 minutes | High txn_count_1min/5min/1hr |
| `NEW_DEVICE_LARGE_TXN` | First-time device with large amount | is_new_device=1, high amount_zscore |
| `NIGHT_LARGE_TRANSFER` | Large transfer between 1–4 AM | is_night=1, modified timestamp |
| `VPA_IMPERSONATION` | VPA mimics a known brand | High vpa_similarity_score |
| `MULE_ACCOUNT_STAR` | Receiving from many unique senders | High unique_receivers_1hr |
| `RAPID_FORWARDING_CHAIN` | Funds forwarded through 4+ VPAs | High txn_count_5min |
| `DORMANT_ACCOUNT_SPIKE` | Inactive 90+ days, sudden activity | High amount_zscore, new device |
| `GEO_IMPOSSIBLE` | Travel speed > 800 km/h | is_geo_impossible=1, high txn_speed |
| `KNOWN_FRAUD_PROXIMITY` | 1 hop from confirmed fraud VPA | fraud_hop_distance=1 |

---

### 2. Feature Engineering Service

**Location:** `feature-service/`  
**Entry Point:** `app.py`  
**Kafka Topic (in):** `upi_transactions`  
**Kafka Topic (out):** `upi_features`  
**Parallelism:** ThreadPoolExecutor with 32 workers

Computes 40+ features across 8 domains in real-time:

| Module | Features | Description |
|---|---|---|
| `velocity.py` | `txn_count_1min`, `txn_count_5min`, `txn_count_1hr`, `amount_sum_1hr`, `unique_receivers_1hr`, `unique_devices_1hr` | Sliding window velocity counters |
| `amount_features.py` | `amount_zscore`, `amount_vs_daily_avg`, `is_round_number`, `history_size` | Statistical amount anomaly detection |
| `temporal.py` | `hour_of_day`, `day_of_week`, `is_weekend`, `is_night`, `days_since_last_txn`, `is_first_txn_ever` | Temporal behavioral patterns |
| `device.py` | `is_new_device`, `device_txn_count`, `device_vpa_count`, `device_risk_score`, `device_last_seen_hours_ago` | Device fingerprinting & risk scoring |
| `geo.py` | `distance_from_last_txn_km`, `txn_speed_kmph`, `is_geo_impossible` | Impossible travel detection |
| `graph_features.py` | `sender_degree_1hr`, `receiver_degree_1hr`, `is_mule_account`, `is_high_sender`, `chain_length` | Graph topology features |
| `vpa.py` | `sender_vpa_age_days`, `receiver_vpa_age_days`, `vpa_similarity_score`, `sender_txn_count_total` | VPA lifecycle & impersonation |
| `merchant.py` | `is_merchant_txn`, `merchant_category_risk`, `merchant_dispute_rate`, `merchant_age_days` | Merchant risk profiling |

---

### 3. ML Scoring Service

**Location:** `ml-service/`  
**Entry Point:** `app.py`  
**Kafka Topic (in):** `upi_features`  
**Kafka Topics (out):** `scored_transactions`, `fraud_alerts`, `gateway_dlq`  
**Metrics Port:** 8002

#### Scoring Pipeline

```
Feature Vector (40D)
        │
        ├──▶ StandardScaler
        │
        ├──▶ Isolation Forest → norm_if ∈ [0,1]
        │
        ├──▶ Autoencoder (PyTorch) → norm_ae ∈ [0,1]
        │       └── Latency guard: skip if >40ms elapsed
        │
        ├──▶ Feature Fusion: [clean_features, if_raw, ae_raw]
        │
        ├──▶ XGBoost (Calibrated) → xgb_prob ∈ [0,1]
        │
        ├──▶ Weighted Ensemble: 0.25×IF + 0.25×AE + 0.50×XGB
        │
        ├──▶ Rule Engine Boost (capped at +0.20):
        │       ├── Mule pattern + XGB>0.6 → +0.10
        │       ├── Device risk>0.8 + XGB>0.5 → +0.05
        │       ├── Merchant dispute>0.7 + XGB>0.6 → +0.05
        │       └── Geo impossible → +0.10
        │
        └──▶ Risk Tier Assignment (context-aware thresholds)
```

#### Prometheus Metrics Exported

| Metric | Type | Description |
|---|---|---|
| `inference_latency_ms` | Histogram | End-to-end scoring latency |
| `ensemble_score` | Histogram | Score distribution |
| `fraud_alerts_total` | Counter | Alerts by risk tier |
| `gateway_webhook_latency_ms` | Histogram | Gateway API round-trip time |
| `gateway_webhook_failures_total` | Counter | Failed gateway calls |

---

### 4. Graph Analytics Service

**Location:** `graph-service/`  
**Entry Point:** `app.py`  
**Kafka Topic (in):** `scored_transactions`  
**Kafka Topic (out):** `risk_escalations`  
**Data Store:** Redis (db=1) + In-memory NetworkX DiGraph

#### Graph Algorithms

| Algorithm | Module | Frequency | Purpose |
|---|---|---|---|
| **PageRank** | `community.py` | Every 100 txns | Identify high-influence nodes (mule accounts) |
| **Louvain Communities** | `community.py` | Every 200 txns | Detect fraud clusters/rings |
| **Star Pattern Detection** | `community.py` | Every txn | Find mule aggregator accounts (20+ unique senders/hr) |
| **Forwarding Chain BFS** | `community.py` | Every txn | Detect rapid fund forwarding (4+ hops in 5 min) |
| **Fraud Proximity BFS** | `community.py` | Every txn | Minimum hops to known fraud VPA |

#### Escalation Rules

| Condition | Escalation Target | Reason |
|---|---|---|
| `fraud_hop_count == 1` | Block | Direct connection to confirmed fraud VPA |
| `is_star_receiver == True` | Block | Mule account star pattern detected |
| `chain_length >= 4` | High-Risk | Rapid forwarding chain |
| `receiver_pagerank > 0.01` | Suspicious | High PageRank receiver (possible aggregator) |

---

### 5. GenAI Explainability Service

**Location:** `genai-service/`  
**Entry Point:** `explainer.py`  
**LLM Providers:** Anthropic Claude Sonnet 4 / OpenAI GPT-4o

Generates structured 5-section fraud analyst reports:

1. **Fraud Summary** — Risk tier, ensemble score, primary flagging reason
2. **Anomaly Breakdown** — IF, AE, XGBoost individual signal analysis
3. **Transaction Pattern** — Matched fraud pattern + SHAP evidence
4. **Network Context** — Graph analysis findings, fraud proximity
5. **Analyst Recommended Actions** — Prioritized bullet points with time guidance

**Fallback**: If LLM APIs are unavailable, a deterministic local explainer generates structured reports using the same data.

---

### 6. API Gateway

**Location:** `api-gateway/`  
**Entry Point:** `main.py`  
**Port:** 8000  
**Framework:** FastAPI with CORS enabled

The central API gateway aggregates data from all services and serves the frontend dashboard.

#### Key Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | System health status |
| `/transactions` | GET | Recent scored transactions |
| `/alerts` | GET | Recent fraud alerts |
| `/stream/transactions` | GET (SSE) | Live transaction stream |
| `/stream/alerts` | GET (SSE) | Live fraud alert stream |
| `/stream/explain/{txn_id}` | GET (SSE) | Streaming GenAI fraud explanation |
| `/metrics/system` | GET | System performance metrics |
| `/metrics/analytics` | GET | Trend data, histograms, model averages |
| `/metrics/model` | GET | Confusion matrix & precision/recall |
| `/graph/data` | GET | Network graph nodes & links |
| `/transaction/{txn_id}` | GET | Single transaction lookup |
| `/investigate/search` | GET | Search by VPA, device, or amount |
| `/investigate/timeline/{vpa}` | GET | Transaction timeline for a VPA |
| `/decision/{txn_id}` | POST | Record analyst decision |
| `/prometheus` | GET | Prometheus metrics endpoint |

---

### 7. Gateway Simulator

**Location:** `gateway-simulator/`  
**Entry Point:** `app.py`  
**Port:** 8001

Simulates a UPI payment gateway with:

| Endpoint | Method | Description |
|---|---|---|
| `/hold` | POST | Place transaction on 30-minute hold |
| `/block` | POST | Block transaction permanently |
| `/release/{txn_id}` | POST | Release a held transaction |
| `/status/{txn_id}` | GET | Check transaction hold/block status |
| `/audit` | GET | Gateway event audit log |
| `/health` | GET | Gateway health check |

Includes a 2% configurable API failure rate to test DLQ retry logic.

---

### 8. Database Consumer

**Location:** `db_consumer.py` (project root)  
**Kafka Topic (in):** `upi_features`  
**Database:** PostgreSQL (fraud_db)

Persists enriched transactions to PostgreSQL in batches of 1,000 with:

- **Chaos Injection**: Adds realistic noise to training data (Gaussian blur, false positives at 4%, false negatives at 6%, 0.5% label flips)
- **Structural Signal Amplification**: Fraud transactions receive slight amplitude boosts to ensure signal survival through noise
- **Graceful Shutdown**: SIGINT handler flushes remaining batch before exit

---

### 9. Frontend Dashboard

**Location:** `frontend/`  
**Framework:** React 19 + Vite 8  
**Port:** 5173

Five main dashboard tabs:

| Tab | Component | Description |
|---|---|---|
| **Fraud Ops Center** | `FraudOpsCenter.jsx` | Live alert queue with analyst decision buttons (Confirm Fraud / Mark Legitimate / Escalate) |
| **Transaction Investigator** | `TransactionInvestigator.jsx` | Search by VPA/device/amount, transaction timelines, streaming GenAI explanations |
| **Network Graph** | `NetworkGraph.jsx` | Force-directed graph visualization with risk-colored nodes, community clusters |
| **Model Performance** | `ModelPerformance.jsx` | Confusion matrix, precision/recall trends, score distributions, calibration curves |
| **System Health** | `SystemHealth.jsx` | SLA tracking, latency breakdown, drift monitoring, fraud pressure indicators |

**Key Frontend Technologies:**
- **Zustand** for global state management
- **Recharts** for charts and visualizations
- **react-force-graph-2d** for interactive network graphs
- **Server-Sent Events (SSE)** for real-time data streaming

---

## ML Pipeline

### Data Collection

```bash
# Step 1: Generate training data (runs the simulator + feature service + db consumer)
# Ensure Docker containers are running
python notebooks/01_collect_dataset.py
```

The data collection pipeline ingests simulated transactions through the full pipeline and persists them to PostgreSQL for offline training.

### Model Training

```bash
# Step 2: Train all 3 models + ensemble
python notebooks/02_train_models.py
```

The training pipeline executes:

1. **Data Loading** — Reads from PostgreSQL, applies 85/15 temporal train/test split
2. **StandardScaler Fit** — Fitted on training data only, serialized to `scaler.pkl`
3. **Isolation Forest** — 200 estimators, contamination=0.003, trained on clean data only
4. **Autoencoder** — PyTorch `64→32→16→32→64` architecture, 30 epochs, MSE loss, trained on clean data only
5. **Feature Fusion** — Raw features + IF anomaly score + AE reconstruction error
6. **Stratified Downsampling** — 4:1 legit:fraud ratio to handle class imbalance
7. **Calibrated XGBoost** — 400 estimators, `max_depth=6`, sigmoid calibration with 3-fold CV
8. **Stage 2 Rule Engine** — Context-aware boosts (mule, device risk, merchant dispute, geo impossible)
9. **Threshold Selection** — Top 1% percentile operational cutoff
10. **SHAP Explainer** — TreeExplainer with interventional perturbation on subsampled background

All artifacts are saved to `ml-service/models/` and optionally logged to MLflow.

### Ensemble Strategy

```
Final Score = min(1.0, Ensemble_Raw + Rule_Boost)

Where:
  Ensemble_Raw = 0.25 × IF_norm + 0.25 × AE_norm + 0.50 × XGB_prob
  Rule_Boost   = min(0.20, Σ context_boosts)
```

| Model | Weight | Training Data | Signal Type |
|---|---|---|---|
| Isolation Forest | 0.25 | Clean transactions only | Unsupervised anomaly |
| Autoencoder (PyTorch) | 0.25 | Clean transactions only | Reconstruction error |
| XGBoost (Calibrated) | 0.50 | Fusion features (raw + IF + AE) | Supervised classification |

### Risk Tier Classification

| Tier | Default Threshold | Night Threshold | P2M Threshold | Action |
|---|---|---|---|---|
| **Legitimate** | < 0.30 | < 0.20 | < 0.35 | Pass through |
| **Suspicious** | 0.30 – 0.55 | 0.20 – 0.40 | 0.35 – 0.60 | Alert to analyst queue |
| **High-Risk** | 0.55 – 0.80 | 0.40 – 0.65 | 0.60 – 0.82 | Hold transaction + alert |
| **Block** | ≥ 0.80 | ≥ 0.65 | ≥ 0.82 | Immediate block + alert |

> Night thresholds are more aggressive (lower cutoffs) to account for higher fraud rates during 1–4 AM.  
> P2M thresholds are slightly relaxed since peer-to-merchant transactions have different risk profiles.

---

## Fraud Detection Patterns

The system recognizes 9 fraud patterns defined in `fraud_patterns.json`:

| # | Pattern | Description | Key Features | Default Action |
|---|---|---|---|---|
| 1 | `VELOCITY_SPIKE` | 50+ txns from one VPA in 10 min | txn_count_1min > 10, txn_count_5min > 25 | Block + Alert |
| 2 | `LARGE_AMOUNT_ANOMALY` | Amount > 5× sender's average | amount_zscore > 5.0 | High-Risk Hold |
| 3 | `NEW_DEVICE_LARGE_TXN` | First-time device, txn > ₹10,000 | is_new_device = 1, amount > 10000 | High-Risk Hold |
| 4 | `MULE_ACCOUNT_STAR` | Receiving from 20+ unique senders/hr | unique_receivers_1hr > 20 | Block + NPCI Report |
| 5 | `RAPID_FORWARDING_CHAIN` | Funds through 4+ VPAs in 5 min | chain_length ≥ 4 | Block all nodes |
| 6 | `GEO_IMPOSSIBLE` | Travel speed > 800 km/h | is_geo_impossible = True | Block + Alert |
| 7 | `NIGHT_LARGE_TRANSFER` | Large amount between 1–4 AM | is_deep_night = 1, amount > 50000 | High-Risk Hold |
| 8 | `VPA_IMPERSONATION` | VPA mimics known brand (edit distance < 3) | vpa_similarity_score > 0.85 | Suspicious Alert |
| 9 | `KNOWN_FRAUD_PROXIMITY` | 1 hop from confirmed fraud VPA | fraud_hop_count = 1 | Block |

---

## API Reference

### System Metrics (`GET /metrics/system`)

```json
{
  "tps": 42.5,
  "latency_ms": 85.3,
  "alerts_per_min": 12,
  "held": 3,
  "queue_size": 2500,
  "uptime_seconds": 3600,
  "fpr": 4.2,
  "recall": 92.5,
  "sla_ok": true,
  "sla_breach_pct": 1.2,
  "drift_status": "Stable",
  "fraud_pressure": "MEDIUM",
  "latency": {
    "feature": 34.1,
    "model": 42.6,
    "api": 8.5
  }
}
```

### Analyst Decision (`POST /decision/{txn_id}`)

**Request Body:**
```json
{
  "action": "confirm_fraud",
  "note": "Verified mule pattern via KYC records"
}
```

**Supported Actions:** `confirm_fraud`, `mark_legitimate`, `escalate`, `note`

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

### Transaction Search (`GET /investigate/search`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search_type` | string | `vpa` | One of: `vpa`, `device`, `amount` |
| `query` | string | `""` | Search query |
| `limit` | int | `50` | Max results |
| `min_amount` | float | `0` | Minimum amount (for amount search) |
| `max_amount` | float | `999999999` | Maximum amount (for amount search) |

---

## Observability & Monitoring

### Prometheus Metrics

Metrics are exposed on two endpoints:

| Service | Port | Path | Key Metrics |
|---|---|---|---|
| **ML Service** | 8002 | `/metrics` | `inference_latency_ms`, `ensemble_score`, `fraud_alerts_total`, `gateway_webhook_latency_ms` |
| **API Gateway** | 8000 | `/prometheus` | `fraud_catch_rate`, `false_positive_rate`, `active_sse_connections`, `genai_rationale_first_token_ms`, `analyst_decisions_total` |

### Grafana Dashboards

Access Grafana at `http://localhost:3001` (credentials: `admin` / `admin123`).

### Drift Monitoring

The `drift_monitor.py` module implements **Population Stability Index (PSI)** for feature distribution drift:

| PSI Range | Interpretation | Action |
|---|---|---|
| < 0.10 | No significant change | Continue |
| 0.10 – 0.20 | Slight change | Monitor closely |
| > 0.20 | Significant shift | Consider retraining |

Additionally, a 40% mean shift threshold triggers immediate drift alerts.

### SLA Tracking

- **Target Latency**: < 200ms end-to-end (Kafka ingest → risk tier assigned)
- **SLA Breach Threshold**: > 5% of transactions exceeding 200ms
- **Breach Indicator**: Real-time `[BREACH]` logging in ML service console

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP` | `localhost:9092` | Kafka bootstrap servers |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `POSTGRES_URL` | `postgresql://admin:admin123@localhost:5432/fraud_db` | PostgreSQL connection string |
| `GATEWAY_URL` | `http://localhost:8001` | Gateway simulator URL |
| `ML_METRICS_URL` | `http://localhost:8002/metrics` | ML service metrics URL |
| `MLFLOW_TRACKING_URI` | `http://localhost:5000` | MLflow tracking server |
| `LLM_PROVIDER` | `anthropic` | GenAI provider (`anthropic` or `openai`) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key for Claude |
| `OPENAI_API_KEY` | — | OpenAI API key for GPT-4o |
| `FRAUD_INJECTION_RATE` | `0.003` | Fraud injection percentage |
| `PRODUCER_RATE_PER_SEC` | `500` | Transaction generation rate |

### Docker Infrastructure Ports

| Service | Internal Port | External Port |
|---|---|---|
| Kafka | 29092 / 9092 | 9092 |
| Redis | 6379 | 6379 |
| PostgreSQL | 5432 | 5432 |
| Prometheus | 9090 | 9090 |
| Grafana | 3000 | 3001 |

---

## Testing

### Smoke Tests

```bash
# Full stack health verification
python tests/live_stack_verification.py

# GenAI explainer smoke test
python tests/explainer_smoke_test.py
```

### Manual Verification

1. **Health Check**: `curl http://localhost:8000/health`
2. **Transaction Flow**: Verify transactions appear in the SSE stream
3. **Alert Pipeline**: Confirm fraud alerts are generated for injected fraud
4. **Gateway Integration**: Check hold/block status at `http://localhost:8001/health`
5. **Database**: Verify records in PostgreSQL: `SELECT COUNT(*) FROM transactions;`

---

## Deployment

### Development

```powershell
.\start.ps1         # Full platform
.\start.ps1 -Minimal  # Without simulator
```

### Production Considerations

> ⚠️ This project is designed as a demonstration platform. For production deployment, consider:

- **Kafka**: Use managed Kafka (Confluent Cloud, AWS MSK) with replication factor ≥ 3
- **Database**: Use managed PostgreSQL with connection pooling (PgBouncer)
- **Redis**: Use Redis Sentinel or Cluster for high availability
- **ML Models**: Implement model versioning with MLflow Model Registry
- **API Gateway**: Deploy behind a load balancer with rate limiting
- **Security**: Implement TLS everywhere, rotate API keys, add authentication/authorization
- **Monitoring**: Set up PagerDuty/OpsGenie alerts on SLA breaches and drift detection
- **Scaling**: Kafka consumer groups allow horizontal scaling of all services

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m "feat: add my feature"`
4. Push to branch: `git push origin feature/my-feature`
5. Open a Pull Request

### Code Style

- Python: Follow PEP 8, use type hints for function signatures
- JavaScript/React: Use ESLint configuration provided (`.eslintrc`)
- Commits: Follow [Conventional Commits](https://conventionalcommits.org/)

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>Built with ❤️ for securing India's digital payments ecosystem</strong>
</p>
