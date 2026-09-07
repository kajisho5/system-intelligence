import subprocess
from pathlib import Path

import pytest

from system_intelligence.discovery.github_target import (
    GitHubTargetError,
    clone_github_repository,
    is_github_spec,
)


def test_is_github_spec_true_for_shorthand_with_no_matching_local_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert is_github_spec("octocat/Hello-World") is True


def test_is_github_spec_false_when_a_matching_local_dir_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "owner" / "repo").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert is_github_spec("owner/repo") is False


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/octocat/Hello-World",
        "https://github.com/octocat/Hello-World.git",
        "https://github.com/octocat/Hello-World/",
    ],
)
def test_is_github_spec_true_for_github_urls(url: str) -> None:
    assert is_github_spec(url) is True


@pytest.mark.parametrize(
    "locator",
    ["/tmp/somewhere", "./relative", "..", ".", "a/b/c", "just-a-name"],
)
def test_is_github_spec_false_for_non_github_locators(locator: str) -> None:
    assert is_github_spec(locator) is False


def test_clone_github_repository_git_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: None
    )

    with pytest.raises(GitHubTargetError, match="git is not installed"):
        clone_github_repository("octocat/Hello-World")


def test_clone_github_repository_success_runs_shallow_single_branch_clone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured: dict[str, list[str]] = {}

    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.discovery.github_target.subprocess.run", _fake_run)

    dest = clone_github_repository("octocat/Hello-World")

    assert dest.is_dir()
    assert captured["argv"][:4] == ["/usr/bin/git", "clone", "--depth", "1"]
    assert captured["argv"][-2] == "https://github.com/octocat/Hello-World.git"
    assert captured["argv"][-1] == str(dest)
    dest.rmdir()


def test_clone_github_repository_url_spec_is_passed_through_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured: dict[str, list[str]] = {}

    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.discovery.github_target.subprocess.run", _fake_run)

    dest = clone_github_repository("https://github.com/octocat/Hello-World.git")

    assert captured["argv"][-2] == "https://github.com/octocat/Hello-World.git"
    dest.rmdir()


def test_clone_github_repository_failure_removes_temp_dir_and_raises_with_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    created: dict[str, Path] = {}

    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        created["dest"] = Path(argv[-1])
        return subprocess.CompletedProcess(
            argv, returncode=128, stdout="", stderr="fatal: repository 'x' not found"
        )

    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.discovery.github_target.subprocess.run", _fake_run)

    with pytest.raises(GitHubTargetError, match="repository 'x' not found"):
        clone_github_repository("no-such-owner/no-such-repo")

    assert not created["dest"].exists()


def test_clone_github_repository_no_token_omits_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured: dict[str, list[str]] = {}

    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.discovery.github_target.subprocess.run", _fake_run)

    dest = clone_github_repository("octocat/Hello-World")

    assert "-c" not in captured["argv"]
    dest.rmdir()


def test_clone_github_repository_with_token_adds_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GITHUB_TOKEN` (the same env var `cli/main.py`/`push_branch` already
    use) must authenticate this clone too -- without it, a private
    repository the token can access was previously unclonable, with no
    indication a token would help."""
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    captured: dict[str, list[str]] = {}

    def _fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.discovery.github_target.subprocess.run", _fake_run)

    dest = clone_github_repository("octocat/Hello-World")

    assert captured["argv"][1] == "-c"
    assert captured["argv"][2].startswith("http.extraheader=AUTHORIZATION: basic ")
    assert captured["argv"][3:7] == ["clone", "--depth", "1", "--quiet"]
    dest.rmdir()


def test_clone_github_repository_disables_terminal_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A private/inaccessible repository must fail fast with git's own
    stderr, not hang on a credential prompt this non-interactive process
    could never answer."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured: dict[str, dict[str, str]] = {}

    def _fake_run(
        argv: list[str], *, env: dict[str, str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["env"] = env
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "system_intelligence.discovery.github_target.shutil.which", lambda _name: "/usr/bin/git"
    )
    monkeypatch.setattr("system_intelligence.discovery.github_target.subprocess.run", _fake_run)

    dest = clone_github_repository("octocat/Hello-World")

    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"
    dest.rmdir()
