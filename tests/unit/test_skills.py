from pathlib import Path

from system_intelligence.discovery.skills import detect_skills


def test_detect_skills_standard_format(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: Does a thing\n---\n\nInstructions.\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "run.py").write_text("", encoding="utf-8")

    skills = detect_skills(tmp_path)

    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "example-skill"
    assert skill.description == "Does a thing"
    assert skill.is_standard_format is True
    assert skill.scripts == ["scripts/run.py"]
    assert skill.evidence


def test_detect_skills_missing_frontmatter_fields(tmp_path: Path) -> None:
    skill_dir = tmp_path / "weird-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: weird-skill\n---\nNo description.\n", encoding="utf-8"
    )

    skills = detect_skills(tmp_path)

    assert len(skills) == 1
    assert skills[0].is_standard_format is False


def test_detect_skills_no_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "plain-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Just plain text, no frontmatter.\n", encoding="utf-8")

    skills = detect_skills(tmp_path)

    assert len(skills) == 1
    assert skills[0].is_standard_format is False
    assert skills[0].name == "plain-skill"


def test_detect_skills_none_found(tmp_path: Path) -> None:
    assert detect_skills(tmp_path) == []


def test_detect_skills_ignores_vendored_venv_and_git_dirs(tmp_path: Path) -> None:
    for vendor_dir in (
        tmp_path / ".venv" / "lib" / "some-pkg" / ".agents" / "skills" / "x",
        tmp_path / "node_modules" / "some-pkg" / "skills" / "x",
        tmp_path / ".git" / "skills" / "x",
    ):
        vendor_dir.mkdir(parents=True)
        (vendor_dir / "SKILL.md").write_text(
            "---\nname: vendored\ndescription: should not be found\n---\n", encoding="utf-8"
        )

    assert detect_skills(tmp_path) == []
