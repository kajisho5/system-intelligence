from pathlib import Path

import pytest

from system_intelligence.core.enums import TargetKind
from system_intelligence.discovery.target import TargetResolutionError, resolve_local_target


def test_resolve_local_target_success(tmp_path: Path) -> None:
    target = resolve_local_target(str(tmp_path))
    assert target.kind == TargetKind.LOCAL_PATH
    assert target.locator == str(tmp_path.resolve())
    assert target.name == tmp_path.name


def test_resolve_local_target_missing_path(tmp_path: Path) -> None:
    with pytest.raises(TargetResolutionError, match="does not exist"):
        resolve_local_target(str(tmp_path / "does-not-exist"))


def test_resolve_local_target_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(TargetResolutionError, match="not a directory"):
        resolve_local_target(str(file_path))
