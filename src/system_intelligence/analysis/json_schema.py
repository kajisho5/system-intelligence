"""A small, dependency-free JSON Schema validator for a fixed keyword subset.

Exists so `analysis/contracts.py` can validate a Capability Contract
document against a real JSON Schema file (draft 2020-12) without adding a
`jsonschema` dependency -- this project's runtime dependencies are only
pydantic, typer and defusedxml, and the schemas it reads use a handful of
keywords. The same reasoning `analysis/gaps.py` gives for JSON over YAML.

Never silently permissive: `check_supported` walks the whole schema up
front and raises `UnsupportedSchemaError` for any keyword outside the
subset below, so a schema that relies on (say) `pattern` or
`if`/`then` is refused loudly instead of half-validated. Pure annotations
(`title`, `description`, `$comment`, ...) are ignored, as the spec says.

Supported assertion/applicator keywords: `type`, `enum`, `const`,
`properties`, `required`, `additionalProperties` (boolean or schema),
`items` (single schema), `anyOf`, `oneOf`, `allOf`, `minLength`,
`minItems`, and `$ref` to a local JSON Pointer (`#/...`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_ANNOTATION_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$comment",
        "$defs",
        "definitions",
        "title",
        "description",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
    }
)
_ASSERTION_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "oneOf",
        "allOf",
        "minLength",
        "minItems",
        "$ref",
    }
)


class UnsupportedSchemaError(ValueError):
    """The schema uses a keyword (or a `$ref` form) this validator does not implement."""


@dataclass(frozen=True)
class SchemaViolation:
    """One place where an instance does not match the schema.

    `pointer` is a JSON Pointer (RFC 6901) into the *instance*, `""` for
    the document root.
    """

    pointer: str
    message: str


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    actual = _json_type_name(value)
    if expected == "number":
        return actual in ("integer", "number")
    if expected == "integer":
        return actual == "integer" or (isinstance(value, float) and value.is_integer())
    return actual == expected


def _resolve_ref(root: Mapping[str, Any], ref: str) -> Mapping[str, Any]:
    if ref == "#":
        return root
    if not ref.startswith("#/"):
        raise UnsupportedSchemaError(f"only local '#/...' $ref values are supported, got {ref!r}")
    node: Any = root
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or token not in node:
            raise UnsupportedSchemaError(f"$ref {ref!r} does not resolve inside the schema")
        node = node[token]
    if not isinstance(node, Mapping):
        raise UnsupportedSchemaError(f"$ref {ref!r} does not point at a schema object")
    return node


def check_supported(schema: Mapping[str, Any]) -> None:
    """Raise `UnsupportedSchemaError` if `schema` uses anything outside the subset.

    Walks every subschema, including those under `$defs`, so an unsupported
    keyword is caught even in a branch a given instance never reaches.
    """

    def walk(node: Any, where: str) -> None:
        if isinstance(node, bool):
            return
        if not isinstance(node, Mapping):
            raise UnsupportedSchemaError(f"{where or '/'}: a schema must be an object or boolean")
        for key, value in node.items():
            if key in _ANNOTATION_KEYWORDS:
                if key in ("$defs", "definitions") and isinstance(value, Mapping):
                    for name, sub in value.items():
                        walk(sub, f"{where}/{key}/{name}")
                continue
            if key not in _ASSERTION_KEYWORDS:
                raise UnsupportedSchemaError(f"{where or '/'}: unsupported keyword {key!r}")
            if key == "$ref":
                if not isinstance(value, str):
                    raise UnsupportedSchemaError(f"{where}/$ref: must be a string")
                _resolve_ref(schema, value)
            elif key == "properties":
                if not isinstance(value, Mapping):
                    raise UnsupportedSchemaError(f"{where}/properties: must be an object")
                for name, sub in value.items():
                    walk(sub, f"{where}/properties/{name}")
            elif key in ("items", "additionalProperties"):
                walk(value, f"{where}/{key}")
            elif key in ("anyOf", "oneOf", "allOf"):
                if not isinstance(value, list) or not value:
                    raise UnsupportedSchemaError(f"{where}/{key}: must be a non-empty array")
                for index, sub in enumerate(value):
                    walk(sub, f"{where}/{key}/{index}")

    walk(schema, "")


def validate(instance: Any, schema: Mapping[str, Any]) -> list[SchemaViolation]:
    """Every violation of `schema` by `instance` (empty list = valid).

    Call `check_supported(schema)` first; this function assumes the schema
    only uses supported keywords.
    """
    return _validate(instance, schema, schema, "")


def _validate(
    instance: Any, node: Any, root: Mapping[str, Any], pointer: str
) -> list[SchemaViolation]:
    if node is True:
        return []
    if node is False:
        return [SchemaViolation(pointer, "no value is allowed here")]

    violations: list[SchemaViolation] = []

    if "$ref" in node:
        violations.extend(_validate(instance, _resolve_ref(root, node["$ref"]), root, pointer))

    expected_type = node.get("type")
    if expected_type is not None:
        expected = [expected_type] if isinstance(expected_type, str) else list(expected_type)
        if not any(_matches_type(instance, t) for t in expected):
            violations.append(
                SchemaViolation(
                    pointer,
                    f"expected {' or '.join(expected)}, got {_json_type_name(instance)}",
                )
            )
            # Every remaining keyword assumes the right type; reporting them
            # too would only restate this one problem several ways.
            return violations

    if "enum" in node and instance not in node["enum"]:
        violations.append(
            SchemaViolation(pointer, f"{instance!r} is not one of {list(node['enum'])!r}")
        )
    if "const" in node and instance != node["const"]:
        violations.append(SchemaViolation(pointer, f"must equal {node['const']!r}"))

    if isinstance(instance, str) and "minLength" in node and len(instance) < node["minLength"]:
        violations.append(
            SchemaViolation(pointer, f"string shorter than minLength {node['minLength']}")
        )

    if isinstance(instance, list):
        if "minItems" in node and len(instance) < node["minItems"]:
            violations.append(
                SchemaViolation(pointer, f"array shorter than minItems {node['minItems']}")
            )
        if "items" in node:
            for index, item in enumerate(instance):
                violations.extend(_validate(item, node["items"], root, f"{pointer}/{index}"))

    if isinstance(instance, Mapping):
        for name in node.get("required", []):
            if name not in instance:
                violations.append(SchemaViolation(pointer, f"missing required property {name!r}"))
        properties: Mapping[str, Any] = node.get("properties", {})
        for name, value in instance.items():
            child = f"{pointer}/{_escape_pointer_token(str(name))}"
            if name in properties:
                violations.extend(_validate(value, properties[name], root, child))
            elif "additionalProperties" in node:
                violations.extend(_validate(value, node["additionalProperties"], root, child))

    for sub in node.get("allOf", []):
        violations.extend(_validate(instance, sub, root, pointer))

    if "anyOf" in node:
        branch_results = [_validate(instance, sub, root, pointer) for sub in node["anyOf"]]
        if all(branch_results):
            reasons = "; ".join(", ".join(v.message for v in branch) for branch in branch_results)
            violations.append(
                SchemaViolation(pointer, f"matches none of the anyOf alternatives ({reasons})")
            )

    if "oneOf" in node:
        matching = sum(1 for sub in node["oneOf"] if not _validate(instance, sub, root, pointer))
        if matching != 1:
            violations.append(
                SchemaViolation(
                    pointer, f"must match exactly one oneOf alternative, matched {matching}"
                )
            )

    return violations
