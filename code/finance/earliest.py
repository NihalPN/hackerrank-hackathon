from __future__ import annotations

from datetime import date

from finance.forecast import Forecast
from finance.safety import earliest_safe_payment_date


def earliest_full_payment_date(
    forecast: Forecast,
    minimum_balance,
    requested_amount,
    request_date: date,
    deadline: date,
):
    return earliest_safe_payment_date(
        forecast=forecast,
        minimum_balance=minimum_balance,
        amount=requested_amount,
        start_date=request_date,
        end_date=min(deadline, forecast.end_date),
    )
