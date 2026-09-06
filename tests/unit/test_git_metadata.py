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
    assert metadata.last_commit_sha is not None
    assert metadata.last_commit_author == "Test"
    assert metadata.is_dirty is False
    assert len(metadata.evidence) >= 2


def test_collect_git_metadata_no_remote_leaves_default_branch_unset(tmp_path: Path) -> None:
    """A plain `git init` repo with no remote configured has no concept of
    a "default branch" this collector could determine without guessing --
    must never be filled in from the current checkout as a stand-in."""
    _init_repo(tmp_path)
    metadata = collect_git_metadata(tmp_path)
    assert metadata.default_branch is None


def test_collect_git_metadata_resolves_default_branch_from_remote(tmp_path: Path) -> None:
    """`default_branch` must name the remote's own default branch (set
    locally at clone time via refs/remotes/origin/HEAD), not whichever
    branch this particular working tree happens to have checked out."""
    remote_path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote_path)], check=True)
    work_path = tmp_path / "work"
    work_path.mkdir()
    _init_repo(work_path)
    subprocess.run(["git", "branch", "-m", "master", "main"], cwd=work_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote_path)], cwd=work_path, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work_path, check=True)
    subprocess.run(["git", "remote", "set-head", "origin", "main"], cwd=work_path, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature-branch"], cwd=work_path, check=True)

    metadata = collect_git_metadata(work_path)

    assert metadata.default_branch == "main"


def test_collect_git_metadata_detached_head_still_resolves_default_branch(
    tmp_path: Path,
) -> None:
    """The common real-world case for a CI checkout: HEAD is detached at a
    specific commit, not on any branch at all. `git rev-parse --abbrev-ref
    HEAD` would return the literal string "HEAD" here -- default_branch
    must never report that as if it were a real branch name."""
    remote_path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote_path)], check=True)
    work_path = tmp_path / "work"
    work_path.mkdir()
    _init_repo(work_path)
    subprocess.run(["git", "branch", "-m", "master", "main"], cwd=work_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote_path)], cwd=work_path, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work_path, check=True)
    subprocess.run(["git", "remote", "set-head", "origin", "main"], cwd=work_path, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach"], cwd=work_path, check=True)

    metadata = collect_git_metadata(work_path)

    assert metadata.default_branch == "main"


def test_collect_git_metadata_dirty(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")
    metadata = collect_git_metadata(tmp_path)
    assert metadata.is_dirty is True
