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
