from typing import Any

import pytest

from system_intelligence.analysis.json_schema import (
    SchemaViolation,
    UnsupportedSchemaError,
    check_supported,
    validate,
)
from system_intelligence.integrations.ai_video_os import load_capability_contract_schema


def _messages(instance: Any, schema: dict[str, Any]) -> list[tuple[str, str]]:
    check_supported(schema)
    return [(v.pointer, v.message) for v in validate(instance, schema)]


def test_type_mismatch_reports_pointer_and_stops_there() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "object", "required": ["x"]}}}

    assert _messages({"a": "text"}, schema) == [("/a", "expected object, got string")]


def test_boolean_is_not_an_integer_and_integral_float_is() -> None:
    assert _messages(True, {"type": "integer"}) == [("", "expected integer, got boolean")]
    assert _messages(2.0, {"type": "integer"}) == []
    assert _messages(2, {"type": "number"}) == []


def test_type_list_accepts_any_listed_type() -> None:
    assert _messages(None, {"type": ["string", "null"]}) == []


def test_required_enum_const_min_length_min_items() -> None:
    schema = {
        "type": "object",
        "required": ["id", "lifecycle"],
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "lifecycle": {"enum": ["STABLE"]},
            "kind": {"const": "skill"},
            "tags": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        },
    }

    assert _messages({"id": "", "kind": "tool", "tags": []}, schema) == [
        ("", "missing required property 'lifecycle'"),
        ("/id", "string shorter than minLength 1"),
        ("/kind", "must equal 'skill'"),
        ("/tags", "array shorter than minItems 1"),
    ]
    assert _messages({"id": "a", "lifecycle": "BETA"}, schema) == [
        ("/lifecycle", "'BETA' is not one of ['STABLE']")
    ]


def test_items_are_checked_with_their_index() -> None:
    assert _messages([1, "x", 3], {"type": "array", "items": {"type": "integer"}}) == [
        ("/1", "expected integer, got string")
    ]


def test_additional_properties_false_and_schema() -> None:
    closed = {"type": "object", "properties": {"a": {}}, "additionalProperties": False}
    typed = {"type": "object", "additionalProperties": {"type": "integer"}}

    assert _messages({"a": 1, "b": 2}, closed) == [("/b", "no value is allowed here")]
    assert _messages({"n": "x"}, typed) == [("/n", "expected integer, got string")]


def test_pointer_tokens_are_escaped() -> None:
    schema = {"type": "object", "additionalProperties": {"type": "string"}}

    assert _messages({"a/b~c": 1}, schema) == [("/a~1b~0c", "expected string, got integer")]


def test_any_of_explains_every_failed_alternative() -> None:
    schema = {"anyOf": [{"required": ["a"]}, {"required": ["b"]}]}

    assert _messages({"b": 1}, schema) == []
    assert _messages({}, schema) == [
        (
            "",
            "matches none of the anyOf alternatives "
            "(missing required property 'a'; missing required property 'b')",
        )
    ]


def test_one_of_requires_exactly_one_match() -> None:
    schema = {"oneOf": [{"type": "string"}, {"type": "number"}, {"type": "integer"}]}

    assert _messages("v", schema) == []
    assert _messages(1, schema) == [("", "must match exactly one oneOf alternative, matched 2")]
    assert _messages(None, schema) == [("", "must match exactly one oneOf alternative, matched 0")]


def test_all_of_collects_every_branch() -> None:
    schema = {"allOf": [{"required": ["a"]}, {"required": ["b"]}]}

    assert len(validate({}, schema)) == 2


def test_local_ref_resolves_against_root() -> None:
    schema = {
        "type": "array",
        "items": {"$ref": "#/$defs/Entry"},
        "$defs": {"Entry": {"type": "object", "required": ["id"]}},
    }

    assert _messages([{"id": 1}, {}], schema) == [("/1", "missing required property 'id'")]


def test_unsupported_keyword_is_refused_not_ignored() -> None:
    with pytest.raises(UnsupportedSchemaError, match="pattern"):
        check_supported({"type": "string", "pattern": "^a"})


def test_unsupported_keyword_inside_defs_is_refused() -> None:
    with pytest.raises(UnsupportedSchemaError, match="if"):
        check_supported({"$defs": {"X": {"if": {}}}})


def test_remote_ref_is_refused() -> None:
    with pytest.raises(UnsupportedSchemaError, match="local"):
        check_supported({"$ref": "https://example.com/schema.json"})


def test_dangling_ref_is_refused() -> None:
    with pytest.raises(UnsupportedSchemaError, match="does not resolve"):
        check_supported({"$ref": "#/$defs/Missing"})


def test_bundled_capability_contract_schema_is_fully_supported() -> None:
    schema = load_capability_contract_schema()

    check_supported(schema)
    assert validate({"skill_id": "x", "provides": []}, schema) == []
    assert validate({"skill_id": "x", "provides": [{"id": "a"}]}, schema) == [
        SchemaViolation("/provides/0", "missing required property 'lifecycle'"),
        SchemaViolation("/provides/0", "missing required property 'tool_id'"),
    ]
