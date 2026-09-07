import subprocess
from pathlib import Path

import pytest

from system_intelligence.core.enums import ComponentKind, TargetKind
from system_intelligence.discovery.inventory import discover_local_repository


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)


def test_discover_local_repository(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n", encoding="utf-8"
    )
    _init_repo(tmp_path)

    result = discover_local_repository(str(tmp_path))

    kinds = [c.kind for c in result.snapshot.components]
    assert ComponentKind.REPOSITORY in kinds
    assert ComponentKind.SKILL in kinds
    assert ComponentKind.DOCUMENT in kinds
    assert len(result.ci_jobs) == 1

    repository = next(c for c in result.snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert "Python" in repository.languages  # type: ignore[attr-defined]


def test_discover_local_repository_populates_license(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining "
        "a copy of this software and associated documentation files, to deal in the Software "
        "without restriction.\n",
        encoding="utf-8",
    )
    _init_repo(tmp_path)

    result = discover_local_repository(str(tmp_path))

    repository = next(c for c in result.snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert repository.license == "MIT"  # type: ignore[attr-defined]


def test_discover_local_repository_no_license_leaves_it_none(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)

    result = discover_local_repository(str(tmp_path))

    repository = next(c for c in result.snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert repository.license is None  # type: ignore[attr-defined]


def test_discover_local_repository_populates_last_commit_metadata(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)

    result = discover_local_repository(str(tmp_path))

    repository = next(c for c in result.snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert repository.last_commit_sha  # type: ignore[attr-defined]
    assert repository.last_commit_author == "Test"  # type: ignore[attr-defined]
    assert repository.last_commit_date  # type: ignore[attr-defined]
    assert repository.is_dirty is False  # type: ignore[attr-defined]


def test_discover_local_repository_dirty_working_tree_is_detected(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    result = discover_local_repository(str(tmp_path))

    repository = next(c for c in result.snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert repository.is_dirty is True  # type: ignore[attr-defined]


def test_discover_local_repository_populates_agents(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews PRs\ntools: Read, Grep\n---\n",
        encoding="utf-8",
    )
    _init_repo(tmp_path)

    result = discover_local_repository(str(tmp_path))

    agents = [c for c in result.snapshot.components if c.kind == ComponentKind.AGENT]
    assert len(agents) == 1
    assert agents[0].name == "reviewer"


def test_discover_local_repository_populates_adrs(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-first-decision.md").write_text(
        "# ADR-001: First decision\n\nStatus: Accepted\n", encoding="utf-8"
    )
    _init_repo(tmp_path)

    result = discover_local_repository(str(tmp_path))

    assert len(result.snapshot.adrs) == 1
    assert result.snapshot.adrs[0].number == 1
    assert result.snapshot.adrs[0].status == "Accepted"


def test_discover_local_repository_resolves_a_github_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone_dir = tmp_path / "cloned"
    clone_dir.mkdir()
    (clone_dir / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(clone_dir)

    monkeypatch.setattr(
        "system_intelligence.discovery.target.clone_github_repository", lambda _spec: clone_dir
    )

    result = discover_local_repository("octocat/Hello-World")

    assert result.snapshot.target.kind == TargetKind.GITHUB_REPOSITORY
    assert result.snapshot.target.name == "octocat/Hello-World"
    documents = [c for c in result.snapshot.components if c.kind == ComponentKind.DOCUMENT]
    assert len(documents) == 1


def test_discover_local_repository_ids_are_stable_across_runs(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    _init_repo(tmp_path)

    first = discover_local_repository(str(tmp_path))
    second = discover_local_repository(str(tmp_path))

    first_ids = {c.id for c in first.snapshot.components}
    second_ids = {c.id for c in second.snapshot.components}
    assert first_ids == second_ids
