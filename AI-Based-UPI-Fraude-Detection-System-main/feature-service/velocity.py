import redis
import time
import os

# ================= REDIS =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# ================= CONFIG =================
TTL_SECONDS = 7200  # 2 hours


# ================= MAIN FUNCTION =================
def update_velocity(sender_vpa: str, amount: float, receiver_vpa: str, device_id: str = "") -> dict:
    now = time.time()  # 🔥 use float for precision

    # -------- KEYS --------
    txn_key  = f"v:txn:{sender_vpa}"
    amt_key  = f"v:amt:{sender_vpa}"
    recv_key = f"v:recv:{sender_vpa}"
    dev_key  = f"v:dev:{sender_vpa}"

    # Unique member (prevents overwrite)
    member_id = f"{now}:{os.getpid()}"

    # -------- TIME WINDOWS --------
    cutoff_1hr  = now - 3600
    cutoff_5min = now - 300
    cutoff_1min = now - 60

    # ================= WRITE =================
    pipe = r.pipeline(transaction=False)

    pipe.zadd(txn_key,  {member_id: now})
    pipe.zadd(amt_key,  {f"{member_id}:{amount}": now})
    pipe.zadd(recv_key, {f"{receiver_vpa}:{member_id}": now})

    if device_id:
        pipe.zadd(dev_key, {f"{device_id}:{member_id}": now})

    # -------- PRUNE OLD --------
    pipe.zremrangebyscore(txn_key,  0, cutoff_1hr)
    pipe.zremrangebyscore(amt_key,  0, cutoff_1hr)
    pipe.zremrangebyscore(recv_key, 0, cutoff_1hr)
    pipe.zremrangebyscore(dev_key,  0, cutoff_1hr)

    # -------- TTL --------
    pipe.expire(txn_key,  TTL_SECONDS)
    pipe.expire(amt_key,  TTL_SECONDS)
    pipe.expire(recv_key, TTL_SECONDS)
    pipe.expire(dev_key,  TTL_SECONDS)

    pipe.execute()

    # ================= READ =================
    pipe2 = r.pipeline(transaction=False)

    pipe2.zcount(txn_key, cutoff_1min, now)
    pipe2.zcount(txn_key, cutoff_5min, now)
    pipe2.zcount(txn_key, cutoff_1hr,  now)

    pipe2.zrangebyscore(amt_key, cutoff_1hr, now)
    pipe2.zrangebyscore(recv_key, cutoff_1hr, now)
    pipe2.zrangebyscore(dev_key, cutoff_1hr, now)

    count_1min, count_5min, count_1hr, raw_amounts, raw_receivers, raw_devices = pipe2.execute()

    # ================= PROCESS =================

    # 🔥 Amount sum (optimized)
    amount_sum = 0.0
    for m in raw_amounts:
        try:
            amount_sum += float(m.split(":")[-1])
        except:
            continue

    # 🔥 Unique receivers
    unique_receivers = len({m.split(":")[0] for m in raw_receivers})

    # 🔥 Unique devices
    unique_devices = len({m.split(":")[0] for m in raw_devices})

    # ================= RETURN =================
    return {
        "txn_count_1min": int(count_1min),
        "txn_count_5min": int(count_5min),
        "txn_count_1hr":  int(count_1hr),

        "amount_sum_1hr": round(amount_sum, 2),

        "unique_receivers_1hr": unique_receivers,
        "unique_devices_1hr": unique_devices,
    }