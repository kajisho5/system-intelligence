"""Contract shape: every component's saved Capability Contract against one schema (ADR-017).

The ecosystem-wide form of ADR-011's contract check, for a CI job that
must fail when a contract breaks the schema. Inputs, all read only:

- the components of an ownership map (`ecosystem.json`);
- a directory of saved contracts (`<tool> contract --json` documents, or
  the copies an orchestrator pins), every `*.json` file at any depth;
- the schema, which the caller reads from wherever the reference copy
  lives (the CLI: `--contract-schema`, else the bundled copy);
- optionally a baseline of violations already known, each with a reason.

Each file is attributed to one component: by its file name (`<repo>.json`),
else by the identities the document gives itself (`skill_id`, `id`,
`skill.id`, `skill.package`, as `contracts.contract_identities` reads
them) equal to a component's name, or to it once one of the caller's
name suffixes (the OS: `-skill`) is added. An identity is compared
exactly after case folding, never by similarity (ADR-002); one that names
no component, or several, leaves the file unattributed -- it is still
checked, and listed as such.

A contract that breaks the schema, or a file that cannot be read as
JSON, fails the check, except a violation the baseline lists for that
component at that JSON Pointer or one above it. A baseline entry that
matched nothing is reported as stale, so the list is seen to shrink. A component with no
contract is listed, not failed: what has no saved contract cannot be
checked, and the report says so. The report carries no ids or
timestamps, rows sorted by repository, so the same inputs give the same
JSON.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from system_intelligence.analysis.contracts import contract_identities
from system_intelligence.analysis.json_schema import validate
from system_intelligence.discovery.contracts import ContractObservation
from system_intelligence.discovery.roadmaps import EcosystemRepository

REPORT_FORMAT = "system-intelligence/contract-shape@1"

ComponentResult = Literal["ok", "breaks", "known", "unreadable", "no_contract", "not_created"]
ContractResult = Literal["ok", "breaks", "known", "unreadable"]


class BaselineEntry(BaseModel):
    """Known violations: the component, a JSON Pointer, and why they are accepted for now.

    The pointer covers itself and everything below it: `/dependencies`
    accepts a violation at `/dependencies/3`; `""` accepts the whole
    contract.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str = Field(min_length=1)
    pointer: str
    reason: str = Field(min_length=1)


class Baseline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    comment: str | None = Field(default=None, alias="$comment")
    known_violations: list[BaselineEntry] = Field(default_factory=list)


class BaselineError(ValueError):
    """The baseline document does not have the baseline shape."""


def parse_baseline(document: Any) -> Baseline:
    """A baseline from its parsed JSON; `BaselineError` names what is wrong."""
    try:
        return Baseline.model_validate(document)
    except ValidationError as exc:
        problems = "; ".join(
            f"/{'/'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise BaselineError(problems) from exc


class ShapeViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    pointer: str = Field(description="JSON Pointer into the contract; '' is the document.")
    message: str
    known: str | None = Field(default=None, description="The baseline's reason, when it lists it.")


class ContractCheck(BaseModel):
    """One saved contract file, the component it belongs to and what the schema says."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="The file, relative to the contracts directory.")
    repo: str | None
    attributed_by: Literal["file name", "identity"] | None
    identities: list[str] = Field(default_factory=list)
    result: ContractResult
    violations: list[ShapeViolation] = Field(default_factory=list)
    error: str | None = None
    note: str | None = None


class ComponentShape(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: str
    status: str | None
    result: ComponentResult
    contracts: list[str] = Field(default_factory=list)


class ContractShapeReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: str = REPORT_FORMAT
    schema_source: str
    schema_sha256: str
    bundled_copy: Literal["this schema", "same", "differs"] | None = Field(
        default=None,
        description="Whether the copy bundled with System Intelligence matches the schema used.",
    )
    passed: bool
    summary: dict[str, int]
    components: list[ComponentShape]
    contracts: list[ContractCheck]
    stale_baseline: list[BaselineEntry] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


@dataclass(frozen=True)
class Attribution:
    repo: str | None
    by: Literal["file name", "identity"] | None
    identities: tuple[str, ...]
    note: str | None = None


def _file_stem(label: str) -> str:
    name = label.rsplit("/", 1)[-1]
    return name[: -len(".json")] if name.endswith(".json") else name


def attribute_contract(
    observation: ContractObservation,
    names: Mapping[str, str],
    suffixes: Sequence[str] = (),
) -> Attribution:
    """The component one saved contract belongs to.

    `names` maps a case-folded component name to the name as the map
    writes it. The file name wins (`<repo>.json`); then the document's
    identities, each matched exactly or, when it matches no component
    exactly, with one of `suffixes` appended.
    """
    stem = _file_stem(observation.label).casefold()
    identities = tuple(contract_identities(observation.document))
    if stem in names:
        return Attribution(names[stem], "file name", identities)
    if observation.error is not None:
        return Attribution(None, None, identities, "not read, so only its file name could say")
    if not identities:
        return Attribution(None, None, identities, "the contract gives no identity")
    matched: list[str] = []
    for identity in identities:
        folded = identity.casefold()
        forms = [folded] if folded in names else [folded + suffix.casefold() for suffix in suffixes]
        for form in forms:
            if form in names and names[form] not in matched:
                matched.append(names[form])
    if len(matched) == 1:
        return Attribution(matched[0], "identity", identities)
    shown = ", ".join(identities)
    if not matched:
        return Attribution(None, None, identities, f"its identities ({shown}) name no component")
    return Attribution(
        None, None, identities, f"its identities ({shown}) name several: {', '.join(matched)}"
    )


def attribute_contracts(
    observations: Sequence[ContractObservation],
    repositories: Sequence[EcosystemRepository],
    suffixes: Sequence[str] = (),
) -> list[tuple[ContractObservation, Attribution]]:
    """`attribute_contract` for every observation, in their order."""
    names = {entry.name.casefold(): entry.name for entry in repositories}
    return [
        (observation, attribute_contract(observation, names, suffixes))
        for observation in observations
    ]


def schema_digest(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def _check(
    observation: ContractObservation,
    attribution: Attribution,
    result: ContractResult,
    *,
    violations: Sequence[ShapeViolation] = (),
    error: str | None = None,
) -> ContractCheck:
    return ContractCheck(
        source=observation.label,
        repo=attribution.repo,
        attributed_by=attribution.by,
        identities=list(attribution.identities),
        result=result,
        violations=list(violations),
        error=error,
        note=attribution.note,
    )


def _known_key(
    known: Mapping[tuple[str, str], BaselineEntry], repo: str | None, pointer: str
) -> tuple[str, str] | None:
    """The baseline entry for a violation: that repository, that pointer or one above it."""
    if repo is None:
        return None
    folded = repo.casefold()
    candidate = pointer
    while True:
        if (folded, candidate) in known:
            return (folded, candidate)
        if not candidate:
            return None
        candidate = candidate.rsplit("/", 1)[0]


def check_contract_shape(
    repositories: Sequence[EcosystemRepository],
    observations: Sequence[ContractObservation],
    schema: Mapping[str, Any],
    *,
    schema_source: str,
    schema_sha256: str,
    bundled_copy: Literal["this schema", "same", "differs"] | None = None,
    suffixes: Sequence[str] = (),
    baseline: Baseline | None = None,
    inactive_statuses: Collection[str] = (),
    problems: Sequence[str] = (),
) -> ContractShapeReport:
    """Validate every saved contract and give each component its result.

    `schema` must already have passed `json_schema.check_supported`.
    """
    known: dict[tuple[str, str], BaselineEntry] = {
        (entry.repo.casefold(), entry.pointer): entry
        for entry in (baseline.known_violations if baseline is not None else [])
    }
    used: set[tuple[str, str]] = set()
    checks: list[ContractCheck] = []
    for observation, attribution in attribute_contracts(observations, repositories, suffixes):
        if observation.error is not None:
            checks.append(_check(observation, attribution, "unreadable", error=observation.error))
            continue
        violations: list[ShapeViolation] = []
        for violation in validate(observation.document, schema):
            key = _known_key(known, attribution.repo, violation.pointer)
            accepted = known[key] if key is not None else None
            if key is not None:
                used.add(key)
            violations.append(
                ShapeViolation(
                    pointer=violation.pointer,
                    message=violation.message,
                    known=accepted.reason if accepted is not None else None,
                )
            )
        result: ContractResult = "ok"
        if any(item.known is None for item in violations):
            result = "breaks"
        elif violations:
            result = "known"
        checks.append(_check(observation, attribution, result, violations=violations))
    checks.sort(key=lambda check: ((check.repo or "\uffff").casefold(), check.source))

    inactive = {status.casefold() for status in inactive_statuses}
    order: dict[ContractResult, int] = {"unreadable": 0, "breaks": 1, "known": 2, "ok": 3}
    components: list[ComponentShape] = []
    for component in sorted(repositories, key=lambda e: e.name.casefold()):
        own = [check for check in checks if check.repo == component.name]
        component_result: ComponentResult
        if own:
            worst: ContractResult = min((item.result for item in own), key=order.__getitem__)
            component_result = worst
        elif component.status is not None and component.status.casefold() in inactive:
            component_result = "not_created"
        else:
            component_result = "no_contract"
        components.append(
            ComponentShape(
                repo=component.name,
                status=component.status,
                result=component_result,
                contracts=[check.source for check in own],
            )
        )

    summary = {
        value: sum(1 for row in components if row.result == value)
        for value in ("ok", "breaks", "known", "unreadable", "no_contract", "not_created")
    }
    summary["unattributed"] = sum(1 for check in checks if check.repo is None)
    stale = [entry for key, entry in known.items() if key not in used]
    stale.sort(key=lambda entry: (entry.repo.casefold(), entry.pointer))
    return ContractShapeReport(
        schema_source=schema_source,
        schema_sha256=schema_sha256,
        bundled_copy=bundled_copy,
        passed=not any(check.result in ("breaks", "unreadable") for check in checks),
        summary=summary,
        components=components,
        contracts=checks,
        stale_baseline=stale,
        problems=list(problems),
    )


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def format_shape_table(report: ContractShapeReport) -> str:
    """A Markdown table (one row per component), then each problem with its JSON Pointer."""
    checked = sum(1 for row in report.components if row.contracts)
    verdict = "passed" if report.passed else "FAILED"
    lines = [
        f"Contract shape {verdict}: {checked} of {len(report.components)} components have a "
        f"saved contract, checked against {report.schema_source}",
        "",
        "| Component | Result | Contracts |",
        "|---|---|---|",
    ]
    for row in report.components:
        contracts = ", ".join(row.contracts) or "-"
        lines.append(f"| {_cell(row.repo)} | {row.result} | {_cell(contracts)} |")
    details: list[str] = []
    for check in report.contracts:
        owner = check.repo or "unattributed"
        if check.error is not None:
            details.append(f"- {owner} {check.source}: unreadable: {check.error}")
        for violation in check.violations:
            where = violation.pointer or "/"
            known = f" (known: {violation.known})" if violation.known else ""
            details.append(f"- {owner} {check.source} {where}: {violation.message}{known}")
    if details:
        lines += ["", "Problems:", *details]
    notes = [
        f"- {check.source}: unattributed ({check.note})" for check in report.contracts if check.note
    ]
    notes += [
        f"- baseline entry {entry.repo} {entry.pointer or '/'} matched nothing (stale)"
        for entry in report.stale_baseline
    ]
    if report.bundled_copy == "differs":
        notes.append("- the schema bundled with System Intelligence differs from this one")
    notes += [f"- ecosystem file: {problem}" for problem in report.problems]
    if notes:
        lines += ["", "Notes:", *notes]
    return "\n".join(lines) + "\n"
