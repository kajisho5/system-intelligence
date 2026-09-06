from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.enums import (
    ComponentKind,
    Confidence,
    PermissionLevel,
    Severity,
    UpdateVerdict,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.state_diff import StateDiff
from system_intelligence.recommendations.engine import (
    generate_recommendations,
    generate_update_recommendations,
    recommend_from_impact,
)


def _finding(
    category: str, severity: Severity, confidence: Confidence = Confidence.HIGH
) -> Finding:
    return Finding(
        category=category,
        severity=severity,
        statement=f"{category} statement",
        confidence=confidence,
        evidence=[Evidence(kind=EvidenceKind.FILE, source="x", observation="x")],
        suggested_actions=[f"Fix {category}"],
    )


def test_recommend_from_finding_carries_evidence_and_confidence() -> None:
    finding = _finding("documentation_gap", Severity.HIGH, Confidence.HIGH)
    [recommendation] = generate_recommendations([finding])

    assert recommendation.objective == "Fix documentation_gap"
    assert recommendation.rationale == finding.statement
    assert recommendation.evidence == finding.evidence
    assert recommendation.confidence == Confidence.HIGH
    assert recommendation.required_approval_level == PermissionLevel.RECOMMEND
    assert recommendation.estimated_effort == "small"


def test_recommend_uses_statement_when_no_suggested_actions() -> None:
    finding = Finding(
        category="test_gap",
        severity=Severity.MEDIUM,
        statement="No tests found.",
        confidence=Confidence.MEDIUM,
        evidence=[Evidence(kind=EvidenceKind.FILE, source="x", observation="x")],
    )
    [recommendation] = generate_recommendations([finding])
    assert recommendation.objective == "No tests found."


def test_unknown_category_gets_unknown_effort() -> None:
    finding = _finding("some_new_category", Severity.LOW)
    [recommendation] = generate_recommendations([finding])
    assert recommendation.estimated_effort == "unknown"


def test_capability_gap_category_has_a_real_effort_estimate() -> None:
    """analysis/gaps.py::audit_capability_gaps produces `capability_gap`
    Findings -- previously absent from `_EFFORT_BY_CATEGORY`, so every one
    fell through to "unknown" effort and an artificially "low" risk despite
    being a HIGH-severity finding."""
    finding = _finding("capability_gap", Severity.HIGH)
    [recommendation] = generate_recommendations([finding])
    assert recommendation.estimated_effort != "unknown"


def test_invalid_requirements_file_category_has_a_real_effort_estimate() -> None:
    finding = _finding("invalid_requirements_file", Severity.HIGH)
    [recommendation] = generate_recommendations([finding])
    assert recommendation.estimated_effort != "unknown"


def test_generate_recommendations_orders_by_severity_then_confidence() -> None:
    low = _finding("documentation_gap", Severity.LOW, Confidence.HIGH)
    critical = _finding("ci_health", Severity.CRITICAL, Confidence.LOW)
    medium_high_conf = _finding("test_gap", Severity.MEDIUM, Confidence.VERIFIED)

    ranked = generate_recommendations([low, critical, medium_high_conf])

    assert [r.rationale for r in ranked] == [
        critical.statement,
        medium_high_conf.statement,
        low.statement,
    ]


def _assessment(verdict: UpdateVerdict) -> ImpactAssessment:
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    current = ComponentState(identity=identity, version="0.8.2")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    return ImpactAssessment(
        state_diff=diff,
        verdict=verdict,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="rationale text",
    )


def test_recommend_from_impact_update_recommended() -> None:
    recommendation = recommend_from_impact(_assessment(UpdateVerdict.UPDATE_RECOMMENDED))
    assert recommendation is not None
    assert recommendation.objective == "Update ffmpeg-skill from 0.8.2 to 0.9.2."
    assert recommendation.risk == "low"
    assert recommendation.rationale == "rationale text"


def test_recommend_from_impact_not_advisable_warns_against_update() -> None:
    recommendation = recommend_from_impact(_assessment(UpdateVerdict.NOT_ADVISABLE))
    assert recommendation is not None
    assert "Do not update" in recommendation.objective
    assert recommendation.risk == "high"


def test_recommend_from_impact_no_update_available_returns_none() -> None:
    assert recommend_from_impact(_assessment(UpdateVerdict.NO_UPDATE_AVAILABLE)) is None


def test_recommend_from_impact_unknown_returns_none() -> None:
    assert recommend_from_impact(_assessment(UpdateVerdict.UNKNOWN)) is None


def test_generate_update_recommendations_filters_non_actionable() -> None:
    assessments = [
        _assessment(UpdateVerdict.REVIEW_REQUIRED),
        _assessment(UpdateVerdict.NO_UPDATE_AVAILABLE),
        _assessment(UpdateVerdict.UNKNOWN),
    ]
    recommendations = generate_update_recommendations(assessments)
    assert len(recommendations) == 1
