import json
import os
from kafka import KafkaProducer

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

_producer = None

def get_producer():
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks=1,
        )
    return _producer


def escalate_risk(txn: dict, new_tier: str, reason: str):
    """
    Publish an escalation event when graph analysis raises the risk tier.
    The API gateway listens on 'risk_escalations' and updates the dashboard.
    """
    event = {
        "txn_id":       txn.get("txn_id"),
        "sender_vpa":   txn.get("sender_vpa"),
        "receiver_vpa": txn.get("receiver_vpa"),
        "old_tier":     txn.get("risk_tier", "Legitimate"),
        "new_tier":     new_tier,
        "reason":       reason,
        "graph_context": {
            "sender_pagerank":   txn.get("sender_pagerank", 0),
            "receiver_pagerank": txn.get("receiver_pagerank", 0),
            "community_id":      txn.get("community_id"),
            "chain_length":      txn.get("chain_length", 0),
            "fraud_hop_count":   txn.get("fraud_hop_count", 999),
            "is_star_receiver":  txn.get("is_star_receiver", False),
        }
    }
    get_producer().send("risk_escalations", value=event)
    print(f"Escalated {txn.get('txn_id')} → {new_tier}: {reason}")