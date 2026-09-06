from pathlib import Path

from system_intelligence.discovery.structure import scan_structure


def test_scan_structure_detects_languages_and_manifest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "util.py").write_text("pass\n", encoding="utf-8")

    result = scan_structure(tmp_path)

    assert result.language_file_counts.get("Python") == 2
    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].ecosystem == "pypi"
    assert result.evidence


def test_scan_structure_excludes_vendor_directories(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "some-pkg"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text("", encoding="utf-8")
    (tmp_path / "app.js").write_text("", encoding="utf-8")

    result = scan_structure(tmp_path)

    assert result.language_file_counts.get("JavaScript") == 1


def test_scan_structure_empty_directory(tmp_path: Path) -> None:
    result = scan_structure(tmp_path)
    assert result.languages == []
    assert result.package_manifests == []


def test_scan_structure_detects_pipfile(tmp_path: Path) -> None:
    """A Pipenv project has no pyproject.toml/setup.py at all -- Pipfile
    must be recognized on its own, not just alongside those."""
    (tmp_path / "Pipfile").write_text("[packages]\n", encoding="utf-8")

    result = scan_structure(tmp_path)

    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].ecosystem == "pypi"


def test_scan_structure_detects_gradle_kotlin_dsl(tmp_path: Path) -> None:
    (tmp_path / "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")

    result = scan_structure(tmp_path)

    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].ecosystem == "gradle"
