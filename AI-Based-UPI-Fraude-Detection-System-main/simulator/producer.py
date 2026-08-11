import time
import uuid
import random
import json
import os
import numpy as np
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from vpa_generator import generate_user_vpa, generate_merchant_vpa, _ACTIVE_USER_POOL, _ACTIVE_MERCHANT_POOL
from fraud_injector import inject_fraud

print("🚀 UPI Transaction Producer Starting...")

# ================= CONFIG =================
KAFKA_BOOTSTRAP = "localhost:9092"

MODE = "stream"   # "debug" or "stream"
MAX_TXNS = 500_000   # only used in debug mode

RATE_PER_SEC = 2000

TXN_TYPES = ["P2P", "P2M"]
STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Tamil Nadu",
    "Telangana", "Gujarat", "Rajasthan", "West Bengal"
]

# ================= KAFKA CONNECT =================
while True:
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode(),
            retries=10,
            linger_ms=10,
            batch_size=65536,
            acks="all",
            compression_type="gzip",
            max_in_flight_requests_per_connection=5
        )
        print("✅ Connected to Kafka")
        break
    except NoBrokersAvailable:
        print("⏳ Waiting for Kafka...")
        time.sleep(3)

# ================= USER PROFILE =================
class UserProfile:
    def __init__(self, vpa):
        self.vpa = vpa
        self.devices = [
            f"DEV_{uuid.uuid4().hex[:12].upper()}"
            for _ in range(random.choices([1, 2, 3], weights=[80, 15, 5])[0])
        ]
        self.base_amt = random.choice([50, 150, 500, 2500, 8000])
        self.favorite_merchants = random.choices(_ACTIVE_MERCHANT_POOL, k=random.randint(2, 5))
        self.friends = []
        self.home_state = random.choice(STATES)

USER_PROFILES = {}

def get_user(vpa: str):
    if vpa not in USER_PROFILES:
        USER_PROFILES[vpa] = UserProfile(vpa)
    return USER_PROFILES[vpa]

# Initialize relationships
for _vpa in _ACTIVE_USER_POOL:
    u = get_user(_vpa)
    u.friends = random.sample(_ACTIVE_USER_POOL, k=random.randint(1, 4))
    if u.vpa in u.friends:
        u.friends.remove(u.vpa)

# ================= TXN GENERATOR =================
def generate_txn():
    if random.random() < 0.85:
        sender = random.choice(_ACTIVE_USER_POOL)
    else:
        sender = generate_user_vpa()

    u = get_user(sender)

    txn_type = random.choices(["P2P", "P2M"], weights=[40, 60])[0]

    if txn_type == "P2M":
        receiver = random.choice(u.favorite_merchants) if random.random() < 0.8 else generate_merchant_vpa()
    else:
        receiver = random.choice(u.friends) if random.random() < 0.8 and u.friends else generate_user_vpa()

    # 🔥 Unified distribution (DO NOT TOUCH)
    amt = np.random.lognormal(mean=8.0, sigma=1.0)
    amt = min(amt, 200000.0)

    if random.random() < 0.3:
        amt *= random.uniform(0.8, 1.5)

    amt = round(max(amt, 10.0), 2)

    txn = {
        "txn_id": str(uuid.uuid4()),
        "sender_vpa": sender,
        "receiver_vpa": receiver,
        "amount": amt,
        "device_id": random.choice(u.devices),
        "timestamp": time.time(),
        "unix_timestamp": time.time(),
        "txn_type": txn_type,
        "ip_state": u.home_state,
        "run_id": "prod_stream" if MODE == "stream" else "debug_run"
    }

    try:
        txn = inject_fraud(txn, {})

        # 🔥 Overlap enforcement (CRITICAL)
        if random.random() < 0.2:
            txn["amount"] = random.uniform(100, 50000)

        txn["amount"] = round(txn["amount"], 2)

    except Exception as e:
        print("⚠️ Fraud injector error:", e)
        txn["is_fraud"] = 0
        txn["fraud_flag"] = "LEGIT"

    return txn

# ================= MAIN LOOP =================
def main():

    print(f"🔥 Mode: {MODE}")
    print(f"📡 Target Rate: {RATE_PER_SEC} txns/sec")

    count = 0
    start = time.time()

    # mode condition
    if MODE == "debug":
        condition = lambda c: c < MAX_TXNS
    else:
        condition = lambda c: True

    while condition(count):
        try:
            batch_start = time.time()

            # 🔥 Batch send (TRUE TPS CONTROL)
            for _ in range(RATE_PER_SEC):
                txn = generate_txn()

                producer.send(
                    "upi_transactions",
                    key=txn["sender_vpa"],
                    value=txn
                )

                count += 1

            producer.flush()

            # 🔥 Maintain 1-second cycle
            elapsed = time.time() - batch_start
            time.sleep(max(0, 1 - elapsed))

            # 🔥 Logging
            if count % 5000 == 0:
                total_time = time.time() - start
                rate = count / total_time if total_time > 0 else 0

                if MODE == "debug":
                    print(f"[{count:,}/{MAX_TXNS:,}] | {rate:.0f} txns/sec")
                else:
                    print(f"[LIVE] {count:,} txns | {rate:.0f} txns/sec")

        except Exception as e:
            print("❌ Producer error:", e)
            time.sleep(1)

    producer.flush()
    print("✅ Producer stopped cleanly")


if __name__ == "__main__":
    main()