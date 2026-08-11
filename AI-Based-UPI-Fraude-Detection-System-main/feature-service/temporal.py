import redis
import os
import time
from datetime import datetime

# ================= REDIS =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

TTL_SECONDS = 86400 * 30  # 30 days


# ================= MAIN FUNCTION =================
def compute_temporal_features(sender_vpa: str, timestamp: float) -> dict:
    """
    Production-grade temporal feature engineering
    - Safe timestamp handling
    - Stable defaults (no extreme values)
    - Realistic fraud signals
    """

    # 🔥 SAFE TIMESTAMP
    try:
        ts = float(timestamp)
    except:
        ts = time.time()

    dt = datetime.fromtimestamp(ts)

    hour = dt.hour
    dow  = dt.weekday()

    key = f"t:last:{sender_vpa}"

    # ================= FETCH LAST =================
    prev_ts = r.get(key)

    if prev_ts:
        try:
            prev_ts = float(prev_ts)
        except:
            prev_ts = ts

        # 🔥 avoid zero/negative gap
        time_diff_sec = max(ts - prev_ts, 1)

        time_diff_min = time_diff_sec / 60
        days_since_last_txn = time_diff_sec / 86400

        is_first_txn = 0

    else:
        # 🔥 realistic defaults (NOT extreme)
        time_diff_sec = 3600.0     # 1 hour
        time_diff_min = 60.0
        days_since_last_txn = 1.0
        is_first_txn = 1

    # ================= UPDATE =================
    r.set(key, ts, ex=TTL_SECONDS)

    # ================= TIME FEATURES =================
    is_weekend = int(dow >= 5)
    is_night = int(hour >= 22 or hour < 6)
    is_deep_night = int(1 <= hour <= 4)
    is_business_hours = int(9 <= hour <= 18 and dow < 5)

    # ================= BURST DETECTION =================
    is_rapid_txn = int(time_diff_sec < 10)     # within 10 sec
    is_quick_txn = int(time_diff_sec < 60)     # within 1 min

    # ================= TIME RISK SCORE =================
    time_risk_score = 0.0

    if is_night:
        time_risk_score += 0.2

    if is_deep_night:
        time_risk_score += 0.3

    if is_rapid_txn:
        time_risk_score += 0.3

    if is_first_txn:
        time_risk_score += 0.2

    time_risk_score = min(time_risk_score, 1.0)

    # ================= RETURN =================
    return {
        # basic
        "hour_of_day": hour,
        "day_of_week": dow,
        "is_weekend": is_weekend,

        # time flags
        "is_night": is_night,
        "is_deep_night": is_deep_night,
        "is_business_hours": is_business_hours,

        # time gaps
        "time_since_last_txn_sec": round(time_diff_sec, 2),
        "time_since_last_txn_min": round(time_diff_min, 2),
        "days_since_last_txn": round(days_since_last_txn, 4),

        # behavior
        "is_first_txn_ever": is_first_txn,
        "is_rapid_txn": is_rapid_txn,
        "is_quick_txn": is_quick_txn,

        # risk score
        "time_risk_score": round(time_risk_score, 3),
    }