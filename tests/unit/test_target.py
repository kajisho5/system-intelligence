from pathlib import Path

import pytest

from system_intelligence.core.enums import TargetKind
from system_intelligence.discovery.github_target import GitHubTargetError
from system_intelligence.discovery.target import (
    TargetResolutionError,
    resolve_local_target,
    resolve_target,
)


def test_resolve_local_target_success(tmp_path: Path) -> None:
    target = resolve_local_target(str(tmp_path))
    assert target.kind == TargetKind.LOCAL_PATH
    assert target.locator == str(tmp_path.resolve())
    assert target.name == tmp_path.name


def test_resolve_local_target_missing_path(tmp_path: Path) -> None:
    with pytest.raises(TargetResolutionError, match="does not exist"):
        resolve_local_target(str(tmp_path / "does-not-exist"))


def test_resolve_local_target_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(TargetResolutionError, match="not a directory"):
        resolve_local_target(str(file_path))


def test_resolve_target_delegates_to_local_target_for_a_local_path(tmp_path: Path) -> None:
    target = resolve_target(str(tmp_path))
    assert target.kind == TargetKind.LOCAL_PATH
    assert target.locator == str(tmp_path.resolve())


def test_resolve_target_clones_a_github_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone_dir = tmp_path / "cloned"
    clone_dir.mkdir()

    def _fake_clone(spec: str) -> Path:
        assert spec == "octocat/Hello-World"
        return clone_dir

    monkeypatch.setattr("system_intelligence.discovery.target.clone_github_repository", _fake_clone)

    target = resolve_target("octocat/Hello-World")

    assert target.kind == TargetKind.GITHUB_REPOSITORY
    assert target.name == "octocat/Hello-World"
    assert target.locator == str(clone_dir.resolve())


def test_resolve_target_clone_failure_raises_target_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_clone(spec: str) -> Path:
        raise GitHubTargetError(f"failed to clone {spec!r}: repository not found")

    monkeypatch.setattr("system_intelligence.discovery.target.clone_github_repository", _fake_clone)

    with pytest.raises(TargetResolutionError, match="repository not found"):
        resolve_target("no-such-owner/no-such-repo")
