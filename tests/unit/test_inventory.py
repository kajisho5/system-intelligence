import subprocess
from pathlib import Path

from system_intelligence.core.enums import ComponentKind
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
