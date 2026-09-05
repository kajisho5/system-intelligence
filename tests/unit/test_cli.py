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
    result = runner.invoke(app, ["diagnose"])
    assert result.exit_code == 1
    assert "not implemented yet" in result.stdout + (result.stderr or "")
