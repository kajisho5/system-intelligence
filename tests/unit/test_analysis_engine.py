import subprocess
from pathlib import Path

from system_intelligence.analysis.engine import analyze_local_repository
from system_intelligence.core.entities import Repository, Skill
from system_intelligence.core.enums import RelationshipType
from system_intelligence.discovery.inventory import discover_local_repository


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=path, check=True)


def test_analyze_local_repository_populates_findings_and_dependencies(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    # No README/LICENSE/CONTRIBUTING, no CI, no tests -> several findings.
    categories = {f.category for f in result.snapshot.findings}
    assert "documentation_gap" in categories
    assert "ci_health" in categories
    assert "test_gap" in categories

    repository = next(c for c in result.snapshot.components if isinstance(c, Repository))
    dependency_names = {d.name for d in repository.dependencies}
    assert dependency_names == {"pydantic"}

    depends_on = [r for r in result.snapshot.relationships if r.type == RelationshipType.DEPENDS_ON]
    assert len(depends_on) == 1
    assert depends_on[0].source_id == repository.id


def test_analyze_local_repository_healthy_project_has_no_gap_findings(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("Contribute\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("", encoding="utf-8")
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    categories = {f.category for f in result.snapshot.findings}
    assert "documentation_gap" not in categories
    assert "ci_health" not in categories
    assert "test_gap" not in categories


def _write_skill(root: Path, rel_dir: str, name: str) -> None:
    skill_dir = root / rel_dir
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: does things\n---\nBody.\n", encoding="utf-8"
    )


def test_analyze_local_repository_attributes_dependencies_to_owning_skill(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "root"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )
    _write_skill(tmp_path, "skills/ffmpeg-skill", "ffmpeg-skill")
    (tmp_path / "skills" / "ffmpeg-skill" / "package.json").write_text(
        '{"dependencies": {"minimist": "^1.0.0"}}', encoding="utf-8"
    )
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    repository = next(c for c in result.snapshot.components if isinstance(c, Repository))
    skill = next(c for c in result.snapshot.components if isinstance(c, Skill))

    # The root manifest's dependency stays on the Repository; the Skill's
    # own manifest's dependency is attributed to the Skill, not folded into
    # the Repository as before.
    assert {d.name for d in repository.dependencies} == {"pydantic"}
    assert {d.name for d in skill.dependencies} == {"minimist"}

    depends_on = {
        r.source_id: r.target_id
        for r in result.snapshot.relationships
        if r.type == RelationshipType.DEPENDS_ON
    }
    assert depends_on[repository.id] == next(d.id for d in repository.dependencies)
    assert depends_on[skill.id] == next(d.id for d in skill.dependencies)


def test_analyze_local_repository_two_skills_each_keep_their_own_dependencies(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "skills/a-skill", "a-skill")
    (tmp_path / "skills" / "a-skill" / "package.json").write_text(
        '{"dependencies": {"left-pad": "^1.0.0"}}', encoding="utf-8"
    )
    _write_skill(tmp_path, "skills/b-skill", "b-skill")
    (tmp_path / "skills" / "b-skill" / "pyproject.toml").write_text(
        '[project]\nname = "b-skill"\ndependencies = ["requests"]\n', encoding="utf-8"
    )
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    skills = {c.name: c for c in result.snapshot.components if isinstance(c, Skill)}
    assert {d.name for d in skills["a-skill"].dependencies} == {"left-pad"}
    assert {d.name for d in skills["b-skill"].dependencies} == {"requests"}

    repository = next(c for c in result.snapshot.components if isinstance(c, Repository))
    assert repository.dependencies == []


def test_analyze_local_repository_unattributable_manifest_falls_back_to_repository(
    tmp_path: Path,
) -> None:
    """A manifest under a directory with no matching Component (no Skill
    there) is attributed to the Repository rather than dropped or guessed
    at — the same fallback used before per-Component attribution existed."""
    tools_dir = tmp_path / "tools" / "random"
    tools_dir.mkdir(parents=True)
    (tools_dir / "package.json").write_text(
        '{"dependencies": {"chalk": "^5.0.0"}}', encoding="utf-8"
    )
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    repository = next(c for c in result.snapshot.components if isinstance(c, Repository))
    assert {d.name for d in repository.dependencies} == {"chalk"}


def test_analyze_local_repository_no_manifests_leaves_dependencies_empty(tmp_path: Path) -> None:
    _write_skill(tmp_path, "skills/lonely-skill", "lonely-skill")
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    repository = next(c for c in result.snapshot.components if isinstance(c, Repository))
    skill = next(c for c in result.snapshot.components if isinstance(c, Skill))
    assert repository.dependencies == []
    assert skill.dependencies == []


def test_analyze_local_repository_populates_capability_consumers(tmp_path: Path) -> None:
    """End-to-end: a Skill whose own manifest declares a dependency on
    another discovered Skill's name becomes a recorded consumer of that
    Skill's Capability, and a USES relationship is materialized (R4 + P1-1
    wired all the way through `si diagnose`)."""
    _write_skill(tmp_path, "skills/ffmpeg-skill", "ffmpeg-skill")
    _write_skill(tmp_path, "skills/subtitle-skill", "subtitle-skill")
    (tmp_path / "skills" / "subtitle-skill" / "package.json").write_text(
        '{"dependencies": {"ffmpeg-skill": "1.0.0"}}', encoding="utf-8"
    )
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    ffmpeg_capability = next(c for c in result.snapshot.capabilities if c.name == "ffmpeg-skill")
    subtitle_skill = next(
        c for c in result.snapshot.components if isinstance(c, Skill) and c.name == "subtitle-skill"
    )
    assert ffmpeg_capability.consumer_ids == [subtitle_skill.id]

    uses = [r for r in result.snapshot.relationships if r.type == RelationshipType.USES]
    assert len(uses) == 1
    assert uses[0].source_id == subtitle_skill.id
    assert uses[0].target_id == ffmpeg_capability.id


def test_analyze_local_repository_without_requirements_file_has_no_capability_gap(
    tmp_path: Path,
) -> None:
    """The overwhelming common case: no `.si/requirements.json` at all
    must never produce an inferred capability_gap finding."""
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    categories = {f.category for f in result.snapshot.findings}
    assert "capability_gap" not in categories


def test_analyze_local_repository_reports_declared_capability_gap_end_to_end(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "skills/ffmpeg-skill", "ffmpeg-skill")
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "requirements.json").write_text(
        '{"capabilities": [{"name": "ffmpeg-skill"}, {"name": "pdf export"}]}', encoding="utf-8"
    )
    _init_repo(tmp_path)

    discovery = discover_local_repository(str(tmp_path))
    result = analyze_local_repository(discovery)

    gap_findings = [f for f in result.snapshot.findings if f.category == "capability_gap"]
    assert len(gap_findings) == 1
    assert "pdf export" in gap_findings[0].statement
