from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from data.models import FinancialEvent, FinancialProfile
from finance.forecast import Forecast

ZERO = Decimal("0")


def apply_spending_changes(
    forecast: Forecast,
    profile: FinancialProfile,
    events: dict[str, FinancialEvent],
    required_reduction: Decimal,
) -> tuple[Forecast, tuple[str, ...]] | None:

    if required_reduction <= ZERO:
        return forecast, ()

    candidates = []

    for flow in forecast.flows:

        if flow.event_id is None:
            continue

        if flow.amount >= ZERO:
            continue

        event = events.get(flow.event_id)

        if event is None:
            continue

        can_stop = (
            event.category in profile.stoppable_categories
            and event.flexibility in {
                "stoppable",
                "reducible_or_stoppable",
            }
        )

        can_reduce = (
            event.category in profile.reducible_categories
            and event.flexibility in {
                "reducible",
                "reducible_or_stoppable",
            }
        )

        if not can_stop and not can_reduce:
            continue

        current_amount = abs(flow.amount)

        minimum = event.minimum_allowed_amount or ZERO

        if can_stop:
            maximum_reduction = current_amount
        else:
            maximum_reduction = max(
                ZERO,
                current_amount - minimum,
            )

        if maximum_reduction <= ZERO:
            continue

        candidates.append(
            (
                maximum_reduction,
                flow,
                event,
                can_stop,
                can_reduce,
            )
        )

    candidates.sort(
        key=lambda item: (
            -item[0],
            item[1].flow_date,
            item[1].event_id or "",
        )
    )

    remaining = required_reduction
    changes: list[str] = []
    new_flows = list(forecast.flows)

    for (
        maximum_reduction,
        flow,
        event,
        can_stop,
        can_reduce,
    ) in candidates:

        if remaining <= ZERO:
            break

        current_amount = abs(flow.amount)
        reduction = min(
            remaining,
            maximum_reduction,
        )

        if can_stop and reduction >= current_amount:
            replacement = replace(
                flow,
                amount=ZERO,
            )

            actual_reduction = current_amount
            action = f"stop:{flow.event_id}"

        elif can_reduce:
            new_amount = current_amount - reduction

            minimum = event.minimum_allowed_amount

            if minimum is not None:
                new_amount = max(
                    new_amount,
                    minimum,
                )

            actual_reduction = current_amount - new_amount

            if actual_reduction <= ZERO:
                continue

            replacement = replace(
                flow,
                amount=-new_amount,
            )

            action = (
                f"reduce_to:{flow.event_id}:{new_amount}"
            )

        else:
            continue

        index = new_flows.index(flow)
        new_flows[index] = replacement

        changes.append(action)
        remaining -= actual_reduction

        if len(changes) >= 3:
            break

    if remaining > ZERO:
        return None

    changed_forecast = Forecast(
        start_date=forecast.start_date,
        end_date=forecast.end_date,
        starting_balance=forecast.starting_balance,
        flows=tuple(
            sorted(
                new_flows,
                key=lambda flow: (
                    flow.flow_date,
                    flow.event_id or "",
                ),
            )
        ),
    )

    return changed_forecast, tuple(changes)
