from pathlib import Path

from system_intelligence.analysis.unused import audit_unused_skills, classify_skill_usage
from system_intelligence.core.entities import Agent, Skill
from system_intelligence.core.enums import UsageStatus


def test_classify_skill_usage_unreferenced(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "orphan"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: orphan\n---\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Nothing about it here.\n", encoding="utf-8")
    # A non-text file mentioning the name must not count as a reference.
    (tmp_path / "orphan.png").write_bytes(b"\x89PNG orphan fake binary")

    skill = Skill(name="orphan", path="skills/orphan/SKILL.md")
    status, references = classify_skill_usage(skill, tmp_path)

    assert status == UsageStatus.UNREFERENCED
    assert references == []


def test_classify_skill_usage_referenced(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "used"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: used\n---\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("See the 'used' skill for details.\n", encoding="utf-8")

    skill = Skill(name="used", path="skills/used/SKILL.md")
    status, references = classify_skill_usage(skill, tmp_path)

    assert status == UsageStatus.UNKNOWN
    assert references == ["README.md"]


def test_audit_unused_skills_finding_has_evidence_and_medium_confidence(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "orphan"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: orphan\n---\n", encoding="utf-8")
    skill = Skill(name="orphan", path="skills/orphan/SKILL.md")

    findings = audit_unused_skills([skill], tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == "unused_candidate"
    assert "unreferenced" in finding.statement
    assert "Runtime usage could not be verified" in finding.statement
    assert finding.confidence.value == "medium"
    assert finding.evidence[0].confidence.value == "verified"


def test_classify_skill_usage_root_level_skill_referenced(tmp_path: Path) -> None:
    # A SKILL.md at the repository root has an empty "own directory" —
    # only the file itself should be excluded, not the whole repo.
    (tmp_path / "SKILL.md").write_text("---\nname: root-skill\n---\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text("# uses root-skill here\n", encoding="utf-8")

    skill = Skill(name="root-skill", path="SKILL.md")
    status, references = classify_skill_usage(skill, tmp_path)

    assert status == UsageStatus.UNKNOWN
    assert references == ["consumer.py"]


def test_classify_skill_usage_root_level_skill_unreferenced(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: root-skill\n---\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("nothing relevant\n", encoding="utf-8")

    skill = Skill(name="root-skill", path="SKILL.md")
    status, references = classify_skill_usage(skill, tmp_path)

    assert status == UsageStatus.UNREFERENCED
    assert references == []


def test_audit_unused_skills_no_finding_when_referenced(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "used"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: used\n---\n", encoding="utf-8")
    (tmp_path / "docs.md").write_text("The used skill does X.\n", encoding="utf-8")
    skill = Skill(name="used", path="skills/used/SKILL.md")

    assert audit_unused_skills([skill], tmp_path) == []


def test_classify_skill_usage_unreferenced_agent(tmp_path: Path) -> None:
    """An Agent (.claude/agents/*.md) is a capability-declaring component
    exactly like a Skill -- previously entirely excluded from unused
    detection, so an unreferenced Agent silently got no finding at all."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "orphan-agent.md").write_text(
        "---\nname: orphan-agent\ndescription: x\n---\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("Nothing about it here.\n", encoding="utf-8")

    agent = Agent(name="orphan-agent", path=".claude/agents/orphan-agent.md")
    status, references = classify_skill_usage(agent, tmp_path)

    assert status == UsageStatus.UNREFERENCED
    assert references == []


def test_audit_unused_skills_flags_unreferenced_agent(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "orphan-agent.md").write_text(
        "---\nname: orphan-agent\ndescription: x\n---\n", encoding="utf-8"
    )
    agent = Agent(name="orphan-agent", path=".claude/agents/orphan-agent.md")

    findings = audit_unused_skills([agent], tmp_path)

    assert len(findings) == 1
    assert findings[0].category == "unused_candidate"
    assert findings[0].affected_entity_ids == [agent.id]


def test_audit_unused_skills_no_finding_for_referenced_agent(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "code-reviewer.md").write_text(
        "---\nname: code-reviewer\ndescription: x\n---\n", encoding="utf-8"
    )
    (tmp_path / "docs.md").write_text("Invoke the code-reviewer agent.\n", encoding="utf-8")
    agent = Agent(name="code-reviewer", path=".claude/agents/code-reviewer.md")

    assert audit_unused_skills([agent], tmp_path) == []
