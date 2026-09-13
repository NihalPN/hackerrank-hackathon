from __future__ import annotations

from pathlib import Path
from typing import Iterable

from data.models import (
    FinancialEvent,
    FinancialProfile,
    FinancialRequest,
    ImageRecord,
    MessageRecord,
)

from .client import GeminiAgent, GeminiResult


SYSTEM_RULES = """
You are a financial evidence extraction component.

Extract ONLY factual claims explicitly supported by the supplied request,
messages, or images.

Never decide affordability, payment method, safe amount, or financial risk.

Never invent missing facts.

Return at most 6 concise facts.
"""


def _event_summary(event: FinancialEvent) -> str:
    return (
        f"{event.event_id}: "
        f"{event.event_date} | "
        f"{event.status.value} | "
        f"{event.direction.value} | "
        f"{event.amount} {event.currency} | "
        f"{event.category} | "
        f"{event.description}"
    )


def build_prompt(
    request: FinancialRequest,
    messages: Iterable[MessageRecord],
    events: Iterable[FinancialEvent] = (),
) -> str:

    message_text = "\n".join(
        (
            f"{m.message_id} | "
            f"request={m.request_id} | "
            f"event={m.related_event_id} | "
            f"{m.message_text}"
        )
        for m in messages
    )

    event_text = "\n".join(
        _event_summary(e)
        for e in events
    )

    return f"""
{SYSTEM_RULES}

REQUEST
id: {request.request_id}
type: {request.request_type}
amount: {request.requested_amount}
deadline: {request.desired_completion_date}
text: {request.request_text}

MESSAGES
{message_text or "<none>"}

REFERENCED EVENTS
{event_text or "<none>"}
""".strip()


def extract_evidence(
    agent: GeminiAgent,
    request: FinancialRequest,
    messages: Iterable[MessageRecord],
    images: Iterable[ImageRecord],
    referenced_events: Iterable[FinancialEvent] = (),
) -> GeminiResult:

    messages = list(messages)
    images = list(images)
    referenced_events = list(referenced_events)

    # Nothing unstructured to interpret.
    if not messages and not images:
        from .client import GeminiResult

        return GeminiResult(
            facts=(),
            input_tokens=0,
            output_tokens=0,
            cached_tokens=0,
            attempts=0,
        )

    prompt = build_prompt(
        request=request,
        messages=messages,
        events=referenced_events,
    )

    image_paths = [
        Path(i.file_path)
        for i in images
        if Path(i.file_path).exists()
    ]

    return agent.extract(
        prompt=prompt,
        images=image_paths,
    )
