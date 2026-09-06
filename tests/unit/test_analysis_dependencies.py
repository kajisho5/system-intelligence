from pathlib import Path

from system_intelligence.analysis.dependencies import (
    extract_dependencies,
    extract_dependencies_by_manifest,
)
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
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
    manifests = [PackageManifest(path="pom.xml", ecosystem="maven", language="Java")]

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


def test_extract_dependencies_by_manifest_groups_by_directory(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "root"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )
    skill_dir = tmp_path / "skills" / "ffmpeg-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "package.json").write_text('{"dependencies": {"react": "^18"}}', encoding="utf-8")
    manifests = [
        PackageManifest(path="pyproject.toml", ecosystem="pypi", language="Python"),
        PackageManifest(
            path="skills/ffmpeg-skill/package.json",
            ecosystem="npm",
            language="JavaScript/TypeScript",
        ),
    ]

    by_directory = extract_dependencies_by_manifest(tmp_path, manifests)

    assert set(by_directory) == {".", "skills/ffmpeg-skill"}
    assert {d.name for d in by_directory["."]} == {"pydantic"}
    assert {d.name for d in by_directory["skills/ffmpeg-skill"]} == {"react"}


def test_extract_dependencies_by_manifest_omits_directories_with_no_parsed_deps(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
    manifests = [PackageManifest(path="pom.xml", ecosystem="maven", language="Java")]

    assert extract_dependencies_by_manifest(tmp_path, manifests) == {}


def test_extract_go_dependencies_manifest_with_no_require_directive_returns_empty(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n\ngo 1.21\n", encoding="utf-8")
    manifests = [PackageManifest(path="go.mod", ecosystem="go", language="Go")]

    assert extract_dependencies_by_manifest(tmp_path, manifests) == {}


def test_extract_cargo_dependencies_manifest_with_no_dependency_sections_returns_empty(
    tmp_path: Path,
) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n", encoding="utf-8")
    manifests = [PackageManifest(path="Cargo.toml", ecosystem="cargo", language="Rust")]

    assert extract_dependencies_by_manifest(tmp_path, manifests) == {}


def test_extract_cargo_dependencies_string_and_table_forms(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\n'
        "[dependencies]\n"
        'serde = "1.0"\n'
        'tokio = { version = "1", features = ["full"] }\n',
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="Cargo.toml", ecosystem="cargo", language="Rust")]

    dependencies = extract_dependencies(tmp_path, manifests)

    by_name = {d.name: d for d in dependencies}
    assert set(by_name) == {"serde", "tokio"}
    assert by_name["serde"].version_constraint == "1.0"
    assert by_name["tokio"].version_constraint == "1"
    assert all(d.ecosystem == "cargo" for d in dependencies)
    assert all(d.evidence for d in dependencies)


def test_extract_cargo_dependencies_dev_and_build_sections(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\n'
        "[dev-dependencies]\n"
        'criterion = "0.5"\n'
        "[build-dependencies]\n"
        'cc = "1.0"\n',
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="Cargo.toml", ecosystem="cargo", language="Rust")]

    dependencies = extract_dependencies(tmp_path, manifests)

    assert {d.name for d in dependencies} == {"criterion", "cc"}


def test_extract_cargo_dependencies_path_and_git_deps_without_version_are_skipped(
    tmp_path: Path,
) -> None:
    """A path/git-only dependency has no registry version to record — must
    be skipped, not recorded with a fabricated or absent constraint."""
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\n'
        "[dependencies]\n"
        'local-crate = { path = "../local-crate" }\n'
        'git-crate = { git = "https://example.com/repo.git" }\n'
        'real-crate = "2.0"\n',
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="Cargo.toml", ecosystem="cargo", language="Rust")]

    dependencies = extract_dependencies(tmp_path, manifests)

    assert {d.name for d in dependencies} == {"real-crate"}


def test_extract_cargo_dependencies_malformed_manifest_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("not valid toml [[[", encoding="utf-8")
    manifests = [PackageManifest(path="Cargo.toml", ecosystem="cargo", language="Rust")]

    assert extract_dependencies(tmp_path, manifests) == []


def test_extract_go_dependencies_single_line_and_block_form(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\ngo 1.21\n\n"
        "require github.com/single/dep v1.2.3\n\n"
        "require (\n"
        "\tgithub.com/pkg/errors v0.9.1\n"
        "\tgolang.org/x/crypto v0.7.0 // indirect\n"
        ")\n",
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="go.mod", ecosystem="go", language="Go")]

    dependencies = extract_dependencies(tmp_path, manifests)

    by_name = {d.name: d for d in dependencies}
    assert set(by_name) == {
        "github.com/single/dep",
        "github.com/pkg/errors",
        "golang.org/x/crypto",
    }
    assert by_name["github.com/single/dep"].version_constraint == "v1.2.3"
    # An indirect dependency is still recorded -- it's a real, declared
    # dependency in Go's own module graph, just not a direct import.
    assert by_name["golang.org/x/crypto"].version_constraint == "v0.7.0"
    assert all(d.ecosystem == "go" for d in dependencies)
    assert all(d.evidence for d in dependencies)


def test_extract_go_dependencies_pseudo_version_is_preserved(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\n"
        "require (\n"
        "\tgithub.com/modern-go/concurrent v0.0.0-20180306012644-bacd9c7ef1dd // indirect\n"
        ")\n",
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="go.mod", ecosystem="go", language="Go")]

    dependencies = extract_dependencies(tmp_path, manifests)

    assert dependencies[0].version_constraint == "v0.0.0-20180306012644-bacd9c7ef1dd"


def test_extract_go_dependencies_ignores_module_go_and_toolchain_directives(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\ngo 1.21\ntoolchain go1.21.5\n\n"
        "require github.com/only/real-dep v1.0.0\n",
        encoding="utf-8",
    )
    manifests = [PackageManifest(path="go.mod", ecosystem="go", language="Go")]

    dependencies = extract_dependencies(tmp_path, manifests)

    assert {d.name for d in dependencies} == {"github.com/only/real-dep"}


def test_extract_go_dependencies_malformed_manifest_missing_file_returns_empty(
    tmp_path: Path,
) -> None:
    manifests = [PackageManifest(path="go.mod", ecosystem="go", language="Go")]

    assert extract_dependencies(tmp_path, manifests) == []


def test_extract_dependencies_flattens_by_manifest_grouping(tmp_path: Path) -> None:
    """`extract_dependencies` stays a pure flattening of the by-manifest view
    — same combined ids/names as before this function existed (each
    function call re-derives its own Evidence with a fresh timestamp, so
    the two calls' objects aren't `==`, but must describe the same facts)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "root"\ndependencies = ["pydantic"]\n', encoding="utf-8"
    )
    manifests = [PackageManifest(path="pyproject.toml", ecosystem="pypi", language="Python")]

    by_directory = extract_dependencies_by_manifest(tmp_path, manifests)
    flat = extract_dependencies(tmp_path, manifests)
    grouped = [dep for deps in by_directory.values() for dep in deps]

    assert [d.id for d in flat] == [d.id for d in grouped]
    assert [d.name for d in flat] == [d.name for d in grouped]
