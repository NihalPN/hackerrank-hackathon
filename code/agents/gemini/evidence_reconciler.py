from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from data.models import (
    EventDirection,
    EventStatus,
    FinancialEvent,
    FinancialProfile,
    FinancialRequest,
)

from .evidence_adapter import facts_to_flows


def reconcile_evidence(
    facts: Iterable[dict],
    profile: FinancialProfile,
    request: FinancialRequest,
    existing_events: dict[str, FinancialEvent],
    rates=None,
) -> tuple[FinancialEvent, ...]:
    """
    Turn high-confidence Gemini evidence into temporary FinancialEvents.

    Safety rules:
      - Gemini never changes an existing event.
      - Gemini cannot overwrite profile state.
      - Evidence must produce a parseable future flow.
      - If an equivalent confirmed event already exists, skip the synthetic one.
    """

    horizon_end = request.request_date.fromordinal(
        request.request_date.toordinal() + 90
    )

    flows = facts_to_flows(
        facts=facts,
        profile=profile,
        request_date=request.request_date,
        horizon_end=horizon_end,
        request_id=request.request_id,
    )

    synthetic: list[FinancialEvent] = []

    existing = list(existing_events.values())

    for index, flow in enumerate(flows, start=1):

        # Never create duplicates of known future events.
        duplicate = False

        for event in existing:
            if event.user_id != profile.user_id:
                continue

            if event.amount is None:
                continue

            event_date = (
                event.settlement_date
                or event.event_date
            )

            if event_date != flow.date:
                continue

            if event.direction.value != flow.direction:
                continue

            # Evidence is already normalized to home currency.
            if event.currency != profile.home_currency:
                continue

            if abs(event.amount - abs(flow.amount)) <= Decimal("0.01"):
                duplicate = True
                break

        if duplicate:
            continue

        if flow.direction == "credit":
            direction = EventDirection.CREDIT
            event_type = "income"
            status = EventStatus.SCHEDULED
        else:
            direction = EventDirection.DEBIT
            event_type = "expense"
            status = EventStatus.SCHEDULED

        synthetic_id = (
            f"evidence_{request.request_id}_{index}"
        )

        synthetic.append(
            FinancialEvent(
                event_id=synthetic_id,
                user_id=profile.user_id,
                event_type=event_type,
                description="Gemini-supported financial evidence",
                category=flow.category,
                direction=direction,
                amount=abs(flow.amount),
                currency=profile.home_currency,
                event_date=flow.date,
                settlement_date=flow.date,
                status=status,
                linked_event_id=flow.event_id,
                flexibility="fixed",
                minimum_allowed_amount=None,
            )
        )

    return tuple(synthetic)
