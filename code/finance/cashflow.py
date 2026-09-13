from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable


# ---------------------------------------------------------------------------
# NORMALIZATION HELPERS
# ---------------------------------------------------------------------------

def _enum_value(value) -> str:
    """
    Return the underlying string value.

    Our data models use Enums, while the CSV values are plain strings.
    For example:

        EventDirection.DEBIT -> "debit"
        EventStatus.SETTLED  -> "settled"

    This also works if the loader gives us a normal string.
    """
    return str(getattr(value, "value", value))


def _decimal(value) -> Decimal:
    """Convert a value to Decimal without silently accepting blanks."""
    if value is None or str(value).strip() == "":
        raise ValueError("Cannot convert blank amount to Decimal")

    return Decimal(str(value))


def _date(value) -> date:
    """Convert a value to a Python date."""
    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


# ---------------------------------------------------------------------------
# NORMALIZED CASH-FLOW OBJECTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CashFlow:
    event_id: str
    user_id: str
    event_date: date
    settlement_date: date
    amount: Decimal
    currency: str
    direction: str
    status: str
    category: str
    description: str
    flexibility: str


@dataclass(frozen=True)
class BalancePoint:
    date: date
    balance: Decimal


# ---------------------------------------------------------------------------
# CASH-FLOW RULES
# ---------------------------------------------------------------------------

# These statuses can affect the future cash position.
#
# settled:
#     Money has already settled.
#
# pending:
#     Money is expected to settle and therefore reserves/affects cash.
#
# scheduled:
#     Known future cash movement.
#
# failed/cancelled/unrealized:
#     Do not affect cash.
VALID_CASH_STATUSES = {
    "settled",
    "pending",
    "scheduled",
}


# ---------------------------------------------------------------------------
# EVENT -> SIGNED CASH AMOUNT
# ---------------------------------------------------------------------------

def signed_amount(event) -> Decimal:
    """
    Convert a financial event into a signed cash amount.

    credit:
        positive

    debit:
        negative

    non_cash:
        zero

    IMPORTANT:
    A missing amount is NOT interpreted as zero.
    Missing financial amounts must be resolved by the evidence layer.
    """

    direction = _enum_value(event.direction)

    if direction == "credit":
        return _decimal(event.amount)

    if direction == "debit":
        return -_decimal(event.amount)

    if direction == "non_cash":
        return Decimal("0")

    raise ValueError(
        f"Unknown event direction: {direction!r}"
    )


# ---------------------------------------------------------------------------
# DETERMINE WHETHER EVENT AFFECTS CASH
# ---------------------------------------------------------------------------

def is_cash_event(event) -> bool:
    """
    Return True when the event should participate in cash forecasting.
    """

    direction = _enum_value(event.direction)
    status = _enum_value(event.status)

    # Investments/valuations and other non-cash events must not
    # change available cash.
    if direction == "non_cash":
        return False

    # Failed, cancelled and unrealized events are excluded.
    if status not in VALID_CASH_STATUSES:
        return False

    return True


# ---------------------------------------------------------------------------
# NORMALIZE ONE EVENT
# ---------------------------------------------------------------------------

def event_cashflow(event) -> CashFlow | None:
    """
    Convert one FinancialEvent into a normalized CashFlow.

    Returns:
        CashFlow -> if the event affects cash
        None     -> if the event is non-cash or excluded

    Missing amounts deliberately raise an error rather than being
    converted to zero.
    """

    if not is_cash_event(event):
        return None

    if event.amount is None or str(event.amount).strip() == "":
        raise ValueError(
            f"Missing amount for cash event {event.event_id}. "
            "Resolve the amount from trusted evidence before forecasting."
        )

    return CashFlow(
        event_id=str(event.event_id),
        user_id=str(event.user_id),
        event_date=_date(event.event_date),
        settlement_date=_date(event.settlement_date),
        amount=signed_amount(event),
        currency=str(event.currency),
        direction=_enum_value(event.direction),
        status=_enum_value(event.status),
        category=str(event.category),
        description=str(event.description),
        flexibility=_enum_value(event.flexibility),
    )


# ---------------------------------------------------------------------------
# USER CASH FLOWS
# ---------------------------------------------------------------------------

def user_cashflows(
    events: Iterable,
    user_id: str,
) -> list[CashFlow]:
    """
    Return normalized cash flows for one user.

    The loader may expose events as either:

        list[FinancialEvent]

    or:

        dict[event_id, FinancialEvent]

    Therefore both representations are supported.

    Events are sorted by settlement date because settlement is the date
    on which the cash movement affects the user's available cash.
    """

    if isinstance(events, dict):
        event_iterable = events.values()
    else:
        event_iterable = events

    result: list[CashFlow] = []

    for event in event_iterable:

        if str(event.user_id) != str(user_id):
            continue

        flow = event_cashflow(event)

        if flow is not None:
            result.append(flow)

    # Deterministic ordering.
    result.sort(
        key=lambda flow: (
            flow.settlement_date,
            flow.event_id,
        )
    )

    return result


# ---------------------------------------------------------------------------
# DAILY CASH-FLOW AGGREGATION
# ---------------------------------------------------------------------------

def daily_cashflow(
    events: Iterable,
    user_id: str,
    start_date: date,
    end_date: date,
) -> dict[date, Decimal]:
    """
    Aggregate all known cash movements by settlement date.

    Only events inside [start_date, end_date] are returned.
    """

    totals: dict[date, Decimal] = defaultdict(
        lambda: Decimal("0")
    )

    for flow in user_cashflows(events, user_id):

        if start_date <= flow.settlement_date <= end_date:
            totals[flow.settlement_date] += flow.amount

    return dict(totals)


# ---------------------------------------------------------------------------
# BALANCE RECONSTRUCTION
# ---------------------------------------------------------------------------

def reconstruct_balance(
    events: Iterable,
    user_id: str,
    starting_balance: Decimal,
    start_date: date,
    end_date: date,
) -> list[BalancePoint]:
    """
    Construct a day-by-day balance trajectory.

    starting_balance is the available balance at start_date BEFORE
    applying events that settle on start_date.

    Example:

        starting balance = 10,000

        March 1:
            salary +20,000
            rent -5,000

        March 1 ending balance:
            25,000
    """

    flows = daily_cashflow(
        events=events,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    points: list[BalancePoint] = []

    balance = Decimal(str(starting_balance))

    current = start_date

    while current <= end_date:

        # Apply all cash movements settling today.
        balance += flows.get(
            current,
            Decimal("0"),
        )

        points.append(
            BalancePoint(
                date=current,
                balance=balance,
            )
        )

        current += timedelta(days=1)

    return points


# ---------------------------------------------------------------------------
# MINIMUM BALANCE
# ---------------------------------------------------------------------------

def minimum_balance(
    trajectory: Iterable[BalancePoint],
) -> Decimal:
    """
    Return the lowest balance in a balance trajectory.
    """

    points = list(trajectory)

    if not points:
        raise ValueError(
            "Cannot calculate minimum balance from empty trajectory"
        )

    return min(
        point.balance
        for point in points
    )


# ---------------------------------------------------------------------------
# FIRST DATE TARGET IS REACHED
# ---------------------------------------------------------------------------

def first_date_balance_reaches(
    trajectory: Iterable[BalancePoint],
    target: Decimal,
) -> date | None:
    """
    Return the first date on which the balance reaches or exceeds target.

    Returns None if the target is never reached.
    """

    target = Decimal(str(target))

    for point in trajectory:

        if point.balance >= target:
            return point.date

    return None