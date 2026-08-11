import json
import os
from difflib import SequenceMatcher

PATTERNS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fraud_patterns.json"
)

_patterns = None

def load_patterns() -> list:
    global _patterns
    if _patterns is None:
        with open(PATTERNS_PATH, "r") as f:
            _patterns = json.load(f)
    return _patterns


def match_pattern(txn: dict) -> dict:
    """
    Match a transaction to the best fraud pattern from the catalog.
    Uses the fraud_flag field first, then falls back to feature matching.
    """
    patterns = load_patterns()
    fraud_flag = txn.get("fraud_flag", "LEGIT")

    # Direct match by name
    for p in patterns:
        if p["name"] == fraud_flag:
            return p

    # Feature-based matching fallback
    scores = []
    for p in patterns:
        score = _feature_match_score(txn, p)
        scores.append((score, p))

    scores.sort(key=lambda x: x[0], reverse=True)
    if scores and scores[0][0] > 0:
        return scores[0][1]

    # Default unknown pattern
    return {
        "name": "UNKNOWN_PATTERN",
        "description": "Transaction does not match any known fraud pattern catalog entry.",
        "key_features": [],
        "default_action": "Manual analyst review required.",
        "analyst_steps": ["Review all features manually", "Check transaction history"],
    }


SUPPORTED_OPS = {
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "=":  lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

def _feature_match_score(txn: dict, pattern: dict) -> int:
    score = 0
    for condition in pattern.get("key_features", []):
        parts = condition.split()
        if len(parts) != 3:
            continue
        field, op, val = parts
        if op not in SUPPORTED_OPS:
            print(f"Warning: unsupported operator '{op}' in pattern condition '{condition}'")
            continue
        try:
            raw_txn_val = txn.get(field, 0)
            raw_thresh = val

            # Boolean-safe path: supports True/False values in pattern catalog.
            if str(raw_thresh).lower() in ("true", "false"):
                thresh = str(raw_thresh).lower() == "true"
                txn_bool = raw_txn_val if isinstance(raw_txn_val, bool) else str(raw_txn_val).lower() == "true"
                if SUPPORTED_OPS[op](txn_bool, thresh):
                    score += 1
                continue

            txn_val = float(raw_txn_val)
            thresh = float(raw_thresh)
            if SUPPORTED_OPS[op](txn_val, thresh):
                score += 1
        except (ValueError, TypeError) as e:
            print(f"Warning: could not evaluate condition '{condition}': {e}")
    return score