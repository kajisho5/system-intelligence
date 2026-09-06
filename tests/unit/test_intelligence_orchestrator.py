from pathlib import Path

from system_intelligence.core.enums import ComponentKind, RelationshipType
from system_intelligence.intelligence.intents import resolve_intent
from system_intelligence.intelligence.orchestrator import run_capabilities


def test_documentation_only_flags_missing_docs_without_other_findings(tmp_path: Path) -> None:
    # No README/LICENSE/CONTRIBUTING, but also no CI and no tests — a
    # ci_test_audit run would add findings too, so their absence here
    # proves documentation_only genuinely didn't run it.
    snapshot = run_capabilities(str(tmp_path), ["documentation_audit"])

    categories = {f.category for f in snapshot.findings}
    assert categories == {"documentation_gap"}
    assert len(snapshot.findings) == 3  # README, LICENSE, CONTRIBUTING


def test_documentation_only_does_not_detect_skills_or_languages(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")

    snapshot = run_capabilities(str(tmp_path), ["documentation_audit"])

    kinds = {c.kind for c in snapshot.components}
    assert ComponentKind.SKILL not in kinds  # skill_detection never ran
    repository = next(c for c in snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert repository.languages == []  # structure_scan never ran


def test_circular_imports_only_runs_independently_of_everything_else(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text("import pkg.b\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("import pkg.a\n", encoding="utf-8")

    snapshot = run_capabilities(str(tmp_path), ["circular_dependency_detection"])

    assert len(snapshot.findings) == 1
    assert snapshot.findings[0].category == "circular_dependency"
    # No documentation/CI findings should appear — those capabilities didn't run.
    assert all(f.category == "circular_dependency" for f in snapshot.findings)


def test_diagnose_intent_produces_full_finding_set(tmp_path: Path) -> None:
    snapshot = run_capabilities(str(tmp_path), resolve_intent("diagnose"))

    categories = {f.category for f in snapshot.findings}
    assert "documentation_gap" in categories
    assert "ci_health" in categories
    assert "test_gap" in categories


def test_improve_intent_populates_recommendations(tmp_path: Path) -> None:
    snapshot = run_capabilities(str(tmp_path), resolve_intent("improve"))

    assert len(snapshot.recommendations) == len(snapshot.findings)
    assert len(snapshot.recommendations) > 0


def test_relationship_graph_construction_produces_depends_on_edges(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )

    snapshot = run_capabilities(str(tmp_path), ["relationship_graph_construction"])

    depends_on = [r for r in snapshot.relationships if r.type == RelationshipType.DEPENDS_ON]
    assert len(depends_on) == 1


def test_diagnose_intent_includes_relationship_graph(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )

    snapshot = run_capabilities(str(tmp_path), resolve_intent("diagnose"))

    assert any(r.type == RelationshipType.DEPENDS_ON for r in snapshot.relationships)


def test_dependency_extraction_without_skill_detection(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )

    snapshot = run_capabilities(str(tmp_path), ["dependency_extraction"])

    kinds = {c.kind for c in snapshot.components}
    assert ComponentKind.SKILL not in kinds
    repository = next(c for c in snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert {d.name for d in repository.dependencies} == {"pydantic"}


def test_agent_detection_runs_independently(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: reviews code\n---\nBody.\n", encoding="utf-8"
    )

    snapshot = run_capabilities(str(tmp_path), ["agent_detection"])

    kinds = {c.kind for c in snapshot.components}
    assert ComponentKind.AGENT in kinds


def test_adr_detection_runs_independently(tmp_path: Path) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-use-python.md").write_text("# ADR-001\n", encoding="utf-8")

    snapshot = run_capabilities(str(tmp_path), ["adr_detection"])

    assert len(snapshot.adrs) == 1


def test_diagnose_intent_runs_agent_and_adr_detection(tmp_path: Path) -> None:
    """`si diagnose` (`discover_local_repository` + `analyze_local_repository`)
    always runs agent/ADR detection -- the `diagnose` intent's plan must
    match, or `si plan diagnose`'s preview would silently omit them."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: reviews code\n---\nBody.\n", encoding="utf-8"
    )
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-use-python.md").write_text("# ADR-001\n", encoding="utf-8")

    snapshot = run_capabilities(str(tmp_path), resolve_intent("diagnose"))

    kinds = {c.kind for c in snapshot.components}
    assert ComponentKind.AGENT in kinds
    assert len(snapshot.adrs) == 1


def test_capability_gap_detection_runs_independently(tmp_path: Path) -> None:
    """Mirrors `analysis.gaps.audit_capability_gaps`'s own opt-in
    `.si/requirements.json` contract: a declared-but-missing capability
    must surface even when this capability is requested on its own."""
    si_dir = tmp_path / ".si"
    si_dir.mkdir()
    (si_dir / "requirements.json").write_text(
        '{"capabilities": [{"name": "nonexistent_capability"}]}\n', encoding="utf-8"
    )

    snapshot = run_capabilities(str(tmp_path), ["capability_gap_detection"])

    assert any(f.category == "capability_gap" for f in snapshot.findings)
