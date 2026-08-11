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

MERCHANT_TTL = 86400 * 30  # 30 days


# ================= HELPER =================
def _is_merchant(vpa: str) -> int:
    vpa = vpa.lower()
    username = vpa.split("@")[0]
    merchants = [
        "amazon", "flipkart", "zomato", "swiggy", "bigbasket",
        "myntra", "ajio", "nykaa", "phonepe", "paytmmall",
        "jiomart", "blinkit", "zepto", "dunzo", "meesho"
    ]
    return int(
        any(x in username for x in merchants + ["merchant", "biz", "shop", "store", "pay", "mart", "food"])
    )


# ================= MAIN =================
def compute_merchant_features(receiver: str, amount: float, timestamp: float) -> dict:
    # 🔥 FINAL FIX: FORCE INTEGER TIMESTAMP
    try:
        now = int(float(timestamp))
    except:
        now = int(time.time())

    key = f"m:{receiver}"

    # ================= NON-MERCHANT =================
    if not _is_merchant(receiver):
        return {
            "is_merchant_txn": 0,
            "merchant_avg_txn_amount": 0.0,
            "merchant_txn_count": 0,
            "merchant_category_risk": 0.0,
            "merchant_age_days": 0.0,
            "merchant_velocity_1hr": 0,
            "merchant_amount_zscore": 0.0,
        }

    # -------- KEYS --------
    txn_key   = f"{key}:txn"
    amt_key   = f"{key}:amt"
    first_key = f"{key}:first"
    vel_key   = f"{key}:vel"

    # ================= READ =================
    pipe = r.pipeline(transaction=False)
    pipe.get(txn_key)
    pipe.get(amt_key)
    pipe.get(first_key)
    pipe.zrangebyscore(vel_key, now - 3600, now)

    raw_txn, raw_amt, first_seen, raw_vel = pipe.execute()

    txn_count = int(raw_txn or 0)
    total_amt = float(raw_amt or 0.0)

    # ================= COMPUTE =================
    txn_count_new = txn_count + 1
    total_amt_new = total_amt + amount
    avg_amt = total_amt_new / txn_count_new

    # -------- AGE (SAFE) --------
    if first_seen:
        try:
            first_seen = int(float(first_seen))
        except:
            first_seen = now
        merchant_age_days = (now - first_seen) / 86400
    else:
        merchant_age_days = 0.0

    # -------- VELOCITY --------
    merchant_velocity = len(raw_vel)

    # -------- AMOUNT ZSCORE --------
    if txn_count < 5:
        amt_z = min(amount / 1000, 5)
    else:
        std = max(avg_amt * 0.2, 1.0)
        amt_z = (amount - avg_amt) / std
        amt_z = max(min(amt_z, 10), -10)

    # ================= RISK SCORE =================
    risk_score = 0.0

    if merchant_velocity > 20:
        risk_score += 0.3
    if avg_amt > 5000:
        risk_score += 0.2
    if merchant_age_days < 2:
        risk_score += 0.3
    if abs(amt_z) > 3:
        risk_score += 0.2

    risk_score = min(risk_score, 1.0)

    # ================= WRITE =================
    pipe2 = r.pipeline(transaction=False)

    pipe2.setnx(first_key, now)
    pipe2.incr(txn_key)
    pipe2.incrbyfloat(amt_key, amount)

    # 🔥 FIX: store INT timestamp only
    pipe2.zadd(vel_key, {f"{now}:{amount}": now})
    pipe2.zremrangebyscore(vel_key, 0, now - 3600)

    pipe2.expire(txn_key, MERCHANT_TTL)
    pipe2.expire(amt_key, MERCHANT_TTL)
    pipe2.expire(first_key, MERCHANT_TTL)
    pipe2.expire(vel_key, MERCHANT_TTL)

    pipe2.execute()

    # ================= RETURN =================
    return {
        "is_merchant_txn": 1,
        "merchant_avg_txn_amount": round(avg_amt, 2),
        "merchant_txn_count": txn_count_new,
        "merchant_category_risk": round(risk_score, 3),
        "merchant_age_days": round(merchant_age_days, 2),
        "merchant_velocity_1hr": merchant_velocity,
        "merchant_amount_zscore": round(amt_z, 3),
    }