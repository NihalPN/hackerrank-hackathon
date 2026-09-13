from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRuntimePolicy:
    max_requests_per_minute: int = 12
    max_requests_per_day: int = 450
    max_concurrent_requests: int = 2
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass
class AgentRuntimeStats:
    total_requests: int = 0
    gemini_attempts: int = 0
    gemini_successes: int = 0
    gemini_failures: int = 0
    quota_failures: int = 0
    cache_hits: int = 0
    deterministic_fallbacks: int = 0

    def as_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "gemini_attempts": self.gemini_attempts,
            "gemini_successes": self.gemini_successes,
            "gemini_failures": self.gemini_failures,
            "quota_failures": self.quota_failures,
            "cache_hits": self.cache_hits,
            "deterministic_fallbacks": self.deterministic_fallbacks,
        }
