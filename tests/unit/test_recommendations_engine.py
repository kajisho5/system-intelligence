from system_intelligence.core.enums import Confidence, PermissionLevel, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.recommendations.engine import generate_recommendations


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
