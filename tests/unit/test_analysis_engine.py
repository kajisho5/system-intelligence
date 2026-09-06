import subprocess
from pathlib import Path

from system_intelligence.analysis.engine import analyze_local_repository
from system_intelligence.core.entities import Repository
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
