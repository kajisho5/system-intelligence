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


def test_scan_structure_detects_requirements_txt(tmp_path: Path) -> None:
    """Many non-packaged Python projects (scripts, container images) have
    only a requirements.txt -- no pyproject.toml/setup.py/Pipfile at all."""
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")

    result = scan_structure(tmp_path)

    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].ecosystem == "pypi"


def test_scan_structure_detects_composer_json(tmp_path: Path) -> None:
    """PHP's de facto standard package manifest (Packagist/Composer) --
    LANGUAGE_EXTENSIONS already recognizes .php, but PACKAGE_MANIFESTS had
    no matching entry, so a PHP repository's manifest was silently never
    reported as ecosystem evidence."""
    (tmp_path / "composer.json").write_text('{"require": {}}\n', encoding="utf-8")

    result = scan_structure(tmp_path)

    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].ecosystem == "packagist"
    assert result.package_manifests[0].language == "PHP"


def test_scan_structure_detects_additional_languages(tmp_path: Path) -> None:
    """PHP/C/C++/C#/Kotlin/Swift were entirely unrepresented in
    LANGUAGE_EXTENSIONS -- a repository using any of them previously
    contributed zero file counts for its own primary language(s)."""
    (tmp_path / "index.php").write_text("<?php\n", encoding="utf-8")
    (tmp_path / "main.c").write_text("int main() {}\n", encoding="utf-8")
    (tmp_path / "app.cpp").write_text("int main() {}\n", encoding="utf-8")
    (tmp_path / "Program.cs").write_text("class Program {}\n", encoding="utf-8")
    (tmp_path / "Main.kt").write_text("fun main() {}\n", encoding="utf-8")
    (tmp_path / "App.swift").write_text('print("hi")\n', encoding="utf-8")

    result = scan_structure(tmp_path)

    assert result.language_file_counts == {
        "PHP": 1,
        "C": 1,
        "C++": 1,
        "C#": 1,
        "Kotlin": 1,
        "Swift": 1,
    }


def test_scan_structure_excludes_bare_env_venv_dir(tmp_path: Path) -> None:
    """`python -m venv env` (no leading dot, unlike .venv) is a real, common
    convention -- an installed third-party package's own setup.py under it
    must never be misattributed as the target repository's own manifest."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["requests"]\n', encoding="utf-8"
    )
    installed = tmp_path / "env" / "lib" / "python3.11" / "site-packages" / "somepkg"
    installed.mkdir(parents=True)
    (installed / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='somepkg')\n", encoding="utf-8"
    )

    result = scan_structure(tmp_path)

    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].path == "pyproject.toml"


def test_scan_structure_excludes_vendored_go_modules(tmp_path: Path) -> None:
    """A `go mod vendor`-managed project checks in a full copy of every
    dependency's own source tree -- including its own go.mod -- under
    vendor/. That vendored go.mod must never be reported as if it were the
    target repository's own dependency manifest."""
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\nrequire github.com/pkg/errors v0.9.1\n", encoding="utf-8"
    )
    vendored = tmp_path / "vendor" / "github.com" / "pkg" / "errors"
    vendored.mkdir(parents=True)
    (vendored / "go.mod").write_text(
        "module github.com/pkg/errors\n\nrequire golang.org/x/sys v0.5.0\n", encoding="utf-8"
    )

    result = scan_structure(tmp_path)

    assert len(result.package_manifests) == 1
    assert result.package_manifests[0].path == "go.mod"
