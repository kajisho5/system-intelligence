import json
from pathlib import Path

import pytest
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
    result = runner.invoke(app, ["design"])
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


def test_report_command_writes_html_and_snapshot(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["report", str(target_dir), "--out", str(out_dir)])

    assert result.exit_code == 0
    report_html = (out_dir / "report.html").read_text(encoding="utf-8")
    assert "<html" in report_html
    assert "System Intelligence report" in report_html
    assert len(list(out_dir.glob("snapshot-*/manifest.json"))) == 1


def test_report_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


def test_diff_command_reports_added_and_resolved(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    before_out = tmp_path / "before"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(before_out)])
    before_dir = next(before_out.glob("snapshot-*"))

    (target_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    after_out = tmp_path / "after"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(after_out)])
    after_dir = next(after_out.glob("snapshot-*"))

    result = runner.invoke(app, ["diff", str(before_dir), str(after_dir)])

    assert result.exit_code == 0
    assert "Components added" in result.stdout
    assert "document:README.md" in result.stdout
    assert "Findings resolved" in result.stdout


def test_diff_command_no_changes(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    out_dir = tmp_path / "out"

    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(out_dir)])
    snapshot_dir = next(out_dir.glob("snapshot-*"))

    result = runner.invoke(app, ["diff", str(snapshot_dir), str(snapshot_dir)])

    assert result.exit_code == 0
    assert "No changes detected." in result.stdout


def test_diff_command_missing_manifest_fails_clearly(tmp_path: Path) -> None:
    empty_a = tmp_path / "a"
    empty_b = tmp_path / "b"
    empty_a.mkdir()
    empty_b.mkdir()

    result = runner.invoke(app, ["diff", str(empty_a), str(empty_b)])

    assert result.exit_code == 1
    assert "no manifest.json" in result.stdout + (result.stderr or "")


def test_research_command_reports_ranked_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = {
        "items": [
            {
                "full_name": "psf/black",
                "html_url": "https://github.com/psf/black",
                "license": {"spdx_id": "MIT"},
                "pushed_at": "2026-08-01T00:00:00Z",
                "stargazers_count": 12345,
                "archived": False,
            }
        ]
    }

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(response).encode()

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _fake_http_get)

    result = runner.invoke(
        app, ["research", "black formatter", "--cache-dir", str(tmp_path / "cache")]
    )

    assert result.exit_code == 0
    assert "psf/black" in result.stdout
    assert "MIT" in result.stdout
    assert "functional_fit" in result.stdout


def test_research_command_uses_cache_on_second_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    response = {"items": [{"full_name": "psf/black", "html_url": "https://github.com/psf/black"}]}

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        nonlocal call_count
        call_count += 1
        return 200, json.dumps(response).encode()

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _fake_http_get)
    cache_dir = tmp_path / "cache"

    runner.invoke(app, ["research", "q", "--cache-dir", str(cache_dir)])
    result = runner.invoke(app, ["research", "q", "--cache-dir", str(cache_dir)])

    assert call_count == 1
    assert "(cached)" in result.stdout


def test_research_command_network_error_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("no network")

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _raise)

    result = runner.invoke(app, ["research", "q", "--cache-dir", str(tmp_path / "cache")])

    assert result.exit_code == 1
    assert "error" in result.stdout + (result.stderr or "")


def test_improve_command_reports_recommendations(tmp_path: Path) -> None:
    result = runner.invoke(app, ["improve", str(tmp_path)])

    assert result.exit_code == 0
    assert "recommendation(s)" in result.stdout
    assert "No README file was found" in result.stdout


def test_improve_command_healthy_project_has_no_recommendations(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("Contribute\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("", encoding="utf-8")

    result = runner.invoke(app, ["improve", str(tmp_path)])

    assert result.exit_code == 0
    assert "No recommendations" in result.stdout


def test_improve_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["improve", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


def test_propose_command_without_research_is_creation(tmp_path: Path) -> None:
    out_path = tmp_path / "proposal.json"

    result = runner.invoke(
        app,
        [
            "propose",
            "Need a markdown renderer",
            "--requirement",
            "renders CommonMark",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert "Proposal kind: creation" in result.stdout
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["kind"] == "creation"
    assert written["requirements"] == ["renders CommonMark"]


def test_propose_command_with_research_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = {
        "items": [
            {
                "full_name": "psf/black",
                "html_url": "https://github.com/psf/black",
                "license": {"spdx_id": "MIT"},
                "pushed_at": "2026-08-01T00:00:00Z",
                "archived": False,
            },
            {
                "full_name": "other/formatter",
                "html_url": "https://github.com/other/formatter",
                "license": None,
                "archived": True,
            },
        ]
    }

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(response).encode()

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _fake_http_get)

    result = runner.invoke(app, ["propose", "Need a formatter", "--research-query", "black"])

    assert result.exit_code == 0
    assert "Proposal kind: integration" in result.stdout
    assert "psf/black" in result.stdout
    assert "Alternatives considered: other/formatter" in result.stdout


def test_propose_command_research_error_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("no network")

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _raise)

    result = runner.invoke(app, ["propose", "Need X", "--research-query", "x"])

    assert result.exit_code == 1
    assert "error" in result.stdout + (result.stderr or "")
