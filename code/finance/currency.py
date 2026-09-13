from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal


class ExchangeRateTable:
    def __init__(self, rates: list[ExchangeRate]):
        self._rates = {
            (
                rate.rate_date,
                rate.from_currency,
                rate.to_currency,
            ): rate.rate
            for rate in rates
        }

    def get(
        self,
        rate_date: date,
        from_currency: str,
        to_currency: str,
    ) -> Decimal:
        if from_currency == to_currency:
            return Decimal("1")

        key = (
            rate_date,
            from_currency,
            to_currency,
        )

        if key not in self._rates:
            raise ValueError(
                f"Missing exchange rate: "
                f"{rate_date} {from_currency}->{to_currency}"
            )

        return self._rates[key]

    def latest_on_or_before(
        self,
        rate_date: date,
        from_currency: str,
        to_currency: str,
    ) -> Decimal:
        if from_currency == to_currency:
            return Decimal("1")

        available = [
            (d, value)
            for (d, src, dst), value in self._rates.items()
            if src == from_currency
            and dst == to_currency
            and d <= rate_date
        ]

        if not available:
            raise ValueError(
                f"Missing exchange rate: "
                f"{rate_date} {from_currency}->{to_currency}"
            )

        _, value = max(available, key=lambda item: item[0])
        return value

    def convert(
        self,
        amount: Decimal,
        rate_date: date,
        from_currency: str,
        to_currency: str,
    ) -> Decimal:
        return amount * self.get(
            rate_date,
            from_currency,
            to_currency,
        )
