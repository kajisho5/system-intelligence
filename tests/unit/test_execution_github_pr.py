import json
import subprocess
from pathlib import Path

import pytest

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.governance import Approval
from system_intelligence.execution.github_pr import (
    GitHubPRError,
    open_draft_pr_for_plan,
    open_draft_pull_request,
    push_branch,
)
from system_intelligence.execution.plan import ChangePlan


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)


def _init_bare_remote(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "--bare"], cwd=path, check=True)


def _plan(**overrides: object) -> ChangePlan:
    defaults: dict[str, object] = {
        "branch_name": "si/add-license",
        "commit_message": "Add LICENSE",
        "files": {"LICENSE": "MIT\n"},
    }
    defaults.update(overrides)
    return ChangePlan(**defaults)  # type: ignore[arg-type]


def _approval_for(target: str) -> Approval:
    return Approval(
        actor="human:test",
        scope="repository",
        action="create_draft_pr",
        target=target,
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )


# --- push_branch: real, fully-local git (a bare repo as the "remote"), no
# network at all --------------------------------------------------------


def test_push_branch_success_against_a_local_bare_remote(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _init_bare_remote(remote)
    _init_repo(repo)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-b", "si/add-license"], cwd=repo, check=True)

    push_branch(repo, "si/add-license")

    branches = subprocess.run(
        ["git", "branch"], cwd=remote, capture_output=True, text=True, check=True
    ).stdout
    assert "si/add-license" in branches


def test_push_branch_never_force_pushes_a_diverged_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _init_bare_remote(remote)
    _init_repo(repo)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-b", "si/add-license"], cwd=repo, check=True)
    subprocess.run(["git", "push", "origin", "si/add-license"], cwd=repo, check=True)

    # Diverge the remote's branch from what the local repo knows about.
    other_clone = tmp_path / "other-clone"
    subprocess.run(["git", "clone", "-q", str(remote), str(other_clone)], check=True)
    subprocess.run(["git", "checkout", "si/add-license"], cwd=other_clone, check=True)
    (other_clone / "NOTICE").write_text("Copyright\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=other_clone, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=other_clone, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=other_clone, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "diverged"], cwd=other_clone, check=True)
    subprocess.run(["git", "push", "origin", "si/add-license"], cwd=other_clone, check=True)

    # Local repo's own commit on the same branch now conflicts with the
    # remote's history -- a real force-push would silently overwrite it.
    (repo / "LICENSE").write_text("MIT\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "local-only change"], cwd=repo, check=True)

    with pytest.raises(GitHubPRError, match="git push failed"):
        push_branch(repo, "si/add-license")


def test_push_branch_git_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("system_intelligence.execution.github_pr.shutil.which", lambda _name: None)

    with pytest.raises(GitHubPRError, match="git is not available"):
        push_branch(Path("/nonexistent"), "some-branch")


def test_push_branch_with_token_passes_an_extraheader_not_a_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "system_intelligence.execution.github_pr.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.execution.github_pr.subprocess.run", _fake_run)

    push_branch(Path("/some/repo"), "si/x", token="secret-token")  # nosec B106

    argv = captured["argv"]
    assert argv[0] == "/usr/bin/git"
    assert "-c" in argv
    extraheader_index = argv.index("-c") + 1
    assert argv[extraheader_index].startswith("http.extraheader=AUTHORIZATION: basic ")
    assert "secret-token" not in " ".join(argv)  # never embedded in argv in plaintext
    assert argv[-2:] == ["origin", "si/x"]
    assert "--force" not in argv
    assert "-f" not in argv


def test_push_branch_failure_surfaces_git_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv, returncode=1, stdout="", stderr="fatal: repository not found"
        )

    monkeypatch.setattr(
        "system_intelligence.execution.github_pr.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.execution.github_pr.subprocess.run", _fake_run)

    with pytest.raises(GitHubPRError, match="repository not found"):
        push_branch(Path("/some/repo"), "si/x")


# --- open_draft_pull_request: HTTP layer mocked, matching every other
# GitHub-API-touching adapter in this codebase --------------------------


def test_open_draft_pull_request_success() -> None:
    response = {"number": 42, "html_url": "https://github.com/o/r/pull/42", "draft": True}

    def _fake_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        assert url == "https://api.github.com/repos/o/r/pulls"
        assert headers["Authorization"] == "Bearer secret-token"
        payload = json.loads(body)
        assert payload["draft"] is True
        assert payload["head"] == "si/x"
        return 201, json.dumps(response).encode()

    pr = open_draft_pull_request(
        owner="o",
        repo="r",
        head="si/x",
        base="main",
        title="Add LICENSE",
        body="",
        token="secret-token",  # nosec B106
        http_post=_fake_post,
    )

    assert pr.number == 42
    assert pr.html_url == "https://github.com/o/r/pull/42"
    assert pr.is_draft is True


def test_open_draft_pull_request_reads_is_draft_from_the_response_not_the_request() -> None:
    # GitHub, not the request payload, is the source of truth.
    response = {"number": 1, "html_url": "https://github.com/o/r/pull/1", "draft": False}

    pr = open_draft_pull_request(
        owner="o",
        repo="r",
        head="si/x",
        base="main",
        title="t",
        body="",
        token="tok",  # nosec B106
        http_post=lambda *_a: (201, json.dumps(response).encode()),
    )

    assert pr.is_draft is False


def test_open_draft_pull_request_http_error_status() -> None:
    with pytest.raises(GitHubPRError, match="HTTP 422"):
        open_draft_pull_request(
            owner="o",
            repo="r",
            head="si/x",
            base="main",
            title="t",
            body="",
            token="tok",  # nosec B106
            http_post=lambda *_a: (422, b'{"message": "Validation Failed"}'),
        )


def test_open_draft_pull_request_invalid_json() -> None:
    with pytest.raises(GitHubPRError, match="invalid JSON"):
        open_draft_pull_request(
            owner="o",
            repo="r",
            head="si/x",
            base="main",
            title="t",
            body="",
            token="tok",  # nosec B106
            http_post=lambda *_a: (201, b"not json"),
        )


def test_open_draft_pull_request_missing_fields() -> None:
    with pytest.raises(GitHubPRError, match="Unexpected GitHub API response shape"):
        open_draft_pull_request(
            owner="o",
            repo="r",
            head="si/x",
            base="main",
            title="t",
            body="",
            token="tok",  # nosec B106
            http_post=lambda *_a: (201, b"{}"),
        )


def test_open_draft_pull_request_network_error() -> None:
    def _raise(*_args: object) -> tuple[int, bytes]:
        raise OSError("connection refused")

    with pytest.raises(GitHubPRError, match="request failed"):
        open_draft_pull_request(
            owner="o",
            repo="r",
            head="si/x",
            base="main",
            title="t",
            body="",
            token="tok",  # nosec B106
            http_post=_raise,
        )


# --- open_draft_pr_for_plan: governance gate, then push + open ---------


def test_open_draft_pr_for_plan_denied_without_approval_never_pushes(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _init_bare_remote(remote)
    _init_repo(repo_dir)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo_dir, check=True)
    subprocess.run(["git", "checkout", "-b", "si/add-license"], cwd=repo_dir, check=True)

    result = open_draft_pr_for_plan(
        _plan(),
        repo_dir,
        owner="o",
        repo="r",
        base="main",
        token="tok",  # nosec B106
    )

    assert result.applied is False
    assert "no matching approval" in result.decision.reason
    assert result.pull_request is None
    branches = subprocess.run(
        ["git", "branch"], cwd=remote, capture_output=True, text=True, check=True
    ).stdout
    assert branches.strip() == ""


def test_open_draft_pr_for_plan_with_approval_pushes_and_opens_pr(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _init_bare_remote(remote)
    _init_repo(repo_dir)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo_dir, check=True)
    subprocess.run(["git", "checkout", "-b", "si/add-license"], cwd=repo_dir, check=True)

    posted: dict[str, object] = {}

    def _fake_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        posted["payload"] = json.loads(body)
        return 201, json.dumps(
            {"number": 7, "html_url": "https://github.com/o/r/pull/7", "draft": True}
        ).encode()

    approval = _approval_for("o/r")
    result = open_draft_pr_for_plan(
        _plan(),
        repo_dir,
        owner="o",
        repo="r",
        base="main",
        token="tok",  # nosec B106
        approvals=[approval],
        http_post=_fake_post,
    )

    assert result.applied is True
    assert result.pull_request is not None
    assert result.pull_request.number == 7
    assert posted["payload"] == {  # type: ignore[comparison-overlap]
        "title": "Add LICENSE",
        "head": "si/add-license",
        "base": "main",
        "body": "Add LICENSE",
        "draft": True,
    }
    branches = subprocess.run(
        ["git", "branch"], cwd=remote, capture_output=True, text=True, check=True
    ).stdout
    assert "si/add-license" in branches
