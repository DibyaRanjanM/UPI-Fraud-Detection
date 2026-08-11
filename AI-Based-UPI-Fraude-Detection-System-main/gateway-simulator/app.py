from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timedelta
import random
import uuid

app = FastAPI(title="UPI Gateway Simulator")

# In-memory store
held_txns    = {}
blocked_txns = {}
audit_log    = []


class GatewayRequest(BaseModel):
    txn_id:     str
    risk_score: float
    reason:     str


def maybe_fail():
    """Simulate 2% API failure rate."""
    if random.random() < 0.02:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Gateway temporarily unavailable")


@app.post("/hold")
def hold_transaction(req: GatewayRequest):
    maybe_fail()
    hold_expires = datetime.now() + timedelta(minutes=30)
    held_txns[req.txn_id] = {
        "status":         "HELD",
        "risk_score":     req.risk_score,
        "reason":         req.reason,
        "held_at":        datetime.now().isoformat(),
        "hold_expires_at": hold_expires.isoformat(),
    }
    audit_log.append({"event": "HOLD", "txn_id": req.txn_id, "at": datetime.now().isoformat()})
    return {"status": "HELD", "txn_id": req.txn_id, "hold_expires_at": hold_expires.isoformat()}


@app.post("/block")
def block_transaction(req: GatewayRequest):
    maybe_fail()
    reason_code = f"FRAUD_{req.reason[:20].upper().replace(' ','_')}"
    blocked_txns[req.txn_id] = {
        "status":      "BLOCKED",
        "reason_code": reason_code,
        "risk_score":  req.risk_score,
        "blocked_at":  datetime.now().isoformat(),
    }
    audit_log.append({"event": "BLOCK", "txn_id": req.txn_id, "at": datetime.now().isoformat()})
    return {"status": "BLOCKED", "txn_id": req.txn_id, "reason_code": reason_code}


@app.post("/release/{txn_id}")
def release_transaction(txn_id: str):
    if txn_id in held_txns:
        entry = held_txns.pop(txn_id)
        entry["status"] = "RELEASED"
        audit_log.append({"event": "RELEASE", "txn_id": txn_id, "at": datetime.now().isoformat()})
        return {"status": "RELEASED", "txn_id": txn_id}
    return {"error": "Transaction not found in HELD status"}


@app.get("/status/{txn_id}")
def get_status(txn_id: str):
    if txn_id in held_txns:
        return held_txns[txn_id]
    if txn_id in blocked_txns:
        return blocked_txns[txn_id]
    return {"status": "NOT_FOUND"}


@app.get("/audit")
def get_audit(limit: int = 100):
    return audit_log[-limit:]


@app.get("/health")
def health():
    return {"status": "ok", "held": len(held_txns), "blocked": len(blocked_txns)}