import json
import os
from pathlib import Path
from typing import Any

import pytest

from system_intelligence.core.evidence import EvidenceKind
from system_intelligence.discovery import discover_local_repository
from system_intelligence.discovery.ownership import (
    collect_ownership,
    read_declared_ownership,
    read_ownership_map,
)


def _declare(root: Path, declaration: Any) -> None:
    (root / ".si").mkdir(exist_ok=True)
    (root / ".si" / "ownership.json").write_text(json.dumps(declaration), encoding="utf-8")


def test_no_declaration_means_no_observations(tmp_path: Path) -> None:
    assert read_declared_ownership(tmp_path) == []
    assert collect_ownership(tmp_path) == []


def test_declaration_and_listed_map_are_read(tmp_path: Path) -> None:
    (tmp_path / "ecosystem.json").write_text('{"components": []}', encoding="utf-8")
    declaration = {"maps": [{"path": "ecosystem.json"}], "job_capabilities": {"job": ["c"]}}
    _declare(tmp_path, declaration)

    [own, listed] = read_declared_ownership(tmp_path)

    assert (own.kind, own.label, own.document, own.error) == (
        "declaration",
        ".si/ownership.json",
        declaration,
        None,
    )
    assert (listed.kind, listed.label, listed.document) == (
        "file",
        "ecosystem.json",
        {"components": []},
    )
    assert listed.evidence.kind == EvidenceKind.FILE


@pytest.mark.parametrize("path", ["/etc/hostname", "../outside.json", "sub/../../outside.json"])
def test_listed_path_outside_root_is_refused(tmp_path: Path, path: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    _declare(root, {"maps": [{"path": path}]})

    [_, refused] = read_declared_ownership(root)

    assert refused.document is None
    assert refused.error is not None and "outside the target root" in refused.error


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_listed_symlink_escaping_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    (root / "link.json").symlink_to(tmp_path / "outside.json")
    _declare(root, {"maps": [{"path": "link.json"}]})

    [_, refused] = read_declared_ownership(root)

    assert refused.error is not None and "outside the target root" in refused.error


@pytest.mark.parametrize(
    ("content", "expected"),
    [("{not json", "not valid JSON"), ('{"maps": "ecosystem.json"}', "could not be parsed")],
)
def test_malformed_declaration_is_an_error_observation(
    tmp_path: Path, content: str, expected: str
) -> None:
    (tmp_path / ".si").mkdir()
    (tmp_path / ".si" / "ownership.json").write_text(content, encoding="utf-8")

    [observation] = read_declared_ownership(tmp_path)

    assert observation.kind == "declaration"
    assert observation.error is not None and expected in observation.error


def test_missing_listed_map_is_an_error_observation(tmp_path: Path) -> None:
    _declare(tmp_path, {"maps": [{"path": "ecosystem.json"}]})

    [_, missing] = read_declared_ownership(tmp_path)

    assert missing.label == "ecosystem.json"
    assert missing.error is not None and "could not be read" in missing.error


def test_operator_map_is_read_after_the_declaration(tmp_path: Path) -> None:
    operator_map = tmp_path / "map.json"
    operator_map.write_text('{"components": []}', encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    _declare(root, {})

    observations = collect_ownership(root, [operator_map])

    assert [o.kind for o in observations] == ["declaration", "file"]
    assert observations[1].label == str(operator_map)
    assert observations[1].document == read_ownership_map(operator_map).document


def test_discover_local_repository_collects_ownership(tmp_path: Path) -> None:
    operator_map = tmp_path / "map.json"
    operator_map.write_text('{"components": []}', encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()

    result = discover_local_repository(str(root), ownership_maps=[operator_map])

    assert [o.document for o in result.ownership] == [{"components": []}]
    assert discover_local_repository(str(root)).ownership == []
