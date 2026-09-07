from datetime import UTC, datetime, timedelta

from system_intelligence.core.enums import Confidence
from system_intelligence.core.research import ResearchResult
from system_intelligence.research.scoring import assess_candidate, rank_candidates


def _result(
    identifier: str,
    *,
    license: str | None = None,
    pushed_days_ago: int | None = None,
    archived: bool | None = None,
    stars: int | None = None,
) -> ResearchResult:
    signals: dict[str, str] = {}
    if pushed_days_ago is not None:
        pushed_at = datetime.now(UTC) - timedelta(days=pushed_days_ago)
        signals["last_push_at"] = pushed_at.isoformat()
    if archived is not None:
        signals["archived"] = str(archived)
    if stars is not None:
        signals["stargazers_count"] = str(stars)
    return ResearchResult(
        query="q",
        provider="github",
        source=f"https://github.com/{identifier}",
        identifier=identifier,
        license=license,
        license_confidence=Confidence.VERIFIED if license else Confidence.UNKNOWN,
        maintenance_signals=signals,
    )


def test_assess_candidate_recently_active() -> None:
    result = _result("a/a", pushed_days_ago=10)
    assessment = assess_candidate(result)
    assert assessment.is_recently_active is True


def test_assess_candidate_stale() -> None:
    result = _result("a/a", pushed_days_ago=1000)
    assessment = assess_candidate(result)
    assert assessment.is_recently_active is False


def test_assess_candidate_unknown_activity_without_signal() -> None:
    result = _result("a/a")
    assessment = assess_candidate(result)
    assert assessment.is_recently_active is None


def test_assess_candidate_malformed_pushed_at_is_unknown() -> None:
    result = _result("a/a")
    result.maintenance_signals["last_push_at"] = "not-a-date"
    assessment = assess_candidate(result)
    assert assessment.is_recently_active is None


def test_assess_candidate_malformed_stargazer_count_is_unknown() -> None:
    result = _result("a/a")
    result.maintenance_signals["stargazers_count"] = "not-a-number"
    assessment = assess_candidate(result)
    assert assessment.stargazer_count is None


def test_assess_candidate_unscorable_dimensions_always_listed() -> None:
    result = _result("a/a")
    assessment = assess_candidate(result)
    assert "functional_fit" in assessment.unknown_dimensions
    assert "security_posture" in assessment.unknown_dimensions


def test_rank_candidates_prefers_license_and_activity_over_stars() -> None:
    popular_but_archived = _result(
        "big/popular", license=None, pushed_days_ago=2000, archived=True, stars=100000
    )
    small_but_healthy = _result(
        "small/healthy", license="MIT", pushed_days_ago=5, archived=False, stars=3
    )

    ranked = rank_candidates([popular_but_archived, small_but_healthy])

    assert ranked[0].result.identifier == "small/healthy"
    assert ranked[1].result.identifier == "big/popular"
    # Stars are still exposed, just not used to decide the order.
    assert ranked[1].stargazer_count == 100000


def test_rank_candidates_unknown_archived_ranks_between_confirmed_states() -> None:
    """An unknown archived status (e.g. a provider whose schema has no such
    field, like the MCP registry) must never be silently treated as
    "verified not archived" -- it should rank strictly below a candidate
    confirmed not archived, and strictly above one confirmed archived."""
    confirmed_not_archived = _result(
        "a/confirmed-clean", license="MIT", pushed_days_ago=5, archived=False
    )
    unknown_archived = _result("b/unknown", license="MIT", pushed_days_ago=5, archived=None)
    confirmed_archived = _result(
        "c/confirmed-archived", license="MIT", pushed_days_ago=5, archived=True
    )

    ranked = rank_candidates([confirmed_archived, unknown_archived, confirmed_not_archived])

    assert [r.result.identifier for r in ranked] == [
        "a/confirmed-clean",
        "b/unknown",
        "c/confirmed-archived",
    ]


def test_rank_candidates_stable_for_ties() -> None:
    a = _result("a/a", license="MIT", pushed_days_ago=5)
    b = _result("b/b", license="MIT", pushed_days_ago=5)

    ranked = rank_candidates([a, b])

    assert [r.result.identifier for r in ranked] == ["a/a", "b/b"]
