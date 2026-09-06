"""`si` command-line entry point.

`si doctor`, `si version`, `si inspect`, `si diagnose`, `si report`,
`si diff`, and `si research` are implemented. The remaining commands from
docs/design/docs/13-cli-and-ux.md (`design`, `improve`, `propose`,
`execute`, `verify`, `watch`) are registered as explicit placeholders so
`si --help` documents the intended surface without claiming functionality
that does not exist yet.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from system_intelligence import __version__
from system_intelligence.analysis import analyze_local_repository
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import ComponentKind, Severity
from system_intelligence.core.findings import Finding
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery import TargetResolutionError, discover_local_repository
from system_intelligence.reporting import diff_snapshots, generate_html_report
from system_intelligence.research import (
    UNSCORABLE_DIMENSIONS,
    GitHubResearchError,
    GitHubResearchProvider,
    ResearchCache,
    rank_candidates,
)

app = typer.Typer(
    name="si",
    help=(
        "System Intelligence: discover, understand, audit, research, and improve software systems."
    ),
    no_args_is_help=True,
)

_PLANNED_COMMANDS = {
    "design": "Architecture/design proposal generation. Planned for Phase 6.",
    "improve": "Generate an improvement plan. Planned for Phase 6.",
    "propose": "Create a concrete change proposal. Planned for Phase 6.",
    "execute": "Perform an approved change. Planned for Phase 8 (human-approved execution).",
    "verify": "Validate a change and compare before/after state. Planned for Phase 8.",
    "watch": "Repeat diagnosis on an interval and detect drift. Planned for Phase 8.",
}


def _register_placeholder(name: str, summary: str) -> None:
    def _command() -> None:
        typer.echo(f"'si {name}' is not implemented yet. {summary}", err=True)
        raise typer.Exit(code=1)

    _command.__name__ = f"cmd_{name}"
    app.command(name=name, help=f"(not yet implemented) {summary}")(_command)


for _name, _summary in _PLANNED_COMMANDS.items():
    _register_placeholder(_name, _summary)


_TARGET_ARGUMENT = typer.Argument(
    ".", help="Local path to inspect. Defaults to the current directory."
)
_OUT_OPTION = typer.Option(
    None, "--out", help="Directory to write the canonical JSON snapshot to. Skipped if omitted."
)


def _format_named_list(label: str, items: list[str]) -> str:
    return f"{label}: {len(items)}" + (f" ({', '.join(items)})" if items else "")


@app.command()
def inspect(target: str = _TARGET_ARGUMENT, out: Path | None = _OUT_OPTION) -> None:
    """Read-only inventory of a local target (git metadata, structure, Skills, CI, docs).

    Only local filesystem targets are supported so far — GitHub/manifest
    targets are future work. Nothing is written unless `--out` is given.
    """
    try:
        result = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    snapshot = result.snapshot
    repository = next(c for c in snapshot.components if isinstance(c, Repository))
    skills = [c for c in snapshot.components if c.kind == ComponentKind.SKILL]
    documents = [c for c in snapshot.components if c.kind == ComponentKind.DOCUMENT]
    evidence_count = sum(len(c.evidence) for c in snapshot.components)

    git_status = f"yes, branch={repository.default_branch}" if repository.default_branch else "no"

    typer.echo(f"Target: {snapshot.target.locator}")
    typer.echo(f"Snapshot: {snapshot.id}")
    typer.echo(f"Git repository: {git_status}")
    typer.echo(f"Languages: {', '.join(repository.languages) or 'none detected'}")
    typer.echo(_format_named_list("Skills", [s.name for s in skills]))
    typer.echo(_format_named_list("CI jobs", [j.name for j in result.ci_jobs]))
    typer.echo(_format_named_list("Root documents", [d.name for d in documents]))
    typer.echo(f"Evidence collected: {evidence_count}")

    if out is not None:
        snapshot_dir = out / snapshot.id
        snapshot.write_to_directory(snapshot_dir)
        typer.echo(f"Snapshot written to {snapshot_dir}")


_SEVERITY_ORDER = [
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
]


@app.command()
def diagnose(target: str = _TARGET_ARGUMENT, out: Path | None = _OUT_OPTION) -> None:
    """Structured health assessment: discovery plus deterministic analysis.

    Runs every Phase 3 analyzer (documentation/CI/test gaps, dependency
    extraction, capability duplication, unreferenced Skills, circular
    imports) and prints findings grouped by severity, each labeled with its
    confidence level. Nothing is written unless `--out` is given.
    """
    try:
        discovery = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = analyze_local_repository(discovery)
    snapshot = result.snapshot

    typer.echo(f"Target: {snapshot.target.locator}")
    typer.echo(f"Snapshot: {snapshot.id}")
    typer.echo(f"Findings: {len(snapshot.findings)}")

    findings_by_severity: dict[Severity, list[Finding]] = {
        severity: [] for severity in _SEVERITY_ORDER
    }
    for finding in snapshot.findings:
        findings_by_severity[finding.severity].append(finding)

    for severity in _SEVERITY_ORDER:
        findings = findings_by_severity[severity]
        if not findings:
            continue
        typer.echo(f"\n{severity.value.upper()} ({len(findings)}):")
        for finding in findings:
            typer.echo(f"  - [{finding.confidence.value}] {finding.statement}")

    if out is not None:
        snapshot_dir = out / snapshot.id
        snapshot.write_to_directory(snapshot_dir)
        typer.echo(f"\nSnapshot written to {snapshot_dir}")


_REPORT_OUT_OPTION = typer.Option(
    Path("si-report"), "--out", help="Directory to write the HTML report and snapshot into."
)


@app.command()
def report(target: str = _TARGET_ARGUMENT, out: Path = _REPORT_OUT_OPTION) -> None:
    """Generate the static HTML intelligence report for a local target.

    Runs discovery and analysis, then writes a self-contained
    `report.html` (no CDN dependencies, viewable offline) plus the
    canonical JSON snapshot into `--out` (default: './si-report').
    """
    try:
        discovery = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = analyze_local_repository(discovery)
    snapshot = result.snapshot

    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "report.html"
    report_path.write_text(generate_html_report(snapshot), encoding="utf-8")
    snapshot_dir = out / snapshot.id
    snapshot.write_to_directory(snapshot_dir)

    typer.echo(f"Report written to {report_path}")
    typer.echo(f"Snapshot written to {snapshot_dir}")


_FROM_DIR_ARGUMENT = typer.Argument(..., help="Directory of the earlier canonical snapshot.")
_TO_DIR_ARGUMENT = typer.Argument(..., help="Directory of the later canonical snapshot.")


@app.command(name="diff")
def diff_command(from_dir: Path = _FROM_DIR_ARGUMENT, to_dir: Path = _TO_DIR_ARGUMENT) -> None:
    """Compare two canonical snapshot directories (each written by --out on another command)."""
    for label, path in (("from", from_dir), ("to", to_dir)):
        if not (path / "manifest.json").is_file():
            typer.echo(f"error: {label} directory {path} has no manifest.json", err=True)
            raise typer.Exit(code=1)

    before = Snapshot.read_from_directory(from_dir)
    after = Snapshot.read_from_directory(to_dir)
    result = diff_snapshots(before, after)

    typer.echo(f"From: {result.from_snapshot_id}")
    typer.echo(f"To:   {result.to_snapshot_id}")

    if not result.has_changes:
        typer.echo("No changes detected.")
        return

    def _section(label: str, lines: list[str]) -> None:
        if not lines:
            return
        typer.echo(f"\n{label} ({len(lines)}):")
        for line in lines:
            typer.echo(f"  - {line}")

    _section("Components added", [f"{c.kind.value}:{c.name}" for c in result.added_components])
    _section("Components removed", [f"{c.kind.value}:{c.name}" for c in result.removed_components])
    _section("Capabilities added", [c.name for c in result.added_capabilities])
    _section("Capabilities removed", [c.name for c in result.removed_capabilities])
    _section("Dependencies added", [f"{d.ecosystem}:{d.name}" for d in result.added_dependencies])
    _section(
        "Dependencies removed", [f"{d.ecosystem}:{d.name}" for d in result.removed_dependencies]
    )
    _section("Findings introduced", [f.statement for f in result.added_findings])
    _section("Findings resolved", [f.statement for f in result.resolved_findings])


_QUERY_ARGUMENT = typer.Argument(..., help="Search query, e.g. 'python markdown parser'.")
_RESEARCH_LIMIT_OPTION = typer.Option(10, "--limit", help="Maximum candidates to return.")
_NO_CACHE_OPTION = typer.Option(False, "--no-cache", help="Bypass the research cache.")
_CACHE_DIR_OPTION = typer.Option(
    Path(".si") / "research-cache", "--cache-dir", help="Directory for the research cache."
)

_ACTIVITY_LABEL = {True: "active", False: "stale", None: "unknown"}


@app.command()
def research(
    query: str = _QUERY_ARGUMENT,
    limit: int = _RESEARCH_LIMIT_OPTION,
    no_cache: bool = _NO_CACHE_OPTION,
    cache_dir: Path = _CACHE_DIR_OPTION,
) -> None:
    """Search GitHub for existing solutions before proposing something new.

    Read-only — only ever issues GET requests. Candidates are ranked by
    license presence, recent activity, and archived status; star count is
    shown for reference only and never used to rank (ADR-009). Several
    scoring dimensions (functional fit, security posture, ...) cannot be
    determined from a GitHub search response and are reported as unknown
    rather than guessed.
    """
    provider = GitHubResearchProvider(token=os.environ.get("GITHUB_TOKEN"))
    cache = ResearchCache(directory=cache_dir)

    results = None if no_cache else cache.get(provider.name, query)
    from_cache = results is not None
    if results is None:
        try:
            results = provider.search(query, limit=limit)
        except GitHubResearchError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        cache.set(provider.name, query, results)

    if not results:
        typer.echo(f"No candidates found for {query!r}.")
        return

    cache_note = " (cached)" if from_cache else ""
    typer.echo(f"Found {len(results)} candidate(s) for {query!r} via {provider.name}{cache_note}:")

    for assessment in rank_candidates(results):
        r = assessment.result
        license_str = r.license or "unknown"
        activity = _ACTIVITY_LABEL[assessment.is_recently_active]
        archived = "archived" if assessment.is_archived else "not archived"
        stars = "unknown" if assessment.stargazer_count is None else str(assessment.stargazer_count)
        typer.echo(f"\n- {r.identifier}")
        typer.echo(f"    source: {r.source}")
        typer.echo(f"    license: {license_str} ({assessment.license_confidence.value})")
        typer.echo(f"    activity: {activity}, {archived}, stars: {stars} (informational only)")

    typer.echo(
        f"\n{len(UNSCORABLE_DIMENSIONS)} dimension(s) could not be assessed from this data "
        f"and are excluded from ranking: {', '.join(UNSCORABLE_DIMENSIONS)}."
    )


@app.command()
def version() -> None:
    """Print the installed System Intelligence version."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Check that the local environment has what System Intelligence needs.

    This is a read-only, deterministic environment check — no target
    analysis is performed. It reports Python version, git availability, and
    whether the working directory is inside a git repository, each labeled
    ok/warning so the output distinguishes verified facts from environment
    gaps rather than asserting overall health.
    """
    checks: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 11)
    checks.append(
        (
            "python-version",
            py_ok,
            f"Python {sys.version.split()[0]} ({'>= 3.11' if py_ok else 'requires >= 3.11'})",
        )
    )

    git_path = shutil.which("git")
    checks.append(("git-available", git_path is not None, git_path or "git not found on PATH"))

    in_git_repo = False
    if git_path is not None:
        # Fixed argv resolved via shutil.which, no shell, no user-controlled
        # input — safe despite bandit's blanket subprocess warning.
        result = subprocess.run(  # noqa: S603 # nosec B603
            [git_path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        in_git_repo = result.returncode == 0 and result.stdout.strip() == "true"
    checks.append(
        (
            "inside-git-repository",
            in_git_repo,
            "current directory is a git working tree" if in_git_repo else "not a git working tree",
        )
    )

    all_ok = True
    for check_name, ok, detail in checks:
        status = "ok" if ok else "warning"
        if not ok:
            all_ok = False
        typer.echo(f"[{status}] {check_name}: {detail}")

    if not all_ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
