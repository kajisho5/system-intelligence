from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind


def test_evidence_defaults_to_medium_confidence() -> None:
    evidence = Evidence(
        kind=EvidenceKind.FILE,
        source="README.md",
        observation="Package declares capability X",
    )
    assert evidence.confidence == Confidence.MEDIUM
    assert evidence.id.startswith("evidence-")
    assert evidence.observed_at.tzinfo is not None


def test_evidence_is_immutable() -> None:
    evidence = Evidence(
        kind=EvidenceKind.GIT_METADATA,
        source=".git",
        observation="Last commit 2026-09-01",
        confidence=Confidence.VERIFIED,
    )
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        evidence.confidence = Confidence.LOW  # type: ignore[misc]
