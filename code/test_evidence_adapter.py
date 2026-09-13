from __future__ import annotations

from datetime import date
from decimal import Decimal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_dataset
from agents.gemini.evidence_adapter import facts_to_flows


def main():
    dataset = load_dataset(Path("dataset"))

    request = dataset.requests["request_26"]
    profile = dataset.profiles[request.user_id]

    facts = [
        {
            "fact_type": "income",
            "value": "IDR 30,780,000",
            "confidence": 1.0,
            "related_event_id": "",
        },
        {
            "fact_type": "date",
            "value": "2025-08-15",
            "confidence": 1.0,
            "related_event_id": "",
        },
    ]

    flows = facts_to_flows(
        facts=facts,
        profile=profile,
        request_date=request.request_date,
        horizon_end=(
            request.request_date
            + __import__("datetime").timedelta(days=90)
        ),
    )

    print("flows:", flows)


if __name__ == "__main__":
    main()
