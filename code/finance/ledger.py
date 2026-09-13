from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from collections import defaultdict
from typing import Iterable

from data.models import (
    FinancialEvent,
    FinancialProfile,
    FinancialRequest,
    EventDirection,
    EventStatus,
)

from finance.recurrence import analyse_recurrence


IGNORED_STATUSES = {
    EventStatus.FAILED,
    EventStatus.CANCELLED,
    EventStatus.UNREALIZED,
}


@dataclass(frozen=True)
class LedgerEntry:
    date: date
    delta: Decimal
    currency: str
    event_id: str | None
    category: str
    description: str
    direction: str
    source: str
    required: bool
    flexibility: str | None
    minimum_allowed_amount: Decimal | None


@dataclass(frozen=True)
class CashLedger:
    as_of: date
    horizon_end: date
    entries: tuple[LedgerEntry, ...]

    def sorted_entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(
            sorted(
                self.entries,
                key=lambda x: (
                    x.date,
                    0 if x.delta < 0 else 1,
                    x.event_id or "",
                ),
            )
        )

    def simulate(
        self,
        starting_balance: Decimal,
        minimum_balance: Decimal,
        payments: Iterable[tuple[date, Decimal]] = (),
    ) -> tuple[Decimal, date | None, list[tuple[date, Decimal]]]:
        payment_map: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))

        for payment_date, amount in payments:
            payment_map[payment_date] += amount

        by_date: dict[date, list[LedgerEntry]] = defaultdict(list)

        for entry in self.entries:
            if self.as_of <= entry.date <= self.horizon_end:
                by_date[entry.date].append(entry)

        for payment_date in payment_map:
            by_date.setdefault(payment_date, [])

        balance = starting_balance
        minimum_seen = balance
        minimum_date: date | None = self.as_of
        trace: list[tuple[date, Decimal]] = [(self.as_of, balance)]

        for current_date in sorted(by_date):
            for entry in sorted(
                by_date[current_date],
                key=lambda x: (0 if x.delta < 0 else 1, x.event_id or ""),
            ):
                balance += entry.delta

                if balance < minimum_seen:
                    minimum_seen = balance
                    minimum_date = current_date

            payment = payment_map.get(current_date, Decimal("0"))
            if payment:
                balance -= payment

                if balance < minimum_seen:
                    minimum_seen = balance
                    minimum_date = current_date

            trace.append((current_date, balance))

        return minimum_seen, minimum_date, trace

    def is_safe(
        self,
        starting_balance: Decimal,
        minimum_balance: Decimal,
        payments: Iterable[tuple[date, Decimal]] = (),
    ) -> bool:
        minimum_seen, _, _ = self.simulate(
            starting_balance,
            minimum_balance,
            payments,
        )
        return minimum_seen >= minimum_balance


def _event_date(event: FinancialEvent) -> date:
    return event.settlement_date or event.event_date


def _convert(
    rates,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    on_date: date,
) -> Decimal:
    if from_currency == to_currency:
        return amount

    # Use the repository's historical-rate fallback when an exact
    # date is unavailable.
    if hasattr(rates, "latest_on_or_before"):
        rate = rates.latest_on_or_before(
            on_date,
            from_currency,
            to_currency,
        )
        if rate is not None:
            return amount * rate

    return rates.convert(
        amount,
        from_currency,
        to_currency,
        on_date,
    )


def _historical_events_for_user(
    events: Iterable[FinancialEvent],
    user_id: str,
    as_of: date,
) -> list[FinancialEvent]:
    result = []

    for event in events:
        if event.user_id != user_id:
            continue
        if event.amount is None:
            continue
        if event.status in IGNORED_STATUSES:
            continue

        event_date = _event_date(event)

        if event_date < as_of and event.direction in (
            EventDirection.DEBIT,
            EventDirection.CREDIT,
        ):
            result.append(event)

    return result


def _future_explicit_events(
    events: Iterable[FinancialEvent],
    user_id: str,
    as_of: date,
    horizon_end: date,
) -> list[FinancialEvent]:
    result = []

    for event in events:
        if event.user_id != user_id:
            continue
        if event.amount is None:
            continue
        if event.status in IGNORED_STATUSES:
            continue
        if event.direction not in (
            EventDirection.DEBIT,
            EventDirection.CREDIT,
        ):
            continue

        event_date = _event_date(event)

        if event_date < as_of or event_date > horizon_end:
            continue

        result.append(event)

    return result


def _group_key(event: FinancialEvent) -> tuple:
    # Description is deliberately excluded. Future evidence such as
    # "Salary credit", "Payroll credit", and "Monthly salary" should
    # represent the same recurring stream when event_type/category/
    # direction agree.
    return (
        event.event_type,
        event.category,
        event.direction,
    )


def _required_event(
    event: FinancialEvent,
    profile: FinancialProfile,
) -> bool:
    if event.direction == EventDirection.CREDIT:
        return False

    if event.category in profile.protected_categories:
        return True

    if event.flexibility in (None, "", "fixed"):
        return True

    return False


def _project_deterministic_recurring(
    historical: list[FinancialEvent],
    explicit_dates: set[tuple],
    profile: FinancialProfile,
    as_of: date,
    horizon_end: date,
    rates,
) -> list[LedgerEntry]:
    groups: dict[tuple, list[FinancialEvent]] = defaultdict(list)

    for event in historical:
        groups[_group_key(event)].append(event)

    projected: list[LedgerEntry] = []

    for key, group in groups.items():
        analysis = analyse_recurrence(group)

        if analysis.kind != "deterministic_recurring":
            continue

        if analysis.interval_days is None:
            continue

        ordered = sorted(group, key=lambda x: _event_date(x))

        if not ordered:
            continue

        amount = Decimal(
            str(
                median(
                    [float(x.amount) for x in ordered[-6:] if x.amount is not None]
                )
            )
        )

        last_date = _event_date(ordered[-1])
        cursor = last_date

        while True:
            cursor += timedelta(days=analysis.interval_days)

            if cursor > horizon_end:
                break

            if cursor < as_of:
                continue

            identity = (
                key,
                cursor,
            )

            if identity in explicit_dates:
                continue

            # Explicit future events take precedence over synthetic
            # recurrence projections. If a confirmed future event for
            # the same stream lands close to the projected recurrence,
            # use the explicit event instead of double-counting it.
            template = ordered[-1]

            delta = amount
            if template.direction == EventDirection.DEBIT:
                delta = -amount

            home_amount = _convert(
                rates,
                amount,
                template.currency,
                profile.home_currency,
                cursor,
            )

            if template.direction == EventDirection.DEBIT:
                delta = -home_amount
            else:
                delta = home_amount

            projected.append(
                LedgerEntry(
                    date=cursor,
                    delta=delta,
                    currency=profile.home_currency,
                    event_id=None,
                    category=template.category,
                    description=template.description,
                    direction=template.direction.value,
                    source="projected_recurring",
                    required=_required_event(template, profile),
                    flexibility=template.flexibility,
                    minimum_allowed_amount=template.minimum_allowed_amount,
                )
            )

    return projected


def build_cash_ledger(
    events: dict[str, FinancialEvent] | Iterable[FinancialEvent],
    profile: FinancialProfile,
    request: FinancialRequest,
    rates,
    horizon_days: int = 90,
) -> CashLedger:
    if isinstance(events, dict):
        event_list = list(events.values())
    else:
        event_list = list(events)

    as_of = request.request_date
    horizon_end = as_of + timedelta(days=horizon_days)

    explicit = _future_explicit_events(
        event_list,
        profile.user_id,
        as_of,
        horizon_end,
    )

    explicit_dates: set[tuple] = set()

    entries: list[LedgerEntry] = []

    for event in explicit:
        event_date = _event_date(event)

        home_amount = _convert(
            rates,
            event.amount,
            event.currency,
            profile.home_currency,
            event_date,
        )

        if event.direction == EventDirection.DEBIT:
            delta = -home_amount
        elif event.direction == EventDirection.CREDIT:
            # Pending credit is deliberately excluded from available cash.
            if event.status == EventStatus.PENDING:
                delta = Decimal("0")
            else:
                delta = home_amount
        else:
            continue

        entries.append(
            LedgerEntry(
                date=event_date,
                delta=delta,
                currency=profile.home_currency,
                event_id=event.event_id,
                category=event.category,
                description=event.description,
                direction=event.direction.value,
                source="explicit_event",
                required=_required_event(event, profile),
                flexibility=event.flexibility,
                minimum_allowed_amount=event.minimum_allowed_amount,
            )
        )

        suppresses_projection = False

        if event.direction == EventDirection.CREDIT:
            suppresses_projection = event.status in {
                EventStatus.SETTLED,
                EventStatus.SCHEDULED,
            }
        elif event.direction == EventDirection.DEBIT:
            suppresses_projection = event.status in {
                EventStatus.SETTLED,
                EventStatus.SCHEDULED,
                EventStatus.PENDING,
            }

        if suppresses_projection:
            explicit_dates.add(
                (
                    _group_key(event),
                    event_date,
                )
            )

    historical = _historical_events_for_user(
        event_list,
        profile.user_id,
        as_of,
    )

    entries.extend(
        _project_deterministic_recurring(
            historical=historical,
            explicit_dates=explicit_dates,
            profile=profile,
            as_of=as_of,
            horizon_end=horizon_end,
            rates=rates,
        )
    )

    return CashLedger(
        as_of=as_of,
        horizon_end=horizon_end,
        entries=tuple(
            sorted(
                entries,
                key=lambda x: (
                    x.date,
                    0 if x.delta < 0 else 1,
                    x.event_id or "",
                ),
            )
        ),
    )
