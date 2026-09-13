from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data.models import FinancialProfile, FinancialRequest, PaymentMethod, PaymentOption

from finance.v3.cashflow_v3 import (
    CashModel,
    apply_spending_changes,
    build_cash_model,
)
from finance.v3.plans_v3 import (
    Plan,
    PlanKind,
    Payment,
    find_earliest_full_payment,
    full_payment_plan,
    installment_plan,
    maximum_safe_today,
    simulate,
    two_payment_plan,
)


@dataclass(frozen=True)
class DecisionV3:
    request_id: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: PaymentMethod
    payment_plan: tuple[Payment, ...]
    earliest_date_for_full_payment: date | None
    spending_changes_needed: tuple[str, ...]
    decision_explanation: str


def _option_allowed(
    profile: FinancialProfile,
    method: str,
) -> bool:
    return method in profile.payment_methods_user_will_consider


def _installment_options(
    options: list[PaymentOption],
    profile: FinancialProfile,
    request: FinancialRequest,
) -> list[PaymentOption]:
    result = []

    for option in options:
        if option.request_id != request.request_id:
            continue

        if not _option_allowed(
            profile,
            option.payment_method,
        ):
            continue

        if option.payment_method != PaymentMethod.INSTALLMENTS.value:
            continue

        if option.first_payment_date < request.request_date:
            continue

        if (
            option.first_payment_date
            > request.desired_completion_date
        ):
            continue

        if profile.max_installment_months is not None:
            if option.payment_frequency_days is not None:
                approx_days = (
                    option.payment_frequency_days
                    * max(option.number_of_payments - 1, 0)
                )
                if approx_days > profile.max_installment_months * 31:
                    continue

        result.append(option)

    return result


def _candidate_partial(
    model: CashModel,
    request: FinancialRequest,
) -> Plan | None:
    safe_today = maximum_safe_today(
        model,
        request.requested_amount,
    )

    if safe_today <= 0:
        return None

    if safe_today >= request.requested_amount:
        return full_payment_plan(
            request.requested_amount,
            request.request_date,
        )

    remaining = request.requested_amount - safe_today

    earliest = find_earliest_full_payment(
        model,
        remaining,
        start_date=request.request_date + __import__("datetime").timedelta(days=1),
        end_date=request.desired_completion_date,
    )

    if earliest is None:
        return None

    return Plan(
        kind=PlanKind.PARTIAL,
        payments=(
            Payment(request.request_date, safe_today),
            Payment(earliest, remaining),
        ),
    )


def _rank_key(plan: Plan) -> tuple:
    priority = {
        PlanKind.FULL: 0,
        PlanKind.PARTIAL: 1,
        PlanKind.INSTALLMENTS: 2,
        PlanKind.WAIT: 3,
        PlanKind.CHANGES: 4,
    }

    latest_payment = max(
        (x.date for x in plan.payments),
        default=date.max,
    )

    return (
        priority[plan.kind],
        latest_payment,
        len(plan.payments),
        plan.total,
    )


def _explanation(
    status: str,
    method: PaymentMethod,
    amount_safe: Decimal,
    model: CashModel,
    changes: tuple[str, ...],
    earliest: date | None,
) -> str:
    currency = ""

    amount_text = f"{amount_safe:.2f}"

    if status == "affordable_now":
        return (
            f"Pay {amount_text} today. "
            f"The projected balance remains above the required minimum."
        )

    if status == "affordable_with_plan":
        if changes:
            return (
                f"Use the recommended payment plan and {', '.join(changes)}. "
                f"The projected balance remains above the required minimum."
            )

        return (
            "Use the recommended payment plan. "
            "All payments remain above the required minimum balance."
        )

    if status == "affordable_later" and earliest is not None:
        return (
            f"Wait until {earliest.isoformat()} to make the full payment. "
            "Paying earlier would risk the required minimum balance."
        )

    return (
        "None of the available payment options keeps the required "
        "minimum balance protected across the forecast."
    )


def decide_v3(
    events,
    profile: FinancialProfile,
    request: FinancialRequest,
    payment_options: list[PaymentOption],
    exchange_rates,
) -> DecisionV3:

    model = build_cash_model(
        events=events,
        profile=profile,
        request=request,
        rates=exchange_rates,
    )

    safe_today = maximum_safe_today(
        model,
        request.requested_amount,
    )

    # 1. Full payment today.
    today_plan = full_payment_plan(
        request.requested_amount,
        request.request_date,
    )

    if (
        _option_allowed(profile, PaymentMethod.FULL_PAYMENT.value)
        and simulate(model, today_plan.payments).safe
    ):
        return DecisionV3(
            request_id=request.request_id,
            amount_safe_to_pay=safe_today,
            affordability_status="affordable_now",
            recommended_payment_method=PaymentMethod.FULL_PAYMENT,
            payment_plan=today_plan.payments,
            earliest_date_for_full_payment=request.request_date,
            spending_changes_needed=(),
            decision_explanation=_explanation(
                "affordable_now",
                PaymentMethod.FULL_PAYMENT,
                safe_today,
                model,
                (),
                request.request_date,
            ),
        )

    candidates: list[tuple[Plan, tuple[str, ...]]] = []

    # 2. Supplied installments.
    for option in _installment_options(
        payment_options,
        profile,
        request,
    ):
        plan = installment_plan(option)

        if not plan.payments:
            continue

        if max(x.date for x in plan.payments) > request.desired_completion_date:
            continue

        if simulate(model, plan.payments).safe:
            candidates.append((plan, ()))

    # 3. Generated two-payment plan.
    if request.allows_partial_payment:
        partial = _candidate_partial(
            model,
            request,
        )

        if partial is not None:
            if (
                max(x.date for x in partial.payments)
                <= request.desired_completion_date
            ):
                if simulate(model, partial.payments).safe:
                    candidates.append((partial, ()))

    # 4. Spending-change plan.
    changed_model, changes = apply_spending_changes(
        model,
        profile,
    )

    if changes:
        if _option_allowed(
            profile,
            PaymentMethod.FULL_PAYMENT.value,
        ):
            changed_full = full_payment_plan(
                request.requested_amount,
                request.request_date,
            )

            if simulate(
                changed_model,
                changed_full.payments,
            ).safe:
                candidates.append(
                    (
                        Plan(
                            kind=PlanKind.CHANGES,
                            payments=changed_full.payments,
                            spending_changes=changes,
                        ),
                        changes,
                    )
                )

    # 5. Pick best complete plan.
    if candidates:
        candidates.sort(
            key=lambda x: _rank_key(x[0])
        )

        plan, changes = candidates[0]

        method = {
            PlanKind.PARTIAL: PaymentMethod.PARTIAL_PAYMENT,
            PlanKind.INSTALLMENTS: PaymentMethod.INSTALLMENTS,
            PlanKind.CHANGES: PaymentMethod.FULL_PAYMENT,
            PlanKind.FULL: PaymentMethod.FULL_PAYMENT,
        }[plan.kind]

        return DecisionV3(
            request_id=request.request_id,
            amount_safe_to_pay=safe_today,
            affordability_status="affordable_with_plan",
            recommended_payment_method=method,
            payment_plan=plan.payments,
            earliest_date_for_full_payment=(
                max(x.date for x in plan.payments)
                if plan.payments
                else None
            ),
            spending_changes_needed=changes,
            decision_explanation=_explanation(
                "affordable_with_plan",
                method,
                safe_today,
                model,
                changes,
                None,
            ),
        )

    # 6. Wait.
    earliest = None

    if _option_allowed(
        profile,
        PaymentMethod.WAIT.value,
    ) or True:
        earliest = find_earliest_full_payment(
            model,
            request.requested_amount,
            start_date=request.request_date,
            end_date=request.desired_completion_date,
        )

    if earliest is not None:
        wait_plan = full_payment_plan(
            request.requested_amount,
            earliest,
        )

        return DecisionV3(
            request_id=request.request_id,
            amount_safe_to_pay=safe_today,
            affordability_status="affordable_later",
            recommended_payment_method=PaymentMethod.WAIT,
            payment_plan=wait_plan.payments,
            earliest_date_for_full_payment=earliest,
            spending_changes_needed=(),
            decision_explanation=_explanation(
                "affordable_later",
                PaymentMethod.WAIT,
                safe_today,
                model,
                (),
                earliest,
            ),
        )

    # 7. Not affordable.
    return DecisionV3(
        request_id=request.request_id,
        amount_safe_to_pay=safe_today,
        affordability_status="not_affordable",
        recommended_payment_method=PaymentMethod.NOT_RECOMMENDED,
        payment_plan=(),
        earliest_date_for_full_payment=None,
        spending_changes_needed=(),
        decision_explanation=_explanation(
            "not_affordable",
            PaymentMethod.NOT_RECOMMENDED,
            safe_today,
            model,
            (),
            None,
        ),
    )
