from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DecisionResult:
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: tuple[tuple[date, Decimal], ...]
    earliest_date_for_full_payment: date | None
    spending_changes_needed: tuple[str, ...]
    decision_explanation: str
