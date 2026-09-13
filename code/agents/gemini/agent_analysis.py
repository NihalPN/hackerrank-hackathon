from __future__ import annotations

from collections import Counter
from pathlib import Path
import json


def analyze_cache(cache_path: str | Path) -> dict:
    path = Path(cache_path)

    if not path.exists():
        return {
            "status": "missing_cache",
            "requests_with_evidence": 0,
            "facts_extracted": 0,
            "fact_types": {},
            "uncertainty_requests": 0,
        }

    data = json.loads(path.read_text(encoding="utf-8"))

    requests_with_evidence = 0
    facts_extracted = 0
    fact_types: Counter[str] = Counter()
    failures = 0
    uncertainty_requests = 0

    for request_id, record in data.items():
        facts = record.get("facts", []) or []

        if facts:
            requests_with_evidence += 1
            facts_extracted += len(facts)

        for fact in facts:
            fact_type = str(
                fact.get("fact_type", "unknown")
            ).strip().lower() or "unknown"
            fact_types[fact_type] += 1

        if record.get("error"):
            failures += 1

    return {
        "status": "ok",
        "cached_requests": len(data),
        "requests_with_evidence": requests_with_evidence,
        "facts_extracted": facts_extracted,
        "fact_types": dict(fact_types.most_common()),
        "gemini_failures": failures,
        "uncertainty_requests": uncertainty_requests,
    }
