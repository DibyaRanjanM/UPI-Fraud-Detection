import random
import datetime
import uuid
from vpa_generator import generate_similar_vpa, MERCHANTS, BANKS

FRAUD_RATE = 0.005

def inject_fraud(txn: dict, history: dict) -> dict:
    if random.random() > FRAUD_RATE:
        txn["fraud_flag"] = "LEGIT"
        txn["is_fraud"]   = 0
        return txn

    scenario = random.choice([
        "VELOCITY_SPIKE",
        "NEW_DEVICE_LARGE_TXN",
        "NIGHT_LARGE_TRANSFER",
        "VPA_IMPERSONATION",
        "MULE_ACCOUNT_STAR",
        "RAPID_FORWARDING_CHAIN",
        "DORMANT_ACCOUNT_SPIKE",
        "GEO_IMPOSSIBLE",
        "KNOWN_FRAUD_PROXIMITY",
    ])

    txn["fraud_flag"] = scenario
    txn["is_fraud"]   = 1

    if scenario == "VELOCITY_SPIKE":
        txn["txn_count_1min"]       = random.randint(3, 8)
        txn["txn_count_5min"]       = random.randint(8, 15)
        txn["txn_count_1hr"]        = random.randint(15, 30)
        txn["amount_sum_1hr"]       = round(txn["txn_count_1hr"] * txn["amount"], 2)
        txn["unique_receivers_1hr"] = random.randint(2, 6)

    elif scenario == "NEW_DEVICE_LARGE_TXN":
        txn["device_id"]        = f"NEW_{uuid.uuid4().hex[:8].upper()}"
        txn["is_new_device"]    = 1
        txn["device_txn_count"] = 1
        txn["amount_zscore"]    = round(random.uniform(1.8, 3.5), 2)

    elif scenario == "NIGHT_LARGE_TRANSFER":
        now   = datetime.datetime.now()
        night = now.replace(
            hour=random.randint(1, 4),
            minute=random.randint(0, 59),
            second=random.randint(0, 59)
        )
        txn["unix_timestamp"] = night.timestamp()
        txn["timestamp"]      = night.timestamp()
        txn["is_night"]       = 1
        txn["hour_of_day"]    = night.hour
        txn["amount_zscore"]  = round(random.uniform(2.0, 4.0), 2)

    elif scenario == "VPA_IMPERSONATION":
        legit = f"{random.choice(MERCHANTS)}@{random.choice(BANKS)}"
        txn["receiver_vpa"] = generate_similar_vpa(legit)
        txn["amount_zscore"]= round(random.uniform(1.5, 3.0), 2)

    elif scenario == "MULE_ACCOUNT_STAR":
        txn["unique_receivers_1hr"] = random.randint(5, 12)
        txn["txn_count_1hr"]        = random.randint(5, 12)
        txn["txn_count_5min"]       = random.randint(2, 5)
        txn["amount_sum_1hr"]       = round(txn["unique_receivers_1hr"] * txn["amount"], 2)

    elif scenario == "RAPID_FORWARDING_CHAIN":
        txn["txn_count_5min"] = random.randint(3, 8)
        txn["txn_count_1min"] = random.randint(2, 4)
        txn["amount_zscore"]  = round(random.uniform(1.5, 3.0), 2)
        txn["amount_sum_1hr"] = round(txn["amount"] * txn["txn_count_5min"], 2)

    elif scenario == "DORMANT_ACCOUNT_SPIKE":
        txn["amount_zscore"]    = round(random.uniform(2.5, 5.0), 2)
        txn["is_new_device"]    = 1
        txn["device_txn_count"] = 1

    elif scenario == "GEO_IMPOSSIBLE":
        txn["is_geo_impossible"] = 1
        txn["distance_from_last_km"] = round(random.uniform(300, 800), 2)
        txn["txn_speed_kmph"]   = round(random.uniform(800, 1200), 2)

    elif scenario == "KNOWN_FRAUD_PROXIMITY":
        txn["fraud_hop_distance"] = 1

    return txn
