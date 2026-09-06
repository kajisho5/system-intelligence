from pathlib import Path

import pytest

from system_intelligence.verification.engine import VerificationError, run_verification


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
