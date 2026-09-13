from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AgentResult:
    facts: tuple[dict, ...]
    source: str
    fallback_reason: str = ""


def gemini_result(
    facts: Iterable[dict],
) -> AgentResult:
    return AgentResult(
        facts=tuple(facts),
        source="gemini",
    )


def deterministic_fallback(
    reason: str,
) -> AgentResult:
    return AgentResult(
        facts=(),
        source="deterministic_fallback",
        fallback_reason=reason,
    )
