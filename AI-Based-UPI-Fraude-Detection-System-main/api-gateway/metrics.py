from prometheus_client import Gauge, Counter, Histogram

FRAUD_CATCH_RATE = Gauge(
    "fraud_catch_rate",
    "Percentage of confirmed fraud caught by model (rolling 1hr)"
)
FALSE_POSITIVE_RATE = Gauge(
    "false_positive_rate",
    "Percentage of analyst-confirmed legitimate among all reviewed alerts"
)
ACTIVE_SSE_CONNECTIONS = Gauge(
    "active_sse_connections",
    "Number of active SSE connections to analyst dashboard"
)
GENAI_FIRST_TOKEN_MS = Gauge(
    "genai_rationale_first_token_ms",
    "Latency from alert triggered to first GenAI token"
)
ANALYST_DECISIONS = Counter(
    "analyst_decisions_total",
    "Analyst decisions by outcome",
    ["decision"]
)
KAFKA_LAG = Gauge(
    "kafka_consumer_lag",
    "Consumer lag on upi_transactions topic"
)