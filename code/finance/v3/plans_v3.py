from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from data.models import PaymentMethod, PaymentOption

from finance.v3.cashflow_v3 import CashModel


class PlanKind(str, Enum):
    FULL = "full_payment"
    PARTIAL = "partial_payment"
    INSTALLMENTS = "installments"
    WAIT = "wait"
    CHANGES = "spending_changes"


@dataclass(frozen=True)
class Payment:
    date: date
    amount: Decimal


@dataclass(frozen=True)
class Plan:
    kind: PlanKind
    payments: tuple[Payment, ...]
    spending_changes: tuple[str, ...] = ()
    note: str = ""

    @property
    def total(self) -> Decimal:
        return sum(
            (x.amount for x in self.payments),
            Decimal("0"),
        )


@dataclass(frozen=True)
class Simulation:
    safe: bool
    minimum_seen: Decimal
    minimum_date: date
    ending_balance: Decimal


def simulate(
    model: CashModel,
    payments: tuple[Payment, ...],
    spending_changes: tuple[str, ...] = (),
) -> Simulation:
    payment_by_date: dict[date, Decimal] = {}

    for payment in payments:
        payment_by_date[payment.date] = (
            payment_by_date.get(payment.date, Decimal("0"))
            + payment.amount
        )

    flow_dates = {x.date for x in model.flows}
    payment_dates = set(payment_by_date)
    all_dates = sorted(
        flow_dates | payment_dates | {model.as_of}
    )

    balance = model.starting_balance
    minimum_seen = balance
    minimum_date = model.as_of

    for current_date in all_dates:
        daily = [
            x
            for x in model.flows
            if x.date == current_date
        ]

        # Debits first, then credits.
        for flow in sorted(
            daily,
            key=lambda x: (
                0 if x.amount < 0 else 1,
                x.event_id or "",
            ),
        ):
            balance += flow.amount

            if balance < minimum_seen:
                minimum_seen = balance
                minimum_date = current_date

        payment = payment_by_date.get(
            current_date,
            Decimal("0"),
        )

        if payment:
            balance -= payment

            if balance < minimum_seen:
                minimum_seen = balance
                minimum_date = current_date

    return Simulation(
        safe=minimum_seen >= model.minimum_balance,
        minimum_seen=minimum_seen,
        minimum_date=minimum_date,
        ending_balance=balance,
    )


def full_payment_plan(
    amount: Decimal,
    payment_date: date,
) -> Plan:
    return Plan(
        kind=PlanKind.FULL,
        payments=(
            Payment(payment_date, amount),
        ),
    )


def installment_plan(
    option: PaymentOption,
) -> Plan:
    payments = []

    for i in range(option.number_of_payments):
        if option.payment_frequency_days is None:
            dt = option.first_payment_date
        else:
            dt = option.first_payment_date + timedelta(
                days=option.payment_frequency_days * i
            )

        payments.append(
            Payment(
                dt,
                option.payment_amount,
            )
        )

    return Plan(
        kind=PlanKind.INSTALLMENTS,
        payments=tuple(payments),
    )


def two_payment_plan(
    first_amount: Decimal,
    second_date: date,
    total_amount: Decimal,
) -> Plan | None:
    second_amount = total_amount - first_amount

    if first_amount <= 0 or second_amount <= 0:
        return None

    return Plan(
        kind=PlanKind.PARTIAL,
        payments=(
            Payment(
                second_date,
                second_amount,
            ),
        ),
    )


def find_earliest_full_payment(
    model: CashModel,
    requested_amount: Decimal,
    start_date: date | None = None,
    end_date: date | None = None,
) -> date | None:
    start = start_date or model.as_of
    end = end_date or model.horizon_end

    current = start

    while current <= end:
        plan = full_payment_plan(
            requested_amount,
            current,
        )

        result = simulate(
            model,
            plan.payments,
        )

        if result.safe:
            return current

        current += timedelta(days=1)

    return None


def maximum_safe_today(
    model: CashModel,
    requested_amount: Decimal,
) -> Decimal:
    """
    Monotone binary search. The simulator is deterministic, so the maximum
    safe payment can be found without a statistical estimate.
    """

    if requested_amount <= 0:
        return Decimal("0")

    low = Decimal("0")
    high = requested_amount

    cents = Decimal("0.01")

    for _ in range(80):
        mid = ((low + high) / 2).quantize(cents)

        if mid <= low:
            break

        result = simulate(
            model,
            (
                Payment(model.as_of, mid),
            ),
        )

        if result.safe:
            low = mid
        else:
            high = mid

    return low
