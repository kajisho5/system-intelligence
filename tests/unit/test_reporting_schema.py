import json
from pathlib import Path

from system_intelligence.core.snapshot import Snapshot
from system_intelligence.reporting.schema import _SCHEMAS, export_json_schemas

_SNAPSHOT_SCALAR_FIELDS = {"id", "target", "tool_version", "created_at"}


def test_schema_keys_exactly_match_snapshots_list_valued_fields() -> None:
    """Guards against a future `Snapshot` list field with no matching schema
    entry -- see `reporting/schema.py`'s module docstring."""
    snapshot_list_fields = set(Snapshot.model_fields) - _SNAPSHOT_SCALAR_FIELDS
    schema_keys = set(_SCHEMAS) - {"manifest", "dashboard_data"}

    assert schema_keys == snapshot_list_fields


def test_export_json_schemas_writes_one_file_per_entry(tmp_path: Path) -> None:
    written = export_json_schemas(tmp_path)

    assert len(written) == len(_SCHEMAS)
    for name in _SCHEMAS:
        path = tmp_path / f"{name}.schema.json"
        assert path in written
        assert path.exists()


def test_components_schema_is_a_union_covering_every_subtype(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)
    schema = json.loads((tmp_path / "components.schema.json").read_text(encoding="utf-8"))

    defs = json.dumps(schema)
    for subtype in ("Repository", "Skill", "Agent", "MCPServer", "Tool", "Workflow", "Document"):
        assert subtype in defs


def test_manifest_schema_has_expected_required_fields(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)
    schema = json.loads((tmp_path / "manifest.schema.json").read_text(encoding="utf-8"))

    assert set(schema["required"]) == {
        "scan_id",
        "target_fingerprint",
        "tool_version",
        "created_at",
    }


def test_export_is_deterministic_across_calls(tmp_path: Path) -> None:
    first = export_json_schemas(tmp_path / "a")
    second = export_json_schemas(tmp_path / "b")

    for path_a, path_b in zip(sorted(first), sorted(second), strict=True):
        assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")


def test_dashboard_data_schema_exists_and_is_an_object(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)
    schema = json.loads((tmp_path / "dashboard_data.schema.json").read_text(encoding="utf-8"))

    assert schema["type"] == "object"
    assert "overview" in schema["properties"]
