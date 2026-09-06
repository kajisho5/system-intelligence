import subprocess
from pathlib import Path

import pytest

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.governance import Approval
from system_intelligence.execution.local_git import LocalGitError, apply_plan
from system_intelligence.execution.plan import ChangePlan


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)


def _plan(**overrides: object) -> ChangePlan:
    defaults: dict[str, object] = {
        "branch_name": "si/add-license",
        "commit_message": "Add LICENSE",
        "files": {"LICENSE": "MIT\n"},
    }
    defaults.update(overrides)
    return ChangePlan(**defaults)  # type: ignore[arg-type]


def _approval_for(repo_root: Path) -> Approval:
    return Approval(
        actor="human:test",
        scope="repository",
        action="create_local_branch_and_commit",
        target=str(repo_root),
        permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )


def test_apply_plan_without_approval_is_denied_and_touches_nothing(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    result = apply_plan(_plan(), tmp_path)

    assert result.applied is False
    assert "no matching approval" in result.decision.reason
    branches = subprocess.run(
        ["git", "branch"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "si/add-license" not in branches
    assert not (tmp_path / "LICENSE").exists()


def test_apply_plan_with_approval_creates_branch_and_commits(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    approval = _approval_for(tmp_path)

    result = apply_plan(_plan(), tmp_path, approvals=[approval])

    assert result.applied is True
    assert result.branch_name == "si/add-license"
    assert result.files_written == ["LICENSE"]
    assert result.commit_sha is not None
    assert (tmp_path / "LICENSE").read_text(encoding="utf-8") == "MIT\n"

    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert current_branch == "si/add-license"

    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "Add LICENSE"


def test_apply_plan_never_pushes_or_touches_remote(tmp_path: Path) -> None:
    # No remote is configured at all — if this ever tried to push, it would
    # fail loudly. Success here proves no push was attempted.
    _init_repo(tmp_path)
    approval = _approval_for(tmp_path)

    result = apply_plan(_plan(), tmp_path, approvals=[approval])

    assert result.applied is True
    remotes = subprocess.run(
        ["git", "remote"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert remotes.strip() == ""


def test_apply_plan_rejects_path_traversal(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    approval = _approval_for(tmp_path)
    plan = _plan(files={"../../etc/evil": "pwned"})

    with pytest.raises(LocalGitError, match="outside the repository root"):
        apply_plan(plan, tmp_path, approvals=[approval])

    # No branch should have been created — validation happens before checkout.
    branches = subprocess.run(
        ["git", "branch"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "si/add-license" not in branches


def test_apply_plan_rejects_absolute_path(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    approval = _approval_for(tmp_path)
    outside_target = tmp_path.parent / "escaped.txt"
    plan = _plan(files={str(outside_target): "pwned"})

    with pytest.raises(LocalGitError, match="outside the repository root"):
        apply_plan(plan, tmp_path, approvals=[approval])

    assert not outside_target.exists()


def test_apply_plan_empty_files_raises(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    approval = _approval_for(tmp_path)

    with pytest.raises(LocalGitError, match="empty"):
        apply_plan(_plan(files={}), tmp_path, approvals=[approval])


def test_apply_plan_non_git_directory_raises(tmp_path: Path) -> None:
    approval = _approval_for(tmp_path)

    with pytest.raises(LocalGitError, match="not a git working tree"):
        apply_plan(_plan(), tmp_path, approvals=[approval])


def test_apply_plan_existing_branch_name_raises(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    subprocess.run(["git", "branch", "si/add-license"], cwd=tmp_path, check=True)
    approval = _approval_for(tmp_path)

    with pytest.raises(LocalGitError, match="checkout"):
        apply_plan(_plan(), tmp_path, approvals=[approval])


def test_preview_lines_lists_branch_files_and_commit_message() -> None:
    plan = _plan(files={"LICENSE": "MIT\n", "NOTICE": "Copyright\n"})

    lines = plan.preview_lines()

    assert lines == [
        "Create local branch 'si/add-license'",
        "Write 2 file(s): LICENSE, NOTICE",
        "Commit with message: 'Add LICENSE'",
    ]


def test_preview_lines_includes_description_when_present() -> None:
    plan = _plan(description="Add the missing LICENSE file.")

    lines = plan.preview_lines()

    assert lines[0] == "Add the missing LICENSE file."
    assert len(lines) == 4
