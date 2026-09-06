import subprocess
from pathlib import Path

from system_intelligence.discovery.git_metadata import collect_git_metadata


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)


def test_collect_git_metadata_non_repo(tmp_path: Path) -> None:
    metadata = collect_git_metadata(tmp_path)
    assert metadata.is_git_repository is False
    assert metadata.evidence == []


def test_collect_git_metadata_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    metadata = collect_git_metadata(tmp_path)
    assert metadata.is_git_repository is True
    assert metadata.default_branch is not None
    assert metadata.last_commit_sha is not None
    assert metadata.last_commit_author == "Test"
    assert metadata.is_dirty is False
    assert len(metadata.evidence) >= 3


def test_collect_git_metadata_dirty(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")
    metadata = collect_git_metadata(tmp_path)
    assert metadata.is_dirty is True
