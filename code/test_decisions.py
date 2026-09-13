from __future__ import annotations

import csv
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_dataset
from data.models import FinancialRequest
from finance.decision import decide


DATASET = Path("dataset")


def load_sample_requests():
    path = DATASET / "sample_requests.csv"

    requests = {}
    expected = {}

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            request = FinancialRequest(
                request_id=row["request_id"],
                user_id=row["user_id"],
                request_date=date.fromisoformat(row["request_date"]),
                requested_amount=Decimal(row["requested_amount"]),
                request_type=row["request_type"],
                desired_completion_date=date.fromisoformat(
                    row["desired_completion_date"]
                ),
                allows_partial_payment=(
                    row["allows_partial_payment"].lower() == "true"
                ),
                request_text=row["request_text"],
            )

            requests[request.request_id] = request

            expected[request.request_id] = {
                "amount_safe_to_pay": Decimal(row["amount_safe_to_pay"]),
                "affordability_status": row["affordability_status"],
                "recommended_payment_method": row[
                    "recommended_payment_method"
                ],
                "payment_plan": row["payment_plan"],
                "earliest_date_for_full_payment": (
                    None
                    if row["earliest_date_for_full_payment"] == ""
                    else date.fromisoformat(
                        row["earliest_date_for_full_payment"]
                    )
                ),
                "spending_changes_needed": row[
                    "spending_changes_needed"
                ],
            }

    return requests, expected


def main():
    dataset = load_dataset(DATASET)
    requests, expected = load_sample_requests()

    print("=== SAMPLE DECISION BENCHMARK ===")
    print()

    for number in range(1, 26):
        request_id = f"request_{number:02d}"

        request = requests[request_id]
        profile = dataset.profiles[request.user_id]

        actual = decide(
        events=dataset.events,
        profile=profile,
        request=request,
        payment_options=dataset.payment_options.get(request_id, []),
        exchange_rates=dataset.exchange_rates,
    )

        exp = expected[request_id]

        safe_match = actual.amount_safe_to_pay == exp["amount_safe_to_pay"]
        status_match = (
            actual.affordability_status == exp["affordability_status"]
        )
        method_match = (
            actual.recommended_payment_method.value
            == exp["recommended_payment_method"]
        )

        earliest_match = (
            actual.earliest_date_for_full_payment
            == exp["earliest_date_for_full_payment"]
        )

        print(
            f"{request_id} | "
            f"safe: {'OK' if safe_match else 'WRONG'} | "
            f"status: {'OK' if status_match else 'WRONG'} | "
            f"method: {'OK' if method_match else 'WRONG'} | "
            f"earliest: {'OK' if earliest_match else 'WRONG'}"
        )

        print(
            f"  expected: "
            f"safe={exp['amount_safe_to_pay']} | "
            f"status={exp['affordability_status']} | "
            f"method={exp['recommended_payment_method']} | "
            f"earliest={exp['earliest_date_for_full_payment']}"
        )

        print(
            f"  actual:   "
            f"safe={actual.amount_safe_to_pay} | "
            f"status={actual.affordability_status} | "
            f"method={actual.recommended_payment_method.value} | "
            f"earliest={actual.earliest_date_for_full_payment}"
        )

        if not safe_match:
            print("  SAFE AMOUNT DIFFERENCE")

        if not status_match:
            print("  STATUS DIFFERENCE")

        if not method_match:
            print("  METHOD DIFFERENCE")

        if not earliest_match:
            print("  EARLIEST DATE DIFFERENCE")

        print()


if __name__ == "__main__":
    main()