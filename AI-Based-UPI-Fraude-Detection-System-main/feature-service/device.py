import redis
import os
import time

# ================= REDIS =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# ================= CONFIG =================
DEVICE_HISTORY_TTL = 86400 * 30  # 30 days


# ================= MAIN FUNCTION =================
def compute_device_features(sender_vpa: str, device_id: str) -> dict:
    now = int(time.time())

    # -------- KEYS --------
    device_set_key   = f"d:set:{sender_vpa}"   # devices used by sender
    device_count_key = f"d:cnt:{device_id}"    # txn count per device
    device_vpa_key   = f"d:vpa:{device_id}"    # VPAs per device
    last_seen_key    = f"d:last:{device_id}"   # last seen timestamp

    # ================= READ =================
    pipe = r.pipeline(transaction=False)
    pipe.sismember(device_set_key, device_id)
    pipe.scard(device_set_key)
    pipe.get(device_count_key)
    pipe.scard(device_vpa_key)
    pipe.get(last_seen_key)
    results = pipe.execute()

    is_known, sender_device_count, raw_txn_count, device_vpa_count, last_seen = results

    # -------- CLEAN VALUES --------
    is_known = bool(is_known)
    sender_device_count = int(sender_device_count or 0)
    device_txn_count = int(raw_txn_count or 0)
    device_vpa_count = int(device_vpa_count or 0)

    is_new_device = 0 if is_known else 1

    # ================= TIME FEATURE =================
    if last_seen:
        last_seen = float(last_seen)
        hours_since_last_seen = (now - last_seen) / 3600
    else:
        hours_since_last_seen = 999.0  # 🔥 important: unseen device

    # ================= RISK SCORE =================
    device_risk_score = 0.0

    # 🔥 1. New device risk
    if is_new_device:
        device_risk_score += 0.4

    # 🔥 2. Device shared across many VPAs (mule behavior)
    if device_vpa_count > 3:
        device_risk_score += min(device_vpa_count * 0.05, 0.4)

    # 🔥 3. Dormant device suddenly active
    if hours_since_last_seen > 24:
        device_risk_score += 0.2
    if hours_since_last_seen > 72:
        device_risk_score += 0.2

    # 🔥 4. Too many devices used by same user
    if sender_device_count > 3:
        device_risk_score += min(sender_device_count * 0.05, 0.3)

    # 🔥 Clamp
    device_risk_score = min(device_risk_score, 1.0)

    # ================= WRITE =================
    pipe2 = r.pipeline(transaction=False)
    pipe2.sadd(device_set_key, device_id)
    pipe2.incr(device_count_key)
    pipe2.sadd(device_vpa_key, sender_vpa)
    pipe2.set(last_seen_key, now)

    pipe2.expire(device_set_key, DEVICE_HISTORY_TTL)
    pipe2.expire(device_count_key, DEVICE_HISTORY_TTL)
    pipe2.expire(device_vpa_key, DEVICE_HISTORY_TTL)
    pipe2.expire(last_seen_key, DEVICE_HISTORY_TTL)

    pipe2.execute()

    # ================= RETURN =================
    return {
        "is_new_device": int(is_new_device),
        "device_txn_count": device_txn_count + 1,  # include current txn
        "device_vpa_count": device_vpa_count,
        "device_last_seen_hours_ago": round(hours_since_last_seen, 3),
        "device_risk_score": round(device_risk_score, 3),
        "sender_device_count": sender_device_count,
    }