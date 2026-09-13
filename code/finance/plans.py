from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data.models import PaymentMethod, PaymentPlanEntry


@dataclass(frozen=True)
class PlanCandidate:
    method: PaymentMethod
    entries: tuple[PaymentPlanEntry, ...]
    total_amount: Decimal
    start_date: date
    payment_count: int
    option_id: str


def make_candidate(
    method: PaymentMethod,
    entries: tuple[PaymentPlanEntry, ...],
    option_id: str,
    total_amount: Decimal | None = None,
) -> PlanCandidate:
    if not entries:
        raise ValueError("Payment plan cannot be empty.")

    if total_amount is None:
        total_amount = sum(
            entry.amount for entry in entries
        )

    return PlanCandidate(
        method=method,
        entries=entries,
        total_amount=total_amount,
        start_date=entries[0].payment_date,
        payment_count=len(entries),
        option_id=option_id,
    )


def rank_candidates(
    candidates: list[PlanCandidate],
) -> list[PlanCandidate]:
    return sorted(
        candidates,
        key=lambda plan: (
            plan.total_amount,
            plan.start_date,
            plan.payment_count,
            plan.option_id,
        ),
    )
