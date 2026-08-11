import redis
import os
import time
import re

# ================= REDIS =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

TTL_SECONDS = 86400 * 30  # 30 days


# ================= HELPERS =================
def _normalize(vpa: str) -> str:
    return vpa.lower().split("@")[0]


def _simple_similarity(a: str, b: str) -> float:
    """Fast similarity (better than SequenceMatcher for realtime)"""
    a, b = _normalize(a), _normalize(b)

    common = sum(1 for x, y in zip(a, b) if x == y)
    return common / max(len(a), len(b), 1)


def _has_numeric_substitution(a: str, b: str) -> int:
    """Detect 0->o, 1->l type fraud"""
    mapping = {'0': 'o', '1': 'l', '5': 's'}

    a_norm = ''.join(mapping.get(c, c) for c in a)
    b_norm = ''.join(mapping.get(c, c) for c in b)

    return int(a_norm == b_norm)


# ================= MAIN =================
def compute_vpa_features(sender: str, receiver: str, timestamp: float) -> dict:
    ts = float(timestamp)

    sender_key = f"vpa:{sender}"
    receiver_key = f"vpa:{receiver}"

    # ================= READ + WRITE =================
    pipe = r.pipeline(transaction=False)

    pipe.setnx(f"{sender_key}:first", ts)
    pipe.setnx(f"{receiver_key}:first", ts)

    pipe.incr(f"{sender_key}:cnt")
    pipe.incr(f"{receiver_key}:cnt")

    pipe.get(f"{sender_key}:first")
    pipe.get(f"{receiver_key}:first")
    pipe.get(f"{sender_key}:cnt")
    pipe.get(f"{receiver_key}:cnt")

    results = pipe.execute()

    sender_first = float(results[4])
    receiver_first = float(results[5])

    sender_count = int(results[6])
    receiver_count = int(results[7])

    # ================= AGE =================
    sender_age_days = (ts - sender_first) / 86400
    receiver_age_days = (ts - receiver_first) / 86400

    # ================= SIMILARITY =================
    sim_score = _simple_similarity(sender, receiver)

    numeric_spoof = _has_numeric_substitution(sender, receiver)

    # prefix similarity (important fraud signal)
    sender_prefix = _normalize(sender)[:5]
    receiver_prefix = _normalize(receiver)[:5]

    prefix_match = int(sender_prefix == receiver_prefix)

    # ================= ACTIVITY SPIKE =================
    is_new_receiver = int(receiver_count < 5)

    # ================= RISK SCORE =================
    vpa_risk_score = 0.0

    if sim_score > 0.8:
        vpa_risk_score += 0.3

    if numeric_spoof:
        vpa_risk_score += 0.3

    if prefix_match:
        vpa_risk_score += 0.2

    if receiver_age_days < 1:
        vpa_risk_score += 0.2

    vpa_risk_score = min(vpa_risk_score, 1.0)

    # ================= TTL FIX =================
    pipe2 = r.pipeline(transaction=False)
    pipe2.expire(f"{sender_key}:first", TTL_SECONDS)
    pipe2.expire(f"{receiver_key}:first", TTL_SECONDS)
    pipe2.expire(f"{sender_key}:cnt", TTL_SECONDS)
    pipe2.expire(f"{receiver_key}:cnt", TTL_SECONDS)
    pipe2.execute()

    # ================= RETURN =================
    return {
        "sender_vpa_age_days": round(sender_age_days, 2),
        "receiver_vpa_age_days": round(receiver_age_days, 2),

        "sender_txn_count_total": sender_count,
        "receiver_txn_count_total": receiver_count,

        "vpa_similarity_score": round(sim_score, 3),
        "vpa_numeric_spoof": numeric_spoof,
        "vpa_prefix_match": prefix_match,

        "is_new_receiver": is_new_receiver,

        "vpa_risk_score": round(vpa_risk_score, 3),
    }