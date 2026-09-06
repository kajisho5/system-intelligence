"""`si` command-line entry point.

`si doctor`, `si version`, and `si inspect` are implemented. The remaining
commands from docs/design/docs/13-cli-and-ux.md (`diagnose`, `research`,
`design`, `improve`, `propose`, `execute`, `verify`, `report`, `diff`,
`watch`) are registered as explicit placeholders so `si --help` documents
the intended surface without claiming functionality that does not exist
yet.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import typer

from system_intelligence import __version__
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import ComponentKind
from system_intelligence.discovery import TargetResolutionError, discover_local_repository

app = typer.Typer(
    name="si",
    help=(
        "System Intelligence: discover, understand, audit, research, and improve software systems."
    ),
    no_args_is_help=True,
)

_PLANNED_COMMANDS = {
    "diagnose": "Structured health assessment of a target. Planned for Phase 2-3 (analysis).",
    "research": "External solution discovery. Planned for Phase 5.",
    "design": "Architecture/design proposal generation. Planned for Phase 6.",
    "improve": "Generate an improvement plan. Planned for Phase 6.",
    "propose": "Create a concrete change proposal. Planned for Phase 6.",
    "execute": "Perform an approved change. Planned for Phase 8 (human-approved execution).",
    "verify": "Validate a change and compare before/after state. Planned for Phase 8.",
    "report": "Generate the static HTML intelligence report. Planned for Phase 4.",
    "diff": "Compare two snapshots. Planned for Phase 4.",
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
