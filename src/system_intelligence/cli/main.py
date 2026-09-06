"""`si` command-line entry point.

`si doctor`, `si version`, `si inspect`, `si diagnose`, `si report`,
`si diff`, `si research`, `si improve`, `si propose`, `si plan`, `si
execute`, `si verify`, `si check-updates`, `si dashboard`, and `si watch`
are implemented. `si plan` is not in docs/design/docs/13-cli-and-ux.md's
original command list; it exposes the Phase 7 capability-selection
planner (docs/design/docs/10-plugin-skill-system.md, "Dynamic selection")
so the capability set a request would run is visible before anything
executes. `si execute` is dry-run by default — it only ever prints
`ChangePlan.preview_lines()` unless `--approve` is passed, and even then
`execution.local_git.apply_plan` still requires a matching `Approval`
record for anything above the default read-only-ish permission ceiling;
it never pushes to any remote and can never perform a
`core.enums.FORBIDDEN_BY_DEFAULT_ACTIONS` action. `si check-updates` is
Component Update Intelligence (`analysis/update_intelligence.py`) —
also not in docs/13's original list, network-touching like `si research`.
`si dashboard` renders the interactive System Intelligence Console
(`reporting/dashboard_data.py` + `reporting/dashboard_html.py`) from one
or more snapshots. `si watch` is `si diagnose` plus `si diff` against a
self-managed history under `--state-dir`, deliberately with no internal
polling loop or daemon (ADR-004, read-only by default; this project has
no background-process machinery anywhere, and `watch` does not introduce
any) — "on an interval" means invoking the command repeatedly from an
external scheduler (cron, a CI schedule), not anything this process does
on its own. The remaining command from docs/13 (`design`) is registered
as an explicit placeholder so `si --help` documents the intended surface
without claiming functionality that does not exist yet.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol, TypeVar

import typer
from pydantic import BaseModel

from system_intelligence import __version__
from system_intelligence.analysis import analyze_local_repository
from system_intelligence.analysis.trust import infer_trust_levels
from system_intelligence.analysis.update_intelligence import check_dependency_updates
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import ComponentKind, PermissionLevel, Severity
from system_intelligence.core.execution_record import ExecutionRecord
from system_intelligence.core.findings import Finding
from system_intelligence.core.governance import Approval
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery import TargetResolutionError, discover_local_repository
from system_intelligence.execution import (
    ChangePlan,
    GitHubPRError,
    LocalGitError,
    apply_plan,
    build_handoff_packet,
    open_draft_pr_for_plan,
)
from system_intelligence.intelligence import CAPABILITIES, INTENTS, classify_intent, resolve_intent
from system_intelligence.policy import audit_log_entry
from system_intelligence.proposals import (
    change_plan_for_component_update,
    propose_component_update,
    propose_solution,
)
from system_intelligence.recommendations import generate_recommendations
from system_intelligence.reporting import (
    SnapshotDiff,
    build_dashboard_data,
    diff_snapshots,
    export_json_schemas,
    generate_dashboard_html,
    generate_html_report,
)
from system_intelligence.research import (
    UNSCORABLE_DIMENSIONS,
    ComponentUpdateProvider,
    CratesIoUpdateProvider,
    GitHubResearchError,
    GitHubResearchProvider,
    GoProxyUpdateProvider,
    MavenCentralUpdateProvider,
    MCPRegistryError,
    MCPRegistryResearchProvider,
    NpmUpdateProvider,
    OSVVulnerabilityProvider,
    PyPIUpdateProvider,
    ResearchCache,
    ResearchProvider,
    VulnerabilityProvider,
    rank_candidates,
)
from system_intelligence.verification import VerificationError, run_verification

app = typer.Typer(
    name="si",
    help=(
        "System Intelligence: discover, understand, audit, research, and improve software systems."
    ),
    no_args_is_help=True,
)

_PLANNED_COMMANDS = {
    "design": "Architecture/design proposal generation. Planned for Phase 6.",
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
    ".",
    help=(
        "Local path, or a GitHub repository as 'owner/repo' or a "
        "https://github.com/... URL (shallow-cloned read-only). "
        "Defaults to the current directory."
    ),
)
_OUT_OPTION = typer.Option(
    None, "--out", help="Directory to write the canonical JSON snapshot to. Skipped if omitted."
)


def _format_named_list(label: str, items: list[str]) -> str:
    return f"{label}: {len(items)}" + (f" ({', '.join(items)})" if items else "")


@app.command()
def inspect(target: str = _TARGET_ARGUMENT, out: Path | None = _OUT_OPTION) -> None:
    """Read-only inventory of a local or GitHub target (git metadata, structure, Skills, CI, docs).

    A GitHub repository is shallow-cloned first (see `_TARGET_ARGUMENT`'s
    help text); manifest/ecosystem targets remain future work. Nothing is
    written unless `--out` is given.
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
    snapshot = result.snapshot.model_copy(
        update={"recommendations": generate_recommendations(result.snapshot.findings)}
    )

    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "report.html"
    report_path.write_text(generate_html_report(snapshot), encoding="utf-8")
    snapshot_dir = out / snapshot.id
    snapshot.write_to_directory(snapshot_dir)

    typer.echo(f"Report written to {report_path}")
    typer.echo(f"Snapshot written to {snapshot_dir}")


_SCHEMA_OUT_OPTION = typer.Option(
    Path("si-schema"), "--out", help="Directory to write the JSON Schema files into."
)


@app.command()
def schema(out: Path = _SCHEMA_OUT_OPTION) -> None:
    """Export JSON Schema files for the canonical snapshot format.

    Writes one `<name>.schema.json` per file in the canonical snapshot
    directory layout (docs/design/docs/12-storage-and-state.md), plus
    `dashboard_data.schema.json` for the Dashboard's read model — so an
    external consumer can validate what it reads without depending on
    this project's own Python types. Takes no target: this describes the
    format itself, not any particular scan.
    """
    written = export_json_schemas(out)
    for path in written:
        typer.echo(f"Wrote {path}")


_FROM_DIR_ARGUMENT = typer.Argument(..., help="Directory of the earlier canonical snapshot.")
_TO_DIR_ARGUMENT = typer.Argument(..., help="Directory of the later canonical snapshot.")


def _print_snapshot_diff_sections(result: SnapshotDiff) -> None:
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

    _print_snapshot_diff_sections(result)


_WATCH_STATE_DIR_OPTION = typer.Option(
    Path(".si") / "watch",
    "--state-dir",
    help=(
        "Directory holding this target's watch history (the same '.si/' convention "
        "'si research'/'.si/requirements.json' already use). Never deleted or pruned "
        "automatically -- grows by one snapshot per run."
    ),
)
_WATCH_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Also write this run's snapshot into this directory (in addition to --state-dir).",
)


@app.command()
def watch(
    target: str = _TARGET_ARGUMENT,
    state_dir: Path = _WATCH_STATE_DIR_OPTION,
    out: Path | None = _WATCH_OUT_OPTION,
) -> None:
    """Detect drift since the last 'si watch' run for this target.

    Runs discovery and analysis exactly like `si diagnose`, then compares
    the result against the snapshot recorded under `--state-dir` by the
    previous `si watch` run for this target, using the same diff engine
    `si diff` does. The first run for a given `--state-dir` has nothing to
    compare against yet, so it only records a baseline.

    Deliberately not a daemon: this process runs once and exits, exactly
    like every other `si` command. Each snapshot is written to its own
    immutable subdirectory of `--state-dir` (per `Snapshot.
    write_to_directory`'s own "never overwrite a prior snapshot in place"
    convention) with a small `latest.txt` pointer updated to it — nothing
    under `--state-dir` is ever deleted by this command. Repeating "on an
    interval" means invoking `si watch` again later (by hand, cron, or a
    CI schedule); this command never sleeps, polls, or backgrounds itself.
    """
    try:
        discovery = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = analyze_local_repository(discovery)
    snapshot = result.snapshot

    latest_pointer = state_dir / "latest.txt"
    baseline: Snapshot | None = None
    if latest_pointer.is_file():
        baseline_dir = state_dir / latest_pointer.read_text(encoding="utf-8").strip()
        if (baseline_dir / "manifest.json").is_file():
            baseline = Snapshot.read_from_directory(baseline_dir)

    if baseline is None:
        typer.echo(
            f"No prior watch snapshot found under {state_dir} -- recording this scan as the "
            "baseline for future 'si watch' runs."
        )
        typer.echo(f"Findings: {len(snapshot.findings)}")
    else:
        diff = diff_snapshots(baseline, snapshot)
        typer.echo(f"Baseline: {diff.from_snapshot_id}")
        typer.echo(f"Current:  {diff.to_snapshot_id}")
        if not diff.has_changes:
            typer.echo("No drift detected since the last watch run.")
        else:
            _print_snapshot_diff_sections(diff)

    snapshot_dir = state_dir / snapshot.id
    snapshot.write_to_directory(snapshot_dir)
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(snapshot.id, encoding="utf-8")

    if out is not None:
        out_snapshot_dir = out / snapshot.id
        snapshot.write_to_directory(out_snapshot_dir)
        typer.echo(f"\nSnapshot written to {out_snapshot_dir}")


_DASHBOARD_OUT_OPTION = typer.Option(
    Path("si-dashboard"), "--out", help="Directory to write the dashboard and snapshot into."
)
_DASHBOARD_COMPARE_OPTION = typer.Option(
    None,
    "--compare-with",
    help="An earlier canonical snapshot directory (from --out on another command) to diff "
    "against for the Changes screen. Also the accumulator directory to read: any "
    "Proposal/ExecutionRecord/Verification/Approval/ResearchResult recorded into it via "
    "--record on other commands is merged into the rendered snapshot, deduplicated by id.",
)
_DASHBOARD_CHECK_UPDATES_OPTION = typer.Option(
    False,
    "--check-updates",
    help="Also run Component Update Intelligence (network requests to pypi/npm/cargo/go/maven) "
    "and include it.",
)
_DASHBOARD_CHECK_VULNERABILITIES_OPTION = typer.Option(
    False,
    "--check-vulnerabilities",
    help=(
        "With --check-updates, also look up known vulnerabilities (OSV.dev) for each "
        "resolved version. Ignored without --check-updates."
    ),
)


@app.command()
def dashboard(
    target: str = _TARGET_ARGUMENT,
    out: Path = _DASHBOARD_OUT_OPTION,
    compare_with: Path | None = _DASHBOARD_COMPARE_OPTION,
    check_updates: bool = _DASHBOARD_CHECK_UPDATES_OPTION,
    check_vulnerabilities: bool = _DASHBOARD_CHECK_VULNERABILITIES_OPTION,
) -> None:
    """Generate the interactive System Intelligence Console for a local target.

    Runs discovery and analysis, then writes a self-contained `dashboard.html`
    (no CDN, viewable offline via file://) plus the canonical JSON snapshot
    into `--out`. This is read-heavy by design: nothing it renders can merge,
    delete, force-push, or write to any remote. `--compare-with` both
    populates the Changes screen (diffed against that earlier snapshot's
    components/findings) and supplies the Proposals/Executions/
    Verifications/Approvals/Research screens: a fresh scan never carries
    those forward on its own, so without `--compare-with` pointed at
    whatever directory `--record` on other commands has been accumulating
    into, those screens are correctly empty rather than showing stale data.
    `--check-updates` adds a network request per pypi/npm/cargo/go/maven dependency
    (skipped by default, unlike `si report`/`si diagnose`, which never
    touch the network at all); `--check-vulnerabilities` adds one more
    per resolved version, for a known-vulnerability lookup (OSV.dev).
    """
    try:
        discovery = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = analyze_local_repository(discovery)
    snapshot = result.snapshot.model_copy(
        update={"recommendations": generate_recommendations(result.snapshot.findings)}
    )

    previous_snapshot = None
    if compare_with is not None:
        if not (compare_with / "manifest.json").is_file():
            typer.echo(f"error: {compare_with} has no manifest.json", err=True)
            raise typer.Exit(code=1)
        previous_snapshot = Snapshot.read_from_directory(compare_with)
        # The Changes diff below compares this fresh `snapshot` against the
        # untouched `previous_snapshot` — merging accumulated audit-trail
        # records here never affects that, since diff_snapshots only looks
        # at components/capabilities/dependencies/findings.
        merged_research = _merge_by_id(snapshot.research, previous_snapshot.research)
        snapshot = snapshot.model_copy(
            update={
                "proposals": _merge_by_id(snapshot.proposals, previous_snapshot.proposals),
                "executions": _merge_by_id(snapshot.executions, previous_snapshot.executions),
                "verification": _merge_by_id(snapshot.verification, previous_snapshot.verification),
                "approvals": _merge_by_id(snapshot.approvals, previous_snapshot.approvals),
                "research": merged_research,
                # A fresh scan never has research to derive Component.trust_level
                # from (si diagnose alone never populates it) — re-derive now
                # that --compare-with may have brought some in.
                "components": infer_trust_levels(snapshot.components, merged_research),
            }
        )

    update_check = None
    if check_updates:
        vulnerability_providers = _vulnerability_providers() if check_vulnerabilities else None
        update_check = check_dependency_updates(
            snapshot.components,
            _update_providers(),
            snapshot.relationships,
            vulnerability_providers,
        )

    data = build_dashboard_data(
        snapshot, previous_snapshot=previous_snapshot, update_check=update_check
    )

    out.mkdir(parents=True, exist_ok=True)
    dashboard_path = out / "dashboard.html"
    dashboard_path.write_text(generate_dashboard_html(data), encoding="utf-8")
    snapshot_dir = out / snapshot.id
    snapshot.write_to_directory(snapshot_dir)

    typer.echo(f"Dashboard written to {dashboard_path}")
    typer.echo(f"Snapshot written to {snapshot_dir}")


_QUERY_ARGUMENT = typer.Argument(..., help="Search query, e.g. 'python markdown parser'.")
_RESEARCH_LIMIT_OPTION = typer.Option(10, "--limit", help="Maximum candidates to return.")
_NO_CACHE_OPTION = typer.Option(False, "--no-cache", help="Bypass the research cache.")
_CACHE_DIR_OPTION = typer.Option(
    Path(".si") / "research-cache", "--cache-dir", help="Directory for the research cache."
)
_RESEARCH_RECORD_OPTION = typer.Option(
    None,
    "--record",
    help=(
        "An existing canonical snapshot directory (from --out on another command) to append "
        "these results to, so 'si dashboard' can show them later."
    ),
)
_RESEARCH_PROVIDER_OPTION = typer.Option(
    "github",
    "--provider",
    help=(
        "Which read-only source to search: 'github' (repositories; license/activity/star "
        "signals available) or 'mcp-registry' (the official MCP server registry; that "
        "registry's own schema carries no license/maintenance field, so those stay unknown "
        "for every result — being listed there proves namespace ownership, not quality)."
    ),
)

_ACTIVITY_LABEL = {True: "active", False: "stale", None: "unknown"}
_RESEARCH_PROVIDER_ERRORS: tuple[type[Exception], ...] = (GitHubResearchError, MCPRegistryError)


def _research_provider(provider_name: str) -> ResearchProvider:
    if provider_name == "github":
        return GitHubResearchProvider(token=os.environ.get("GITHUB_TOKEN"))
    if provider_name == "mcp-registry":
        return MCPRegistryResearchProvider()
    typer.echo(
        f"error: unknown --provider {provider_name!r} (expected 'github' or 'mcp-registry')",
        err=True,
    )
    raise typer.Exit(code=1)


@app.command()
def research(
    query: str = _QUERY_ARGUMENT,
    limit: int = _RESEARCH_LIMIT_OPTION,
    no_cache: bool = _NO_CACHE_OPTION,
    cache_dir: Path = _CACHE_DIR_OPTION,
    record: Path | None = _RESEARCH_RECORD_OPTION,
    provider_name: str = _RESEARCH_PROVIDER_OPTION,
) -> None:
    """Search for existing solutions before proposing something new.

    Read-only — only ever issues GET requests. Candidates are ranked by
    license presence, recent activity, and archived status; star count is
    shown for reference only and never used to rank (ADR-009). Several
    scoring dimensions (functional fit, security posture, ...) cannot be
    determined from either provider's response and are reported as unknown
    rather than guessed — for `--provider mcp-registry` this includes
    license and activity themselves, since that registry's schema doesn't
    carry them at all.
    """
    provider = _research_provider(provider_name)
    cache = ResearchCache(directory=cache_dir)

    results = None if no_cache else cache.get(provider.name, query)
    from_cache = results is not None
    if results is None:
        try:
            results = provider.search(query, limit=limit)
        except _RESEARCH_PROVIDER_ERRORS as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        cache.set(provider.name, query, results)

    if not results:
        typer.echo(f"No candidates found for {query!r}.")
        return

    if record is not None:
        for result in results:
            _append_json_record(record, "research.json", result)

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


def _update_providers() -> dict[str, ComponentUpdateProvider]:
    # Constructed fresh per call (like `research()`'s GitHubResearchProvider)
    # rather than as a module-level singleton, so each invocation's HTTP
    # layer can be independently injected/tested.
    return {
        "pypi": PyPIUpdateProvider(),
        "npm": NpmUpdateProvider(),
        "cargo": CratesIoUpdateProvider(),
        "go": GoProxyUpdateProvider(),
        "maven": MavenCentralUpdateProvider(),
    }


def _vulnerability_providers() -> dict[str, VulnerabilityProvider]:
    # OSV.dev's own ecosystem names are case-sensitive ("PyPI"/"crates.io"/
    # "Go"/"Maven", not "pypi"/"cargo"/"go"/"maven") -- confirmed against the
    # live API, not guessed.
    return {
        "pypi": OSVVulnerabilityProvider("pypi", "PyPI"),
        "npm": OSVVulnerabilityProvider("npm", "npm"),
        "cargo": OSVVulnerabilityProvider("cargo", "crates.io"),
        "go": OSVVulnerabilityProvider("go", "Go"),
        "maven": OSVVulnerabilityProvider("maven", "Maven"),
    }


_CHECK_UPDATES_PROPOSE_OPTION = typer.Option(
    False,
    "--propose",
    help="Also print a component_update Proposal for each actionable verdict.",
)
_CHECK_UPDATES_RECORD_OPTION = typer.Option(
    None,
    "--record",
    help=(
        "An existing canonical snapshot directory (from --out on another command) to append "
        "generated Proposals to, so 'si dashboard' can show them later."
    ),
)
_CHECK_UPDATES_PLAN_OUT_OPTION = typer.Option(
    None,
    "--plan-out",
    help=(
        "Directory to write a ready-to-run ChangePlan JSON file for each actionable verdict "
        "this can turn into one deterministically (today: a pypi, npm, or go dependency "
        "pinned to an exact version, or a Cargo.toml dependency using its simple string "
        "form, per proposals.change_plan_for_component_update). Feed the result "
        "straight to 'si execute <file> <target> --approve'. Verdicts this can't determine "
        "deterministically (range constraints, other ecosystems, Cargo's table form) are "
        "skipped, not guessed."
    ),
)
_CHECK_UPDATES_VULNERABILITIES_OPTION = typer.Option(
    False,
    "--check-vulnerabilities",
    help=(
        "Also look up known vulnerabilities (OSV.dev) for the current/available version of "
        "each pypi/npm/cargo/go/maven dependency. Off by default: one extra network request per "
        "resolved version, independent of whether an update is available."
    ),
)


@app.command(name="check-updates")
def check_updates(
    target: str = _TARGET_ARGUMENT,
    propose: bool = _CHECK_UPDATES_PROPOSE_OPTION,
    record: Path | None = _CHECK_UPDATES_RECORD_OPTION,
    plan_out: Path | None = _CHECK_UPDATES_PLAN_OUT_OPTION,
    check_vulnerabilities: bool = _CHECK_UPDATES_VULNERABILITIES_OPTION,
) -> None:
    """Component Update Intelligence: current vs. available state for every dependency.

    Read-only, but unlike `si diagnose` this makes network requests (one GET
    per pypi/npm/cargo/go/maven dependency, to the public registries) —
    closer in kind to `si research`. Dependencies in an ecosystem with no
    configured provider (anything but pypi/npm/cargo/go/maven today) are skipped, not reported
    as unknown.

    Never concludes `UPDATE_RECOMMENDED` from a version number alone: see
    `analysis.update_intelligence` and `core.enums.UpdateVerdict` — that
    verdict requires capability/dependency/interface impact to have
    actually been evaluated, which today's providers rarely can for an
    arbitrary third-party package. `REVIEW_REQUIRED` is the common, honest
    outcome, not a shortcoming of this command. `--propose` (closing
    "... -> Impact -> Recommendation -> Proposal") never produces a
    Proposal for a NOT_ADVISABLE/NO_UPDATE_AVAILABLE/UNKNOWN verdict —
    there is nothing to propose in those cases. `--plan-out` closes
    "... -> Proposal -> ChangePlan" one step further, but only where doing
    so is fully deterministic (a pypi, npm, or go dependency pinned to an
    exact version, or a Cargo.toml dependency using its simple string
    form) — see `proposals.change_plan_for_component_update`. Every
    other case still has no automatic path to a ChangePlan; that remains a
    job for a human or an external implementer, never guessed here.

    `--check-vulnerabilities` additionally checks each resolved current/
    available version against OSV.dev for known vulnerabilities
    (`ImpactAssessment.current_version_advisories`/`available_version_
    advisories`) — a separate, informational fact from the update verdict
    itself: a known-vulnerable current version never by itself unlocks
    `UPDATE_RECOMMENDED` (see `analysis.update_intelligence.assess_impact`).
    """
    try:
        discovery = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = analyze_local_repository(discovery)
    providers = _update_providers()
    vulnerability_providers = _vulnerability_providers() if check_vulnerabilities else None
    check = check_dependency_updates(
        result.snapshot.components,
        providers,
        result.snapshot.relationships,
        vulnerability_providers,
    )

    if not check.assessments and not check.unavailable:
        typer.echo(
            "No dependencies found in an ecosystem with a configured update "
            f"provider ({', '.join(sorted(providers))})."
        )
        return

    for assessment in check.assessments:
        diff = assessment.state_diff
        typer.echo(f"\n- {diff.identity.name} ({diff.identity.distribution_source})")
        typer.echo(f"    current: {diff.from_state.version or 'unknown'}")
        typer.echo(f"    available: {diff.to_state.version or 'unknown'}")
        typer.echo(
            f"    verdict: {assessment.verdict.value} ({assessment.verdict_confidence.value})"
        )
        typer.echo(f"    why: {assessment.verdict_rationale}")
        if assessment.affected_entity_ids:
            typer.echo(f"    affects: {', '.join(assessment.affected_entity_ids)}")
        if assessment.unknown_dimensions:
            typer.echo(f"    unresolved dimensions: {', '.join(assessment.unknown_dimensions)}")
        if assessment.current_version_advisories:
            ids = ", ".join(
                f"{a.id} ({a.severity})" if a.severity else a.id
                for a in assessment.current_version_advisories
            )
            typer.echo(f"    known vulnerabilities (current version): {ids}")
        if assessment.available_version_advisories:
            ids = ", ".join(
                f"{a.id} ({a.severity})" if a.severity else a.id
                for a in assessment.available_version_advisories
            )
            typer.echo(f"    known vulnerabilities (available version): {ids}")

    if check.unavailable:
        typer.echo(
            f"\n{len(check.unavailable)} lookup(s) could not be completed (source unavailable):"
        )
        for failure in check.unavailable:
            typer.echo(f"  - {failure.ecosystem}:{failure.name}: {failure.message}")

    if propose or record is not None:
        proposals = [
            p for p in (propose_component_update(a) for a in check.assessments) if p is not None
        ]
        if propose:
            if not proposals:
                typer.echo("\nNo actionable verdict produced a Proposal.")
            for proposal in proposals:
                typer.echo(f"\nProposal ({proposal.kind}): {proposal.problem}")
                typer.echo(f"    required permission: {proposal.required_permission_level.name}")
        if record is not None:
            for proposal in proposals:
                _append_json_record(record, "proposals.json", proposal)

    if plan_out is not None:
        plan_out.mkdir(parents=True, exist_ok=True)
        written = 0
        for assessment in check.assessments:
            change_plan = change_plan_for_component_update(assessment, Path(target))
            if change_plan is None:
                continue
            plan_path = plan_out / f"{change_plan.branch_name.replace('/', '-')}.json"
            plan_path.write_text(
                json.dumps(change_plan.to_plan_file_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            typer.echo(f"ChangePlan written to {plan_path}")
            written += 1
        if written == 0:
            typer.echo(
                "\nNo ChangePlan could be generated deterministically for any assessment "
                "(today: pypi/npm/go exact-pin version bumps, or a Cargo.toml simple "
                "string form pin)."
            )


@app.command()
def improve(target: str = _TARGET_ARGUMENT) -> None:
    """Generate a ranked improvement plan: discovery, analysis, then recommendations.

    Every recommendation traces back to a Finding's own evidence — this
    does not invent anything Phase 3's analyzers didn't already find.
    """
    try:
        discovery = discover_local_repository(target)
    except TargetResolutionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    result = analyze_local_repository(discovery)
    recommendations = generate_recommendations(result.snapshot.findings)

    if not recommendations:
        typer.echo("No recommendations — no findings to act on.")
        return

    typer.echo(f"{len(recommendations)} recommendation(s), highest priority first:\n")
    for rec in recommendations:
        typer.echo(f"- {rec.objective}")
        typer.echo(f"    why: {rec.rationale}")
        typer.echo(f"    effort: {rec.estimated_effort}, risk: {rec.risk}")
        typer.echo(f"    confidence: {rec.confidence.value}")


_PROBLEM_ARGUMENT = typer.Argument(..., help="The need or problem statement, in plain language.")
_REQUIREMENT_OPTION = typer.Option(
    [], "--requirement", help="A requirement the solution must satisfy. Repeatable."
)
_RESEARCH_QUERY_OPTION = typer.Option(
    None, "--research-query", help="If given, search GitHub for candidates before deciding."
)
_CONFIRM_FIT_OPTION = typer.Option(
    False,
    "--confirm-fit",
    help=(
        "Assert that a human (or other process) has already verified the best "
        "candidate's functional fit. Never set this from research data alone."
    ),
)
_PROPOSAL_OUT_OPTION = typer.Option(
    None, "--out", help="File to write the proposal as JSON. Skipped if omitted."
)
_PROPOSAL_RECORD_OPTION = typer.Option(
    None,
    "--record",
    help=(
        "An existing canonical snapshot directory (from --out on another command) to append "
        "this Proposal to, so 'si dashboard' can show it later."
    ),
)
_PROPOSAL_HANDOFF_OUT_OPTION = typer.Option(
    None,
    "--handoff-out",
    help=(
        "File to write a self-contained handoff packet to (execution.handoff."
        "build_handoff_packet): the Proposal, --target, and the exact JSON shape "
        "'si execute' expects back. For creation/adoption/integration Proposals, System "
        "Intelligence has no deterministic way to author the actual diff (ADR-007) — this "
        "hands that off to a human or an external implementer such as Claude Code, never "
        "invoking one itself. Requires --target."
    ),
)
_PROPOSAL_TARGET_OPTION = typer.Option(
    None,
    "--target",
    help=(
        "Local repository path an implementer would apply this Proposal against. "
        "Required by --handoff-out."
    ),
)
_PROPOSAL_TARGET_KIND_OPTION = typer.Option(
    None,
    "--target-kind",
    help=(
        "What kind of component this Proposal is for (e.g. 'skill', 'agent', "
        "'mcp_server', 'package'; see ComponentKind) — shapes test_strategy/"
        "documentation_requirements to how that kind is actually verified in practice, "
        "and populates interfaces with that kind's own known discovery convention "
        "(e.g. a Skill's SKILL.md, an Agent's .claude/agents/*.md), where one exists."
    ),
)


@app.command()
def propose(
    problem: str = _PROBLEM_ARGUMENT,
    requirement: list[str] = _REQUIREMENT_OPTION,
    research_query: str | None = _RESEARCH_QUERY_OPTION,
    confirm_fit: bool = _CONFIRM_FIT_OPTION,
    out: Path | None = _PROPOSAL_OUT_OPTION,
    record: Path | None = _PROPOSAL_RECORD_OPTION,
    target: str | None = _PROPOSAL_TARGET_OPTION,
    handoff_out: Path | None = _PROPOSAL_HANDOFF_OUT_OPTION,
    target_kind: str | None = _PROPOSAL_TARGET_KIND_OPTION,
) -> None:
    """Produce a concrete proposal: adopt, integrate, or create (docs/07-improvement-engine.md).

    Without `--research-query`, no external solution is searched for and
    the result is always a creation proposal. `--confirm-fit` must reflect
    an actual verification you (or another process) performed — this
    command never infers functional fit from research metadata alone.
    """
    if handoff_out is not None and target is None:
        typer.echo("error: --handoff-out requires --target.", err=True)
        raise typer.Exit(code=1)
    parsed_target_kind: ComponentKind | None = None
    if target_kind is not None:
        try:
            parsed_target_kind = ComponentKind(target_kind)
        except ValueError:
            valid = ", ".join(sorted(k.value for k in ComponentKind))
            typer.echo(
                f"error: unknown --target-kind {target_kind!r} (expected one of: {valid})",
                err=True,
            )
            raise typer.Exit(code=1) from None
    research_results = []
    if research_query:
        provider = GitHubResearchProvider(token=os.environ.get("GITHUB_TOKEN"))
        try:
            research_results = provider.search(research_query)
        except GitHubResearchError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    proposal = propose_solution(
        problem,
        requirements=requirement,
        research_results=research_results,
        functional_fit_confirmed=confirm_fit,
        target_kind=parsed_target_kind,
    )

    typer.echo(f"Proposal kind: {proposal.kind}")
    typer.echo(f"Problem: {proposal.problem}")
    if proposal.requirements:
        typer.echo(f"Requirements: {', '.join(proposal.requirements)}")
    if proposal.proposed_component_name:
        typer.echo(f"Proposed component: {proposal.proposed_component_name}")
    if proposal.alternatives_considered:
        typer.echo(f"Alternatives considered: {', '.join(proposal.alternatives_considered)}")
    if proposal.why_existing_solutions_insufficient:
        typer.echo(f"Why not sufficient as-is: {proposal.why_existing_solutions_insufficient}")
    if proposal.capabilities:
        typer.echo(f"Capabilities: {', '.join(proposal.capabilities)}")
    if proposal.interfaces:
        typer.echo(f"Interfaces: {', '.join(proposal.interfaces)}")
    if proposal.test_strategy:
        typer.echo(f"Test strategy: {proposal.test_strategy}")
    if proposal.documentation_requirements:
        typer.echo(f"Documentation requirements: {proposal.documentation_requirements}")
    if proposal.rollback_strategy:
        typer.echo(f"Rollback strategy: {proposal.rollback_strategy}")
    typer.echo(f"Required permission level: {proposal.required_permission_level.name}")

    if out is not None:
        out.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"\nProposal written to {out}")

    if record is not None:
        _append_json_record(record, "proposals.json", proposal)

    if handoff_out is not None and target is not None:
        packet = build_handoff_packet(proposal, target)
        handoff_out.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        typer.echo(f"\nHandoff packet written to {handoff_out}")


_REQUEST_ARGUMENT = typer.Argument(
    None,
    help=(
        "A known intent name (see 'si plan --list') or free text, e.g. 'Diagnose this repository.'"
    ),
)
_LIST_INTENTS_OPTION = typer.Option(
    False, "--list", help="List known intent names and exit, ignoring REQUEST."
)


@app.command()
def plan(
    request: str | None = _REQUEST_ARGUMENT, list_intents: bool = _LIST_INTENTS_OPTION
) -> None:
    """Show which capabilities a request would run, without running any of them.

    docs/design/docs/10-plugin-skill-system.md: "Given an intent, select
    the minimum capability set required. ... It should not blindly
    activate every installed capability." This command makes that
    selection visible and auditable before anything executes.
    """
    if list_intents:
        for name in sorted(INTENTS):
            typer.echo(name)
        return

    if request is None:
        typer.echo("error: REQUEST is required unless --list is given.", err=True)
        raise typer.Exit(code=1)

    if request in INTENTS:
        intent = request
    else:
        intent = classify_intent(request)
        typer.echo(f"Classified {request!r} as intent {intent!r}.")

    capability_ids = resolve_intent(intent)
    typer.echo(f"\nIntent {intent!r} would run {len(capability_ids)} capabilit(y/ies):")
    for capability_id in capability_ids:
        typer.echo(f"  - {capability_id}: {CAPABILITIES[capability_id].description}")


class _Identifiable(Protocol):
    id: str


_T = TypeVar("_T", bound=_Identifiable)


def _merge_by_id(current: list[_T], accumulated: list[_T]) -> list[_T]:
    """Combine two lists of the same record type, deduplicated by `.id`.

    Used to fold a `--record`-accumulated snapshot directory's Proposals/
    ExecutionRecords/Verifications/Approvals/ResearchResults into a freshly
    scanned Snapshot for `si dashboard`. `current` wins on an id collision.
    """
    merged: dict[str, _T] = {record.id: record for record in accumulated}
    merged.update({record.id: record for record in current})
    return list(merged.values())


def _append_json_record(directory: Path, filename: str, record: BaseModel) -> None:
    """Append `record` to a JSON list file, creating it if needed.

    Used only to attach `ExecutionRecord`/`Verification` results to an
    existing canonical snapshot directory (`--record`) so a later
    `si dashboard` invocation on that same directory can show them —
    otherwise both live only for the lifetime of one CLI invocation.
    """
    path = directory / filename
    existing: list[object] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    existing.append(record.model_dump(mode="json"))
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


_PLAN_FILE_ARGUMENT = typer.Argument(
    ...,
    help=(
        "JSON file describing the ChangePlan: branch_name, commit_message, "
        "files (path -> content), and optionally description."
    ),
)
_EXECUTE_TARGET_ARGUMENT = typer.Argument(".", help="Local repository to apply the plan to.")
_APPROVE_OPTION = typer.Option(
    False,
    "--approve",
    help="Actually apply the plan. Without this flag, only a dry-run preview is printed.",
)
_APPROVAL_FILE_OPTION = typer.Option(
    None,
    "--approval-file",
    help="JSON file with an Approval record (or a list of them) authorizing this action.",
)
_EXECUTE_RECORD_OPTION = typer.Option(
    None,
    "--record",
    help=(
        "An existing canonical snapshot directory (from --out on another command) to append "
        "this run's ExecutionRecord (and any Approval actually supplied via --approval-file) "
        "to, so 'si dashboard' can show them later. Optional — without it, this run's result "
        "is only ever printed, not persisted."
    ),
)
_PUSH_OPTION = typer.Option(
    False,
    "--push",
    help=(
        "After applying locally, also push the branch and open it as a Draft PR "
        "(execution.github_pr, gated separately from the local step — see --repo). "
        "Requires the GITHUB_TOKEN environment variable and --repo. Never merges, "
        "closes, approves, or force-pushes."
    ),
)
_PUSH_REPO_OPTION = typer.Option(
    None,
    "--repo",
    help="'owner/repo' to push to and open the Draft PR against. Required with --push.",
)
_PUSH_BASE_OPTION = typer.Option(
    "main", "--base", help="Base branch for the Draft PR (only used with --push)."
)


@app.command()
def execute(
    plan_file: Path = _PLAN_FILE_ARGUMENT,
    target: str = _EXECUTE_TARGET_ARGUMENT,
    approve: bool = _APPROVE_OPTION,
    approval_file: Path | None = _APPROVAL_FILE_OPTION,
    record: Path | None = _EXECUTE_RECORD_OPTION,
    push: bool = _PUSH_OPTION,
    repo: str | None = _PUSH_REPO_OPTION,
    base: str = _PUSH_BASE_OPTION,
) -> None:
    """Preview, or apply, a local ChangePlan (branch + commit), optionally pushed as a Draft PR.

    Without `--approve` this only prints what would happen
    (`ChangePlan.preview_lines()`) and touches nothing. With `--approve`,
    `execution.local_git.apply_plan` still requires a matching `Approval`
    record via `--approval-file` unless the plan's required permission
    level is within the default maximum — human approval is never
    bypassed. Without `--push`, this never touches a remote at all.

    `--push` additionally pushes the branch and opens it as a Draft PR
    (`execution.github_pr.open_draft_pr_for_plan`) against `--repo`
    (required, `owner/repo`) — gated by its **own** `create_draft_pr`
    policy check, separate from the local step's: an `--approval-file`
    covering only the local action does not also authorize the push.
    Requires the `GITHUB_TOKEN` environment variable. This never merges,
    closes, approves, or force-pushes, and never performs a
    `core.enums.FORBIDDEN_BY_DEFAULT_ACTIONS` action either way.
    """
    try:
        raw_plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        typer.echo(f"error: could not read plan file: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        plan_kwargs: dict[str, object] = {
            "branch_name": raw_plan["branch_name"],
            "commit_message": raw_plan["commit_message"],
            "files": raw_plan["files"],
            "description": raw_plan.get("description", ""),
            "evidence_summary": raw_plan.get("evidence_summary", []),
        }
        if "required_permission_level" in raw_plan:
            plan_kwargs["required_permission_level"] = PermissionLevel[
                raw_plan["required_permission_level"]
            ]
        plan = ChangePlan(**plan_kwargs)  # type: ignore[arg-type]
    except (KeyError, TypeError) as exc:
        typer.echo(f"error: invalid plan file: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Plan preview:")
    for line in plan.preview_lines():
        typer.echo(f"  - {line}")

    if not approve:
        typer.echo("\nDry run only (pass --approve to apply). Nothing was changed.")
        return

    approvals: list[Approval] = []
    if approval_file is not None:
        try:
            raw_approvals = json.loads(approval_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            typer.echo(f"error: could not read approval file: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        raw_list = raw_approvals if isinstance(raw_approvals, list) else [raw_approvals]
        approvals = [Approval.model_validate(item) for item in raw_list]

    try:
        result = apply_plan(plan, Path(target), approvals=approvals)
    except LocalGitError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if record is not None:
        _append_json_record(
            record,
            "executions.json",
            ExecutionRecord(
                action="create_local_branch_and_commit",
                target=target,
                plan_description=plan.description,
                branch_name=result.branch_name,
                commit_sha=result.commit_sha,
                files_written=result.files_written,
                applied=result.applied,
                decision_reason=result.decision.reason,
            ),
        )
        # Records the Approval(s) actually supplied via --approval-file, not
        # a fabricated one — an execution denied for lack of an approval
        # writes no approvals.json entry.
        for approval in approvals:
            _append_json_record(record, "approvals.json", approval)
        _append_json_record(
            record,
            "audit_log.json",
            audit_log_entry(
                result.decision,
                action="create_local_branch_and_commit",
                target=target,
                intent=plan.description or plan.commit_message,
                actor=approvals[0].actor if approvals else "system:cli",
                correlation_id=result.commit_sha,
            ),
        )

    if not result.applied:
        typer.echo(f"\nDenied: {result.decision.reason}")
        raise typer.Exit(code=1)

    typer.echo(f"\nApplied: branch {result.branch_name!r}, commit {result.commit_sha}")
    typer.echo(f"Files written: {', '.join(result.files_written)}")

    if not push:
        return

    if not repo or "/" not in repo:
        typer.echo("error: --push requires --repo in the form 'owner/repo'", err=True)
        raise typer.Exit(code=1)
    owner, repo_name = repo.split("/", 1)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        typer.echo("error: --push requires the GITHUB_TOKEN environment variable", err=True)
        raise typer.Exit(code=1)

    try:
        pr_result = open_draft_pr_for_plan(
            plan,
            Path(target),
            owner=owner,
            repo=repo_name,
            base=base,
            token=token,
            approvals=approvals,
        )
    except GitHubPRError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    pull_request = pr_result.pull_request
    if record is not None:
        _append_json_record(
            record,
            "executions.json",
            ExecutionRecord(
                action="create_draft_pr",
                target=f"{owner}/{repo_name}",
                plan_description=plan.description,
                branch_name=plan.branch_name,
                pull_request_number=pull_request.number if pull_request else None,
                pull_request_url=pull_request.html_url if pull_request else None,
                applied=pr_result.applied,
                decision_reason=pr_result.decision.reason,
            ),
        )
        _append_json_record(
            record,
            "audit_log.json",
            audit_log_entry(
                pr_result.decision,
                action="create_draft_pr",
                target=f"{owner}/{repo_name}",
                intent=plan.description or plan.commit_message,
                actor=approvals[0].actor if approvals else "system:cli",
                correlation_id=str(pull_request.number) if pull_request else None,
            ),
        )

    if not pr_result.applied or pull_request is None:
        typer.echo(f"\nDraft PR denied: {pr_result.decision.reason}")
        raise typer.Exit(code=1)

    typer.echo(f"\nDraft PR opened: {pull_request.html_url}")


_VERIFY_COMMAND_ARGUMENT = typer.Argument(
    ..., help="Test command to run, e.g. 'pytest -q'. Parsed shell-style, so quoting works."
)
_VERIFY_TARGET_OPTION = typer.Option(".", "--target", help="Repository to run the command in.")
_VERIFY_RECORD_OPTION = typer.Option(
    None,
    "--record",
    help=(
        "An existing canonical snapshot directory (from --out on another command) to append "
        "this run's Verification to, so 'si dashboard' can show it later."
    ),
)
_VERIFY_COMPONENT_OPTION = typer.Option(
    None,
    "--component",
    help=(
        "A Component id from an existing snapshot's components.json this check is about "
        "(e.g. one Skill's own conformance/test command) — attaches it to the recorded "
        "Verification so 'si dashboard' can show it on that Component's detail view. Omit "
        "when the check isn't about one specific discovered Component."
    ),
)
_VERIFY_BEFORE_SNAPSHOT_OPTION = typer.Option(
    None,
    "--before-snapshot",
    help="A canonical snapshot directory captured before the change, for regression "
    "detection (findings present after the change but not before). Must be given "
    "together with --after-snapshot.",
)
_VERIFY_AFTER_SNAPSHOT_OPTION = typer.Option(
    None,
    "--after-snapshot",
    help="A canonical snapshot directory captured after the change, for regression "
    "detection. Must be given together with --before-snapshot.",
)


def _load_verification_snapshot(directory: Path) -> Snapshot:
    if not (directory / "manifest.json").is_file():
        typer.echo(f"error: {directory} has no manifest.json", err=True)
        raise typer.Exit(code=1)
    return Snapshot.read_from_directory(directory)


@app.command()
def verify(
    command: str = _VERIFY_COMMAND_ARGUMENT,
    target: str = _VERIFY_TARGET_OPTION,
    record: Path | None = _VERIFY_RECORD_OPTION,
    component: str | None = _VERIFY_COMPONENT_OPTION,
    before_snapshot: Path | None = _VERIFY_BEFORE_SNAPSHOT_OPTION,
    after_snapshot: Path | None = _VERIFY_AFTER_SNAPSHOT_OPTION,
) -> None:
    """Run a test command locally and report the result (R10).

    Pass/fail is taken directly from the command's own exit code — never
    inferred or assumed. Passing both --before-snapshot and --after-snapshot
    (two canonical snapshot directories, e.g. from 'si diagnose --out'
    before and after applying a change) additionally computes
    regressions_found from their diff's added findings — never guessed
    from the command's own pass/fail alone. Exits non-zero if the command
    failed or a regression was found.
    """
    if (before_snapshot is None) != (after_snapshot is None):
        typer.echo("error: --before-snapshot and --after-snapshot must be given together", err=True)
        raise typer.Exit(code=1)

    before_snap = (
        _load_verification_snapshot(before_snapshot) if before_snapshot is not None else None
    )
    after_snap = _load_verification_snapshot(after_snapshot) if after_snapshot is not None else None

    try:
        verification = run_verification(
            Path(target),
            shlex.split(command),
            component_id=component,
            before_snapshot=before_snap,
            after_snapshot=after_snap,
        )
    except VerificationError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if record is not None:
        _append_json_record(record, "verification.json", verification)

    status = "PASSED" if verification.tests_passed else "FAILED"
    typer.echo(f"Command: {verification.tests_run[0]}")
    typer.echo(f"Result: {status}")
    if verification.regressions_found:
        typer.echo(f"\nRegressions detected ({len(verification.regressions_found)}):")
        for regression in verification.regressions_found:
            typer.echo(f"  - {regression}")
    if verification.evidence:
        typer.echo(f"\nOutput:\n{verification.evidence[0].observation}")

    if not verification.tests_passed or verification.regressions_found:
        raise typer.Exit(code=1)


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
