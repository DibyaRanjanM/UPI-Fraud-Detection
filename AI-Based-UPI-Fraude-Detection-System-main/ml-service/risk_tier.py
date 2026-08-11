from typing import Tuple

# Thresholds — configurable per transaction type
THRESHOLDS = {
    "default": [
        (0.30, "Legitimate"),
        (0.55, "Suspicious"),
        (0.80, "High-Risk"),
        (1.01, "Block"),
    ],
    "night": [          # Lower thresholds at night (more aggressive)
        (0.20, "Legitimate"),
        (0.40, "Suspicious"),
        (0.65, "High-Risk"),
        (1.01, "Block"),
    ],
    "P2M": [            # Peer-to-merchant slightly relaxed
        (0.35, "Legitimate"),
        (0.60, "Suspicious"),
        (0.82, "High-Risk"),
        (1.01, "Block"),
    ],
}


def assign_tier(ensemble_score: float, is_night: bool = False,
                txn_type: str = "P2P") -> Tuple[str, str]:
    """
    Returns (risk_tier, threshold_set_used).
    """
    if is_night:
        key = "night"
    elif txn_type == "P2M":
        key = "P2M"
    else:
        key = "default"

    thresholds = THRESHOLDS[key]
    for cutoff, tier in thresholds:
        if ensemble_score < cutoff:
            return tier, key

    return "Block", key


def tier_to_color(tier: str) -> str:
    return {
        "SAFE": "green",
        "SUSPICIOUS": "amber",
        "HIGH":  "orange",
        "BLOCK":      "red",
        "Legitimate": "green",
        "High-Risk": "orange",
        "Block": "red",
    }.get(tier, "gray")


def tier_requires_alert(tier: str) -> bool:
    return tier in ("Suspicious", "High-Risk", "Block", "SUSPICIOUS", "HIGH", "BLOCK")


def tier_requires_gateway(tier: str) -> bool:
    return tier in ("High-Risk", "Block", "HIGH", "BLOCK")