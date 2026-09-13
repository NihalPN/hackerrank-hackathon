from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data.models import FinancialEvent


@dataclass(frozen=True)
class EffectiveCashEvent:
    event: FinancialEvent
    cash_date: date
    amount: Decimal


IGNORED_STATUSES = {
    "failed",
    "cancelled",
    "unrealized",
}


def valid_cash_event(event: FinancialEvent) -> bool:
    if event.direction.value == "non_cash":
        return False

    if event.status.value in IGNORED_STATUSES:
        return False

    return event.amount is not None


def cash_date(event: FinancialEvent) -> date | None:
    """
    Settlement date is authoritative when available.
    For pending/scheduled events without settlement information,
    event_date is used.
    """
    if event.settlement_date is not None:
        return event.settlement_date

    if event.status.value in {"pending", "scheduled"}:
        return event.event_date

    return None


def signed_cash_amount(event: FinancialEvent) -> Decimal:
    if event.amount is None:
        return Decimal("0")

    if event.direction.value == "debit":
        return -event.amount

    if event.direction.value == "credit":
        # Pending credits cannot be counted as available money.
        if event.status.value == "pending":
            return Decimal("0")

        return event.amount

    return Decimal("0")


def effective_future_events(
    events: dict[str, FinancialEvent],
    user_id: str,
    start_date: date,
    end_date: date,
) -> tuple[EffectiveCashEvent, ...]:

    result: list[EffectiveCashEvent] = []

    for event in events.values():

        if event.user_id != user_id:
            continue

        if not valid_cash_event(event):
            continue

        event_date = cash_date(event)

        if event_date is None:
            continue

        if event_date < start_date or event_date > end_date:
            continue

        result.append(
            EffectiveCashEvent(
                event=event,
                cash_date=event_date,
                amount=signed_cash_amount(event),
            )
        )

    result.sort(
        key=lambda item: (
            item.cash_date,
            item.event.event_id,
        )
    )

    return tuple(result)
