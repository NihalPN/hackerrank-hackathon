from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from data.models import FinancialEvent, FinancialProfile, EventDirection, EventStatus


@dataclass(frozen=True)
class PendingObligation:
    event_id: str
    due_date: date
    amount: Decimal
    currency: str
    home_amount: Decimal
    category: str
    description: str


@dataclass(frozen=True)
class FinancialState:
    user_id: str
    as_of: date
    home_currency: str
    starting_balance: Decimal
    minimum_balance: Decimal
    pending_debits: tuple[PendingObligation, ...]

    @property
    def cash_after_pending_debits(self) -> Decimal:
        return self.starting_balance - sum(
            (x.home_amount for x in self.pending_debits),
            Decimal("0"),
        )


def _effective_date(event: FinancialEvent) -> date:
    return event.settlement_date or event.event_date


def _is_pending_debit(event: FinancialEvent, as_of: date) -> bool:
    return (
        event.direction == EventDirection.DEBIT
        and event.status == EventStatus.PENDING
        and event.event_date >= as_of
        and event.amount is not None
    )


def build_financial_state(
    profile: FinancialProfile,
    events: Iterable[FinancialEvent],
    as_of: date,
    convert_amount,
) -> FinancialState:
    pending: list[PendingObligation] = []

    for event in events:
        if event.user_id != profile.user_id:
            continue

        if not _is_pending_debit(event, as_of):
            continue

        home_amount = convert_amount(
            event.amount,
            event.currency,
            profile.home_currency,
            as_of,
        )

        pending.append(
            PendingObligation(
                event_id=event.event_id,
                due_date=_effective_date(event),
                amount=event.amount,
                currency=event.currency,
                home_amount=home_amount,
                category=event.category,
                description=event.description,
            )
        )

    pending.sort(key=lambda x: (x.due_date, x.event_id))

    return FinancialState(
        user_id=profile.user_id,
        as_of=as_of,
        home_currency=profile.home_currency,
        starting_balance=profile.current_available_balance,
        minimum_balance=profile.minimum_balance_to_keep,
        pending_debits=tuple(pending),
    )
