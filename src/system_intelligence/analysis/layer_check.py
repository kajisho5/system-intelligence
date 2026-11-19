"""Dependency direction: every declared call goes down the ecosystem's layers (ADR-018).

The layering is the ecosystem's, never inferred here. Inputs, all read only:

- the components of an ownership map (`ecosystem.json`), each with a
  `layer` (a string; a component without one is reported, not guessed);
- a directory of saved contracts (the same kind `si contract-check`
  reads), whose `dependencies[]` are the calls each component declares;
- the layering file: the layer names from the lowest to the highest, and
  the exceptions, each a caller and a callee with the reason it is allowed.

A call is a `dependencies[]` entry that names another component, by
`skill_id` or `id`, whose `kind` is absent, `skill` or `app`, matched
exactly after case folding or with one of the caller's suffixes added
(ADR-017's rule, never by similarity, ADR-002). Entries of any other
kind (packages, binaries, model weights, a `schema` the component reads)
are not calls between components and are skipped. An entry that says it is a skill but names no
component is listed as unresolved, not failed.

A call to a lower layer is fine. A call within the same layer, or to a
higher one, fails the check unless the layering lists that caller and
callee as an exception. A component whose layer is missing or is not one
of the layering's names fails the check too: the model is incomplete. So
does a contract file that cannot be read, since its calls are unknown. An
exception that excused nothing is reported as stale, so the list is seen
to shrink. Data contracts (shared specs, sidecar files) are not declared
as dependencies and are not calls; this check does not see them.

The report has no ids or timestamps; rows are sorted, so the same inputs
give the same JSON.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from system_intelligence.analysis.contract_shape import attribute_contracts
from system_intelligence.discovery.contracts import ContractObservation
from system_intelligence.discovery.roadmaps import EcosystemRepository

REPORT_FORMAT = "system-intelligence/layer-check@1"

Direction = Literal["down", "same", "up", "unknown"]
CallResult = Literal["ok", "excepted", "violation", "unclassified"]

CALL_RESULTS: tuple[CallResult, ...] = ("ok", "excepted", "violation", "unclassified")
SKILL_KINDS = frozenset({"skill", "app"})


class LayerException(BaseModel):
    """One call allowed against the layering: caller, callee and why."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    caller: str = Field(min_length=1, alias="from")
    callee: str = Field(min_length=1, alias="to")
    reason: str = Field(min_length=1)


class Layering(BaseModel):
    """The layer names, lowest first, and the exceptions."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    comment: str | None = Field(default=None, alias="$comment")
    layers: list[str] = Field(min_length=1)
    exceptions: list[LayerException] = Field(default_factory=list)

    @model_validator(mode="after")
    def _distinct(self) -> Layering:
        folded = [name.casefold() for name in self.layers]
        if any(not name.strip() for name in self.layers):
            raise ValueError("a layer name is empty")
        if len(set(folded)) != len(folded):
            raise ValueError("a layer is named twice")
        pairs = [(item.caller.casefold(), item.callee.casefold()) for item in self.exceptions]
        if len(set(pairs)) != len(pairs):
            raise ValueError("an exception is listed twice")
        return self


class LayeringError(ValueError):
    """The layering document does not have the layering shape."""


def parse_layering(document: Any) -> Layering:
    """A layering from its parsed JSON; `LayeringError` names what is wrong."""
    try:
        return Layering.model_validate(document)
    except ValidationError as exc:
        problems = "; ".join(
            f"/{'/'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise LayeringError(problems) from exc


def component_layers(document: Any) -> dict[str, str | None]:
    """Each component's `layer` (None when absent or not a string), keyed by its stripped name."""
    layers: dict[str, str | None] = {}
    components = document.get("components") if isinstance(document, Mapping) else None
    if not isinstance(components, list):
        return layers
    for component in components:
        if not isinstance(component, Mapping):
            continue
        name = component.get("repo", component.get("name"))
        if not isinstance(name, str) or not name.strip() or name.strip() in layers:
            continue
        name = name.strip()
        layer = component.get("layer")
        layers[name] = layer if isinstance(layer, str) and layer.strip() else None
    return layers


class ComponentLayer(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: str
    layer: str | None
    problem: str | None = None


class LayerCall(BaseModel):
    """One declared call: where it is declared, both ends with their layers, and the verdict."""

    model_config = ConfigDict(frozen=True)

    caller: str
    callee: str
    caller_layer: str | None
    callee_layer: str | None
    direction: Direction
    result: CallResult
    source: str = Field(description="The contract file, relative to the contracts directory.")
    pointer: str = Field(description="JSON Pointer of the dependency entry in that file.")
    reason: str | None = Field(default=None, description="The exception's reason, when excepted.")


class UnresolvedDependency(BaseModel):
    model_config = ConfigDict(frozen=True)

    caller: str | None
    name: str
    source: str
    pointer: str


class LayerCheckReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: str = REPORT_FORMAT
    layers: list[str]
    passed: bool
    report_only: bool = False
    summary: dict[str, int]
    components: list[ComponentLayer]
    calls: list[LayerCall]
    unresolved: list[UnresolvedDependency] = Field(default_factory=list)
    unattributed: list[str] = Field(default_factory=list)
    unreadable: list[str] = Field(
        default_factory=list, description="Contract files that could not be read: a failure."
    )
    stale_exceptions: list[LayerException] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2, by_alias=True) + "\n"


def dependency_name(entry: Any) -> tuple[str | None, bool]:
    """The component name a `dependencies[]` entry gives, and whether it says it is a skill.

    An entry with a `kind` other than `skill` or `app` (python-package,
    binary, model-weights, schema, ...) is not a call to a component, even
    when it carries a `skill_id`; a `schema` entry is a data contract.
    Otherwise `skill_id` names a skill, and `id` names one when `kind` says
    so, or names a component only if one has that name (`kind` absent).
    """
    if not isinstance(entry, Mapping):
        return None, False
    kind = entry.get("kind")
    if kind is not None and not (isinstance(kind, str) and kind.casefold() in SKILL_KINDS):
        return None, False
    for field in ("skill_id", "id"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value, field == "skill_id" or kind is not None
    return None, False


def _resolve(name: str, names: Mapping[str, str], suffixes: Sequence[str]) -> str | None:
    folded = name.casefold()
    if folded in names:
        return names[folded]
    matched = {names[folded + s.casefold()] for s in suffixes if folded + s.casefold() in names}
    return matched.pop() if len(matched) == 1 else None


def check_layers(
    repositories: Sequence[EcosystemRepository],
    layers_by_repo: Mapping[str, str | None],
    observations: Sequence[ContractObservation],
    layering: Layering,
    *,
    suffixes: Sequence[str] = (),
    report_only: bool = False,
    problems: Sequence[str] = (),
) -> LayerCheckReport:
    """Every declared call between components, against the layering."""
    rank = {name.casefold(): index for index, name in enumerate(layering.layers)}
    names = {entry.name.casefold(): entry.name for entry in repositories}

    components: list[ComponentLayer] = []
    layer_of: dict[str, str | None] = {}
    for entry in sorted(repositories, key=lambda e: e.name.casefold()):
        layer = layers_by_repo.get(entry.name)
        problem = None
        if layer is None:
            problem = "no layer"
        elif layer.casefold() not in rank:
            problem = f"layer {layer!r} is not one of {', '.join(layering.layers)}"
        layer_of[entry.name] = layer if problem is None else None
        components.append(ComponentLayer(repo=entry.name, layer=layer, problem=problem))

    exceptions = {
        (item.caller.casefold(), item.callee.casefold()): item for item in layering.exceptions
    }
    used: set[tuple[str, str]] = set()
    calls: list[LayerCall] = []
    unresolved: list[UnresolvedDependency] = []
    unattributed: list[str] = []
    unreadable: list[str] = []
    for observation, attribution in attribute_contracts(observations, repositories, suffixes):
        if observation.error is not None:
            unreadable.append(observation.label)
            continue
        if not isinstance(observation.document, Mapping):
            continue
        caller = attribution.repo
        if caller is None:
            unattributed.append(observation.label)
        dependencies = observation.document.get("dependencies")
        if not isinstance(dependencies, list):
            continue
        for index, entry in enumerate(dependencies):
            name, says_skill = dependency_name(entry)
            if name is None:
                continue
            pointer = f"/dependencies/{index}"
            callee = _resolve(name, names, suffixes)
            if callee is None:
                if says_skill:
                    unresolved.append(
                        UnresolvedDependency(
                            caller=caller, name=name, source=observation.label, pointer=pointer
                        )
                    )
                continue
            if caller is None:
                continue
            if callee == caller:
                continue
            caller_layer, callee_layer = layer_of[caller], layer_of[callee]
            direction: Direction = "unknown"
            if caller_layer is not None and callee_layer is not None:
                low, high = rank[callee_layer.casefold()], rank[caller_layer.casefold()]
                direction = "down" if low < high else "same" if low == high else "up"
            key = (caller.casefold(), callee.casefold())
            reason = None
            result: CallResult
            if direction == "down":
                result = "ok"
            elif direction == "unknown":
                result = "unclassified"
            elif key in exceptions:
                result, reason = "excepted", exceptions[key].reason
                used.add(key)
            else:
                result = "violation"
            calls.append(
                LayerCall(
                    caller=caller,
                    callee=callee,
                    caller_layer=layers_by_repo.get(caller),
                    callee_layer=layers_by_repo.get(callee),
                    direction=direction,
                    result=result,
                    source=observation.label,
                    pointer=pointer,
                    reason=reason,
                )
            )
    calls.sort(key=lambda c: (c.caller.casefold(), c.callee.casefold(), c.source, c.pointer))
    unresolved.sort(key=lambda u: (u.source, u.pointer))
    stale = [item for key, item in exceptions.items() if key not in used]
    stale.sort(key=lambda item: (item.caller.casefold(), item.callee.casefold()))

    summary: dict[str, int] = {
        value: sum(1 for c in calls if c.result == value) for value in CALL_RESULTS
    }
    summary["unlayered_components"] = sum(1 for row in components if row.problem is not None)
    summary["unreadable_contracts"] = len(unreadable)
    failed = any(
        summary[key]
        for key in ("violation", "unclassified", "unlayered_components", "unreadable_contracts")
    )
    return LayerCheckReport(
        layers=list(layering.layers),
        passed=not failed,
        report_only=report_only,
        summary=summary,
        components=components,
        calls=calls,
        unresolved=unresolved,
        unattributed=sorted(unattributed),
        unreadable=sorted(unreadable),
        stale_exceptions=stale,
        problems=list(problems),
    )


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def format_layer_table(report: LayerCheckReport) -> str:
    """The verdict, the calls that are not plain downward ones, then every call and component."""
    verdict = "passed" if report.passed else "FAILED"
    if report.report_only:
        verdict += " (report only: does not fail the run)"
    counts = report.summary
    lines = [
        f"Layer check {verdict}: {len(report.calls)} declared calls, {counts['ok']} downward, "
        f"{counts['excepted']} excepted, {counts['violation']} against the layering, "
        f"{counts['unclassified']} unclassified; layers from lowest: " + " < ".join(report.layers),
        "",
        "| Caller (layer) | Callee (layer) | Direction | Result | Declared in |",
        "|---|---|---|---|---|",
    ]
    for call in report.calls:
        where = f"{call.source} {call.pointer}"
        result = call.result + (f": {call.reason}" if call.reason else "")
        lines.append(
            f"| {_cell(call.caller)} ({call.caller_layer or '-'}) | {_cell(call.callee)} "
            f"({call.callee_layer or '-'}) | {call.direction} | {_cell(result)} | {_cell(where)} |"
        )
    lines += ["", "| Component | Layer |", "|---|---|"]
    for row in report.components:
        shown = row.layer or "-"
        if row.problem:
            shown += f" ({row.problem})"
        lines.append(f"| {_cell(row.repo)} | {_cell(shown)} |")
    notes = [
        f"- {item.source} {item.pointer}: names {item.name!r}, which is no component (unresolved)"
        for item in report.unresolved
    ]
    notes += [
        f"- {label}: unattributed, its calls are not checked" for label in report.unattributed
    ]
    notes += [f"- {label}: unreadable, so its calls are unknown" for label in report.unreadable]
    notes += [
        f"- exception {item.caller} -> {item.callee} excused nothing (stale)"
        for item in report.stale_exceptions
    ]
    notes += [f"- ecosystem file: {problem}" for problem in report.problems]
    if notes:
        lines += ["", "Notes:", *notes]
    return "\n".join(lines) + "\n"
