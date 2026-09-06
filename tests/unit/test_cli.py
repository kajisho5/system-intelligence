from pathlib import Path

from typer.testing import CliRunner

from system_intelligence import __version__
from system_intelligence.cli.main import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_doctor_command_runs_and_reports_checks() -> None:
    result = runner.invoke(app, ["doctor"])
    assert "python-version" in result.stdout
    assert "git-available" in result.stdout


def test_unimplemented_command_fails_clearly() -> None:
    result = runner.invoke(app, ["research"])
    assert result.exit_code == 1
    assert "not implemented yet" in result.stdout + (result.stderr or "")


def test_inspect_command_reports_summary(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "Languages: Python" in result.stdout
    assert "Root documents: 1 (README.md)" in result.stdout


def test_inspect_command_writes_snapshot_with_out(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["inspect", str(target_dir), "--out", str(out_dir)])

    assert result.exit_code == 0
    written = list(out_dir.glob("snapshot-*/manifest.json"))
    assert len(written) == 1


def test_inspect_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


def test_diagnose_command_reports_findings(tmp_path: Path) -> None:
    # An empty directory: no README/LICENSE/CONTRIBUTING, no CI, no tests.
    result = runner.invoke(app, ["diagnose", str(tmp_path)])

    assert result.exit_code == 0
    assert "documentation_gap" not in result.stdout  # category isn't printed, statement is
    assert "No README file was found" in result.stdout
    assert "No CI configuration" in result.stdout
    assert "HIGH (" in result.stdout or "MEDIUM (" in result.stdout


def test_diagnose_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["diagnose", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


def test_diagnose_command_writes_snapshot_with_out(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["diagnose", str(target_dir), "--out", str(out_dir)])

    assert result.exit_code == 0
    written = list(out_dir.glob("snapshot-*/findings.json"))
    assert len(written) == 1
