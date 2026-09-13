from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_dataset
from finance.currency import ExchangeRateTable
from agents.gemini import GeminiAgent
from agents.gemini.evidence import extract_evidence


def flatten_values(mapping):
    out = []

    for value in mapping.values():
        if isinstance(value, (list, tuple)):
            out.extend(value)
        else:
            out.append(value)

    return out


def main():
    if not (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    ):
        raise SystemExit("Gemini API key missing.")

    dataset = load_dataset(Path("dataset"))

    # Use one real production request.
    request_id = "request_26"
    request = dataset.requests[request_id]
    profile = dataset.profiles[request.user_id]

    messages = [
        m
        for m in flatten_values(dataset.messages)
        if m.user_id == request.user_id
        and (
            m.request_id == request.request_id
            or m.request_id is None
        )
    ]

    images = [
        i
        for i in flatten_values(dataset.images)
        if i.user_id == request.user_id
        and (
            i.request_id == request.request_id
            or i.request_id is None
        )
    ]

    # Only events explicitly referenced by the unstructured evidence.
    referenced_ids = {
        x.related_event_id
        for x in messages
        if x.related_event_id
    } | {
        x.related_event_id
        for x in images
        if x.related_event_id
    }

    referenced_events = [
        dataset.events[event_id]
        for event_id in referenced_ids
        if event_id in dataset.events
    ]

    print("request:", request_id)
    print("messages:", len(messages))
    print("images:", len(images))
    print("referenced events:", len(referenced_events))

    if not messages and not images:
        print("No unstructured evidence -> Gemini call skipped.")
        return

    agent = GeminiAgent()

    result = extract_evidence(
        agent=agent,
        request=request,
        messages=messages,
        images=images,
        referenced_events=referenced_events,
    )

    print("MODEL:", agent.model)
    print("ATTEMPTS:", result.attempts)
    print("INPUT TOKENS:", result.input_tokens)
    print("OUTPUT TOKENS:", result.output_tokens)
    print("CACHED TOKENS:", result.cached_tokens)
    print("FACTS:", len(result.facts))

    for fact in result.facts:
        print(fact)


if __name__ == "__main__":
    main()
