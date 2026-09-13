from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_dataset
from finance.currency import ExchangeRateTable
from finance.v4.decision_v4 import decide_v4
from agents.gemini import GeminiAgent
from agents.gemini.evidence import extract_evidence
from agents.gemini.evidence_reconciler import reconcile_evidence


load_dotenv()

DATASET = Path("dataset")
CACHE_DIR = Path("runtime_cache")
EVIDENCE_CACHE = CACHE_DIR / "evidence.json"
OUTPUT = DATASET / "output.csv"
USAGE = Path("usage_report.json")


def flatten_values(mapping):
    result = []

    for value in mapping.values():
        if isinstance(value, (list, tuple)):
            result.extend(value)
        else:
            result.append(value)

    return result


def load_cache():
    if not EVIDENCE_CACHE.exists():
        return {}

    try:
        return json.loads(
            EVIDENCE_CACHE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_cache(cache):
    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = EVIDENCE_CACHE.with_suffix(".tmp")

    tmp.write_text(
        json.dumps(
            cache,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(EVIDENCE_CACHE)


def main():

    dataset = load_dataset(DATASET)
    rates = ExchangeRateTable(
        dataset.exchange_rates
    )

    all_messages = flatten_values(
        dataset.messages
    )

    all_images = flatten_values(
        dataset.images
    )

    messages_by_request = defaultdict(list)
    images_by_request = defaultdict(list)

    for message in all_messages:
        if message.request_id:
            messages_by_request[
                message.request_id
            ].append(message)

    for image in all_images:
        if image.request_id:
            images_by_request[
                image.request_id
            ].append(image)

    cache = load_cache()

    usage = {
        "model": os.getenv(
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite",
        ),
        "requests_total": 0,
        "gemini_calls": 0,
        "gemini_cache_hits": 0,
        "gemini_failures": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "facts_extracted": 0,
        "requests_without_unstructured_evidence": 0,
    }

    agent = GeminiAgent()

    rows = []

    requests = dict(dataset.requests)

    for request_id in sorted(requests):

        usage["requests_total"] += 1

        request = requests[request_id]
        profile = dataset.profiles[
            request.user_id
        ]

        request_messages = messages_by_request.get(
            request_id,
            [],
        )

        request_images = images_by_request.get(
            request_id,
            [],
        )

        facts = []

        # -----------------------------------------
        # AI evidence layer
        # -----------------------------------------

        if not request_messages and not request_images:

            usage[
                "requests_without_unstructured_evidence"
            ] += 1

        else:

            cached = cache.get(request_id)

            if cached is not None:

                usage["gemini_cache_hits"] += 1

                facts = cached.get(
                    "facts",
                    [],
                )

            else:

                try:

                    result = extract_evidence(
                        agent=agent,
                        request=request,
                        messages=request_messages,
                        images=request_images,
                        referenced_events=(),
                    )

                    facts = list(result.facts)

                    cache[request_id] = {
                        "facts": facts,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cached_tokens": result.cached_tokens,
                        "attempts": result.attempts,
                    }

                    usage["gemini_calls"] += 1

                    usage["input_tokens"] += (
                        result.input_tokens
                    )

                    usage["output_tokens"] += (
                        result.output_tokens
                    )

                    usage["cached_tokens"] += (
                        result.cached_tokens
                    )

                    usage["facts_extracted"] += (
                        len(facts)
                    )

                except Exception as exc:

                    usage["gemini_failures"] += 1

                    cache[request_id] = {
                        "facts": [],
                        "error": str(exc),
                    }

        # -----------------------------------------
        # Deterministic financial engine
        # -----------------------------------------
        #
        # IMPORTANT:
        # The LLM is intentionally NOT allowed to decide
        # affordability. V4 remains the authority.
        #

        # -----------------------------------------
        # Gemini evidence -> validated temporary events
        # -----------------------------------------
        #
        # Gemini does not decide affordability.
        # It can only contribute high-confidence future evidence.
        # V4 remains the financial decision authority.

        synthetic_events = reconcile_evidence(
            facts=facts,
            profile=profile,
            request=request,
            existing_events=dataset.events,
        )

        if synthetic_events:
            events_for_decision = dict(dataset.events)

            for event in synthetic_events:
                events_for_decision[event.event_id] = event
        else:
            events_for_decision = dataset.events

        decision = decide_v4(
            events=events_for_decision,
            profile=profile,
            request=request,
            payment_options=dataset.payment_options.get(
                request_id,
                [],
            ),
            exchange_rates=rates,
        )

        payment_plan = ";".join(
            (
                f"{p.date.isoformat()}:"
                f"{p.amount}"
            )
            for p in decision.payment_plan
        )

        changes = ";".join(
            decision.spending_changes_needed
        )

        rows.append(
            [
                decision.request_id,
                decision.amount_safe_to_pay,
                decision.affordability_status,
                decision.recommended_payment_method.value,
                payment_plan,
                (
                    decision.earliest_date_for_full_payment.isoformat()
                    if decision.earliest_date_for_full_payment
                    else ""
                ),
                changes,
                decision.decision_explanation,
            ]
        )

        # Save cache periodically so an interrupted run
        # does not lose completed Gemini calls.
        if usage["requests_total"] % 10 == 0:
            save_cache(cache)

            print(
                f"processed={usage['requests_total']}/"
                f"{len(requests)} "
                f"gemini_calls={usage['gemini_calls']} "
                f"cache_hits={usage['gemini_cache_hits']}"
            )

    # ---------------------------------------------
    # Output
    # ---------------------------------------------

    with OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "request_id",
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
                "spending_changes_needed",
                "decision_explanation",
            ]
        )

        writer.writerows(rows)

    save_cache(cache)

    USAGE.write_text(
        json.dumps(
            usage,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=== FINAL RUN COMPLETE ===")
    print("requests:", usage["requests_total"])
    print("gemini calls:", usage["gemini_calls"])
    print("cache hits:", usage["gemini_cache_hits"])
    print("gemini failures:", usage["gemini_failures"])
    print("facts:", usage["facts_extracted"])
    print("input tokens:", usage["input_tokens"])
    print("output tokens:", usage["output_tokens"])
    print("cached tokens:", usage["cached_tokens"])
    print("output:", OUTPUT)
    print("usage:", USAGE)


if __name__ == "__main__":
    main()
