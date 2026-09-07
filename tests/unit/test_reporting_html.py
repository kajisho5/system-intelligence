from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Agent, Dependency, Repository, Skill, Target
from system_intelligence.core.enums import (
    CapabilityStatus,
    Confidence,
    Severity,
    TargetKind,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.core.verification import Verification
from system_intelligence.reporting.html import generate_html_report


def _target() -> Target:
    return Target(name="my-repo", kind=TargetKind.LOCAL_PATH, locator="/repo")


def test_generate_html_report_is_valid_shell() -> None:
    snapshot = Snapshot(target=_target())
    html = generate_html_report(snapshot)
    assert html.startswith("<!doctype html>")
    assert "<title>" in html
    assert "my-repo" in html
    assert "No recommendations were generated for this snapshot." in html
    assert "Not computed for this report" in html  # research / proposed-changes placeholders


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


def test_generate_html_report_not_a_git_repository() -> None:
    repository = Repository(id="r1", name="repo", path=".", is_git_repository=False)
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "not a git repository" in html


def test_generate_html_report_git_repository_with_no_remote_branch() -> None:
    """A real git repository with no configured/resolvable remote branch
    must never be reported as "not a git repository" just because
    `default_branch` happens to be unset -- those are distinct facts."""
    repository = Repository(id="r1", name="repo", path=".", is_git_repository=True)
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "not a git repository" not in html
    assert "no remote branch detected" in html


def test_generate_html_report_git_repository_with_branch() -> None:
    repository = Repository(
        id="r1", name="repo", path=".", is_git_repository=True, default_branch="main"
    )
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "<dt>Git branch</dt><dd>main</dd>" in html


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


def test_generate_html_report_renders_agent_detail() -> None:
    """An Agent is a peer Component to Skill with the same `is_standard_format`
    signal -- previously fell through `_render_components`'s isinstance
    dispatch entirely, rendering an empty Detail column."""
    agent = Agent(
        id="a1",
        name="code-reviewer",
        path=".claude/agents/code-reviewer.md",
        is_standard_format=True,
        model_provider="sonnet",
    )
    snapshot = Snapshot(target=_target(), components=[agent])

    html = generate_html_report(snapshot)

    assert "code-reviewer" in html
    assert "standard format" in html
    assert "model: sonnet" in html


def test_generate_html_report_renders_non_standard_agent_detail() -> None:
    agent = Agent(id="a1", name="mystery-agent", is_standard_format=False)
    snapshot = Snapshot(target=_target(), components=[agent])

    html = generate_html_report(snapshot)

    assert "non-standard format" in html


def test_generate_html_report_surfaces_regressions_even_when_tests_passed() -> None:
    """A Verification can exit 0 (`tests_passed=True`) yet still have
    `regressions_found` non-empty -- si verify (cli/main.py) treats that
    combination as a failing run too and exits non-zero for it. Previously
    `_render_verification` only ever showed `tests_run`/`passed: True`,
    silently dropping the one field that actually made the CLI fail."""
    verification = Verification(
        tests_run=["pytest"],
        tests_passed=True,
        regressions_found=["a new HIGH-severity finding appeared after the change"],
    )
    snapshot = Snapshot(target=_target(), verification=[verification])

    html = generate_html_report(snapshot)

    assert "passed: True" in html
    assert "a new HIGH-severity finding appeared after the change" in html
    assert "regressions found" in html
