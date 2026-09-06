from datetime import UTC, datetime, timedelta

from system_intelligence.analysis.trust import infer_trust_levels
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import Confidence, TrustLevel
from system_intelligence.core.research import ResearchResult


def _result(
    identifier: str,
    *,
    license: str | None = "MIT",
    pushed_days_ago: int = 5,
    archived: bool = False,
) -> ResearchResult:
    pushed_at = datetime.now(UTC) - timedelta(days=pushed_days_ago)
    return ResearchResult(
        query="q",
        provider="github",
        source=f"https://github.com/{identifier}",
        identifier=identifier,
        license=license,
        license_confidence=Confidence.VERIFIED if license else Confidence.UNKNOWN,
        maintenance_signals={
            "last_push_at": pushed_at.isoformat(),
            "archived": str(archived),
        },
    )


def test_no_matching_research_result_stays_unknown() -> None:
    component = Repository(id="r1", name="unrelated-repo", path=".")

    [updated] = infer_trust_levels([component], research=[])

    assert updated.trust_level == TrustLevel.UNKNOWN
    assert updated.evidence == []


def test_matching_result_without_license_stays_unknown() -> None:
    component = Repository(id="r1", name="owner/some-repo", path=".")
    result = _result("owner/some-repo", license=None)

    [updated] = infer_trust_levels([component], research=[result])

    assert updated.trust_level == TrustLevel.UNKNOWN


def test_matching_archived_result_stays_unknown() -> None:
    component = Repository(id="r1", name="owner/some-repo", path=".")
    result = _result("owner/some-repo", archived=True)

    [updated] = infer_trust_levels([component], research=[result])

    assert updated.trust_level == TrustLevel.UNKNOWN


def test_matching_result_with_license_and_not_archived_is_community() -> None:
    component = Repository(id="r1", name="owner/some-repo", path=".")
    result = _result("owner/some-repo")

    [updated] = infer_trust_levels([component], research=[result])

    assert updated.trust_level == TrustLevel.COMMUNITY
    # Evidence must be traceable back to the actual research result.
    assert any(e.source == result.source for e in updated.evidence)


def test_matches_short_repo_name_against_owner_repo_identifier() -> None:
    """A locally discovered Component's own name is its short name; matching
    the trailing segment of an 'owner/repo' identifier is still an exact,
    deterministic comparison, never a fuzzy one."""
    component = Repository(id="r1", name="some-repo", path=".")
    result = _result("owner/some-repo")

    [updated] = infer_trust_levels([component], research=[result])

    assert updated.trust_level == TrustLevel.COMMUNITY


def test_high_stargazer_count_alone_never_grants_trust() -> None:
    """ADR-009: no single popularity signal may drive a trust decision.

    A result with a huge stargazer count but no license must not be
    promoted — only license+non-archived status (via
    research.scoring.assess_candidate) is ever used, stargazer_count is
    never read by this module at all.
    """
    component = Repository(id="r1", name="owner/some-repo", path=".")
    result = _result("owner/some-repo", license=None)
    result = result.model_copy(
        update={"maintenance_signals": {**result.maintenance_signals, "stargazers_count": "999999"}}
    )

    [updated] = infer_trust_levels([component], research=[result])

    assert updated.trust_level == TrustLevel.UNKNOWN


def test_stargazer_count_does_not_change_outcome_when_license_present() -> None:
    """The same license+not-archived result yields the same COMMUNITY
    verdict whether or not a stargazer count is present — proving the
    count itself is not part of the decision."""
    component_a = Repository(id="r1", name="owner/some-repo", path=".")
    component_b = Repository(id="r2", name="owner/some-repo", path=".")
    low_stars = _result("owner/some-repo")
    low_stars = low_stars.model_copy(
        update={"maintenance_signals": {**low_stars.maintenance_signals, "stargazers_count": "1"}}
    )
    high_stars = low_stars.model_copy(
        update={
            "maintenance_signals": {**low_stars.maintenance_signals, "stargazers_count": "999999"}
        }
    )

    [updated_a] = infer_trust_levels([component_a], research=[low_stars])
    [updated_b] = infer_trust_levels([component_b], research=[high_stars])

    assert updated_a.trust_level == updated_b.trust_level == TrustLevel.COMMUNITY


def test_existing_non_unknown_trust_level_is_never_overridden() -> None:
    component = Repository(
        id="r1", name="owner/some-repo", path=".", trust_level=TrustLevel.BLOCKED
    )
    result = _result("owner/some-repo")

    [updated] = infer_trust_levels([component], research=[result])

    assert updated.trust_level == TrustLevel.BLOCKED


def test_no_composite_score_field_exists_or_is_computed() -> None:
    """There is no single weighted trust score anywhere in this module's
    output — only the enum `TrustLevel` is ever set, with plain Evidence
    behind it, matching the explicit REJECT decision on composite trust
    scoring (agentoperations/agent-registry's self-contradicting model)."""
    component = Repository(id="r1", name="owner/some-repo", path=".")
    result = _result("owner/some-repo")

    [updated] = infer_trust_levels([component], research=[result])

    assert isinstance(updated.trust_level, TrustLevel)
    assert not hasattr(updated, "trust_score")
