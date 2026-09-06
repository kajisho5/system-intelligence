import pytest

from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.enums import (
    ComponentKind,
    Confidence,
    StateDiffCategory,
    UpdateVerdict,
)
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.security import SecurityAdvisory
from system_intelligence.core.state_diff import StateDiff, StateDiffItem


def _identity() -> ComponentIdentity:
    return ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="pkg")


def _diff(items: list[StateDiffItem] | None = None) -> StateDiff:
    current = ComponentState(identity=_identity(), version="1.0.0")
    available = AvailableState(identity=_identity(), provider="pypi", version="1.1.0")
    return StateDiff(
        identity=_identity(), from_state=current, to_state=available, items=items or []
    )


def test_update_recommended_forbidden_with_breaking_items() -> None:
    breaking = StateDiffItem(
        category=StateDiffCategory.BREAKING, description="x", confidence=Confidence.HIGH
    )
    with pytest.raises(ValueError, match="UPDATE_RECOMMENDED"):
        ImpactAssessment(
            state_diff=_diff([breaking]),
            breaking_items=[breaking],
            verdict=UpdateVerdict.UPDATE_RECOMMENDED,
            verdict_confidence=Confidence.HIGH,
            verdict_rationale="should not be allowed",
        )


def test_update_recommended_forbidden_with_unknown_dimensions() -> None:
    with pytest.raises(ValueError, match="UPDATE_RECOMMENDED"):
        ImpactAssessment(
            state_diff=_diff(),
            unknown_dimensions=("capability",),
            verdict=UpdateVerdict.UPDATE_RECOMMENDED,
            verdict_confidence=Confidence.HIGH,
            verdict_rationale="should not be allowed",
        )


def test_update_recommended_allowed_with_no_breaking_or_unknown() -> None:
    assessment = ImpactAssessment(
        state_diff=_diff(),
        verdict=UpdateVerdict.UPDATE_RECOMMENDED,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="everything resolved",
    )
    assert assessment.verdict == UpdateVerdict.UPDATE_RECOMMENDED


def test_review_required_allowed_with_unknown_dimensions() -> None:
    assessment = ImpactAssessment(
        state_diff=_diff(),
        unknown_dimensions=("capability", "interface"),
        verdict=UpdateVerdict.REVIEW_REQUIRED,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="cannot confirm safety",
    )
    assert assessment.unknown_dimensions == ("capability", "interface")


def test_advisories_default_to_empty() -> None:
    assessment = ImpactAssessment(
        state_diff=_diff(),
        verdict=UpdateVerdict.NO_UPDATE_AVAILABLE,
        verdict_confidence=Confidence.VERIFIED,
        verdict_rationale="unrelated to advisories",
    )
    assert assessment.current_version_advisories == []
    assert assessment.available_version_advisories == []


def test_a_vulnerable_current_version_still_cannot_unlock_update_recommended() -> None:
    """Advisories are informational: they never bypass the validator that
    forbids UPDATE_RECOMMENDED without every material dimension resolved."""
    advisory = SecurityAdvisory(id="GHSA-xxxx", summary="something bad")
    with pytest.raises(ValueError, match="UPDATE_RECOMMENDED"):
        ImpactAssessment(
            state_diff=_diff(),
            unknown_dimensions=("capability",),
            verdict=UpdateVerdict.UPDATE_RECOMMENDED,
            verdict_confidence=Confidence.HIGH,
            verdict_rationale="should not be allowed",
            current_version_advisories=[advisory],
        )


def test_advisories_can_be_carried_alongside_a_valid_verdict() -> None:
    advisory = SecurityAdvisory(
        id="GHSA-xxxx", summary="Command injection", severity="HIGH", aliases=["CVE-2021-1"]
    )
    assessment = ImpactAssessment(
        state_diff=_diff(),
        unknown_dimensions=("capability",),
        verdict=UpdateVerdict.REVIEW_REQUIRED,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="review needed",
        current_version_advisories=[advisory],
    )
    assert assessment.current_version_advisories == [advisory]
    assert assessment.available_version_advisories == []
