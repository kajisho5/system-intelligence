from pathlib import Path

from system_intelligence.analysis.dependencies import extract_dependencies
from system_intelligence.discovery.structure import PackageManifest


def test_extract_pyproject_dependencies(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["pydantic>=2.6,<3", "typer"]\n',
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="pyproject.toml", ecosystem="pypi", language="Python")]

    dependencies = extract_dependencies(tmp_path, manifests)

    names = {d.name for d in dependencies}
    assert names == {"pydantic", "typer"}
    pydantic = next(d for d in dependencies if d.name == "pydantic")
    assert pydantic.version_constraint == ">=2.6,<3"
    assert pydantic.ecosystem == "pypi"
    assert pydantic.evidence


def test_extract_package_json_dependencies(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}, "devDependencies": {"eslint": "^9.0.0"}}',
        encoding="utf-8",
    )
    manifests = [
        PackageManifest(path="package.json", ecosystem="npm", language="JavaScript/TypeScript")
    ]

    dependencies = extract_dependencies(tmp_path, manifests)

    names = {d.name for d in dependencies}
    assert names == {"react", "eslint"}
    assert all(d.ecosystem == "npm" for d in dependencies)


def test_extract_dependencies_unknown_manifest_type_ignored(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n", encoding="utf-8")
    manifests = [PackageManifest(path="Cargo.toml", ecosystem="cargo", language="Rust")]

    assert extract_dependencies(tmp_path, manifests) == []


def test_extract_dependencies_malformed_manifest_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("not valid toml [[[", encoding="utf-8")
    manifests = [PackageManifest(path="pyproject.toml", ecosystem="pypi", language="Python")]

    assert extract_dependencies(tmp_path, manifests) == []


def test_extract_dependencies_malformed_package_json_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("not valid json {{{", encoding="utf-8")
    manifests = [PackageManifest(path="package.json", ecosystem="npm", language="JavaScript")]

    assert extract_dependencies(tmp_path, manifests) == []


def test_extract_dependencies_skips_unparseable_requirement_string(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["", "typer"]\n', encoding="utf-8"
    )
    manifests = [PackageManifest(path="pyproject.toml", ecosystem="pypi", language="Python")]

    dependencies = extract_dependencies(tmp_path, manifests)

    assert {d.name for d in dependencies} == {"typer"}


def test_extract_package_json_dependencies_non_dict_section_is_ignored(tmp_path: Path) -> None:
    # A malformed-but-valid-JSON package.json: "dependencies" is a list, not
    # the conventional name->version mapping. Must degrade, not crash.
    (tmp_path / "package.json").write_text('{"dependencies": ["a", "b"]}', encoding="utf-8")
    manifests = [PackageManifest(path="package.json", ecosystem="npm", language="JavaScript")]

    assert extract_dependencies(tmp_path, manifests) == []


def test_extract_dependencies_same_package_in_two_manifests_does_not_collide(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "root"\ndependencies = ["pydantic>=2"]\n', encoding="utf-8"
    )
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    (sub_dir / "pyproject.toml").write_text(
        '[project]\nname = "sub"\ndependencies = ["pydantic<2"]\n', encoding="utf-8"
    )
    manifests = [
        PackageManifest(path="pyproject.toml", ecosystem="pypi", language="Python"),
        PackageManifest(path="sub/pyproject.toml", ecosystem="pypi", language="Python"),
    ]

    dependencies = extract_dependencies(tmp_path, manifests)

    assert len(dependencies) == 2
    assert len({d.id for d in dependencies}) == 2
    constraints = {d.version_constraint for d in dependencies}
    assert constraints == {">=2", "<2"}
