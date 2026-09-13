from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from collections import defaultdict
from typing import Iterable

from data.models import (
    EventDirection,
    EventStatus,
    FinancialEvent,
    FinancialProfile,
    FinancialRequest,
)

from finance.recurrence import analyse_recurrence


IGNORED_STATUSES = {
    EventStatus.FAILED,
    EventStatus.CANCELLED,
    EventStatus.UNREALIZED,
}


@dataclass(frozen=True)
class Flow:
    date: date
    amount: Decimal
    category: str
    direction: str
    event_id: str | None
    source: str
    flexibility: str | None
    minimum_allowed_amount: Decimal | None
    required: bool


@dataclass(frozen=True)
class CashModel:
    as_of: date
    horizon_end: date
    starting_balance: Decimal
    minimum_balance: Decimal
    flows: tuple[Flow, ...]


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

    if hasattr(rates, "latest_on_or_before"):
        return amount * rates.latest_on_or_before(
            on_date,
            from_currency,
            to_currency,
        )

    return rates.convert(
        amount,
        on_date,
        from_currency,
        to_currency,
    )


def _cash_status(event: FinancialEvent) -> bool:
    if event.status in IGNORED_STATUSES:
        return False

    if event.direction == EventDirection.CREDIT:
        return event.status in {
            EventStatus.SETTLED,
            EventStatus.SCHEDULED,
        }

    if event.direction == EventDirection.DEBIT:
        return event.status in {
            EventStatus.PENDING,
            EventStatus.SETTLED,
            EventStatus.SCHEDULED,
        }

    return False


def _required(
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


def _stream_key(event: FinancialEvent) -> tuple:
    return (
        event.event_type,
        event.category,
        event.direction,
    )


def _future_explicit(
    events: Iterable[FinancialEvent],
    profile: FinancialProfile,
    request_date: date,
    horizon_end: date,
) -> list[FinancialEvent]:
    result = []

    for event in events:
        if event.user_id != profile.user_id:
            continue
        if event.amount is None:
            continue
        if event.direction == EventDirection.NON_CASH:
            continue
        if not _cash_status(event):
            continue

        dt = _event_date(event)

        if request_date <= dt <= horizon_end:
            result.append(event)

    return result


def _historical(
    events: Iterable[FinancialEvent],
    profile: FinancialProfile,
    request_date: date,
) -> list[FinancialEvent]:
    result = []

    for event in events:
        if event.user_id != profile.user_id:
            continue
        if event.amount is None:
            continue
        if event.direction == EventDirection.NON_CASH:
            continue
        if event.status in IGNORED_STATUSES:
            continue

        if _event_date(event) < request_date:
            result.append(event)

    return result


def _confirmed_dates(
    explicit_events: Iterable[FinancialEvent],
) -> dict[tuple, list[date]]:
    result: dict[tuple, list[date]] = defaultdict(list)

    for event in explicit_events:
        result[_stream_key(event)].append(_event_date(event))

    return result


def _nearby_confirmed(
    dates: Iterable[date],
    target: date,
    tolerance_days: int,
) -> bool:
    return any(abs((x - target).days) <= tolerance_days for x in dates)


def _recurring_flows(
    historical: list[FinancialEvent],
    explicit_events: list[FinancialEvent],
    profile: FinancialProfile,
    request: FinancialRequest,
    rates,
    horizon_end: date,
) -> list[Flow]:
    groups: dict[tuple, list[FinancialEvent]] = defaultdict(list)

    for event in historical:
        if event.direction not in {
            EventDirection.CREDIT,
            EventDirection.DEBIT,
        }:
            continue

        groups[_stream_key(event)].append(event)

    confirmed = _confirmed_dates(explicit_events)
    projected: list[Flow] = []

    for key, group in groups.items():
        analysis = analyse_recurrence(group)

        if analysis.kind != "deterministic_recurring":
            continue

        if analysis.interval_days is None:
            continue

        ordered = sorted(group, key=_event_date)
        template = ordered[-1]

        # Ordinary flexible spending is not part of the baseline.
        if (
            template.direction == EventDirection.DEBIT
            and template.flexibility not in (None, "", "fixed")
            and template.category not in profile.protected_categories
        ):
            continue

        recent = [
            x.amount
            for x in ordered[-6:]
            if x.amount is not None
        ]

        if not recent:
            continue

        amount = Decimal(str(median(float(x) for x in recent)))
        cursor = _event_date(template)

        while True:
            cursor += timedelta(days=analysis.interval_days)

            if cursor > horizon_end:
                break

            if cursor < request.request_date:
                continue

            # A confirmed future event of the same stream supersedes
            # the synthetic occurrence.
            tolerance = max(3, analysis.interval_days // 4)

            if _nearby_confirmed(
                confirmed.get(key, ()),
                cursor,
                tolerance,
            ):
                continue

            home_amount = _convert(
                rates,
                amount,
                template.currency,
                profile.home_currency,
                cursor,
            )

            if template.direction == EventDirection.CREDIT:
                delta = home_amount
                direction = "credit"
            else:
                delta = -home_amount
                direction = "debit"

            projected.append(
                Flow(
                    date=cursor,
                    amount=delta,
                    category=template.category,
                    direction=direction,
                    event_id=None,
                    source="projected_recurring",
                    flexibility=template.flexibility,
                    minimum_allowed_amount=template.minimum_allowed_amount,
                    required=_required(template, profile),
                )
            )

    return projected


def build_cash_model(
    events: dict[str, FinancialEvent] | Iterable[FinancialEvent],
    profile: FinancialProfile,
    request: FinancialRequest,
    rates,
    horizon_days: int = 90,
) -> CashModel:
    event_list = (
        list(events.values())
        if isinstance(events, dict)
        else list(events)
    )

    request_date = request.request_date
    horizon_end = request_date + timedelta(days=horizon_days)

    explicit = _future_explicit(
        event_list,
        profile,
        request_date,
        horizon_end,
    )

    flows: list[Flow] = []

    for event in explicit:
        dt = _event_date(event)
        amount = _convert(
            rates,
            event.amount,
            event.currency,
            profile.home_currency,
            dt,
        )

        if event.direction == EventDirection.CREDIT:
            # Pending credits are already excluded by _cash_status.
            delta = amount
            direction = "credit"
        else:
            delta = -amount
            direction = "debit"

        flows.append(
            Flow(
                date=dt,
                amount=delta,
                category=event.category,
                direction=direction,
                event_id=event.event_id,
                source="explicit",
                flexibility=event.flexibility,
                minimum_allowed_amount=event.minimum_allowed_amount,
                required=_required(event, profile),
            )
        )

    historical = _historical(
        event_list,
        profile,
        request_date,
    )

    flows.extend(
        _recurring_flows(
            historical=historical,
            explicit_events=explicit,
            profile=profile,
            request=request,
            rates=rates,
            horizon_end=horizon_end,
        )
    )

    flows.sort(
        key=lambda x: (
            x.date,
            0 if x.amount < 0 else 1,
            x.event_id or "",
            x.source,
        )
    )

    return CashModel(
        as_of=request_date,
        horizon_end=horizon_end,
        starting_balance=profile.current_available_balance,
        minimum_balance=profile.minimum_balance_to_keep,
        flows=tuple(flows),
    )


def apply_spending_changes(
    model: CashModel,
    profile: FinancialProfile,
) -> tuple[CashModel, tuple[str, ...]]:
    """
    Return a modified model where only future recurring flexible expenses
    are changed.

    Stoppable categories are removed.
    Reducible categories are reduced to minimum_allowed_amount when one
    is explicitly supplied by the event.
    """

    changed: list[str] = []
    output: list[Flow] = []

    for flow in model.flows:
        if flow.source != "projected_recurring":
            output.append(flow)
            continue

        if flow.direction != "debit":
            output.append(flow)
            continue

        if flow.category in profile.stoppable_categories:
            if flow.category not in changed:
                changed.append(
                    f"stop {flow.category}"
                )
            continue

        if flow.category in profile.reducible_categories:
            minimum = flow.minimum_allowed_amount

            if minimum is not None:
                new_amount = -minimum
                if new_amount > flow.amount:
                    new_amount = flow.amount

                if new_amount != flow.amount:
                    if flow.category not in changed:
                        changed.append(
                            f"reduce {flow.category}"
                        )

                    output.append(
                        Flow(
                            date=flow.date,
                            amount=new_amount,
                            category=flow.category,
                            direction=flow.direction,
                            event_id=flow.event_id,
                            source=flow.source,
                            flexibility=flow.flexibility,
                            minimum_allowed_amount=flow.minimum_allowed_amount,
                            required=flow.required,
                        )
                    )
                    continue

        output.append(flow)

    return (
        CashModel(
            as_of=model.as_of,
            horizon_end=model.horizon_end,
            starting_balance=model.starting_balance,
            minimum_balance=model.minimum_balance,
            flows=tuple(output),
        ),
        tuple(changed),
    )
