def _mask_vpa(vpa: str) -> str:
    """Safely mask VPA: rahul123@oksbi → ***@oksbi"""
    if not vpa or "@" not in vpa:
        return "***"
    parts = vpa.split("@", 1)   # split on first @ only
    return f"***@{parts[1]}"

def build_fraud_analyst_prompt(txn: dict, scores: dict,
                                shap_top5: list, pattern: dict,
                                graph_ctx: dict) -> str:
    # Safe masking
    masked_sender   = _mask_vpa(txn.get("sender_vpa", ""))
    masked_receiver = _mask_vpa(txn.get("receiver_vpa", ""))

    shap_text = "\n".join([
        f"  - {s['feature']}: value={s['value']:.3f}, SHAP={s['shap']:+.4f} ({s['direction']})"
        for s in shap_top5
    ])

    graph_text = (
        f"  Sender PageRank: {graph_ctx.get('sender_pagerank', 0):.6f}\n"
        f"  Receiver PageRank: {graph_ctx.get('receiver_pagerank', 0):.6f}\n"
        f"  Forwarding chain length: {graph_ctx.get('chain_length', 0)}\n"
        f"  Hops to nearest fraud VPA: {graph_ctx.get('fraud_hop_count', 999)}\n"
        f"  Receiver is star/mule: {graph_ctx.get('is_star_receiver', False)}"
    )

    prompt = f"""You are a senior UPI fraud analyst at an Indian bank.
A transaction has been flagged by the AI fraud detection system.
Write a structured 5-section fraud analyst report in clear, professional English.

TRANSACTION DETAILS:
  Transaction ID: {txn.get('txn_id')}
  Sender VPA: {masked_sender}
  Receiver VPA: {masked_receiver}
  Amount: Rs {txn.get('amount', 0):,.2f}
  Timestamp: {txn.get('timestamp')}
  Transaction type: {txn.get('txn_type', 'P2P')}

ENSEMBLE RISK SCORES:
  Isolation Forest (anomaly): {scores.get('if_score', 0):.4f}
  Autoencoder (reconstruction error): {scores.get('ae_score', 0):.4f}
  XGBoost (fraud probability): {scores.get('xgb_score', 0):.4f}
  Ensemble score: {scores.get('ensemble_score', 0):.4f}
  Risk tier assigned: {scores.get('risk_tier', 'Unknown')}

TOP 5 SHAP FEATURES (driving the risk score):
{shap_text}

MATCHED FRAUD PATTERN:
  Pattern name: {pattern.get('name')}
  Description: {pattern.get('description')}
  Recommended action: {pattern.get('default_action')}

GRAPH NETWORK CONTEXT:
{graph_text}

Write the report in EXACTLY this structure:

## 1. Fraud Summary
[One paragraph: risk tier, ensemble score, primary reason for flagging, recommended immediate action]

## 2. Anomaly Breakdown
### Isolation Forest signal
### Autoencoder signal
### XGBoost signal

## 3. Transaction Pattern
[Which fraud pattern this matches. Quote specific SHAP features as evidence.]

## 4. Network Context
[Graph analysis findings. Connections to fraud accounts, suspicious clusters.]

## 5. Analyst Recommended Actions
[3-5 bullet points in priority order with time guidance]

Be specific, cite actual numbers, and be actionable."""

    return prompt