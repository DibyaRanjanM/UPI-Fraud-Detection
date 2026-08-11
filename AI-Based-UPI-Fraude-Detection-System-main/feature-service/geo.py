import redis
import time
import math
import random
import os

# ================= REDIS =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

TTL_SECONDS = 86400  # 1 day


# ================= HELPERS =================
def _random_location():
    """Generate realistic India location"""
    return (
        random.uniform(8.0, 37.0),
        random.uniform(68.0, 97.0)
    )


def _haversine(lat1, lon1, lat2, lon2):
    """Distance in KM"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )

    return 2 * R * math.asin(math.sqrt(a))


# ================= MAIN FUNCTION =================
def compute_geo_features(sender_vpa: str, timestamp: float, device_id: str = "") -> dict:
    # 🔥 FINAL FIX: ALWAYS INTEGER TIMESTAMP
    try:
        ts = int(float(timestamp))
    except:
        ts = int(time.time())

    base_key = f"geo:{sender_vpa}"
    device_key = f"geo_dev:{device_id}" if device_id else None

    key = device_key or base_key

    # -------- LOAD PREVIOUS --------
    prev = r.get(key)

    # -------- LOCATION GENERATION --------
    if prev:
        try:
            prev_lat, prev_lon, prev_time = map(float, prev.split(","))
        except:
            prev_lat, prev_lon, prev_time = *_random_location(), ts

        # 🔥 realistic small drift
        lat = prev_lat + random.uniform(-0.02, 0.02)
        lon = prev_lon + random.uniform(-0.02, 0.02)
    else:
        lat, lon = _random_location()
        prev_time = ts

    # -------- DEFAULT VALUES --------
    distance = 0.0
    speed = 0.0
    is_geo_impossible = 0

    # -------- COMPUTE --------
    if prev:
        try:
            distance = _haversine(prev_lat, prev_lon, lat, lon)

            time_diff = max(ts - float(prev_time), 1)

            speed = distance / (time_diff / 3600)

            # 🔥 realistic fraud thresholds
            if speed > 900:
                is_geo_impossible = 1

        except:
            distance = 0.0
            speed = 0.0
            is_geo_impossible = 0

    # -------- STORE (INT TIMESTAMP ONLY) --------
    r.set(key, f"{lat},{lon},{ts}", ex=TTL_SECONDS)

    # -------- RETURN --------
    return {
        "distance_from_last_txn_km": round(distance, 2),
        "txn_speed_kmph": round(speed, 2),
        "is_geo_impossible": is_geo_impossible,
    }