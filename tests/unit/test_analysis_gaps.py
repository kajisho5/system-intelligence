from pathlib import Path

from system_intelligence.analysis.gaps import (
    DeclaredCapability,
    DeclaredRequirements,
    RequirementsParseError,
    audit_capability_gaps,
    detect_capability_gaps,
    load_declared_requirements,
)
from system_intelligence.core.capability import Capability
from system_intelligence.core.enums import CapabilityStatus, Confidence


def _capability(name: str, status: CapabilityStatus = CapabilityStatus.AVAILABLE) -> Capability:
    return Capability(name=name, status=status, confidence=Confidence.HIGH)


def test_load_declared_requirements_returns_none_when_file_missing(tmp_path: Path) -> None:
    assert load_declared_requirements(tmp_path) is None


def test_load_declared_requirements_parses_valid_file(tmp_path: Path) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text(
        '{"capabilities": [{"name": "markdown rendering", "description": "Render CommonMark"}]}',
        encoding="utf-8",
    )

    declared = load_declared_requirements(tmp_path)

    assert declared is not None
    assert declared.capabilities == [
        DeclaredCapability(name="markdown rendering", description="Render CommonMark")
    ]


def test_load_declared_requirements_empty_capabilities_list_is_not_none(tmp_path: Path) -> None:
    """An explicit `{"capabilities": []}` (zero requirements declared) must
    be distinguishable from "no file at all" -- both return non-None here,
    only a missing file returns None."""
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text('{"capabilities": []}', encoding="utf-8")

    declared = load_declared_requirements(tmp_path)

    assert declared == DeclaredRequirements(capabilities=[])


def test_load_declared_requirements_invalid_json_raises(tmp_path: Path) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text("not json", encoding="utf-8")

    try:
        load_declared_requirements(tmp_path)
        raise AssertionError("expected RequirementsParseError")
    except RequirementsParseError:
        pass


def test_load_declared_requirements_wrong_shape_raises(tmp_path: Path) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text(
        '{"capabilities": "not a list"}', encoding="utf-8"
    )

    try:
        load_declared_requirements(tmp_path)
        raise AssertionError("expected RequirementsParseError")
    except RequirementsParseError:
        pass


def test_detect_capability_gaps_reports_missing_capability() -> None:
    declared = DeclaredRequirements(capabilities=[DeclaredCapability(name="PDF export")])

    findings = detect_capability_gaps(declared, capabilities=[])

    assert len(findings) == 1
    assert findings[0].category == "capability_gap"
    assert "PDF export" in findings[0].statement


def test_detect_capability_gaps_satisfied_by_exact_case_insensitive_match() -> None:
    declared = DeclaredRequirements(capabilities=[DeclaredCapability(name="PDF Export")])
    capabilities = [_capability("pdf export")]

    findings = detect_capability_gaps(declared, capabilities)

    assert findings == []


def test_detect_capability_gaps_never_matches_a_partial_status_capability() -> None:
    """Declared and looks partial is not satisfied -- a matching name with
    a non-AVAILABLE status still counts as a gap."""
    declared = DeclaredRequirements(capabilities=[DeclaredCapability(name="PDF export")])
    capabilities = [_capability("PDF export", status=CapabilityStatus.PARTIAL)]

    findings = detect_capability_gaps(declared, capabilities)

    assert len(findings) == 1


def test_detect_capability_gaps_never_fuzzy_matches() -> None:
    """A near-miss name is still a gap -- only exact (trimmed,
    case-insensitive) equality counts as satisfied, never a heuristic."""
    declared = DeclaredRequirements(capabilities=[DeclaredCapability(name="PDF export")])
    capabilities = [_capability("PDF exporting")]

    findings = detect_capability_gaps(declared, capabilities)

    assert len(findings) == 1


def test_detect_capability_gaps_no_declared_requirements_produces_no_findings() -> None:
    findings = detect_capability_gaps(DeclaredRequirements(), capabilities=[_capability("x")])
    assert findings == []


def test_audit_capability_gaps_missing_file_contributes_zero_findings(tmp_path: Path) -> None:
    findings = audit_capability_gaps(tmp_path, capabilities=[])
    assert findings == []


def test_audit_capability_gaps_invalid_file_produces_one_finding_not_a_crash(
    tmp_path: Path,
) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text("not json", encoding="utf-8")

    findings = audit_capability_gaps(tmp_path, capabilities=[])

    assert len(findings) == 1
    assert findings[0].category == "invalid_requirements_file"


def test_audit_capability_gaps_end_to_end(tmp_path: Path) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text(
        '{"capabilities": [{"name": "satisfied"}, {"name": "missing"}]}', encoding="utf-8"
    )
    capabilities = [_capability("satisfied")]

    findings = audit_capability_gaps(tmp_path, capabilities)

    assert len(findings) == 1
    assert "missing" in findings[0].statement
