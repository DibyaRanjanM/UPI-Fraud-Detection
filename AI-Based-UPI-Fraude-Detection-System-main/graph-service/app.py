import json
import time
import os
import redis
import networkx as nx
from kafka import KafkaConsumer
from community import (
    detect_star_pattern, detect_forwarding_chain,
    detect_communities, compute_pagerank, find_fraud_proximity
)
from escalator import escalate_risk

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
REDIS_HOST      = os.getenv("REDIS_HOST", "localhost")

r = redis.Redis(host=REDIS_HOST, port=6379, db=1, decode_responses=True)

# In-memory directed graph — edges expire after 30 minutes
G = nx.DiGraph()
EDGE_TTL_SECONDS = 1800   # 30 minutes

# Known confirmed fraud VPAs (loaded from Redis key "fraud_vpas")
known_fraud_vpas: set = set()

# Cached PageRank (recomputed every PAGERANK_INTERVAL transactions)
PAGERANK_INTERVAL = 100
_cached_pagerank = {}
_pagerank_counter = 0

# Cached communities (recomputed every 200 transactions)
COMMUNITY_INTERVAL = 200
_cached_communities = {}
_community_counter = 0

consumer = KafkaConsumer(
    "scored_transactions",
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    group_id="graph-service-v1",
    auto_offset_reset="latest",
    max_poll_records=100,
)

print("Graph Service started — consuming scored_transactions")


def prune_old_edges():
    """Remove edges older than 30 minutes to keep graph manageable."""
    now = time.time()
    to_remove = [
        (u, v) for u, v, d in G.edges(data=True)
        if now - d.get("timestamp", 0) > EDGE_TTL_SECONDS
    ]
    G.remove_edges_from(to_remove)
    # Remove isolated nodes
    isolated = list(nx.isolates(G))
    G.remove_nodes_from(isolated)


def refresh_fraud_vpas():
    """Load known fraud VPAs from Redis."""
    global known_fraud_vpas
    members = r.smembers("fraud_vpas")
    known_fraud_vpas = set(members)


def refresh_pagerank():
    """Recompute PageRank and cache it."""
    global _cached_pagerank
    _cached_pagerank = compute_pagerank(G)


def refresh_communities():
    """Recompute Louvain communities and cache."""
    global _cached_communities
    _cached_communities = detect_communities(G)


prune_counter = 0

for msg in consumer:
    txn = msg.value

    sender   = txn.get("sender_vpa", "")
    receiver = txn.get("receiver_vpa", "")
    amount   = float(txn.get("amount", 0))
    now      = time.time()

    # Add edge to graph
    G.add_edge(sender, receiver, amount=amount, timestamp=now,
               txn_id=txn.get("txn_id"), risk_tier=txn.get("risk_tier", "Legitimate"))

    # Update node metadata
    for vpa in [sender, receiver]:
        if vpa in G.nodes:
            G.nodes[vpa]["risk_tier"] = txn.get("risk_tier", "Legitimate")
            G.nodes[vpa]["txn_count"] = G.nodes[vpa].get("txn_count", 0) + 1

    # Prune every 500 transactions
    prune_counter += 1
    if prune_counter % 500 == 0:
        prune_old_edges()
        refresh_fraud_vpas()

    # --- Cached PageRank (every PAGERANK_INTERVAL txns) ---
    _pagerank_counter += 1
    if _pagerank_counter % PAGERANK_INTERVAL == 0:
        refresh_pagerank()

    # --- Cached Communities (every COMMUNITY_INTERVAL txns) ---
    _community_counter += 1
    if _community_counter % COMMUNITY_INTERVAL == 0:
        refresh_communities()

    # Use cached values
    sender_pr   = _cached_pagerank.get(sender, 0.0)
    receiver_pr = _cached_pagerank.get(receiver, 0.0)

    # Store pagerank and community on nodes for graph data export
    if sender in G.nodes:
        G.nodes[sender]["pagerank"] = sender_pr
        G.nodes[sender]["community_id"] = _cached_communities.get(sender)
    if receiver in G.nodes:
        G.nodes[receiver]["pagerank"] = receiver_pr
        G.nodes[receiver]["community_id"] = _cached_communities.get(receiver)

    # Star pattern on receiver
    is_star = detect_star_pattern(G, receiver)
    if receiver in G.nodes:
        G.nodes[receiver]["is_star_receiver"] = is_star

    # Forwarding chain from sender
    chains = detect_forwarding_chain(G, sender)
    chain_len = max((len(c) for c in chains), default=0)
    if sender in G.nodes:
        G.nodes[sender]["chain_length"] = chain_len

    # Fraud proximity
    hop_count = find_fraud_proximity(G, sender, known_fraud_vpas)
    if sender in G.nodes:
        G.nodes[sender]["fraud_hop_count"] = hop_count

    # Build enriched context
    graph_ctx = {
        "sender_pagerank":   round(sender_pr, 6),
        "receiver_pagerank": round(receiver_pr, 6),
        "is_star_receiver":  is_star,
        "chain_length":      chain_len,
        "fraud_hop_count":   hop_count,
        "graph_node_count":  G.number_of_nodes(),
        "graph_edge_count":  G.number_of_edges(),
    }

    # --- Escalation logic ---
    current_tier = txn.get("risk_tier", "Legitimate")

    if hop_count == 1 and current_tier not in ("Block",):
        escalate_risk({**txn, **graph_ctx}, "Block", "Direct connection to confirmed fraud VPA")

    elif is_star and current_tier not in ("Block",):
        escalate_risk({**txn, **graph_ctx}, "Block", "Receiver is a mule account star pattern")

    elif chain_len >= 4 and current_tier not in ("Block", "High-Risk"):
        escalate_risk({**txn, **graph_ctx}, "High-Risk", f"Rapid forwarding chain of {chain_len} hops")

    elif receiver_pr > 0.01 and current_tier == "Legitimate":
        escalate_risk({**txn, **graph_ctx}, "Suspicious", "High PageRank receiver — possible aggregator")

    # Cache graph data to Redis for API gateway consumption
    try:
        # Store graph summary for the API gateway /graph/data endpoint
        graph_summary = {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "updated_at": time.time(),
        }
        r.set("graph:summary", json.dumps(graph_summary))

        # Store node data (limited to last 500 nodes)
        nodes_data = []
        for node in list(G.nodes(data=True))[-500:]:
            vpa, data = node
            nodes_data.append({
                "id": vpa,
                "label": _mask_vpa(vpa),
                "risk_tier": data.get("risk_tier", "Legitimate"),
                "pagerank": data.get("pagerank", 0),
                "txn_count": data.get("txn_count", 0),
                "community_id": data.get("community_id"),
                "chain_length": data.get("chain_length", 0),
                "fraud_hop_count": data.get("fraud_hop_count", 999),
                "is_star_receiver": data.get("is_star_receiver", False),
                "is_suspicious_cluster": data.get("community_id") is not None,
            })

        # Store edge data (limited to last 1000 edges)
        links_data = []
        for u, v, data in list(G.edges(data=True))[-1000:]:
            links_data.append({
                "source": u,
                "target": v,
                "amount": data.get("amount", 0),
                "risk_tier": data.get("risk_tier", "Legitimate"),
                "is_chain": (G.nodes.get(u, {}).get("chain_length", 0) >= 4),
            })

        r.set("graph:nodes", json.dumps(nodes_data), ex=120)
        r.set("graph:links", json.dumps(links_data), ex=120)

    except Exception as e:
        pass  # Non-critical — don't crash graph service for Redis writes

    # Add confirmed fraud VPAs to Redis set when analyst confirms
    if txn.get("fraud_flag") != "LEGIT" and txn.get("risk_tier") == "Block":
        r.sadd("fraud_vpas", sender)
        r.sadd("fraud_vpas", receiver)


def _mask_vpa(vpa: str) -> str:
    if not vpa or "@" not in vpa:
        return "***"
    parts = vpa.split("@", 1)
    return f"{parts[0][:3]}***@{parts[1]}"