from pathlib import Path

from system_intelligence.discovery.paths import is_excluded, iter_files


def test_is_excluded_matches_known_vendor_dirs() -> None:
    assert is_excluded((".venv", "lib")) is True
    assert is_excluded(("node_modules", "pkg")) is True
    assert is_excluded(("src", "app")) is False


def test_is_excluded_matches_vendor_tox_and_target_dirs() -> None:
    """vendor (Go `go mod vendor` / PHP Composer's own dependency-vendoring
    convention -- a full copy of every dependency's source tree, including
    its own manifest/README/LICENSE files) is this module's own docstring
    concern realized exactly; .tox and target are the same "dependency
    cache / build output" shape as the already-excluded .venv/dist/build."""
    assert is_excluded(("vendor", "github.com", "pkg", "go.mod")) is True
    assert is_excluded((".tox", "py312", "lib")) is True
    assert is_excluded(("target", "debug", "build")) is True


def test_is_excluded_matches_bare_env_venv_dir() -> None:
    """`python -m venv env` is a real, common convention (widely used in
    older/tutorial-derived Django and Flask projects) alongside the
    already-excluded .venv/venv."""
    assert is_excluded(("env", "lib", "python3.11", "site-packages")) is True


def test_is_excluded_matches_egg_info_suffix() -> None:
    assert is_excluded(("foo.egg-info",)) is True


def test_iter_files_skips_excluded_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")
    vendored = tmp_path / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "vendored.py").write_text("", encoding="utf-8")

    files = iter_files(tmp_path)

    assert {p.name for p in files} == {"app.py"}
