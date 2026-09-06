from pathlib import Path

from system_intelligence.core.enums import ComponentKind
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


def test_dependency_extraction_without_skill_detection(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )

    snapshot = run_capabilities(str(tmp_path), ["dependency_extraction"])

    kinds = {c.kind for c in snapshot.components}
    assert ComponentKind.SKILL not in kinds
    repository = next(c for c in snapshot.components if c.kind == ComponentKind.REPOSITORY)
    assert {d.name for d in repository.dependencies} == {"pydantic"}
