import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "genai-service"))

from explainer import stream_fraud_explanation  # noqa: E402


async def main():
    txn = {
        "txn_id": "TXN_TEST_001",
        "sender_vpa": "user@oksbi",
        "receiver_vpa": "merchant@ybl",
        "amount": 12000,
        "if_score": 0.62,
        "ae_score": 0.41,
        "xgb_score": 0.77,
        "ensemble_score": 0.84,
        "risk_tier": "BLOCK",
        "shap_top5": [
            {"feature": "txn_count_1min", "direction": "increases_risk", "shap": 0.19},
            {"feature": "is_new_device", "direction": "increases_risk", "shap": 0.15},
        ],
    }
    text = ""
    async for token in stream_fraud_explanation(txn):
        text += token

    if len(text.strip()) < 100:
        raise RuntimeError("Explainer stream output too short")

    print("EXPLAINER_STREAM_OK", len(text))
    print(text[:180])


if __name__ == "__main__":
    asyncio.run(main())
