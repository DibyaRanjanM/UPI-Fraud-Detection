import os
import json
import httpx
from pattern_matcher import match_pattern
from prompts import build_fraud_analyst_prompt

# Supports both OpenAI and Anthropic — set via env var
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")


async def stream_fraud_explanation(txn: dict):
    """
    Async generator that yields text tokens of the fraud explanation.
    Used by the FastAPI SSE endpoint.
    """
    scores = {
        "if_score":       txn.get("if_score", 0),
        "ae_score":       txn.get("ae_score", 0),
        "xgb_score":      txn.get("xgb_score", 0),
        "ensemble_score": txn.get("ensemble_score", 0),
        "risk_tier":      txn.get("risk_tier", "Unknown"),
    }
    shap_top5 = []
    for item in txn.get("shap_top5", []) or []:
        direction = item.get("direction", "increases_risk")
        default_shap = 0.05 if direction == "increases_risk" else -0.05
        shap_val = item.get("shap", default_shap)
        feat_val = item.get("value", abs(shap_val))
        shap_top5.append({
            "feature": item.get("feature", "unknown_feature"),
            "value": float(feat_val),
            "shap": float(shap_val),
            "direction": direction,
        })
    pattern   = match_pattern(txn)
    graph_ctx = {
        "sender_pagerank":   txn.get("sender_pagerank", 0),
        "receiver_pagerank": txn.get("receiver_pagerank", 0),
        "chain_length":      txn.get("chain_length", 0),
        "fraud_hop_count":   txn.get("fraud_hop_count", 999),
        "is_star_receiver":  txn.get("is_star_receiver", False),
    }

    prompt = build_fraud_analyst_prompt(txn, scores, shap_top5, pattern, graph_ctx)

    try:
        if LLM_PROVIDER == "anthropic":
            if not ANTHROPIC_KEY:
                raise RuntimeError("Anthropic key missing")
            async for token in _stream_anthropic(prompt):
                yield token
        else:
            if not OPENAI_KEY:
                raise RuntimeError("OpenAI key missing")
            async for token in _stream_openai(prompt):
                yield token
    except Exception:
        # Deterministic local fallback to keep analyst workflow alive.
        text = _fallback_explanation(txn, scores, shap_top5, pattern, graph_ctx)
        for chunk in text.split(" "):
            yield chunk + " "


def _fallback_explanation(txn: dict, scores: dict, shap_top5: list, pattern: dict, graph_ctx: dict) -> str:
    top_feats = ", ".join(
        [f"{s.get('feature', 'feature')}({s.get('direction', 'impact')})" for s in (shap_top5 or [])[:5]]
    ) or "No SHAP features available"

    risk_tier = scores.get("risk_tier", "Unknown")
    ens = scores.get("ensemble_score", 0)
    ifs = scores.get("if_score", 0)
    aes = scores.get("ae_score", 0)
    xgb = scores.get("xgb_score", 0)
    amount = txn.get("amount", 0)
    txn_id = txn.get("txn_id", "unknown")
    sender = txn.get("sender_vpa", "unknown")
    receiver = txn.get("receiver_vpa", "unknown")
    pattern_name = pattern.get("name", txn.get("fraud_flag", "UNCLASSIFIED"))

    actions = [
        "- Verify sender identity via registered channel.",
        "- Check device consistency and prior transaction behavior.",
        "- Review nearby transactions for rapid forwarding or star patterns.",
        "- If risk remains high, place hold/block and escalate for manual review.",
    ]

    return (
        f"1) Fraud Summary\n"
        f"Transaction {txn_id} from {sender} to {receiver} for amount {amount} is classified as {risk_tier} "
        f"with ensemble score {ens:.3f}. Immediate review is recommended based on risk signals.\n\n"
        f"2) Anomaly Breakdown\n"
        f"- Isolation Forest score: {ifs:.3f}\n"
        f"- Autoencoder reconstruction error: {aes:.3f}\n"
        f"- XGBoost fraud probability: {xgb:.3f}\n"
        f"Top feature contributors: {top_feats}.\n\n"
        f"3) Transaction Pattern\n"
        f"Matched pattern: {pattern_name}. This indicates behavior deviating from expected normal activity and warrants analyst attention.\n\n"
        f"4) Network Context\n"
        f"sender_pagerank={graph_ctx.get('sender_pagerank', 0)}, receiver_pagerank={graph_ctx.get('receiver_pagerank', 0)}, "
        f"chain_length={graph_ctx.get('chain_length', 0)}, fraud_hop_count={graph_ctx.get('fraud_hop_count', 999)}, "
        f"is_star_receiver={graph_ctx.get('is_star_receiver', False)}.\n\n"
        f"5) Analyst Recommended Actions\n"
        + "\n".join(actions)
    )


async def _stream_anthropic(prompt: str):
    headers = {
        "x-api-key":         ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "stream":     True,
        "messages":   [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST",
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        if obj.get("type") == "content_block_delta":
                            text = obj["delta"].get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        pass


async def _stream_openai(prompt: str):
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":    "gpt-4o",
        "stream":   True,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST",
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        obj   = json.loads(data)
                        delta = obj["choices"][0]["delta"]
                        text  = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError):
                        pass