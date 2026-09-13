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
from finance.v3.decision_v3 import decide_v3


DATASET = Path("dataset")
OUTPUT = DATASET / "output_v3.csv"


def sample_requests():
    result = {}

    with (DATASET / "sample_requests.csv").open(
        newline="",
        encoding="utf-8",
    ) as f:
        for row in csv.DictReader(f):
            result[row["request_id"]] = FinancialRequest(
                request_id=row["request_id"],
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

    return result


def main():
    dataset = load_dataset(DATASET)
    rates = ExchangeRateTable(dataset.exchange_rates)

    requests = dict(dataset.requests)
    requests.update(sample_requests())

    with OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.writer(f)

        writer.writerow(
            [
                "request_id",
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
                "spending_changes_needed",
                "decision_explanation",
            ]
        )

        for request_id in sorted(requests):
            request = requests[request_id]
            profile = dataset.profiles[request.user_id]

            decision = decide_v3(
                events=dataset.events,
                profile=profile,
                request=request,
                payment_options=dataset.payment_options.get(
                    request_id,
                    [],
                ),
                exchange_rates=rates,
            )

            plan = ";".join(
                f"{p.date.isoformat()}:{p.amount}"
                for p in decision.payment_plan
            )

            changes = ";".join(
                decision.spending_changes_needed
            )

            writer.writerow(
                [
                    decision.request_id,
                    decision.amount_safe_to_pay,
                    decision.affordability_status,
                    decision.recommended_payment_method.value,
                    plan,
                    (
                        decision.earliest_date_for_full_payment.isoformat()
                        if decision.earliest_date_for_full_payment
                        else ""
                    ),
                    changes,
                    decision.decision_explanation,
                ]
            )

    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
