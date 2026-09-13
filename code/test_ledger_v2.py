from __future__ import annotations

import csv
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_dataset
from data.models import FinancialRequest
from finance.ledger import build_cash_ledger
from finance.currency import ExchangeRateTable


DATASET = Path("dataset")


def load_sample_requests():
    result = {}

    with (DATASET / "sample_requests.csv").open(
        newline="", encoding="utf-8"
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
    requests = load_sample_requests()
    rates = ExchangeRateTable(dataset.exchange_rates)

    print("=== LEDGER V2 CHECK ===")

    for rid in [
        "request_01",
        "request_03",
        "request_05",
        "request_10",
        "request_19",
        "request_21",
        "request_25",
    ]:
        request = requests[rid]
        profile = dataset.profiles[request.user_id]

        ledger = build_cash_ledger(
            events=dataset.events,
            profile=profile,
            request=request,
            rates=rates,
        )

        print()
        print(
            rid,
            "|",
            request.user_id,
            "|",
            request.request_date,
            "|",
            profile.home_currency,
        )
        print(
            "start=",
            profile.current_available_balance,
            "minimum=",
            profile.minimum_balance_to_keep,
        )
        print("entries=", len(ledger.entries))

        required_debits = [
            x
            for x in ledger.entries
            if x.delta < 0 and x.required
        ]

        credits = [
            x
            for x in ledger.entries
            if x.delta > 0
        ]

        print(
            "required debit total=",
            sum(((-x.delta) for x in required_debits), Decimal("0")),
        )
        print(
            "credit total=",
            sum((x.delta for x in credits), Decimal("0")),
        )

        print("first 12 entries:")
        for entry in ledger.entries[:12]:
            print(
                entry.date,
                f"{entry.delta:>15}",
                entry.category,
                entry.source,
                entry.required,
                entry.event_id,
            )


if __name__ == "__main__":
    main()
