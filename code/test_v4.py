from __future__ import annotations

import csv
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_dataset
from data.models import FinancialRequest
from finance.currency import ExchangeRateTable
from finance.v4.decision_v4 import decide_v4


DATASET = Path("dataset")


def load_sample():
    requests = {}
    expected = {}

    with (DATASET / "sample_requests.csv").open(
        newline="",
        encoding="utf-8",
    ) as f:
        for row in csv.DictReader(f):
            rid = row["request_id"]

            requests[rid] = FinancialRequest(
                request_id=rid,
                user_id=row["user_id"],
                request_date=date.fromisoformat(row["request_date"]),
                request_type=row["request_type"],
                requested_amount=Decimal(row["requested_amount"]),
                desired_completion_date=date.fromisoformat(
                    row["desired_completion_date"]
                ),
                allows_partial_payment=(
                    row["allows_partial_payment"].lower() == "true"
                ),
                request_text=row["request_text"],
            )

            expected[rid] = {
                "safe": Decimal(row["amount_safe_to_pay"]),
                "status": row["affordability_status"],
                "method": row["recommended_payment_method"],
                "earliest": (
                    None
                    if not row["earliest_date_for_full_payment"]
                    else date.fromisoformat(
                        row["earliest_date_for_full_payment"]
                    )
                ),
            }

    return requests, expected


def main():
    dataset = load_dataset(DATASET)
    rates = ExchangeRateTable(dataset.exchange_rates)

    requests, expected = load_sample()

    score = {
        "safe": 0,
        "status": 0,
        "method": 0,
        "earliest": 0,
    }

    for number in range(1, 26):
        rid = f"request_{number:02d}"

        request = requests[rid]
        profile = dataset.profiles[request.user_id]

        actual = decide_v4(
            events=dataset.events,
            profile=profile,
            request=request,
            payment_options=dataset.payment_options.get(rid, []),
            exchange_rates=rates,
        )

        exp = expected[rid]

        safe_ok = actual.amount_safe_to_pay == exp["safe"]
        status_ok = actual.affordability_status == exp["status"]
        method_ok = actual.recommended_payment_method.value == exp["method"]
        earliest_ok = (
            actual.earliest_date_for_full_payment == exp["earliest"]
        )

        score["safe"] += safe_ok
        score["status"] += status_ok
        score["method"] += method_ok
        score["earliest"] += earliest_ok

        if not all(
            [safe_ok, status_ok, method_ok, earliest_ok]
        ):
            print(
                f"{rid} | "
                f"safe={'OK' if safe_ok else 'WRONG'} | "
                f"status={'OK' if status_ok else 'WRONG'} | "
                f"method={'OK' if method_ok else 'WRONG'} | "
                f"earliest={'OK' if earliest_ok else 'WRONG'}"
            )
            print(
                f"  expected: {exp['safe']} | "
                f"{exp['status']} | "
                f"{exp['method']} | "
                f"{exp['earliest']}"
            )
            print(
                f"  actual:   {actual.amount_safe_to_pay} | "
                f"{actual.affordability_status} | "
                f"{actual.recommended_payment_method.value} | "
                f"{actual.earliest_date_for_full_payment}"
            )

    print()
    print("=== V4 SCORE ===")
    for key, value in score.items():
        print(f"{key:9s}: {value}/25")


if __name__ == "__main__":
    main()
