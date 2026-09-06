import pytest
from pydantic import ValidationError

from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding


def _evidence() -> Evidence:
    return Evidence(
        kind=EvidenceKind.STATIC_REFERENCE,
        source="src/",
        observation="No import of motion_graphics_skill found in analyzed consumers",
        confidence=Confidence.HIGH,
    )


def test_finding_with_confidence_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="cites no evidence"):
        Finding(
            category="unused_candidate",
            severity=Severity.LOW,
            statement="motion-graphics-skill is unused",
            confidence=Confidence.HIGH,
            evidence=[],
        )


def test_finding_unknown_confidence_may_omit_evidence() -> None:
    finding = Finding(
        category="unused_candidate",
        severity=Severity.INFO,
        statement="Runtime usage of motion-graphics-skill could not be determined",
        confidence=Confidence.UNKNOWN,
    )
    assert finding.evidence == []


def test_finding_with_evidence_is_valid() -> None:
    finding = Finding(
        category="unused_candidate",
        severity=Severity.LOW,
        statement=(
            "motion-graphics-skill is currently unreferenced by the analyzed "
            "consumers. Runtime usage could not be verified."
        ),
        confidence=Confidence.MEDIUM,
        evidence=[_evidence()],
    )
    assert finding.evidence[0].source == "src/"
