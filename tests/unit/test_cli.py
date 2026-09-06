import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from system_intelligence import __version__
from system_intelligence.cli.main import app

runner = CliRunner()


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)


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


def test_research_command_mcp_registry_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = {
        "servers": [
            {
                "server": {
                    "name": "com.pulsemcp/remote-filesystem",
                    "description": "MCP server for remote filesystem operations.",
                    "version": "0.1.2",
                    "repository": {
                        "url": "https://github.com/pulsemcp/mcp-servers",
                        "source": "github",
                    },
                }
            }
        ]
    }

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(response).encode()

    monkeypatch.setattr(
        "system_intelligence.research.mcp_registry._default_http_get", _fake_http_get
    )

    result = runner.invoke(
        app,
        [
            "research",
            "filesystem",
            "--provider",
            "mcp-registry",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )

    assert result.exit_code == 0
    assert "com.pulsemcp/remote-filesystem" in result.stdout
    assert "license: unknown (unknown)" in result.stdout


def test_research_command_unknown_provider_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["research", "x", "--provider", "bogus", "--cache-dir", str(tmp_path / "cache")],
    )

    assert result.exit_code == 1
    assert "unknown --provider" in (result.stdout + (result.stderr or ""))


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


def test_plan_command_with_known_intent_name() -> None:
    result = runner.invoke(app, ["plan", "documentation_only"])

    assert result.exit_code == 0
    assert "Classified" not in result.stdout  # it's already a known intent
    assert "documentation_audit" in result.stdout
    assert "structure_scan" not in result.stdout


def test_plan_command_classifies_free_text() -> None:
    result = runner.invoke(app, ["plan", "Diagnose this repository."])

    assert result.exit_code == 0
    assert "Classified 'Diagnose this repository.' as intent 'diagnose'" in result.stdout
    assert "circular_dependency_detection" in result.stdout


def test_plan_command_list_intents() -> None:
    result = runner.invoke(app, ["plan", "--list"])

    assert result.exit_code == 0
    assert "diagnose" in result.stdout
    assert "documentation_only" in result.stdout


def test_plan_command_requires_request_without_list() -> None:
    result = runner.invoke(app, ["plan"])

    assert result.exit_code == 1
    assert "required" in result.stdout + (result.stderr or "")


def _write_plan_file(path: Path, **overrides: object) -> Path:
    plan = {
        "branch_name": "si/add-license",
        "commit_message": "Add LICENSE",
        "files": {"LICENSE": "MIT\n"},
    }
    plan.update(overrides)
    plan_file = path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    return plan_file


def test_execute_command_dry_run_by_default_touches_nothing(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)

    result = runner.invoke(app, ["execute", str(plan_file), str(tmp_path)])

    assert result.exit_code == 0
    assert "Create local branch 'si/add-license'" in result.stdout
    assert "Dry run only" in result.stdout
    assert not (tmp_path / "LICENSE").exists()


def test_execute_command_denied_without_approval_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)

    result = runner.invoke(app, ["execute", str(plan_file), str(tmp_path), "--approve"])

    assert result.exit_code == 1
    assert "Denied" in result.stdout
    assert not (tmp_path / "LICENSE").exists()


def test_execute_command_applies_with_matching_approval(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "actor": "human:test",
                "scope": "repository",
                "action": "create_local_branch_and_commit",
                "target": str(tmp_path),
                "permission_level": 4,
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(tmp_path),
            "--approve",
            "--approval-file",
            str(approval_file),
        ],
    )

    assert result.exit_code == 0
    assert "Applied: branch 'si/add-license'" in result.stdout
    assert (tmp_path / "LICENSE").read_text(encoding="utf-8") == "MIT\n"


def test_execute_command_invalid_plan_file_fails_clearly(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"branch_name": "x"}), encoding="utf-8")

    result = runner.invoke(app, ["execute", str(plan_file), str(tmp_path)])

    assert result.exit_code == 1
    assert "invalid plan file" in result.stdout + (result.stderr or "")


def test_execute_command_missing_plan_file_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["execute", str(tmp_path / "nope.json"), str(tmp_path)])

    assert result.exit_code == 1
    assert "error" in result.stdout + (result.stderr or "")


def test_verify_command_reports_passing_command(tmp_path: Path) -> None:
    result = runner.invoke(app, ["verify", "python3 -c print(1)", "--target", str(tmp_path)])

    assert result.exit_code == 0
    assert "Result: PASSED" in result.stdout


def test_verify_command_reports_failing_command(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["verify", "python3 -c 'import sys; sys.exit(1)'", "--target", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert "Result: FAILED" in result.stdout


def test_verify_command_missing_executable_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["verify", "definitely-not-a-real-executable-xyz", "--target", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert "not available on PATH" in result.stdout + (result.stderr or "")


def test_verify_command_record_appends_to_snapshot(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(
        app,
        ["verify", "python3 -c print(1)", "--target", str(tmp_path), "--record", str(snapshot_dir)],
    )

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "verification.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1
    assert recorded[0]["tests_passed"] is True


def test_verify_command_component_option_is_recorded(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "verify",
            "python3 -c print(1)",
            "--target",
            str(tmp_path),
            "--component",
            "skill-ffmpeg",
            "--record",
            str(snapshot_dir),
        ],
    )

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "verification.json").read_text(encoding="utf-8"))
    assert recorded[0]["component_id"] == "skill-ffmpeg"


def test_verify_command_without_component_option_leaves_it_null(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(
        app,
        ["verify", "python3 -c print(1)", "--target", str(tmp_path), "--record", str(snapshot_dir)],
    )

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "verification.json").read_text(encoding="utf-8"))
    assert recorded[0]["component_id"] is None


def test_verify_command_before_after_snapshot_detects_regression(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    (target_dir / "LICENSE").write_text("MIT\n", encoding="utf-8")

    before_out = tmp_path / "before"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(before_out)])
    before_dir = next(before_out.glob("snapshot-*"))

    (target_dir / "LICENSE").unlink()  # introduces a new "no LICENSE" finding
    after_out = tmp_path / "after"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(after_out)])
    after_dir = next(after_out.glob("snapshot-*"))

    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()
    result = runner.invoke(
        app,
        [
            "verify",
            "python3 -c print(1)",
            "--target",
            str(target_dir),
            "--before-snapshot",
            str(before_dir),
            "--after-snapshot",
            str(after_dir),
            "--record",
            str(snapshot_dir),
        ],
    )

    # The command itself passed, but a regression was introduced -> non-zero exit.
    assert result.exit_code == 1
    assert "Regressions detected" in result.stdout
    assert "LICENSE" in result.stdout
    recorded = json.loads((snapshot_dir / "verification.json").read_text(encoding="utf-8"))
    assert len(recorded[0]["regressions_found"]) == 1
    assert "LICENSE" in recorded[0]["regressions_found"][0]
    assert recorded[0]["before_snapshot_id"] is not None
    assert recorded[0]["after_snapshot_id"] is not None


def test_verify_command_before_after_snapshot_no_regression_passes(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    snap_out = tmp_path / "snap-src"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))

    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()
    result = runner.invoke(
        app,
        [
            "verify",
            "python3 -c print(1)",
            "--target",
            str(target_dir),
            "--before-snapshot",
            str(snap_dir),
            "--after-snapshot",
            str(snap_dir),
            "--record",
            str(snapshot_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Regressions detected" not in result.stdout


def test_verify_command_only_one_snapshot_flag_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["verify", "python3 -c print(1)", "--target", str(tmp_path), "--before-snapshot", "x"],
    )

    assert result.exit_code == 1
    assert "must be given together" in (result.stdout + (result.stderr or ""))


def test_verify_command_snapshot_missing_manifest_fails_clearly(tmp_path: Path) -> None:
    missing_a = tmp_path / "a"
    missing_b = tmp_path / "b"
    missing_a.mkdir()
    missing_b.mkdir()

    result = runner.invoke(
        app,
        [
            "verify",
            "python3 -c print(1)",
            "--target",
            str(tmp_path),
            "--before-snapshot",
            str(missing_a),
            "--after-snapshot",
            str(missing_b),
        ],
    )

    assert result.exit_code == 1
    assert "no manifest.json" in (result.stdout + (result.stderr or ""))


def test_execute_command_record_appends_to_snapshot(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "actor": "human:test",
                "scope": "repository",
                "action": "create_local_branch_and_commit",
                "target": str(tmp_path),
                "permission_level": 4,
            }
        ),
        encoding="utf-8",
    )
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(tmp_path),
            "--approve",
            "--approval-file",
            str(approval_file),
            "--record",
            str(snapshot_dir),
        ],
    )

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "executions.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1
    assert recorded[0]["applied"] is True
    assert recorded[0]["branch_name"] == "si/add-license"

    recorded_approvals = json.loads((snapshot_dir / "approvals.json").read_text(encoding="utf-8"))
    assert len(recorded_approvals) == 1
    assert recorded_approvals[0]["actor"] == "human:test"


def test_execute_command_denied_does_not_record_a_fabricated_approval(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(
        app,
        ["execute", str(plan_file), str(tmp_path), "--approve", "--record", str(snapshot_dir)],
    )

    assert result.exit_code == 1
    recorded = json.loads((snapshot_dir / "executions.json").read_text(encoding="utf-8"))
    assert recorded[0]["applied"] is False
    assert not (snapshot_dir / "approvals.json").exists()


def test_propose_command_record_appends_to_snapshot(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(app, ["propose", "Need X", "--record", str(snapshot_dir)])

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "proposals.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1
    assert recorded[0]["problem"] == "Need X"


def test_research_command_record_appends_to_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = {"items": [{"full_name": "psf/black", "html_url": "https://github.com/psf/black"}]}

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(response).encode()

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _fake_http_get)
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "research",
            "q",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--record",
            str(snapshot_dir),
        ],
    )

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "research.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1
    assert recorded[0]["identifier"] == "psf/black"


def _fake_pypi_response(name: str, version: str) -> dict[str, object]:
    return {"info": {"version": version}}


def test_check_updates_command_reports_review_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(_fake_pypi_response("pydantic", "2.9.0")).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )

    result = runner.invoke(app, ["check-updates", str(target_dir)])

    assert result.exit_code == 0
    assert "pydantic" in result.stdout
    assert "current: 2.0.0" in result.stdout
    assert "available: 2.9.0" in result.stdout
    assert "review_required" in result.stdout


def test_check_updates_command_propose_prints_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(_fake_pypi_response("pydantic", "2.9.0")).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )

    result = runner.invoke(app, ["check-updates", str(target_dir), "--propose"])

    assert result.exit_code == 0
    assert "Proposal (component_update)" in result.stdout
    assert "pydantic" in result.stdout


def test_check_updates_command_record_appends_proposal_to_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(_fake_pypi_response("pydantic", "2.9.0")).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )
    snapshot_dir = tmp_path / "snap"
    snapshot_dir.mkdir()

    result = runner.invoke(app, ["check-updates", str(target_dir), "--record", str(snapshot_dir)])

    assert result.exit_code == 0
    recorded = json.loads((snapshot_dir / "proposals.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1
    assert recorded[0]["kind"] == "component_update"


def test_check_updates_command_reports_source_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )

    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("no network")

    monkeypatch.setattr("system_intelligence.research.providers.pypi._default_http_get", _raise)

    result = runner.invoke(app, ["check-updates", str(target_dir)])

    assert result.exit_code == 0
    assert "could not be completed" in result.stdout


def test_check_updates_command_no_matching_provider(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")

    result = runner.invoke(app, ["check-updates", str(target_dir)])

    assert result.exit_code == 0
    assert "No dependencies found in an ecosystem with a configured update provider" in (
        result.stdout
    )


def test_check_updates_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check-updates", str(tmp_path / "nope")])

    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


def test_dashboard_command_writes_html_and_snapshot(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["dashboard", str(target_dir), "--out", str(out_dir)])

    assert result.exit_code == 0
    dashboard_html = (out_dir / "dashboard.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in dashboard_html
    assert 'id="si-dashboard-data"' in dashboard_html
    assert len(list(out_dir.glob("snapshot-*/manifest.json"))) == 1


def test_dashboard_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["dashboard", str(tmp_path / "nope")])

    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


def test_dashboard_command_compare_with_populates_changes(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    before_out = tmp_path / "before"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(before_out)])
    before_dir = next(before_out.glob("snapshot-*"))

    (target_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "dashboard",
            str(target_dir),
            "--out",
            str(out_dir),
            "--compare-with",
            str(before_dir),
        ],
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert dashboard_json["overview"]["has_previous_snapshot"] is True


def test_dashboard_command_compare_with_surfaces_recorded_proposals(tmp_path: Path) -> None:
    """--record accumulates into a snapshot dir; --compare-with is how the
    dashboard actually reads that accumulator back — without it, a
    freshly-scanned snapshot has empty proposals/executions/etc. by
    construction, regardless of what was ever --record'ed anywhere."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    snap_out = tmp_path / "snap"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))

    propose_result = runner.invoke(app, ["propose", "Need X", "--record", str(snap_dir)])
    assert propose_result.exit_code == 0

    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["dashboard", str(target_dir), "--out", str(out_dir), "--compare-with", str(snap_dir)],
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert dashboard_json["overview"]["proposal_count"] == 1
    assert dashboard_json["proposals"][0]["problem"] == "Need X"


def test_dashboard_command_without_compare_with_never_shows_recorded_data(tmp_path: Path) -> None:
    """The inverse of the above: no --compare-with means no accumulator was
    read, so proposals/executions stay empty even if some exist on disk
    elsewhere — a fresh scan must never silently show stale prior state."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    snap_out = tmp_path / "snap"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))
    runner.invoke(app, ["propose", "Need X", "--record", str(snap_dir)])

    out_dir = tmp_path / "out"
    result = runner.invoke(app, ["dashboard", str(target_dir), "--out", str(out_dir)])

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert dashboard_json["overview"]["proposal_count"] == 0


def test_dashboard_command_compare_with_derives_trust_level_from_research(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end P1-4 wiring: `si research --record` accumulates a
    ResearchResult identifying the same repository `si diagnose` discovers;
    `si dashboard --compare-with` must derive `Component.trust_level` from
    it (COMMUNITY, licensed + not archived) rather than leaving it UNKNOWN."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    snap_out = tmp_path / "snap"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))

    response = {
        "items": [
            {
                # "target_dir.name" is "target" -- the repo-name suffix must
                # match the locally discovered Repository's own short name.
                "full_name": "someowner/target",
                "html_url": "https://github.com/someowner/target",
                "license": {"spdx_id": "MIT"},
                "pushed_at": "2026-08-01T00:00:00Z",
                "stargazers_count": 1,
                "archived": False,
            }
        ]
    }

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(response).encode()

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _fake_http_get)

    research_result = runner.invoke(
        app,
        [
            "research",
            "target",
            "--record",
            str(snap_dir),
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert research_result.exit_code == 0

    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["dashboard", str(target_dir), "--out", str(out_dir), "--compare-with", str(snap_dir)],
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    repository = next(c for c in dashboard_json["components"] if c["kind"] == "repository")
    assert repository["trust_level"] == "community"


def test_dashboard_command_compare_with_surfaces_component_scoped_verification(
    tmp_path: Path,
) -> None:
    """`si verify --component <id> --record` attaches a Verification to a
    specific discovered Component; `si dashboard --compare-with` must
    surface it in the rendered snapshot's verifications list."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    snap_out = tmp_path / "snap"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))
    components = json.loads((snap_dir / "components.json").read_text(encoding="utf-8"))
    repository_id = next(c["id"] for c in components if c["kind"] == "repository")

    verify_result = runner.invoke(
        app,
        [
            "verify",
            "python3 -c print(1)",
            "--target",
            str(target_dir),
            "--component",
            repository_id,
            "--record",
            str(snap_dir),
        ],
    )
    assert verify_result.exit_code == 0

    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["dashboard", str(target_dir), "--out", str(out_dir), "--compare-with", str(snap_dir)],
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert len(dashboard_json["verifications"]) == 1
    assert dashboard_json["verifications"][0]["component_id"] == repository_id


def test_dashboard_command_compare_with_missing_manifest_fails_clearly(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    bad_compare = tmp_path / "not-a-snapshot"
    bad_compare.mkdir()

    result = runner.invoke(app, ["dashboard", str(target_dir), "--compare-with", str(bad_compare)])

    assert result.exit_code == 1
    assert "no manifest.json" in result.stdout + (result.stderr or "")


def test_dashboard_command_check_updates_populates_update_intelligence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(_fake_pypi_response("pydantic", "2.9.0")).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app, ["dashboard", str(target_dir), "--out", str(out_dir), "--check-updates"]
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert dashboard_json["overview"]["has_update_check"] is True
    assert dashboard_json["overview"]["update_assessment_count"] == 1
