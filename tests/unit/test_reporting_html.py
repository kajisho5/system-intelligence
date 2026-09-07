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


def test_generate_html_report_no_remote_configured() -> None:
    repository = Repository(id="r1", name="repo", path=".", is_git_repository=True)
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "<dt>Remote</dt><dd>none configured</dd>" in html


def test_generate_html_report_shows_configured_remote_url() -> None:
    """`Repository.url` (the discovered `git remote get-url origin`, its
    own dedicated Evidence in discovery/git_metadata.py) was genuinely
    populated by discovery but never rendered by the static report's
    overview -- it already renders every other GitMetadata-derived fact
    (is_git_repository/default_branch, languages) sitting right next to
    it."""
    repository = Repository(
        id="r1",
        name="repo",
        path=".",
        is_git_repository=True,
        url="https://example.com/octocat/demo.git",
    )
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "<dt>Remote</dt><dd>https://example.com/octocat/demo.git</dd>" in html


def test_generate_html_report_shows_unknown_license_by_default() -> None:
    repository = Repository(id="r1", name="repo", path=".")
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "<dt>License</dt><dd>unknown</dd>" in html


def test_generate_html_report_shows_detected_license() -> None:
    """`Repository.license` (`discovery/ci_docs.py::detect_license`) was
    already surfaced in `si inspect`'s text output but never rendered by
    the static report's overview -- it renders every other Repository
    fact sitting right next to it (Remote, Git branch, Languages)."""
    repository = Repository(id="r1", name="repo", path=".", license="MIT")
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "<dt>License</dt><dd>MIT</dd>" in html


def test_generate_html_report_omits_last_commit_when_unknown() -> None:
    repository = Repository(id="r1", name="repo", path=".")
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "Last commit" not in html


def test_generate_html_report_shows_last_commit_date_and_dirty_state() -> None:
    """`Repository.last_commit_date`/`is_dirty` (`discovery/git_metadata.py`)
    were already surfaced in `si inspect`'s text output but never rendered
    by the static report's overview -- the same gap as `license` above."""
    repository = Repository(
        id="r1", name="repo", path=".", last_commit_date="2026-01-15T10:00:00+00:00", is_dirty=True
    )
    snapshot = Snapshot(target=_target(), components=[repository])

    html = generate_html_report(snapshot)

    assert "<dt>Last commit</dt><dd>2026-01-15T10:00:00+00:00, uncommitted changes</dd>" in html


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


def test_generate_html_report_shows_skill_tool_scope() -> None:
    """`Skill.tool_names`/`permissions` (`allowed-tools`/`disallowed-tools`
    frontmatter, `discovery/skills.py`) were already discovered and stored
    but never rendered by any of the three user-facing surfaces -- a
    security-relevant fact (which tools a Skill explicitly forbids itself
    from using) invisible without opening the raw JSON snapshot."""
    skill = Skill(
        id="s1",
        name="my-skill",
        path="skills/my-skill/SKILL.md",
        tool_names=["Bash(git add *)", "Read"],
        permissions=["Write", "Edit"],
    )
    snapshot = Snapshot(target=_target(), components=[skill])

    html = generate_html_report(snapshot)

    assert "tools: Bash(git add *), Read" in html
    assert "disallowed: Write, Edit" in html


def test_generate_html_report_shows_agent_tool_scope() -> None:
    agent = Agent(
        id="a1",
        name="code-reviewer",
        tool_names=["Read", "Grep"],
        permissions=["Write", "Edit"],
    )
    snapshot = Snapshot(target=_target(), components=[agent])

    html = generate_html_report(snapshot)

    assert "tools: Read, Grep" in html
    assert "disallowed: Write, Edit" in html


def test_generate_html_report_dependency_graph_attributes_to_the_owning_component() -> None:
    """The Dependency Graph previously drew every dependency as an edge
    from a single, hard-coded node labeled "repository" regardless of
    which Component actually declares it -- but `analysis/dependencies.py::
    attach_dependencies_by_component` already correctly attributes each
    Dependency to its real owning Component (e.g. a Skill's own
    package.json, not the Repository's), the same way
    `_render_capability_graph` right above it already resolves
    `provider_ids` to real component names. A Skill's own dependency must
    be labeled with the Skill's name, not "repository"."""
    repo_dependency = Dependency(id="d1", name="top-level-dep", ecosystem="npm")
    skill_dependency = Dependency(id="d2", name="left-pad", ecosystem="npm")
    repository = Repository(id="r1", name="repo", path=".", dependencies=[repo_dependency])
    skill = Skill(
        id="s1",
        name="demo-skill",
        path="skills/demo/SKILL.md",
        dependencies=[skill_dependency],
    )
    snapshot = Snapshot(target=_target(), components=[repository, skill])

    html = generate_html_report(snapshot)

    idx = html.index("left-pad")
    row_start = html.rindex("<line ", 0, idx)
    row = html[row_start:idx]
    assert "demo-skill" in row
    assert ">repository<" not in row


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
