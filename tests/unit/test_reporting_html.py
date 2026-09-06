from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Dependency, Repository, Skill, Target
from system_intelligence.core.enums import (
    CapabilityStatus,
    Confidence,
    Severity,
    TargetKind,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.reporting.html import generate_html_report


def _target() -> Target:
    return Target(name="my-repo", kind=TargetKind.LOCAL_PATH, locator="/repo")


def test_generate_html_report_is_valid_shell() -> None:
    snapshot = Snapshot(target=_target())
    html = generate_html_report(snapshot)
    assert html.startswith("<!doctype html>")
    assert "<title>" in html
    assert "my-repo" in html
    assert "Not yet available" in html  # Recommendations placeholder


def test_generate_html_report_escapes_untrusted_content() -> None:
    repository = Repository(id="r1", name="repo", path=".")
    finding = Finding(
        category="test",
        severity=Severity.HIGH,
        statement="<script>alert('xss')</script>",
        confidence=Confidence.HIGH,
        evidence=[Evidence(kind=EvidenceKind.FILE, source="x", observation="x")],
    )
    snapshot = Snapshot(target=_target(), components=[repository], findings=[finding])

    html = generate_html_report(snapshot)

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_generate_html_report_includes_components_capabilities_dependencies() -> None:
    dependency = Dependency(id="d1", name="pydantic", ecosystem="pypi", version_constraint=">=2")
    repository = Repository(id="r1", name="repo", path=".", dependencies=[dependency])
    skill = Skill(
        id="s1", name="my-skill", path="skills/my-skill/SKILL.md", is_standard_format=True
    )
    capability = Capability(
        id="c1",
        name="my-skill",
        provider_ids=["s1"],
        status=CapabilityStatus.AVAILABLE,
        confidence=Confidence.HIGH,
    )
    snapshot = Snapshot(target=_target(), components=[repository, skill], capabilities=[capability])

    html = generate_html_report(snapshot)

    assert "my-skill" in html
    assert "pydantic" in html
    assert "standard format" in html


def test_generate_html_report_no_findings_message() -> None:
    snapshot = Snapshot(target=_target())
    html = generate_html_report(snapshot)
    assert "No findings." in html
