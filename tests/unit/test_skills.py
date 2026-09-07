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
    (skill_dir / "assets").mkdir()
    (skill_dir / "assets" / "logo.png").write_text("", encoding="utf-8")

    skills = detect_skills(tmp_path)

    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "example-skill"
    assert skill.description == "Does a thing"
    assert skill.is_standard_format is True
    assert skill.scripts == ["scripts/run.py"]
    assert skill.assets == ["assets/logo.png"]
    assert skill.evidence


def test_detect_skills_assets_only(tmp_path: Path) -> None:
    """A Skill bundling only `assets/` (no `scripts/`/`references/`) is
    exactly as valid as one with only `scripts/` -- each of the three
    optional subdirectories is listed independently."""
    skill_dir = tmp_path / "skills" / "asset-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: asset-skill\ndescription: Ships only assets\n---\n", encoding="utf-8"
    )
    (skill_dir / "assets").mkdir()
    (skill_dir / "assets" / "template.docx").write_text("", encoding="utf-8")

    skills = detect_skills(tmp_path)

    assert len(skills) == 1
    skill = skills[0]
    assert skill.assets == ["assets/template.docx"]
    assert skill.scripts == []
    assert skill.references == []


def test_detect_skills_allowed_tools_field_populates_tool_names(tmp_path: Path) -> None:
    """`allowed-tools` is a documented Agent Skills frontmatter field
    (code.claude.com/docs/en/skills) -- verified live against a real,
    vendored SKILL.md (playwright-cli) using this exact space-separated
    form: `allowed-tools: Bash(playwright-cli:*) Bash(npx:*)`."""
    skill_dir = tmp_path / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: x\nallowed-tools: Bash(git add *) Read\n---\n",
        encoding="utf-8",
    )

    skills = detect_skills(tmp_path)

    assert skills[0].tool_names == ["Bash(git add *)", "Read"]


def test_detect_skills_disallowed_tools_field_populates_permissions(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: x\ndisallowed-tools: Write, Edit\n---\n",
        encoding="utf-8",
    )

    skills = detect_skills(tmp_path)

    assert skills[0].permissions == ["Write", "Edit"]


def test_detect_skills_no_allowed_or_disallowed_tools_fields_leave_lists_empty(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: x\n---\n", encoding="utf-8"
    )

    skills = detect_skills(tmp_path)

    assert skills[0].tool_names == []
    assert skills[0].permissions == []
    assert skills[0].triggers == []


def test_detect_skills_paths_field_populates_triggers(tmp_path: Path) -> None:
    """`paths` is a documented Agent Skills frontmatter field
    (code.claude.com/docs/en/skills: "Glob patterns that limit when this
    skill is activated") -- `Skill.triggers` has existed on the model
    since Phase 1 (docs/design/docs/05-analysis-engine.md lists it
    alongside `scripts`/`references`) but nothing ever populated it."""
    skill_dir = tmp_path / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: x\npaths: src/**/*.{ts,tsx}, docs/**/*.md\n---\n",
        encoding="utf-8",
    )

    skills = detect_skills(tmp_path)

    assert skills[0].triggers == ["src/**/*.{ts,tsx}", "docs/**/*.md"]


def test_detect_skills_no_paths_field_leaves_triggers_empty(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "example-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: x\n---\n", encoding="utf-8"
    )

    skills = detect_skills(tmp_path)

    assert skills[0].triggers == []


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
