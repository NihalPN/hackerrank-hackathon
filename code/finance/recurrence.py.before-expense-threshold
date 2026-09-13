from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from decimal import Decimal
from typing import Literal

from data.models import FinancialEvent


RecurrenceKind = Literal[
    "deterministic_recurring",
    "variable_repeated",
    "irregular",
]


@dataclass(frozen=True)
class RecurrenceAnalysis:
    kind: RecurrenceKind
    interval_days: int | None
    interval_variation: float
    amount_variation: float
    observations: int


def _intervals(events: list[FinancialEvent]) -> list[int]:
    dates = sorted(
        {event.event_date for event in events}
    )

    return [
        (dates[i] - dates[i - 1]).days
        for i in range(1, len(dates))
    ]


def _interval_variation(intervals: list[int]) -> float:
    if not intervals:
        return 1.0

    typical = float(median(intervals))

    if typical <= 0:
        return 1.0

    return max(
        abs(value - typical) / typical
        for value in intervals
    )


def _amount_variation(events: list[FinancialEvent]) -> float:
    amounts = [
        float(event.amount)
        for event in events
        if event.amount is not None
        and event.amount > 0
    ]

    if len(amounts) < 2:
        return 0.0

    maximum = max(amounts)

    if maximum <= 0:
        return 1.0

    return (max(amounts) - min(amounts)) / maximum


def analyse_recurrence(
    events: list[FinancialEvent],
) -> RecurrenceAnalysis:

    if len(events) < 3:
        return RecurrenceAnalysis(
            kind="irregular",
            interval_days=None,
            interval_variation=1.0,
            amount_variation=1.0,
            observations=len(events),
        )

    intervals = _intervals(events)

    if not intervals:
        return RecurrenceAnalysis(
            kind="irregular",
            interval_days=None,
            interval_variation=1.0,
            amount_variation=1.0,
            observations=len(events),
        )

    typical = int(round(median(intervals)))
    interval_variation = _interval_variation(intervals)
    amount_variation = _amount_variation(events)

    event_type = events[0].event_type
    direction = events[0].direction.value

    # --------------------------------------------------------
    # Deterministic income needs strong evidence.
    #
    # This is deliberately stricter because future income
    # materially changes affordability.
    # --------------------------------------------------------

    if direction == "credit" or event_type == "income":
        if (
            interval_variation <= 0.10
            and amount_variation <= 0.10
        ):
            return RecurrenceAnalysis(
                kind="deterministic_recurring",
                interval_days=typical,
                interval_variation=interval_variation,
                amount_variation=amount_variation,
                observations=len(events),
            )

        if (
            interval_variation <= 0.35
            and amount_variation <= 0.30
        ):
            return RecurrenceAnalysis(
                kind="variable_repeated",
                interval_days=typical,
                interval_variation=interval_variation,
                amount_variation=amount_variation,
                observations=len(events),
            )

        return RecurrenceAnalysis(
            kind="irregular",
            interval_days=None,
            interval_variation=interval_variation,
            amount_variation=amount_variation,
            observations=len(events),
        )

    # --------------------------------------------------------
    # Expense streams can tolerate more amount variation.
    # We distinguish stable recurring obligations from repeated
    # variable spending.
    # --------------------------------------------------------

    if (
        interval_variation <= 0.15
        and amount_variation <= 0.25
    ):
        return RecurrenceAnalysis(
            kind="deterministic_recurring",
            interval_days=typical,
            interval_variation=interval_variation,
            amount_variation=amount_variation,
            observations=len(events),
        )

    if (
        interval_variation <= 0.50
        and amount_variation <= 0.40
    ):
        return RecurrenceAnalysis(
            kind="variable_repeated",
            interval_days=typical,
            interval_variation=interval_variation,
            amount_variation=amount_variation,
            observations=len(events),
        )

    return RecurrenceAnalysis(
        kind="irregular",
        interval_days=None,
        interval_variation=interval_variation,
        amount_variation=amount_variation,
        observations=len(events),
    )
