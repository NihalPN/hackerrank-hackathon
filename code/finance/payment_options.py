from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from data.models import FinancialProfile, PaymentMethod, PaymentOption


@dataclass(frozen=True)
class PaymentPlan:
    option_id: str
    method: PaymentMethod
    entries: tuple[tuple[date, Decimal], ...]
    total_amount: Decimal

    @property
    def first_payment_date(self) -> date:
        return self.entries[0][0]

    @property
    def last_payment_date(self) -> date:
        return self.entries[-1][0]

    @property
    def number_of_payments(self) -> int:
        return len(self.entries)


def plan_entries(
    option: PaymentOption,
) -> tuple[tuple[date, Decimal], ...]:

    entries = []

    for index in range(option.number_of_payments):

        if option.payment_frequency_days is None:
            payment_date = option.first_payment_date
        else:
            payment_date = (
                option.first_payment_date
                + timedelta(
                    days=option.payment_frequency_days * index
                )
            )

        entries.append(
            (
                payment_date,
                option.payment_amount,
            )
        )

    return tuple(entries)


def build_plan(option: PaymentOption) -> PaymentPlan:
    entries = plan_entries(option)

    return PaymentPlan(
        option_id=option.payment_option_id,
        method=PaymentMethod(option.payment_method),
        entries=entries,
        total_amount=sum(
            amount for _, amount in entries
        ),
    )


def valid_option(
    profile: FinancialProfile,
    option: PaymentOption,
    deadline: date,
) -> bool:

    entries = plan_entries(option)

    if not entries:
        return False

    if option.payment_method not in {
        "full_payment",
        "installments",
    }:
        return False

    if option.payment_method not in (
        profile.payment_methods_user_will_consider
    ):
        return False

    if entries[0][0] is None:
        return False

    if entries[0][0] < deadline.replace(
        year=deadline.year - 100
    ):
        return False

    if entries[-1][0] > deadline:
        return False

    if (
        option.payment_method == "installments"
        and profile.max_installment_months is not None
        and option.payment_frequency_days is not None
    ):
        total_days = (
            option.payment_frequency_days
            * max(option.number_of_payments - 1, 0)
        )

        months = (total_days + 29) // 30

        if months > profile.max_installment_months:
            return False

    return True


def eligible_plans(
    profile: FinancialProfile,
    options: list[PaymentOption],
    deadline: date,
) -> tuple[PaymentPlan, ...]:

    plans = []

    for option in options:

        if not valid_option(
            profile,
            option,
            deadline,
        ):
            continue

        plans.append(
            build_plan(option)
        )

    return tuple(plans)


def rank_plans(
    plans: tuple[PaymentPlan, ...],
) -> tuple[PaymentPlan, ...]:

    return tuple(
        sorted(
            plans,
            key=lambda plan: (
                plan.total_amount,
                plan.first_payment_date,
                plan.number_of_payments,
                plan.option_id,
            ),
        )
    )
