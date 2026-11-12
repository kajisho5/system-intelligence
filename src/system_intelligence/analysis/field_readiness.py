"""Field readiness: per skill, what its contract and CI say about work in the field (ADR-016).

For every repository of an ownership map, one row with one cell per
`ReadinessColumn` (the caller's; the CLI passes the AI Video Production
OS's: resume after a stop, progress events, error classes, long-file
tests, hardware encoder use, alpha output, loudness output). Each cell
is `yes`, `no` or `unknown`, with the evidence (file and key, the text
matched). Two sources, both only read:

- **the skill's Capability Contract** (a saved `<tool> contract --json`
  document). A column names the contract keys that state it: a bare key
  name counts only at the top level (`/loudness`, `/alpha`), and a name
  with a `/` is one exact path (`errors/classes`, `proxy/hardware`). A key
  anywhere else is never read, so a colour parameter's `alpha`
  (`/operations/0/parameters/tint/alpha`) is not an alpha output. A stated
  value is `yes` (`true`, a non-empty value) or `no` (`false`, an empty
  value, `"none"`); `null` states nothing.
- **the CI config** (`.github/workflows/*.yml`): job ids, step names and
  `run` commands. A column's pattern found there is `yes` (the CI says it
  runs it); CI never says `no`.

A cell is `yes` when a source says yes and none says no, `no` when a
source says no and none says yes, and `unknown` otherwise: a capability
the contract and CI do not state is `unknown`, never `no`, and so is one
they state both ways (the cell keeps all the evidence and says so).
Nothing is inferred from source code, READMEs or names. The report is
deterministic (no ids, no timestamps, rows sorted by repository,
evidence in source order).
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from system_intelligence.discovery.roadmaps import (
    EcosystemRepository,
    RoadmapSource,
)

REPORT_FORMAT = "system-intelligence/field-readiness@1"
#: The file `si diagnose --field --out DIR` writes into DIR.
FIELD_READINESS_REPORT_FILENAME = "field-readiness.json"
WORKFLOWS_DIRECTORY = ".github/workflows"
_CONTEXT_CHARS = 160
_NO_WORDS = frozenset({"", "no", "none", "false", "n/a", "unsupported", "not supported"})

Value = Literal["yes", "no", "unknown"]


@dataclass(frozen=True)
class ReadinessColumn:
    """One column: the contract keys and the CI pattern that state it."""

    id: str
    label: str
    description: str
    contract_keys: tuple[str, ...] = ()
    ci_pattern: str | None = None


@dataclass(frozen=True)
class ContractDocument:
    """One skill's contract: the parsed document (`read`), or why there is none."""

    status: Literal["read", "missing", "unavailable"]
    label: str
    document: Any = None
    error: str | None = None


class ReadinessEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = Field(description="The contract file or the CI workflow file.")
    key: str = Field(description="JSON Pointer in the contract, or the CI key (job id, name, run).")
    line: int | None = Field(default=None, description="1-based line in a CI file.")
    matched_text: str
    says: Literal["yes", "no"]


class ReadinessCell(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Value
    evidence: list[ReadinessEvidence] = Field(default_factory=list)
    note: str | None = None


class SkillReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: str
    status: str | None
    contract: Literal["read", "missing", "unavailable", "not_created"]
    contract_source: str | None = None
    ci: Literal["read", "missing", "unavailable", "not_created"]
    ci_files: list[str] = Field(default_factory=list)
    cells: dict[str, ReadinessCell]
    notes: list[str] = Field(default_factory=list)


class ColumnInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    description: str
    contract_keys: list[str]
    ci_pattern: str | None


class FieldReadinessReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: str = REPORT_FORMAT
    source: str
    columns: list[ColumnInfo]
    summary: dict[str, dict[str, int]]
    skills: list[SkillReadiness]
    problems: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _CONTEXT_CHARS else text[: _CONTEXT_CHARS - 1] + "…"


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _says(value: Any) -> Literal["yes", "no"] | None:
    """What a stated contract value says: yes, no, or nothing (`null`)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return "yes" if value else "no"
    if isinstance(value, str):
        return "no" if value.strip().casefold() in _NO_WORDS else "yes"
    if isinstance(value, Mapping | list):
        return "yes" if value else "no"
    return None


def _lookup(document: Any, path: Sequence[str]) -> tuple[bool, Any]:
    """(found, value) of an exact key path, compared case-insensitively."""
    current = document
    for segment in path:
        if not isinstance(current, Mapping):
            return False, None
        key = next((k for k in current if str(k).casefold() == segment.casefold()), None)
        if key is None:
            return False, None
        current = current[key]
    return True, current


def _contract_evidence(
    column: ReadinessColumn, contract: ContractDocument
) -> list[ReadinessEvidence]:
    """What the contract states for `column`: its top-level keys, then its exact paths."""
    if contract.status != "read" or not isinstance(contract.document, Mapping):
        return []
    bare = {key.casefold() for key in column.contract_keys if "/" not in key}
    candidates: list[tuple[str, Any]] = [
        (f"/{_escape(str(name))}", value)
        for name, value in contract.document.items()
        if str(name).casefold() in bare
    ]
    for path in (key for key in column.contract_keys if "/" in key):
        found, value = _lookup(contract.document, path.split("/"))
        if found:
            candidates.append(("/" + "/".join(_escape(part) for part in path.split("/")), value))
    evidence: list[ReadinessEvidence] = []
    for pointer, value in candidates:
        says = _says(value)
        if says is None:
            continue
        evidence.append(
            ReadinessEvidence(
                source=contract.label,
                key=pointer,
                matched_text=_clip(json.dumps(value, ensure_ascii=False, sort_keys=True)),
                says=says,
            )
        )
    return evidence


@dataclass(frozen=True)
class CILine:
    """One line of a CI workflow that can state what the CI runs."""

    source: str
    line: int
    key: str
    text: str


_JOBS_RE = re.compile(r"^jobs:\s*(#.*)?$")
_JOB_ID_RE = re.compile(r"^(?P<indent>\s+)(?P<id>[A-Za-z0-9_.-]+):\s*(#.*)?$")
_NAME_RE = re.compile(r"^\s*(?:-\s+)?name:\s*(?P<value>.+?)\s*$")
_RUN_RE = re.compile(r"^(?P<indent>\s*)(?:-\s+)?run:\s*(?P<value>.*?)\s*$")


def ci_lines(source: str, text: str) -> list[CILine]:
    """The job ids, `name:` values and `run` commands of a GitHub Actions workflow.

    A line-based reader for the few keys the audit reads, not a YAML
    parser: `run: |` / `run: >` blocks are followed by indentation.
    """
    lines: list[CILine] = []
    in_jobs = False
    job_indent: int | None = None
    run_indent: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if run_indent is not None:
            if stripped and indent > run_indent:
                lines.append(CILine(source, number, "run", stripped))
                continue
            if stripped:
                run_indent = None
        if not stripped or stripped.startswith("#"):
            continue
        if indent == 0:
            in_jobs = bool(_JOBS_RE.match(line))
            job_indent = None
            continue
        job = _JOB_ID_RE.match(line)
        if in_jobs and job and (job_indent is None or indent == job_indent):
            job_indent = indent
            lines.append(CILine(source, number, f"jobs.{job.group('id')}", job.group("id")))
            continue
        name = _NAME_RE.match(line)
        if name:
            lines.append(CILine(source, number, "name", name.group("value").strip("'\"")))
            continue
        run = _RUN_RE.match(line)
        if run:
            value = run.group("value")
            if value in {"|", ">", "|-", ">-", "|+", ">+"}:
                run_indent = len(run.group("indent"))
            elif value:
                lines.append(CILine(source, number, "run", value))
    return lines


def _ci_evidence(column: ReadinessColumn, lines: Sequence[CILine]) -> list[ReadinessEvidence]:
    if column.ci_pattern is None:
        return []
    pattern = re.compile(column.ci_pattern, re.IGNORECASE)
    evidence: list[ReadinessEvidence] = []
    for line in lines:
        match = pattern.search(line.text)
        if match:
            evidence.append(
                ReadinessEvidence(
                    source=line.source,
                    key=line.key,
                    line=line.line,
                    matched_text=_clip(line.text),
                    says="yes",
                )
            )
    return evidence


def _cell(evidence: list[ReadinessEvidence]) -> ReadinessCell:
    said = {item.says for item in evidence}
    if said == {"yes"}:
        return ReadinessCell(value="yes", evidence=evidence)
    if said == {"no"}:
        return ReadinessCell(value="no", evidence=evidence)
    if said:
        return ReadinessCell(
            value="unknown", evidence=evidence, note="the sources say both yes and no"
        )
    return ReadinessCell(value="unknown")


@dataclass(frozen=True)
class _CIRead:
    status: Literal["read", "missing", "unavailable"]
    files: tuple[str, ...] = ()
    lines: tuple[CILine, ...] = ()
    notes: tuple[str, ...] = ()


def _read_ci(source: RoadmapSource, repo: str) -> _CIRead:
    """One repository's GitHub Actions workflows (`*.yml`, `*.yaml`), as CI lines."""
    listing = source.list_directory(repo, WORKFLOWS_DIRECTORY)
    if listing.status == "missing":
        return _CIRead("missing")
    if listing.status == "unavailable":
        return _CIRead("unavailable", notes=(f"CI config could not be listed: {listing.error}",))
    files: list[str] = []
    lines: list[CILine] = []
    notes: list[str] = []
    for name in listing.names:
        if not name.endswith((".yml", ".yaml")):
            continue
        read = source.read_file(repo, f"{WORKFLOWS_DIRECTORY}/{name}")
        if read.text is None:
            notes.append(f"{read.label} could not be read: {read.error or read.status}")
            continue
        files.append(read.label)
        lines.extend(ci_lines(read.label, read.text))
    status: Literal["read", "missing", "unavailable"] = (
        "read" if files else ("unavailable" if notes else "missing")
    )
    return _CIRead(status, tuple(files), tuple(lines), tuple(notes))


def audit_field_readiness(
    repositories: Sequence[EcosystemRepository],
    source: RoadmapSource,
    columns: Sequence[ReadinessColumn],
    contracts: Mapping[str, ContractDocument],
    *,
    inactive_statuses: Collection[str] = (),
    problems: Sequence[str] = (),
) -> FieldReadinessReport:
    """One row per repository, one cell per column.

    `contracts` maps a repository name to its contract as read (a missing
    entry means no contract was given for it). A repository whose status
    is in `inactive_statuses` has no repository yet: every cell is
    `unknown` and nothing is read.
    """
    inactive = {status.casefold() for status in inactive_statuses}
    rows: list[SkillReadiness] = []
    for entry in sorted(repositories, key=lambda e: e.name.casefold()):
        if entry.status is not None and entry.status.casefold() in inactive:
            rows.append(
                SkillReadiness(
                    repo=entry.name,
                    status=entry.status,
                    contract="not_created",
                    ci="not_created",
                    cells={column.id: ReadinessCell(value="unknown") for column in columns},
                    notes=[f"status {entry.status}: no repository yet"],
                )
            )
            continue
        contract = contracts.get(entry.name) or ContractDocument(
            "missing", f"{entry.name}: no contract given"
        )
        notes: list[str] = []
        if contract.status == "unavailable":
            notes.append(f"contract {contract.label}: {contract.error}")
        ci = _read_ci(source, entry.name)
        notes.extend(ci.notes)
        cells = {
            column.id: _cell(
                [*_contract_evidence(column, contract), *_ci_evidence(column, ci.lines)]
            )
            for column in columns
        }
        rows.append(
            SkillReadiness(
                repo=entry.name,
                status=entry.status,
                contract=contract.status,
                contract_source=contract.label if contract.status == "read" else None,
                ci=ci.status,
                ci_files=list(ci.files),
                cells=cells,
                notes=notes,
            )
        )
    summary = {
        column.id: {
            value: sum(1 for row in rows if row.cells[column.id].value == value)
            for value in ("yes", "no", "unknown")
        }
        for column in columns
    }
    return FieldReadinessReport(
        source=source.kind,
        columns=[
            ColumnInfo(
                id=column.id,
                label=column.label,
                description=column.description,
                contract_keys=list(column.contract_keys),
                ci_pattern=column.ci_pattern,
            )
            for column in columns
        ],
        summary=summary,
        skills=rows,
        problems=list(problems),
    )


def _cell_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def format_readiness_table(report: FieldReadinessReport) -> str:
    """A Markdown table (one row per skill), then the evidence behind every yes and no."""
    labels = [column.label for column in report.columns]
    lines = [
        f"Field readiness ({report.source}): {len(report.skills)} skills; a cell is yes or no "
        "only where the contract or CI states it, otherwise unknown",
        "",
        "| Skill | Contract | CI | " + " | ".join(labels) + " |",
        "|---|---|---|" + "---|" * len(labels),
    ]
    for row in report.skills:
        cells = [row.cells[column.id].value for column in report.columns]
        lines.append(
            "| "
            + " | ".join(_cell_text(text) for text in (row.repo, row.contract, row.ci, *cells))
            + " |"
        )
    evidence_lines: list[str] = []
    for row in report.skills:
        for column in report.columns:
            cell = row.cells[column.id]
            if not cell.evidence:
                continue
            where = "; ".join(
                f"{item.source}"
                + (f":{item.line}" if item.line is not None else "")
                + f" {item.key} = {item.matched_text}"
                for item in cell.evidence
            )
            value = f"{cell.value} ({cell.note})" if cell.note else cell.value
            evidence_lines.append(f"- {row.repo} / {column.label}: {value} — {where}")
    if evidence_lines:
        lines += ["", "Evidence:", *evidence_lines]
    notes = [f"- {row.repo}: {'; '.join(row.notes)}" for row in report.skills if row.notes]
    notes += [f"- ecosystem file: {problem}" for problem in report.problems]
    if notes:
        lines += ["", "Notes:", *notes]
    return "\n".join(lines) + "\n"
