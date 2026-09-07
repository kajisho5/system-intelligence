"""Capability gap detection — declared-but-missing capabilities.

Closes a documented gap (`analysis/__init__.py`'s own docstring, before
this module existed): every other analyzer only reports what a repository
*declares about itself*, never what it *should* have — there was no input
a project could use to say "I need capability X" at all. `Capability.name`
already exists for "what was discovered"; nothing let a project assert
"what is required" until now.

`.si/requirements.json` (the same `.si/` convention `si research`'s cache
directory already uses) is that declaration, read only when a project
opts in by creating it — a repository with no such file contributes zero
gap Findings, never an inferred one. JSON, not YAML: this project has no
YAML dependency today (only pydantic and typer), and adding one for a
single optional input file is not justified.

A declared capability is only ever reported as a gap by exact, verifiable
absence (case-insensitive name match against `Capability.name` with
`status == CapabilityStatus.AVAILABLE`) — never a fuzzy/semantic match,
which would be guessing rather than verifying (ADR-002).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import CapabilityStatus, Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding

#: Relative to a target's root, mirroring `si research`'s
#: `.si/research-cache` -- `.si/` is this project's own established
#: directory for target-local, opt-in state.
REQUIREMENTS_PATH = Path(".si") / "requirements.json"


class DeclaredCapability(BaseModel):
    name: str
    description: str | None = None


class DeclaredRequirements(BaseModel):
    """The schema of `.si/requirements.json`.

    ```json
    {"capabilities": [{"name": "markdown rendering", "description": "..."}]}
    ```
    """

    capabilities: list[DeclaredCapability] = Field(default_factory=list)


class RequirementsParseError(RuntimeError):
    """`.si/requirements.json` exists but could not be read or parsed."""


def load_declared_requirements(root: Path) -> DeclaredRequirements | None:
    """Load `<root>/.si/requirements.json`, if present.

    `None` means the file does not exist at all — distinct from an empty
    `DeclaredRequirements()` (a project that explicitly declares zero
    required capabilities). A file that exists but is malformed raises
    `RequirementsParseError` rather than being silently treated as "no
    requirements declared," which would hide a real authoring mistake.
    """
    path = root / REQUIREMENTS_PATH
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RequirementsParseError(f"could not read {path}: {exc}") from exc
    try:
        return DeclaredRequirements.model_validate(raw)
    except ValidationError as exc:
        raise RequirementsParseError(f"invalid requirements file at {path}: {exc}") from exc


def detect_capability_gaps(
    declared: DeclaredRequirements, capabilities: list[Capability], repository: Repository
) -> list[Finding]:
    """Compare declared capabilities against what was actually discovered.

    A declared capability counts as satisfied only when a discovered
    `Capability` with an exactly matching name (case-insensitive, trimmed)
    has `status == CapabilityStatus.AVAILABLE`. A matching name whose
    status is `PARTIAL`/`MISSING`/`DEPRECATED`/`UNKNOWN` is still reported
    as a gap — "declared and looks partial" is not "satisfied".
    """
    available_names = {
        c.name.strip().lower() for c in capabilities if c.status == CapabilityStatus.AVAILABLE
    }
    source = str(REQUIREMENTS_PATH)
    findings: list[Finding] = []
    for capability in declared.capabilities:
        if capability.name.strip().lower() in available_names:
            continue
        evidence = [
            Evidence(
                kind=EvidenceKind.FILE,
                source=source,
                observation=f"{capability.name!r} is declared as a required capability in {source}",
                confidence=Confidence.VERIFIED,
            )
        ]
        findings.append(
            Finding(
                category="capability_gap",
                severity=Severity.HIGH,
                statement=(
                    f"{capability.name!r} is declared as a required capability in {source} "
                    "but no available capability with that name was discovered."
                ),
                confidence=Confidence.HIGH,
                affected_entity_ids=[repository.id],
                evidence=evidence,
                suggested_actions=[
                    f"Provide the {capability.name!r} capability, or remove it from "
                    f"{source} if it is no longer required."
                ],
            )
        )
    return findings


def _invalid_requirements_finding(error: RequirementsParseError, repository: Repository) -> Finding:
    source = str(REQUIREMENTS_PATH)
    return Finding(
        category="invalid_requirements_file",
        severity=Severity.HIGH,
        statement=f"{source} exists but could not be parsed: {error}",
        confidence=Confidence.VERIFIED,
        affected_entity_ids=[repository.id],
        evidence=[
            Evidence(
                kind=EvidenceKind.FILE,
                source=source,
                observation=str(error),
                confidence=Confidence.VERIFIED,
            )
        ],
        suggested_actions=[f"Fix the JSON in {source}."],
    )


def audit_capability_gaps(
    root: Path, capabilities: list[Capability], repository: Repository
) -> list[Finding]:
    """Run gap detection for a target root, if it declares any requirements.

    A missing `.si/requirements.json` (the overwhelming common case)
    contributes zero findings — this is opt-in, never inferred. A
    malformed one is surfaced as its own Finding rather than raised,
    consistent with every other analyzer here never aborting the whole
    `si diagnose` run over one bad input. `repository` is only ever used
    for `Finding.affected_entity_ids` (mirroring `audit_documentation`/
    `audit_ci_and_tests`'s own `repository` parameter) so every category
    this module produces can appear in the Dashboard's per-component
    "Findings affecting this component" view, like every other analyzer's
    Findings already do.
    """
    try:
        declared = load_declared_requirements(root)
    except RequirementsParseError as exc:
        return [_invalid_requirements_finding(exc, repository)]
    if declared is None:
        return []
    return detect_capability_gaps(declared, capabilities, repository)
