from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from finance.forecast import Forecast, simulate_payment

ZERO = Decimal("0")


def plan_is_safe(
    forecast: Forecast,
    minimum_balance: Decimal,
    payments: list[tuple[date, Decimal]],
) -> bool:
    if any(amount < ZERO for _, amount in payments):
        raise ValueError("Payment amounts cannot be negative.")

    simulated = simulate_payment(forecast, payments)

    return simulated.minimum_balance() >= minimum_balance


def safe_amount_today(
    forecast: Forecast,
    minimum_balance: Decimal,
    requested_amount: Decimal,
) -> Decimal:
    if requested_amount <= ZERO:
        return ZERO

    cushion = forecast.minimum_balance() - minimum_balance

    if cushion <= ZERO:
        return ZERO

    return min(cushion, requested_amount)


def earliest_safe_payment_date(
    forecast: Forecast,
    minimum_balance: Decimal,
    amount: Decimal,
    start_date: date,
    end_date: date,
) -> date | None:
    if amount <= ZERO:
        return start_date

    current = start_date

    while current <= end_date:
        if plan_is_safe(
            forecast,
            minimum_balance,
            [(current, amount)],
        ):
            return current

        current += timedelta(days=1)

    return None
