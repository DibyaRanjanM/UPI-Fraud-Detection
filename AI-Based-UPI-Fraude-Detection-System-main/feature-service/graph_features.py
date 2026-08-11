import redis
import os
import time
import uuid

# ================= REDIS =================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

WINDOW = 3600  # 1 hour


# ================= MAIN FUNCTION =================
def compute_graph_features(sender: str, receiver: str, timestamp: float) -> dict:
    # 🔥 SAFE + STABLE TIMESTAMP
    try:
        ts = int(float(timestamp))
    except:
        ts = int(time.time())

    # -------- KEYS --------
    sender_key = f"g_out:{sender}"
    receiver_key = f"g_in:{receiver}"

    # 🔥 UNIQUE EDGE (NO COLLISION)
    edge_out = f"{receiver}:{ts}:{uuid.uuid4().hex[:6]}"
    edge_in  = f"{sender}:{ts}:{uuid.uuid4().hex[:6]}"

    # ================= WRITE =================
    pipe = r.pipeline(transaction=False)

    pipe.zadd(sender_key, {edge_out: ts})
    pipe.zadd(receiver_key, {edge_in: ts})

    # prune old edges
    pipe.zremrangebyscore(sender_key, 0, ts - WINDOW)
    pipe.zremrangebyscore(receiver_key, 0, ts - WINDOW)

    # TTL
    pipe.expire(sender_key, WINDOW * 2)
    pipe.expire(receiver_key, WINDOW * 2)

    pipe.execute()

    # ================= READ =================
    pipe2 = r.pipeline(transaction=False)

    pipe2.zrangebyscore(sender_key, ts - WINDOW, ts)
    pipe2.zrangebyscore(receiver_key, ts - WINDOW, ts)

    raw_out, raw_in = pipe2.execute()

    # ================= PROCESS =================

    # unique receivers (out-degree)
    unique_receivers = {item.split(":")[0] for item in raw_out}

    # unique senders (in-degree)
    unique_senders = {item.split(":")[0] for item in raw_in}

    sender_degree = len(unique_receivers)
    receiver_degree = len(unique_senders)

    # ================= FRAUD SIGNALS =================

    is_mule_account = int(receiver_degree > 10)
    is_high_sender  = int(sender_degree > 8)

    chain_length = min(sender_degree, 5)

    # 🔥 GRAPH RISK SCORE
    graph_risk_score = 0.0

    if receiver_degree > 5:
        graph_risk_score += min(receiver_degree * 0.05, 0.4)

    if sender_degree > 5:
        graph_risk_score += min(sender_degree * 0.05, 0.3)

    if is_mule_account:
        graph_risk_score += 0.3

    graph_risk_score = min(graph_risk_score, 1.0)

    # ================= RETURN =================
    return {
        "sender_degree_1hr": sender_degree,
        "receiver_degree_1hr": receiver_degree,
        "is_mule_account": is_mule_account,
        "is_high_sender": is_high_sender,
        "chain_length": chain_length,
        "graph_risk_score": round(graph_risk_score, 3),
    }