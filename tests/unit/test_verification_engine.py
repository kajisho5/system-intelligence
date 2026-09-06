from pathlib import Path

import pytest

from system_intelligence.core.entities import Target
from system_intelligence.core.enums import Confidence, Severity, TargetKind
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.verification.engine import VerificationError, run_verification


def _target() -> Target:
    return Target(name="repo", kind=TargetKind.LOCAL_PATH, locator="/repo")


def _finding(statement: str) -> Finding:
    return Finding(
        category="test_gap",
        severity=Severity.MEDIUM,
        statement=statement,
        confidence=Confidence.MEDIUM,
        evidence=[Evidence(kind=EvidenceKind.FILE, source="x", observation="x")],
    )


def test_run_verification_records_passing_command(tmp_path: Path) -> None:
    verification = run_verification(tmp_path, ["python3", "-c", "print('ok')"])

    assert verification.tests_passed is True
    assert verification.tests_run == ["python3 -c print('ok')"]
    assert len(verification.evidence) == 1
    assert "exited with code 0" in verification.evidence[0].observation
    assert "ok" in verification.evidence[0].observation


def test_run_verification_records_failing_command(tmp_path: Path) -> None:
    verification = run_verification(tmp_path, ["python3", "-c", "import sys; sys.exit(1)"])

    assert verification.tests_passed is False
    assert "exited with code 1" in verification.evidence[0].observation


def test_run_verification_empty_command_raises(tmp_path: Path) -> None:
    with pytest.raises(VerificationError, match="empty"):
        run_verification(tmp_path, [])


def test_run_verification_missing_executable_raises(tmp_path: Path) -> None:
    with pytest.raises(VerificationError, match="not available on PATH"):
        run_verification(tmp_path, ["definitely-not-a-real-executable-xyz"])


def test_run_verification_links_proposal_and_snapshot_ids(tmp_path: Path) -> None:
    verification = run_verification(
        tmp_path,
        ["python3", "-c", "pass"],
        proposal_id="proposal-1",
        change_id="change-1",
        before_snapshot_id="snapshot-before",
        after_snapshot_id="snapshot-after",
    )

    assert verification.proposal_id == "proposal-1"
    assert verification.change_id == "change-1"
    assert verification.before_snapshot_id == "snapshot-before"
    assert verification.after_snapshot_id == "snapshot-after"


def test_run_verification_links_component_id(tmp_path: Path) -> None:
    verification = run_verification(
        tmp_path, ["python3", "-c", "pass"], component_id="skill-ffmpeg"
    )

    assert verification.component_id == "skill-ffmpeg"


def test_run_verification_without_component_id_leaves_it_none(tmp_path: Path) -> None:
    verification = run_verification(tmp_path, ["python3", "-c", "pass"])

    assert verification.component_id is None


def test_run_verification_without_snapshots_never_reports_regressions(tmp_path: Path) -> None:
    verification = run_verification(tmp_path, ["python3", "-c", "pass"])

    assert verification.regressions_found == []


def test_run_verification_detects_new_finding_as_regression(tmp_path: Path) -> None:
    before = Snapshot(target=_target(), findings=[_finding("existing issue")])
    after = Snapshot(target=_target(), findings=[_finding("existing issue"), _finding("new issue")])

    verification = run_verification(
        tmp_path, ["python3", "-c", "pass"], before_snapshot=before, after_snapshot=after
    )

    assert verification.regressions_found == ["new issue"]
    assert verification.before_snapshot_id == before.id
    assert verification.after_snapshot_id == after.id


def test_run_verification_no_regressions_when_findings_unchanged(tmp_path: Path) -> None:
    before = Snapshot(target=_target(), findings=[_finding("existing issue")])
    after = Snapshot(target=_target(), findings=[_finding("existing issue")])

    verification = run_verification(
        tmp_path, ["python3", "-c", "pass"], before_snapshot=before, after_snapshot=after
    )

    assert verification.regressions_found == []


def test_run_verification_explicit_snapshot_id_overrides_snapshot_object_id(
    tmp_path: Path,
) -> None:
    before = Snapshot(target=_target())
    after = Snapshot(target=_target())

    verification = run_verification(
        tmp_path,
        ["python3", "-c", "pass"],
        before_snapshot=before,
        after_snapshot=after,
        before_snapshot_id="explicit-before",
        after_snapshot_id="explicit-after",
    )

    assert verification.before_snapshot_id == "explicit-before"
    assert verification.after_snapshot_id == "explicit-after"


def test_run_verification_only_one_snapshot_given_skips_regression_detection(
    tmp_path: Path,
) -> None:
    before = Snapshot(target=_target(), findings=[_finding("existing issue")])

    verification = run_verification(
        tmp_path, ["python3", "-c", "pass"], before_snapshot=before, after_snapshot=None
    )

    assert verification.regressions_found == []
