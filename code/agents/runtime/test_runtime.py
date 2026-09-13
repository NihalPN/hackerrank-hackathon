from fallback import deterministic_fallback, gemini_result
from policy import AgentRuntimePolicy, AgentRuntimeStats


def test_policy():
    p = AgentRuntimePolicy()
    assert p.max_requests_per_minute > 0
    assert p.max_requests_per_day > 0
    assert p.max_concurrent_requests > 0


def test_success():
    result = gemini_result(
        [{"fact_type": "income", "value": "1000"}]
    )
    assert result.source == "gemini"
    assert len(result.facts) == 1


def test_fallback():
    result = deterministic_fallback("quota exhausted")
    assert result.source == "deterministic_fallback"
    assert "quota" in result.fallback_reason


def test_stats():
    stats = AgentRuntimeStats()
    stats.total_requests = 1000
    stats.gemini_attempts = 400
    stats.gemini_successes = 380
    stats.gemini_failures = 20
    stats.quota_failures = 20
    stats.deterministic_fallbacks = 620

    data = stats.as_dict()

    assert data["total_requests"] == 1000
    assert data["deterministic_fallbacks"] == 620


if __name__ == "__main__":
    test_policy()
    test_success()
    test_fallback()
    test_stats()
    print("PHASE 4 RUNTIME TESTS: PASS")
