from pathlib import Path

from system_intelligence.analysis.architecture import (
    build_import_graph,
    detect_circular_dependencies,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_circular_dependencies_absolute_imports(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "a.py", "import pkg.b\n")
    _write(tmp_path / "pkg" / "b.py", "import pkg.a\n")

    findings = detect_circular_dependencies(tmp_path)

    assert len(findings) == 1
    assert findings[0].category == "circular_dependency"
    assert "pkg.a" in findings[0].statement
    assert "pkg.b" in findings[0].statement
    assert findings[0].confidence.value == "verified"


def test_detect_circular_dependencies_relative_imports(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "a.py", "from .b import thing\n")
    _write(tmp_path / "pkg" / "b.py", "from .a import other\n")

    findings = detect_circular_dependencies(tmp_path)

    assert len(findings) == 1


def test_no_circular_dependency_for_acyclic_imports(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "a.py", "import pkg.b\n")
    _write(tmp_path / "pkg" / "b.py", "x = 1\n")

    assert detect_circular_dependencies(tmp_path) == []


def test_build_import_graph_ignores_external_imports(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "a.py", "import os\nimport sys\nfrom typing import Any\n")

    graph = build_import_graph(tmp_path)

    assert graph["pkg.a"] == set()


def test_build_import_graph_skips_files_with_syntax_errors(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "broken.py", "def f(:\n")

    graph = build_import_graph(tmp_path)

    assert "pkg.broken" not in graph or graph["pkg.broken"] == set()


def test_resolve_from_import_beyond_package_root_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "from ... import something\n")

    graph = build_import_graph(tmp_path)

    assert graph["pkg"] == set()


def test_build_import_graph_uses_src_layout(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "__init__.py", "")
    _write(tmp_path / "src" / "pkg" / "a.py", "import pkg.b\n")
    _write(tmp_path / "src" / "pkg" / "b.py", "import pkg.a\n")

    findings = detect_circular_dependencies(tmp_path)

    assert len(findings) == 1
