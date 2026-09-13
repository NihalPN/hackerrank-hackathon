from __future__ import annotations

from datetime import date
from decimal import Decimal


def explain(
    *,
    currency: str,
    requested_amount: Decimal,
    safe_amount: Decimal,
    status: str,
    method: str,
    earliest: date | None,
    changes: tuple[str, ...],
) -> str:

    if status == "affordable_now":
        return (
            f"Pay {currency} {requested_amount} today. "
            "The projected balance remains at or above "
            "the required minimum."
        )

    if status == "affordable_later":
        return (
            f"Pay {currency} {requested_amount} in full on "
            f"{earliest}. Paying earlier would put the "
            "required minimum balance at risk."
        )

    if status == "affordable_with_plan":
        if changes:
            return (
                "The request is affordable with the selected "
                "payment plan and the listed spending changes "
                "while preserving the required minimum balance."
            )

        return (
            "The request can be completed safely using the "
            f"recommended {method} plan while preserving "
            "the required minimum balance."
        )

    return (
        f"Do not make this {currency} {requested_amount} request "
        f"under the available options. Although {currency} "
        f"{safe_amount} is available safely today, the full "
        "request cannot be completed within the allowed period "
        "while preserving the required minimum balance."
    )
