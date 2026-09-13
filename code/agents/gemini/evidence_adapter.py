from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable

from data.models import FinancialProfile
from finance.v4.cashflow_v4 import Flow


AMOUNT_RE = re.compile(
    r"(?:IDR|INR|ZAR|USD|EUR|GBP|AUD|CAD)?\s*"
    r"([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"\b(20\d{2})-(\d{2})-(\d{2})\b"
)

CURRENCIES = {
    "IDR",
    "INR",
    "ZAR",
    "USD",
    "EUR",
    "GBP",
    "AUD",
    "CAD",
}

INCOME_TERMS = (
    "salary",
    "payroll",
    "invoice payment",
    "payment approved",
    "client payment",
    "employer payment",
    "refund",
    "reimbursement",
    "money received",
    "received payment",
    "credit",
)

EXPENSE_TERMS = (
    "purchase",
    "transfer",
    "rent",
    "bill",
    "payment due",
    "payment to",
    "fee",
    "expense",
    "debit",
)


@dataclass(frozen=True)
class ParsedGroup:
    group_id: str
    amount: Decimal | None
    currency: str | None
    event_date: date | None
    description: str
    confidence: float


def _parse_amount(text: str):
    match = AMOUNT_RE.search(text or "")

    if not match:
        return None

    try:
        amount = Decimal(
            match.group(1).replace(",", "")
        )
    except InvalidOperation:
        return None

    upper = (text or "").upper()

    currency = next(
        (
            c for c in CURRENCIES
            if c in upper
        ),
        None,
    )

    return amount, currency


def _parse_date(text: str):
    match = DATE_RE.search(text or "")

    if not match:
        return None

    try:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
    except ValueError:
        return None


def _fact_type(fact: dict) -> str:
    return str(
        fact.get("fact_type", "")
    ).lower().strip()


def _fact_text(fact: dict) -> str:
    return " ".join(
        str(fact.get(k, "") or "")
        for k in (
            "fact_type",
            "value",
            "evidence_text",
        )
    ).lower()


def _group_facts(
    facts: Iterable[dict],
) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}

    for fact in facts:
        if float(
            fact.get("confidence", 0) or 0
        ) < 0.90:
            continue

        group_id = str(
            fact.get("related_event_id", "")
            or "ungrouped"
        )

        groups.setdefault(
            group_id,
            [],
        ).append(fact)

    return groups


def _infer_direction(
    group: list[dict],
) -> str | None:

    types = {
        _fact_type(f)
        for f in group
    }

    if "income" in types or "refund" in types:
        return "credit"

    if "expense" in types or "payment" in types:
        return "debit"

    text = " ".join(
        _fact_text(f)
        for f in group
    )

    if any(
        term in text
        for term in INCOME_TERMS
    ):
        return "credit"

    if any(
        term in text
        for term in EXPENSE_TERMS
    ):
        return "debit"

    return None


def _parse_group(
    group_id: str,
    group: list[dict],
) -> ParsedGroup:

    amount = None
    currency = None
    event_date = None
    confidence = 0.0
    descriptions = []

    for fact in group:
        confidence = max(
            confidence,
            float(
                fact.get(
                    "confidence",
                    0,
                )
                or 0
            ),
        )

        value = str(
            fact.get("value", "")
            or ""
        )

        evidence = str(
            fact.get("evidence_text", "")
            or ""
        )

        parsed_amount = (
            _parse_amount(value)
            or _parse_amount(evidence)
        )

        if parsed_amount and amount is None:
            amount, currency = parsed_amount

        parsed_date = (
            _parse_date(value)
            or _parse_date(evidence)
        )

        if parsed_date is not None:
            event_date = parsed_date

        if _fact_type(fact) in {
            "description",
            "status",
            "income",
            "expense",
            "payment",
            "refund",
        }:
            descriptions.append(value)

    return ParsedGroup(
        group_id=group_id,
        amount=amount,
        currency=currency,
        event_date=event_date,
        description=" ".join(descriptions),
        confidence=confidence,
    )


def facts_to_flows(
    facts: Iterable[dict],
    profile: FinancialProfile,
    request_date: date,
    horizon_end: date,
    request_id: str | None = None,
) -> tuple[Flow, ...]:

    groups = _group_facts(facts)

    result: list[Flow] = []

    for group_id, group in groups.items():

        # The request itself is not a future cash event.
        if request_id and group_id == request_id:
            continue

        parsed = _parse_group(
            group_id,
            group,
        )

        if (
            parsed.amount is None
            or parsed.event_date is None
        ):
            continue

        if not (
            request_date
            <= parsed.event_date
            <= horizon_end
        ):
            continue

        if parsed.amount <= 0:
            continue

        if parsed.currency not in (
            None,
            profile.home_currency,
        ):
            continue

        direction = _infer_direction(group)

        # Critical safety rule:
        # an amount + date without semantic direction
        # is NEVER turned into a cash flow.
        if direction is None:
            continue

        delta = (
            parsed.amount
            if direction == "credit"
            else -parsed.amount
        )

        result.append(
            Flow(
                date=parsed.event_date,
                amount=delta,
                category=(
                    "evidence_income"
                    if direction == "credit"
                    else "evidence_expense"
                ),
                direction=direction,
                event_id=(
                    group_id
                    if group_id != "ungrouped"
                    else None
                ),
                source="gemini_evidence",
                flexibility="fixed",
                minimum_allowed_amount=None,
                required=(
                    direction == "debit"
                ),
            )
        )

    # Exact deduplication.
    unique = {}

    for flow in result:
        unique[
            (
                flow.date,
                flow.amount,
                flow.direction,
                flow.event_id,
            )
        ] = flow

    return tuple(unique.values())
