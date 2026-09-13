from pathlib import Path
from collections import Counter

from data.loader import load_dataset
from finance.cashflow import user_cashflows


def main():
    root = Path(__file__).resolve().parents[1]
    dataset = load_dataset(root / "dataset")

    print("=== CASH-FLOW DATA DIAGNOSTIC ===")

    events = (
        dataset.events.values()
        if isinstance(dataset.events, dict)
        else dataset.events
    )

    event_users = Counter()

    for event in events:
        event_users[event.user_id] += 1

    print(f"Users with events: {len(event_users)}")
    print(f"Total events: {sum(event_users.values())}")

    print("\n=== USERS WITH MOST EVENTS ===")

    for user_id, count in event_users.most_common(10):
        print(user_id, "|", count)

    # Pick a user that definitely has events.
    user_id = event_users.most_common(1)[0][0]

    print("\n=== TEST USER ===")
    print("User:", user_id)

    flows = user_cashflows(dataset.events, user_id)

    print("Cash-flow events:", len(flows))

    print("\n=== FIRST 10 CASH FLOWS ===")

    for flow in flows[:10]:
        print(
            flow.event_id,
            "|",
            flow.settlement_date,
            "|",
            flow.amount,
            flow.currency,
            "|",
            flow.category,
            "|",
            flow.status,
        )

    print("\n=== CHECKS ===")

    assert len(flows) > 0

    for flow in flows:
        assert flow.settlement_date is not None
        assert flow.amount is not None

    debit = next(
        (x for x in flows if x.direction == "debit"),
        None,
    )

    credit = next(
        (x for x in flows if x.direction == "credit"),
        None,
    )

    if debit:
        assert debit.amount < 0
        print("✓ Debit sign correct")

    if credit:
        assert credit.amount > 0
        print("✓ Credit sign correct")

    print("✓ Events converted to cash flows")
    print("✓ Settlement dates preserved")
    print("✓ Cash-flow sanity checks passed")


if __name__ == "__main__":
    main()