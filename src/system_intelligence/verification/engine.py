"""Verification engine: run a test command locally and record the outcome.

Phase 8 scope (R10, docs/design/docs/02-requirements.md): execute a
configured command and produce a `Verification` record from its actual
exit code and output. Pass/fail is never inferred from anything but the
process's own return code.

Regression detection (R10's other half, "before/after comparison") reuses
`reporting.diff.diff_snapshots` rather than re-deriving one: when a caller
supplies both a before- and after-change `Snapshot`, `regressions_found`
is populated from that diff's `added_findings` (findings observed after
the change that were not observed before) — never guessed from the test
command's own pass/fail alone, and left empty (not fabricated) when no
before/after pair is supplied.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.core.verification import Verification
from system_intelligence.reporting.diff import diff_snapshots

_MAX_OUTPUT_CHARS = 4000


class VerificationError(RuntimeError):
    """Raised when the verification command itself cannot be located or run."""


def run_verification(
    repo_root: Path,
    command: list[str],
    *,
    proposal_id: str | None = None,
    change_id: str | None = None,
    before_snapshot_id: str | None = None,
    after_snapshot_id: str | None = None,
    component_id: str | None = None,
    before_snapshot: Snapshot | None = None,
    after_snapshot: Snapshot | None = None,
) -> Verification:
    """Run `command` in `repo_root` and record whether it passed.

    `command[0]` must resolve via `shutil.which`, so this can only invoke
    an existing executable already on PATH — never a shell string. A
    failing test run is a valid, recorded result and does not raise;
    `VerificationError` is raised only when the command itself cannot be
    located or executed at all.

    `before_snapshot`/`after_snapshot` are optional actual `Snapshot`
    objects used only to compute `regressions_found` (via
    `diff_snapshots`); when given, their own `.id` fills
    `before_snapshot_id`/`after_snapshot_id` unless the caller already
    passed an explicit id. Passing only one of the two snapshots is
    treated the same as passing neither — a diff needs both sides.
    """
    if not command:
        raise VerificationError("command must not be empty")

    executable = shutil.which(command[0])
    if executable is None:
        raise VerificationError(f"{command[0]!r} is not available on PATH")

    try:
        result = subprocess.run(  # nosec B603
            [executable, *command[1:]],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise VerificationError(f"failed to run {command!r}: {exc}") from exc

    passed = result.returncode == 0
    command_str = " ".join(command)
    output = (result.stdout + result.stderr).strip()[:_MAX_OUTPUT_CHARS]

    evidence = Evidence(
        kind=EvidenceKind.RUNTIME_TELEMETRY,
        source=command_str,
        locator=str(repo_root),
        observation=(
            f"Command {command_str!r} exited with code {result.returncode} "
            f"(passed={passed}). Output:\n{output}"
        ),
        confidence=Confidence.VERIFIED,
    )

    regressions_found: list[str] = []
    if before_snapshot is not None and after_snapshot is not None:
        before_snapshot_id = before_snapshot_id or before_snapshot.id
        after_snapshot_id = after_snapshot_id or after_snapshot.id
        diff = diff_snapshots(before_snapshot, after_snapshot)
        regressions_found = [f.statement for f in diff.added_findings]

    return Verification(
        proposal_id=proposal_id,
        change_id=change_id,
        before_snapshot_id=before_snapshot_id,
        after_snapshot_id=after_snapshot_id,
        component_id=component_id,
        tests_run=[command_str],
        tests_passed=passed,
        regressions_found=regressions_found,
        evidence=[evidence],
    )
