"""
Live stack verification against Project-6 dashboard / API expectations.

Run when your stack is up:
  python tests/live_stack_verification.py

Optional env:
  API_BASE=http://127.0.0.1:8000
  ML_METRICS_URL=http://127.0.0.1:8002/metrics
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000").rstrip("/")
ML_METRICS_URL = os.getenv("ML_METRICS_URL", "http://127.0.0.1:8002/metrics")


def _get_json(path: str, timeout: float = 8.0) -> tuple[int, Any]:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(body) if body.strip() else None


def _get_text(url: str, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _sse_first_events(path: str, max_bytes: int = 8000, timeout: float = 6.0) -> tuple[bool, str]:
    """Read first chunk of SSE stream (non-blocking parse of a few data lines)."""
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            chunk = resp.read(max_bytes).decode("utf-8", errors="replace")
            return True, chunk
    except Exception as e:
        return False, str(e)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # 1) REST core
    for name, path in [
        ("GET /health", "/health"),
        ("GET /metrics/system", "/metrics/system"),
        ("GET /transactions", "/transactions?limit=5"),
        ("GET /alerts", "/alerts?limit=5"),
        ("GET /graph/data", "/graph/data"),
        ("GET /metrics/analytics", "/metrics/analytics"),
        ("GET /metrics/model", "/metrics/model"),
    ]:
        try:
            code, data = _get_json(path)
            ok = code == 200 and data is not None
            detail = "ok" if ok else f"status={code}"
            checks.append((name, ok, detail))
        except urllib.error.HTTPError as e:
            checks.append((name, False, f"HTTP {e.code}"))
        except Exception as e:
            checks.append((name, False, str(e)))

    # 2) System metrics fields (PDF observability)
    try:
        _, sysm = _get_json("/metrics/system")
        required = [
            "tps", "latency_ms", "fpr", "recall", "drift_psi",
            "kafka_lag", "gateway_failures", "genai_first_token_ms",
            "active_sse_connections", "uptime_seconds", "held_count",
        ]
        missing = [k for k in required if sysm is None or k not in sysm]
        checks.append(("metrics/system fields", len(missing) == 0, f"missing: {missing}" if missing else "all present"))
    except Exception as e:
        checks.append(("metrics/system fields", False, str(e)))

    # 3) ML Prometheus scrape (optional)
    try:
        code, text = _get_text(ML_METRICS_URL)
        has_inf = "inference_latency_ms" in text
        checks.append(("ML :8002 /metrics reachable", code == 200 and has_inf, f"status={code}, has_inference_hist={has_inf}"))
    except Exception as e:
        checks.append(("ML :8002 /metrics reachable", False, str(e)))

    # 4) GenAI explainer stream (needs at least one txn in memory)
    txn_id = None
    try:
        _, txns = _get_json("/transactions?limit=1")
        if isinstance(txns, list) and txns:
            txn_id = txns[0].get("txn_id")
    except Exception:
        pass

    if txn_id:
        ok, payload = _sse_first_events(f"/stream/explain/{urllib.parse.quote(txn_id, safe='')}")
        has_data = ok and ("data:" in payload or "token" in payload.lower())
        checks.append((f"SSE /stream/explain/{txn_id[:8]}…", has_data, payload[:120].replace("\n", " ") if ok else payload))
    else:
        checks.append(("SSE /stream/explain/{txn_id}", False, "no transactions in gateway buffer - start pipeline and retry"))

    # 5) SSE transactions stream (heartbeat or data)
    ok, payload = _sse_first_events("/stream/transactions")
    has_evt = ok and ("data:" in payload or "heartbeat" in payload)
    checks.append(("SSE /stream/transactions first chunk", has_evt, payload[:100].replace("\n", " ") if ok else payload))

    # Print report
    print("\n=== Live stack verification ===\n")
    print(f"API_BASE = {API_BASE}\n")
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok or len(detail) > 80:
            print(f"       {detail[:200]}")
    print(f"\nResult: {passed}/{total} checks passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
