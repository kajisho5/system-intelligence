from pathlib import Path

from system_intelligence.discovery.paths import is_excluded, iter_files


def test_is_excluded_matches_known_vendor_dirs() -> None:
    assert is_excluded((".venv", "lib")) is True
    assert is_excluded(("node_modules", "pkg")) is True
    assert is_excluded(("src", "app")) is False


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
