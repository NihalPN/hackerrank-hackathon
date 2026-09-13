from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from data.models import FinancialEvent
from finance.currency import ExchangeRateTable


ZERO = Decimal("0")


@dataclass(frozen=True)
class VariableCategoryEstimate:
    category: str
    historical_amount: Decimal
    daily_burn: Decimal
    observations: int
    projected_amount: Decimal


def estimate_variable_category(
    events: dict[str, FinancialEvent],
    user_id: str,
    category: str,
    start_date: date,
    end_date: date,
    home_currency: str,
    rates: ExchangeRateTable,
    lookback_days: int = 90,
) -> VariableCategoryEstimate | None:

    history_start = start_date - timedelta(days=lookback_days)

    total = ZERO
    observations = 0

    for event in events.values():

        if event.user_id != user_id:
            continue

        if event.category != category:
            continue

        if event.direction.value != "debit":
            continue

        if event.amount is None:
            continue

        if not (
            history_start
            <= event.event_date
            < start_date
        ):
            continue

        if event.status.value in {
            "failed",
            "cancelled",
            "unrealized",
        }:
            continue

        if event.currency == home_currency:
            converted = event.amount
        else:
            try:
                converted = rates.convert(
                    event.amount,
                    event.event_date,
                    event.currency,
                    home_currency,
                )
            except ValueError:
                converted = (
                    event.amount
                    * rates.latest_on_or_before(
                        event.event_date,
                        event.currency,
                        home_currency,
                    )
                )

        total += converted
        observations += 1

    if observations < 3:
        return None

    daily_burn = total / Decimal(str(lookback_days))

    horizon_days = (
        end_date - start_date
    ).days

    projected = (
        daily_burn
        * Decimal(str(horizon_days))
    )

    return VariableCategoryEstimate(
        category=category,
        historical_amount=total,
        daily_burn=daily_burn,
        observations=observations,
        projected_amount=projected,
    )


def variable_categories(
    events: dict[str, FinancialEvent],
    user_id: str,
    start_date: date,
    lookback_days: int = 90,
) -> set[str]:

    start = start_date - timedelta(days=lookback_days)

    categories: set[str] = set()

    for event in events.values():
        if event.user_id != user_id:
            continue

        if event.direction.value != "debit":
            continue

        if event.amount is None:
            continue

        if not (
            start
            <= event.event_date
            < start_date
        ):
            continue

        if event.status.value in {
            "failed",
            "cancelled",
            "unrealized",
        }:
            continue

        categories.add(event.category)

    return categories
