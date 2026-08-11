import redis
import numpy as np
import os

# ================= REDIS CONNECTION =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# ================= CONFIG =================
MAX_HISTORY = 100        # last 100 transactions
TTL_SECONDS = 86400 * 7  # 7 days expiry


# ================= MAIN FUNCTION =================
def compute_amount_features(sender_vpa: str, amount: float) -> dict:
    key = f"a:{sender_vpa}"

    # -------- READ HISTORY --------
    raw_values = r.lrange(key, 0, MAX_HISTORY - 1)
    historical = [float(v) for v in raw_values]

    history_size = len(historical)

    # -------- COMPUTE FEATURES --------
    if history_size < 5:
        # 🔥 Early-stage fallback (important for new users)
        zscore = min(amount / 1000, 5)
        daily_avg = amount
    else:
        arr = np.array(historical)

        mean = float(np.mean(arr))
        std  = float(np.std(arr))

        # 🔥 Adaptive std (critical fix)
        std = max(std, mean * 0.1, 1.0)

        zscore = (amount - mean) / std
        zscore = max(min(zscore, 10), -10)

        daily_avg = mean

    # -------- DEVIATION FEATURE --------
    amount_vs_daily = (amount - daily_avg) / (daily_avg + 1)
    amount_vs_daily = max(min(amount_vs_daily, 10), -10)

    # -------- ROUND NUMBER DETECTION --------
    is_round = _is_round(amount)

    # -------- WRITE BACK TO REDIS --------
    pipe = r.pipeline(transaction=False)
    pipe.lpush(key, amount)
    pipe.ltrim(key, 0, MAX_HISTORY - 1)
    pipe.expire(key, TTL_SECONDS)
    pipe.execute()

    # -------- RETURN FEATURES --------
    return {
        "amount_zscore": round(zscore, 4),
        "amount_vs_daily_avg": round(amount_vs_daily, 4),
        "is_round_number": is_round,
        "history_size": history_size,
    }


# ================= HELPER =================
def _is_round(amount: float) -> int:
    """
    Detect suspicious round numbers
    """
    try:
        amt = int(amount)
        return int(
            amt % 100 == 0 or
            amt % 500 == 0 or
            amt % 1000 == 0 or
            str(amt).endswith("000")
        )
    except:
        return 0