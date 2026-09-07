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
    assert "Git repository: no" in result.stdout
    assert "Remote: none configured" in result.stdout
    assert "License: unknown" in result.stdout
    assert "Languages: Python" in result.stdout
    assert "Root documents: 1 (README.md)" in result.stdout


def test_inspect_command_reports_discovered_agents(tmp_path: Path) -> None:
    """`si inspect` already lists discovered Skills by name but never even
    listed Agents at all -- a peer Component discovered the same way, with
    its own dedicated `agents = [...]` extraction never wired to any
    output line, so a real `.claude/agents/*.md` Agent was completely
    invisible in this command's summary, even though it fully appears in
    both the static report and the dashboard."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "code-reviewer.md").write_text(
        "---\nname: code-reviewer\ndescription: Reviews code for bugs\n---\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "Agents: 1 (code-reviewer)" in result.stdout


def test_inspect_command_reports_discovered_adrs(tmp_path: Path) -> None:
    """`si inspect` already extracts Skills/Agents/CI jobs/Root documents
    by name, and `discovery/adr.py::detect_adrs` already discovers ADRs
    into `Snapshot.adrs` (fully surfaced in the dashboard's "Architecture
    Decisions" tab) -- but this command never even read `snapshot.adrs`,
    so a real, discovered ADR was completely invisible in this command's
    summary."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-use-pydantic.md").write_text(
        "# ADR-001: Use pydantic\n\nStatus: Accepted\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "ADRs: 1 (Use pydantic)" in result.stdout


def test_inspect_command_reports_git_repository_yes_with_no_remote(tmp_path: Path) -> None:
    """A real, valid git repository with real commits but no configured
    (or unfetched) `origin` remote must never be reported as "not a git
    repository" just because `default_branch` (which requires a
    resolvable remote symref) happens to be unset -- those are two
    distinct facts."""
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "Git repository: yes (no remote branch detected)" in result.stdout
    assert "Remote: none configured" in result.stdout


def test_inspect_command_reports_configured_remote_url(tmp_path: Path) -> None:
    """`Repository.url` (the real `git remote get-url origin`, captured
    with its own dedicated Evidence in discovery/git_metadata.py) was
    genuinely populated by discovery but never printed by any consumer --
    `si inspect` already prints every other GitMetadata-derived fact
    (is_git_repository, default_branch, last_commit_*, license) except
    this one."""
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/octocat/demo.git"],
        cwd=tmp_path,
        check=True,
    )

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "Remote: https://example.com/octocat/demo.git" in result.stdout


def test_inspect_command_reports_known_license(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining "
        "a copy of this software and associated documentation files, to deal in the Software "
        "without restriction.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "License: MIT" in result.stdout


def test_inspect_command_reports_last_commit_when_a_git_repository(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "Last commit: " in result.stdout
    assert "uncommitted changes" not in result.stdout


def test_inspect_command_reports_dirty_working_tree(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "uncommitted changes" in result.stdout


def test_inspect_command_no_git_repository_omits_last_commit_line(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "Last commit:" not in result.stdout


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


def test_inspect_command_resolves_a_github_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone_dir = tmp_path / "cloned"
    clone_dir.mkdir()
    (clone_dir / "README.md").write_text("# Hi\n", encoding="utf-8")

    monkeypatch.setattr(
        "system_intelligence.discovery.target.clone_github_repository", lambda _spec: clone_dir
    )

    result = runner.invoke(app, ["inspect", "octocat/Hello-World"])

    assert result.exit_code == 0
    assert "Target: octocat/Hello-World" not in result.stdout  # locator, not name, is printed
    assert str(clone_dir.resolve()) in result.stdout


def test_inspect_command_github_clone_failure_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from system_intelligence.discovery.github_target import GitHubTargetError

    def _fail(_spec: str) -> None:
        raise GitHubTargetError("failed to clone 'no/such-repo': repository not found")

    monkeypatch.setattr("system_intelligence.discovery.target.clone_github_repository", _fail)

    result = runner.invoke(app, ["inspect", "no/such-repo"])

    assert result.exit_code == 1
    assert "repository not found" in result.stdout + (result.stderr or "")


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


def test_schema_command_writes_one_file_per_canonical_snapshot_file(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["schema", "--out", str(out_dir)])

    assert result.exit_code == 0
    assert (out_dir / "components.schema.json").exists()
    assert (out_dir / "manifest.schema.json").exists()
    assert (out_dir / "dashboard_data.schema.json").exists()
    schema = json.loads((out_dir / "capabilities.schema.json").read_text(encoding="utf-8"))
    assert schema["type"] == "array"


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


def test_watch_command_first_run_records_baseline(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    state_dir = tmp_path / "watch-state"

    result = runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])

    assert result.exit_code == 0
    assert "recording this scan as the baseline" in result.stdout
    assert (state_dir / "latest.txt").is_file()
    recorded_id = (state_dir / "latest.txt").read_text(encoding="utf-8").strip()
    assert (state_dir / recorded_id / "manifest.json").is_file()


def test_watch_command_second_run_reports_no_drift_when_unchanged(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    state_dir = tmp_path / "watch-state"

    runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])
    result = runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])

    assert result.exit_code == 0
    assert "Baseline:" in result.stdout
    assert "Current:" in result.stdout
    assert "No drift detected since the last watch run." in result.stdout


def test_watch_command_detects_new_finding_as_drift(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    state_dir = tmp_path / "watch-state"

    runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])
    (target_dir / "README.md").unlink()
    result = runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])

    assert result.exit_code == 0
    assert "Findings introduced" in result.stdout


def test_watch_command_keeps_each_run_as_its_own_immutable_snapshot(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    state_dir = tmp_path / "watch-state"

    runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])
    first_id = (state_dir / "latest.txt").read_text(encoding="utf-8").strip()
    runner.invoke(app, ["watch", str(target_dir), "--state-dir", str(state_dir)])
    second_id = (state_dir / "latest.txt").read_text(encoding="utf-8").strip()

    assert first_id != second_id
    # Neither run's own snapshot directory is deleted by a later run.
    assert (state_dir / first_id / "manifest.json").is_file()
    assert (state_dir / second_id / "manifest.json").is_file()


def test_watch_command_out_option_also_writes_snapshot(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    state_dir = tmp_path / "watch-state"
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        ["watch", str(target_dir), "--state-dir", str(state_dir), "--out", str(out_dir)],
    )

    assert result.exit_code == 0
    assert next(out_dir.glob("snapshot-*")).joinpath("manifest.json").is_file()


def test_watch_command_missing_target_fails_clearly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["watch", str(tmp_path / "nope")])

    assert result.exit_code == 1
    assert "does not exist" in result.stdout + (result.stderr or "")


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
    # The MCP registry's own schema has no "archived" field at all -- this
    # must never be displayed as the fabricated claim "not archived".
    assert "archived: unknown" in result.stdout
    assert "not archived" not in result.stdout


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


def test_research_command_cache_does_not_ignore_different_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache entry written for `--limit 10` must not be silently reused
    for a later `--limit 30` within the same TTL -- previously the cache
    key ignored `limit` entirely, so the second, differently-limited call
    never re-hit the provider and got back the first call's smaller
    result set with no indication the requested limit wasn't honored."""
    call_count = 0

    response = {
        "items": [
            {"full_name": f"org/repo-{i}", "html_url": f"https://github.com/org/repo-{i}"}
            for i in range(2)
        ]
    }

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        nonlocal call_count
        call_count += 1
        return 200, json.dumps(response).encode()

    monkeypatch.setattr("system_intelligence.research.github._default_http_get", _fake_http_get)
    cache_dir = tmp_path / "cache"

    runner.invoke(app, ["research", "q", "--limit", "10", "--cache-dir", str(cache_dir)])
    result = runner.invoke(app, ["research", "q", "--limit", "30", "--cache-dir", str(cache_dir)])

    assert call_count == 2
    assert "(cached)" not in result.stdout


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


def test_propose_command_handoff_out_writes_packet(tmp_path: Path) -> None:
    handoff_path = tmp_path / "handoff.json"

    result = runner.invoke(
        app,
        [
            "propose",
            "Need a markdown renderer",
            "--target",
            "/repo/root",
            "--handoff-out",
            str(handoff_path),
        ],
    )

    assert result.exit_code == 0
    assert f"Handoff packet written to {handoff_path}" in result.stdout
    packet = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert packet["target_root"] == "/repo/root"
    assert packet["proposal"]["kind"] == "creation"
    assert "change_plan_file_schema" in packet


def test_propose_command_handoff_out_without_target_fails_clearly() -> None:
    result = runner.invoke(app, ["propose", "Need X", "--handoff-out", "handoff.json"])

    assert result.exit_code == 1
    assert "--handoff-out requires --target" in result.stdout + (result.stderr or "")


def test_propose_command_target_kind_shapes_test_strategy(tmp_path: Path) -> None:
    out_path = tmp_path / "proposal.json"

    result = runner.invoke(
        app,
        ["propose", "Need a linter Skill", "--target-kind", "skill", "--out", str(out_path)],
    )

    assert result.exit_code == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert "SKILL.md" in written["test_strategy"]
    assert len(written["interfaces"]) == 1
    assert "SKILL.md" in written["interfaces"][0]


def test_propose_command_prints_capabilities_interfaces_and_strategies(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "propose",
            "Need a linter Skill",
            "--requirement",
            "lints Python",
            "--target-kind",
            "skill",
        ],
    )

    assert result.exit_code == 0
    assert "Capabilities: lints Python" in result.stdout
    assert "Interfaces: " in result.stdout and "SKILL.md" in result.stdout
    assert "Implementation stages: " in result.stdout
    assert "Test strategy: " in result.stdout
    assert "Security considerations: " in result.stdout
    assert "Documentation requirements: " in result.stdout
    assert "Rollback strategy: " in result.stdout


def test_propose_command_prints_interface_fields_for_skill(tmp_path: Path) -> None:
    """`Interfaces` only ever names the SKILL.md convention as a whole --
    `Interface fields` is the field-level breakdown, grounded in exactly
    what discovery/skills.py parses out of SKILL.md frontmatter, including
    which fields are required vs optional."""
    result = runner.invoke(
        app,
        [
            "propose",
            "Need a linter Skill",
            "--requirement",
            "lints Python",
            "--target-kind",
            "skill",
        ],
    )

    assert result.exit_code == 0
    assert "Interface fields:" in result.stdout
    assert "- name (required):" in result.stdout
    assert "- allowed-tools (optional):" in result.stdout


def test_propose_command_unknown_target_kind_fails_clearly() -> None:
    result = runner.invoke(app, ["propose", "Need X", "--target-kind", "spaceship"])

    assert result.exit_code == 1
    assert "unknown --target-kind" in result.stdout + (result.stderr or "")


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


def _local_approval(
    target: str, action: str = "create_local_branch_and_commit"
) -> dict[str, object]:
    return {
        "actor": "human:test",
        "scope": "repository",
        "action": action,
        "target": target,
        "permission_level": 4,
    }


def test_execute_command_push_requires_repo_option(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(json.dumps(_local_approval(str(tmp_path))), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(tmp_path),
            "--approve",
            "--approval-file",
            str(approval_file),
            "--push",
        ],
    )

    assert result.exit_code == 1
    assert "--repo" in result.stdout + (result.stderr or "")


def test_execute_command_push_requires_github_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(json.dumps(_local_approval(str(tmp_path))), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(tmp_path),
            "--approve",
            "--approval-file",
            str(approval_file),
            "--push",
            "--repo",
            "o/r",
        ],
    )

    assert result.exit_code == 1
    assert "GITHUB_TOKEN" in result.stdout + (result.stderr or "")


def test_execute_command_push_denied_without_a_create_draft_pr_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    _init_repo(tmp_path)
    plan_file = _write_plan_file(tmp_path)
    approval_file = tmp_path / "approval.json"
    # Only the local action is approved -- the remote action needs its own.
    approval_file.write_text(json.dumps(_local_approval(str(tmp_path))), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(tmp_path),
            "--approve",
            "--approval-file",
            str(approval_file),
            "--push",
            "--repo",
            "o/r",
        ],
    )

    assert result.exit_code == 1
    assert "Draft PR denied" in result.stdout
    # The local step still succeeded and is not rolled back.
    assert (tmp_path / "LICENSE").read_text(encoding="utf-8") == "MIT\n"


def test_execute_command_push_opens_a_draft_pr_with_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    subprocess.run(["git", "init", "-q", "--bare"], cwd=remote, check=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo_dir, check=True)

    plan_file = _write_plan_file(repo_dir)
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            [
                _local_approval(str(repo_dir)),
                _local_approval("o/r", action="create_draft_pr"),
            ]
        ),
        encoding="utf-8",
    )

    def _fake_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        return 201, json.dumps(
            {"number": 9, "html_url": "https://github.com/o/r/pull/9", "draft": True}
        ).encode()

    monkeypatch.setattr("system_intelligence.execution.github_pr._default_http_post", _fake_post)

    result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(repo_dir),
            "--approve",
            "--approval-file",
            str(approval_file),
            "--push",
            "--repo",
            "o/r",
        ],
    )

    assert result.exit_code == 0
    assert "Draft PR opened: https://github.com/o/r/pull/9" in result.stdout
    branches = subprocess.run(
        ["git", "branch"], cwd=remote, capture_output=True, text=True, check=True
    ).stdout
    assert "si/add-license" in branches


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

    recorded_audit_log = json.loads((snapshot_dir / "audit_log.json").read_text(encoding="utf-8"))
    assert len(recorded_audit_log) == 1
    assert recorded_audit_log[0]["result"] == "allowed"
    # the actual approving actor, not fabricated
    assert recorded_audit_log[0]["actor"] == "human:test"
    assert recorded_audit_log[0]["action"] == "create_local_branch_and_commit"
    assert recorded_audit_log[0]["correlation_id"] == recorded[0]["commit_sha"]


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

    # A denied decision is still audited (with a generated correlation id,
    # since there is no commit to correlate it with) -- audit trail is not
    # conditional on the action having succeeded.
    recorded_audit_log = json.loads((snapshot_dir / "audit_log.json").read_text(encoding="utf-8"))
    assert recorded_audit_log[0]["result"] == "denied"
    assert recorded_audit_log[0]["actor"] == "system:cli"
    assert recorded_audit_log[0]["correlation_id"].startswith("correlation-")


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
    # Without --check-vulnerabilities, no vulnerability lookup is attempted
    # at all -- confirmed here by never mocking OSV's endpoint and still
    # getting a clean pass with no advisory output.
    assert "known vulnerabilities" not in result.stdout


def test_check_updates_command_check_vulnerabilities_reports_advisory(
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

    def _fake_http_post(url: str, headers: dict[str, str], data: bytes) -> tuple[int, bytes]:
        body = json.loads(data)
        if body["version"] == "2.0.0":
            vuln = {"id": "GHSA-test", "summary": "x", "database_specific": {"severity": "HIGH"}}
            return 200, json.dumps({"vulns": [vuln]}).encode()
        return 200, b"{}"

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )
    monkeypatch.setattr(
        "system_intelligence.research.providers.osv._default_http_post", _fake_http_post
    )

    result = runner.invoke(app, ["check-updates", str(target_dir), "--check-vulnerabilities"])

    assert result.exit_code == 0
    assert "known vulnerabilities (current version): GHSA-test (HIGH)" in result.stdout
    assert "known vulnerabilities (available version)" not in result.stdout


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


def test_check_updates_command_shows_release_date_when_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        response = _fake_pypi_response("pydantic", "2.9.0")
        response["releases"] = {"2.9.0": [{"upload_time_iso_8601": "2026-01-15T00:00:00.000000Z"}]}
        return 200, json.dumps(response).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )

    result = runner.invoke(app, ["check-updates", str(target_dir)])

    assert result.exit_code == 0
    assert "available: 2.9.0 (released 2026-01-15)" in result.stdout
    why_line = next(line for line in result.stdout.splitlines() if line.strip().startswith("why:"))
    assert "(released 2026-01-15)" in why_line


def test_check_updates_command_prints_recommendation(
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
    assert "1 recommendation(s):" in result.stdout
    assert "Update pydantic from 2.0.0 to 2.9.0." in result.stdout


def test_check_updates_command_record_appends_recommendation_to_snapshot(
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
    recorded = json.loads((snapshot_dir / "recommendations.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1
    assert recorded[0]["objective"] == "Update pydantic from 2.0.0 to 2.9.0."


def test_check_updates_command_plan_out_writes_change_plan(
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
    plan_out = tmp_path / "plans"

    result = runner.invoke(app, ["check-updates", str(target_dir), "--plan-out", str(plan_out)])

    assert result.exit_code == 0
    plan_files = list(plan_out.glob("*.json"))
    assert len(plan_files) == 1
    plan = json.loads(plan_files[0].read_text(encoding="utf-8"))
    expected_content = (
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.9.0"]\n'
    )
    assert plan["branch_name"] == "si/update-pydantic-to-2.9.0"
    assert plan["files"] == {"pyproject.toml": expected_content}
    assert plan["required_permission_level"] == "CREATE_BRANCH_OR_DRAFT_PR"


def test_check_updates_command_plan_out_writes_change_plan_for_github_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--plan-out` previously passed the raw, unresolved CLI target string
    straight to `change_plan_for_component_update` as the repository root,
    instead of the actual resolved root `discover_local_repository` already
    computed (`discovery.snapshot.target.locator` -- the same value every
    other consumer, e.g. `analysis/engine.py`, reads). For a local path
    this happened to be identical to the resolved root, so it went
    unnoticed; for a GitHub target (explicitly supported by this command's
    own `_TARGET_ARGUMENT`), the raw spec (`"octocat/demo-repo"`) is not a
    real directory, so every plan silently failed to build with no
    indication the cause was the target type rather than a genuinely
    non-deterministic verdict."""
    clone_dir = tmp_path / "cloned"
    clone_dir.mkdir()
    (clone_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "system_intelligence.discovery.target.clone_github_repository", lambda _spec: clone_dir
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(_fake_pypi_response("pydantic", "2.9.0")).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )
    plan_out = tmp_path / "plans"

    result = runner.invoke(app, ["check-updates", "octocat/demo-repo", "--plan-out", str(plan_out)])

    assert result.exit_code == 0
    plan_files = list(plan_out.glob("*.json"))
    assert len(plan_files) == 1
    plan = json.loads(plan_files[0].read_text(encoding="utf-8"))
    assert plan["branch_name"] == "si/update-pydantic-to-2.9.0"


def test_check_updates_command_plan_out_writes_change_plan_for_npm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "package.json").write_text(
        '{\n  "dependencies": {\n    "left-pad": "1.2.3"\n  }\n}\n', encoding="utf-8"
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        response = {
            "dist-tags": {"latest": "1.3.0"},
            "versions": {"1.3.0": {}},
            "time": {"1.3.0": "2026-01-01T00:00:00.000Z"},
        }
        return 200, json.dumps(response).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.npm._default_http_get", _fake_http_get
    )
    plan_out = tmp_path / "plans"

    result = runner.invoke(app, ["check-updates", str(target_dir), "--plan-out", str(plan_out)])

    assert result.exit_code == 0
    plan_files = list(plan_out.glob("*.json"))
    assert len(plan_files) == 1
    plan = json.loads(plan_files[0].read_text(encoding="utf-8"))
    expected_content = '{\n  "dependencies": {\n    "left-pad": "1.3.0"\n  }\n}\n'
    assert plan["branch_name"] == "si/update-left-pad-to-1.3.0"
    assert plan["files"] == {"package.json": expected_content}
    assert plan["required_permission_level"] == "CREATE_BRANCH_OR_DRAFT_PR"


def test_check_updates_plan_out_end_to_end_through_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full deterministic loop: check-updates --plan-out -> execute --approve
    actually patches the manifest on disk, with no hand-written plan.json."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.0.0"]\n',
        encoding="utf-8",
    )
    _init_repo(target_dir)

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps(_fake_pypi_response("pydantic", "2.9.0")).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )
    plan_out = tmp_path / "plans"
    runner.invoke(app, ["check-updates", str(target_dir), "--plan-out", str(plan_out)])
    plan_file = next(plan_out.glob("*.json"))

    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "actor": "human:test",
                "scope": "repository",
                "action": "create_local_branch_and_commit",
                "target": str(target_dir),
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
            str(target_dir),
            "--approve",
            "--approval-file",
            str(approval_file),
        ],
    )

    expected_content = (
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = ["pydantic==2.9.0"]\n'
    )
    assert result.exit_code == 0
    assert "Applied: branch 'si/update-pydantic-to-2.9.0'" in result.stdout
    assert (target_dir / "pyproject.toml").read_text(encoding="utf-8") == expected_content


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


def test_check_updates_command_reports_cargo_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\n[dependencies]\nserde = "=1.0.0"\n',
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        response = {"crate": {"max_stable_version": "1.0.219"}, "versions": []}
        return 200, json.dumps(response).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.crates_io._default_http_get", _fake_http_get
    )

    result = runner.invoke(app, ["check-updates", str(target_dir)])

    assert result.exit_code == 0
    assert "serde" in result.stdout
    assert "current: 1.0.0" in result.stdout
    assert "available: 1.0.219" in result.stdout


def test_check_updates_command_reports_go_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "go.mod").write_text(
        "module example.com/x\n\ngo 1.21\n\nrequire golang.org/x/crypto v0.7.0\n",
        encoding="utf-8",
    )

    def _fake_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        return 200, json.dumps({"Version": "v0.31.0"}).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.go_proxy._default_http_get", _fake_http_get
    )

    result = runner.invoke(app, ["check-updates", str(target_dir)])

    assert result.exit_code == 0
    assert "golang.org/x/crypto" in result.stdout
    assert "current: v0.7.0" in result.stdout
    assert "available: v0.31.0" in result.stdout


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
    # --check-updates alone never triggers the OSV lookup -- confirmed here
    # by never mocking its endpoint and still getting a clean pass.
    assert dashboard_json["update_assessments"][0]["current_version_advisories"] == []


def test_dashboard_command_check_updates_merges_recommendation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An actionable Update Intelligence verdict must reach the dashboard's
    Recommendations screen, not just the separate update-check section --
    otherwise a user browsing Recommendations never sees it."""
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
    objectives = [r["objective"] for r in dashboard_json["recommendations"]]
    assert "Update pydantic from 2.0.0 to 2.9.0." in objectives


def test_dashboard_command_compare_with_surfaces_recorded_update_recommendation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`si check-updates --record` appends an actionable verdict's
    Recommendation to `recommendations.json` (see
    `test_check_updates_command_record_appends_recommendation_to_snapshot`),
    and `check_updates()`'s own docstring promises `si dashboard
    --compare-with` then surfaces it -- but a fresh `dashboard()` run
    unconditionally overwrites `snapshot.recommendations` with only
    Finding-based ones before the `--compare-with` merge, and that merge
    block never included `recommendations` among the fields it folds in
    from the accumulator (unlike proposals/executions/verification/
    approvals/research, all merged there already), so the recorded update
    recommendation silently never reached the dashboard at all."""
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

    snap_out = tmp_path / "snap"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))

    check_result = runner.invoke(app, ["check-updates", str(target_dir), "--record", str(snap_dir)])
    assert check_result.exit_code == 0

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
    objectives = [r["objective"] for r in dashboard_json["recommendations"]]
    assert "Update pydantic from 2.0.0 to 2.9.0." in objectives


def test_dashboard_command_compare_with_surfaces_recorded_audit_log(tmp_path: Path) -> None:
    """`si execute --record` appends a real `AuditLogEntry` to
    `audit_log.json` (see `test_execute_command_record_appends_to_
    snapshot`) -- the same accumulated-audit-trail record type as
    Proposals/Executions/Verifications/Approvals/Research, all of which
    `si dashboard --compare-with` already merges in. But `audit_log` was
    the one field never added to `DashboardData` at all (unlike
    `recommendations`, which had the same bug fixed separately), so the
    recorded audit trail never reached the dashboard in any form."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    _init_repo(target_dir)
    plan_file = _write_plan_file(target_dir)
    approval_file = target_dir / "approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "actor": "human:test",
                "scope": "repository",
                "action": "create_local_branch_and_commit",
                "target": str(target_dir),
                "permission_level": 4,
            }
        ),
        encoding="utf-8",
    )

    snap_out = tmp_path / "snap"
    runner.invoke(app, ["diagnose", str(target_dir), "--out", str(snap_out)])
    snap_dir = next(snap_out.glob("snapshot-*"))

    execute_result = runner.invoke(
        app,
        [
            "execute",
            str(plan_file),
            str(target_dir),
            "--approve",
            "--approval-file",
            str(approval_file),
            "--record",
            str(snap_dir),
        ],
    )
    assert execute_result.exit_code == 0

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
    correlation_ids = [a["correlation_id"] for a in dashboard_json["audit_log"]]
    assert len(correlation_ids) == 1


def test_dashboard_command_check_vulnerabilities_populates_advisories(
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

    def _fake_http_post(url: str, headers: dict[str, str], data: bytes) -> tuple[int, bytes]:
        return 200, json.dumps({"vulns": [{"id": "GHSA-test", "summary": "x"}]}).encode()

    monkeypatch.setattr(
        "system_intelligence.research.providers.pypi._default_http_get", _fake_http_get
    )
    monkeypatch.setattr(
        "system_intelligence.research.providers.osv._default_http_post", _fake_http_post
    )
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "dashboard",
            str(target_dir),
            "--out",
            str(out_dir),
            "--check-updates",
            "--check-vulnerabilities",
        ],
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    advisories = dashboard_json["update_assessments"][0]["current_version_advisories"]
    assert advisories == [
        {"id": "GHSA-test", "summary": "x", "severity": None, "aliases": [], "url": None}
    ]


def test_dashboard_command_check_vulnerabilities_without_check_updates_is_ignored(
    tmp_path: Path,
) -> None:
    """--check-vulnerabilities has nothing to attach to without
    --check-updates -- it must not fail, just be a no-op."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    out_dir = tmp_path / "out"

    result = runner.invoke(
        app, ["dashboard", str(target_dir), "--out", str(out_dir), "--check-vulnerabilities"]
    )

    assert result.exit_code == 0
    dashboard_json = json.loads(
        (out_dir / "dashboard.html")
        .read_text(encoding="utf-8")
        .split('id="si-dashboard-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert dashboard_json["overview"]["has_update_check"] is False
