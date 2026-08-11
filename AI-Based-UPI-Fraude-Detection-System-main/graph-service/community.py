import networkx as nx
from collections import defaultdict
import time

try:
    import community as community_louvain
    LOUVAIN_AVAILABLE = True
except ImportError:
    LOUVAIN_AVAILABLE = False
    print("Warning: python-louvain not installed. Community detection disabled.")


def detect_star_pattern(G: nx.DiGraph, vpa: str, window_seconds: int = 3600) -> bool:
    """
    Star pattern: VPA receiving from 20+ unique senders in 1 hour.
    This is the classic mule account aggregator pattern.
    """
    in_edges = list(G.in_edges(vpa, data=True))
    now = time.time()
    recent_senders = set()
    for src, _, data in in_edges:
        if now - data.get("timestamp", 0) <= window_seconds:
            recent_senders.add(src)
    return len(recent_senders) >= 20


def detect_forwarding_chain(G: nx.DiGraph, start_vpa: str,
                             window_seconds: int = 300) -> list:
    """
    Rapid forwarding: BFS to find chains of 4+ hops within 5 minutes.
    Returns the chain path if found, empty list otherwise.
    """
    now = time.time()
    # BFS with time constraint
    queue  = [(start_vpa, [start_vpa], time.time())]
    chains = []

    while queue:
        node, path, start_time = queue.pop(0)
        if len(path) > 8:   # max chain depth
            continue

        for _, neighbor, data in G.out_edges(node, data=True):
            txn_time = data.get("timestamp", 0)
            if txn_time < now - window_seconds:
                continue
            new_path = path + [neighbor]
            if len(new_path) >= 4:
                chains.append(new_path)
            if neighbor not in path:   # avoid cycles
                queue.append((neighbor, new_path, start_time))

    return chains


def detect_communities(G: nx.DiGraph) -> dict:
    """
    Louvain community detection on undirected version of the graph.
    Returns {vpa: community_id}.
    """
    if not LOUVAIN_AVAILABLE or G.number_of_nodes() < 3:
        return {}
    undirected = G.to_undirected()
    try:
        partition = community_louvain.best_partition(undirected)
        return partition
    except Exception as e:
        print(f"Community detection error: {e}")
        return {}


def compute_pagerank(G: nx.DiGraph) -> dict:
    """PageRank on the full directed graph. High score on receiver = mule risk."""
    if G.number_of_nodes() < 2:
        return {}
    try:
        return nx.pagerank(G, alpha=0.85, max_iter=100)
    except Exception:
        return {}


def find_fraud_proximity(G: nx.DiGraph, vpa: str,
                          known_fraud_vpas: set, max_hops: int = 2) -> int:
    """
    BFS to find minimum hops from vpa to any known fraud VPA.
    Returns hop count (0 = is fraud VPA, 999 = not connected).
    """
    if vpa in known_fraud_vpas:
        return 0
    visited = {vpa}
    frontier = {vpa}
    for hop in range(1, max_hops + 1):
        next_frontier = set()
        for node in frontier:
            for neighbor in list(G.successors(node)) + list(G.predecessors(node)):
                if neighbor in known_fraud_vpas:
                    return hop
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
    return 999