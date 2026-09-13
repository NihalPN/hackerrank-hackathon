from __future__ import annotations

from pathlib import Path
import json


def build_report(
    cache_path: str | Path,
    output_path: str | Path,
) -> dict:
    cache_path = Path(cache_path)
    output_path = Path(output_path)

    cache = json.loads(
        cache_path.read_text(encoding="utf-8")
    ) if cache_path.exists() else {}

    evidence_requests = 0
    facts = 0
    failures = 0
    linked_events = 0

    fact_types = {}

    for request_id, record in cache.items():
        request_facts = record.get("facts", []) or []

        if request_facts:
            evidence_requests += 1
            facts += len(request_facts)

        if record.get("error"):
            failures += 1

        for fact in request_facts:
            fact_type = str(
                fact.get("fact_type", "unknown")
            ).strip().lower() or "unknown"

            fact_types[fact_type] = (
                fact_types.get(fact_type, 0) + 1
            )

            if fact.get("related_event_id"):
                linked_events += 1

    report = {
        "agent_architecture": {
            "model_role": "evidence extraction and contextual interpretation",
            "financial_authority": "deterministic V4 financial engine",
            "llm_can_modify_existing_events": False,
            "llm_can_override_affordability": False,
            "evidence_reconciled_into_temporary_events": True,
        },
        "evidence_processing": {
            "requests_cached": len(cache),
            "requests_with_evidence": evidence_requests,
            "facts_extracted": facts,
            "facts_linked_to_events": linked_events,
            "gemini_failures": failures,
            "fact_types": dict(
                sorted(
                    fact_types.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
        },
        "output": {
            "path": str(output_path),
            "financial_decision_source": "V4 deterministic engine",
        },
    }

    Path("agent_analysis_report.json").write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return report
