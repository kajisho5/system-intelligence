from pathlib import Path

from system_intelligence.discovery.agents import detect_agents


def test_detect_agents_standard_format(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "code-reviewer.md").write_text(
        "---\nname: code-reviewer\ndescription: Reviews code for bugs\n"
        "tools: Read, Grep, Glob\nmodel: sonnet\n---\n\nSystem prompt.\n",
        encoding="utf-8",
    )

    agents = detect_agents(tmp_path)

    assert len(agents) == 1
    agent = agents[0]
    assert agent.name == "code-reviewer"
    assert agent.description == "Reviews code for bugs"
    assert agent.tool_names == ["Read", "Grep", "Glob"]
    assert agent.model_provider == "sonnet"
    assert agent.path == ".claude/agents/code-reviewer.md"
    assert agent.is_standard_format is True
    assert agent.evidence


def test_detect_agents_missing_frontmatter_fields(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "weird.md").write_text(
        "---\nname: weird\n---\nNo description.\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert len(agents) == 1
    assert agents[0].name == "weird"
    assert agents[0].description is None
    assert agents[0].is_standard_format is False


def test_detect_agents_no_frontmatter_falls_back_to_filename(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "plain-agent.md").write_text(
        "Just plain text, no frontmatter.\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert len(agents) == 1
    assert agents[0].name == "plain-agent"
    assert agents[0].model_provider is None
    assert agents[0].tool_names == []


def test_detect_agents_no_tools_field_leaves_tool_names_empty(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "a.md").write_text(
        "---\nname: a\ndescription: does a thing\n---\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert agents[0].tool_names == []
    assert agents[0].model_provider is None


def test_detect_agents_none_found_when_directory_absent(tmp_path: Path) -> None:
    assert detect_agents(tmp_path) == []


def test_detect_agents_ignores_non_md_files(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "readme.txt").write_text("not an agent", encoding="utf-8")

    assert detect_agents(tmp_path) == []


def test_detect_agents_only_scans_the_fixed_claude_agents_path(tmp_path: Path) -> None:
    """Unlike SKILL.md's arbitrary-depth search, a `.md` file under some
    other `agents/` directory is never mistaken for a Claude Code subagent
    -- only the exact `.claude/agents/` path is this convention's own."""
    other_agents_dir = tmp_path / "src" / "agents"
    other_agents_dir.mkdir(parents=True)
    (other_agents_dir / "not-a-subagent.md").write_text(
        "---\nname: not-a-subagent\ndescription: x\n---\n", encoding="utf-8"
    )

    assert detect_agents(tmp_path) == []


def test_detect_agents_multiple_agents_sorted(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "b-agent.md").write_text(
        "---\nname: b-agent\ndescription: second\n---\n", encoding="utf-8"
    )
    (agents_dir / "a-agent.md").write_text(
        "---\nname: a-agent\ndescription: first\n---\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert [a.name for a in agents] == ["a-agent", "b-agent"]


def test_detect_agents_tools_field_trims_whitespace(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "a.md").write_text(
        "---\nname: a\ndescription: x\ntools:  Read ,  Write  \n---\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert agents[0].tool_names == ["Read", "Write"]


def test_detect_agents_disallowed_tools_field_populates_permissions(tmp_path: Path) -> None:
    """`disallowedTools` is a documented Claude Code subagent frontmatter
    field (code.claude.com/docs/en/sub-agents) -- `Agent.permissions` has
    existed since the model was introduced specifically for this, but
    nothing ever populated it."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "a.md").write_text(
        "---\nname: a\ndescription: x\ndisallowedTools:  Write ,  Edit  \n---\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert agents[0].permissions == ["Write", "Edit"]


def test_detect_agents_no_disallowed_tools_field_leaves_permissions_empty(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "a.md").write_text(
        "---\nname: a\ndescription: does a thing\n---\n", encoding="utf-8"
    )

    agents = detect_agents(tmp_path)

    assert agents[0].permissions == []
