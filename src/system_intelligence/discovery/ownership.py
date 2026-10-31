"""Ownership-map discovery: collect the documents that say who owns which job.

An ownership map gives each job (a unit of work, named in plain words) to
the components that own it. The reference shape is the AI Video
Production OS `ecosystem.json` (ADR-012):

```json
{"components": [{"repo": "publish-skill", "status": "scaffold",
                 "owns": ["配信先アップロード", "アップロード制限"]}]}
```

A document may also bind jobs to the capability ids that realize them,
so a capability a component *provides* (its Capability Contract) can be
checked against the job's owner:

```json
{"job_capabilities": {"配信プラットフォーム仕様": ["ffmpeg-skill.export"]}}
```

This module only *collects* such documents; `analysis/ownership.py`
reads them. Two sources, both static -- nothing here ever runs a command
(ADR-011's rule, kept for ownership maps without exception):

1. **`.si/ownership.json` in the target** (checked-in, read
   automatically). It is itself an ownership document (it may carry
   `components` and `job_capabilities`), and its `maps` list names more
   ownership documents by path: `{"maps": [{"path": "ecosystem.json"}]}`.
   Each path must be relative and stay inside the target root.
2. **`--ownership-map`** (operator-supplied): an ownership document read
   from anywhere, e.g. the OS's `ecosystem.json` while auditing a Skill.

A target with no `.si/ownership.json` and no operator-supplied map yields
no observations at all -- never an inferred one.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.discovery.contracts import MAX_CONTRACT_BYTES, confined_path

#: Relative to a target's root, next to `.si/contracts.json`.
OWNERSHIP_DECLARATION_PATH = Path(".si") / "ownership.json"


@dataclass(frozen=True)
class OwnershipObservation:
    """One collected ownership document, or why there is none.

    Exactly one of `document`/`error` is set. `label` is a stable name for
    the source (the path as declared or given) used in Finding statements,
    so repeated scans compare equal (`si watch`).
    """

    kind: Literal["file", "declaration"]
    label: str
    evidence: Evidence
    document: Any = None
    error: str | None = None


class _DeclaredMap(BaseModel):
    path: str


class _OwnershipDeclaration(BaseModel):
    """The `maps` part of `.si/ownership.json`; the rest is read as an ownership document."""

    maps: list[_DeclaredMap] = Field(default_factory=list)


def _evidence(label: str, observation: str) -> Evidence:
    return Evidence(
        kind=EvidenceKind.FILE,
        source=label,
        observation=observation,
        confidence=Confidence.VERIFIED,
    )


def _read_json(
    path: Path, label: str, kind: Literal["file", "declaration"]
) -> OwnershipObservation:
    def failed(error: str) -> OwnershipObservation:
        return OwnershipObservation(kind, label, _evidence(label, error), error=error)

    try:
        size = path.stat().st_size
        if size > MAX_CONTRACT_BYTES:
            return failed(f"larger than {MAX_CONTRACT_BYTES} bytes ({size}); not read")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return failed(f"could not be read: {exc.__class__.__name__}: {exc}")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return failed(f"not valid JSON: {exc}")
    return OwnershipObservation(
        kind, label, _evidence(label, "ownership document read from file"), document=document
    )


def read_declared_ownership(root: Path) -> list[OwnershipObservation]:
    """`<root>/.si/ownership.json` and the maps it lists, if that file exists.

    The declaration itself comes first (it may bind jobs to capabilities),
    then each listed map. A malformed declaration, or a listed path that
    is absolute or leaves the target root, is returned as an observation
    with `error` set rather than raised.
    """
    declaration_path = root / OWNERSHIP_DECLARATION_PATH
    if not declaration_path.is_file():
        return []
    label = OWNERSHIP_DECLARATION_PATH.as_posix()
    declaration = _read_json(declaration_path, label, "declaration")
    if declaration.error is not None:
        return [declaration]
    try:
        parsed = _OwnershipDeclaration.model_validate(declaration.document)
    except ValidationError as exc:
        error = f"could not be parsed: {exc}"
        return [OwnershipObservation("declaration", label, _evidence(label, error), error=error)]

    observations = [declaration]
    for entry in parsed.maps:
        path = confined_path(root, entry.path)
        if path is None:
            error = f"lists {entry.path!r}, which is absolute or outside the target root; not read"
            observations.append(
                OwnershipObservation("declaration", label, _evidence(label, error), error=error)
            )
            continue
        observations.append(_read_json(path, entry.path, "file"))
    return observations


def read_ownership_map(path: Path) -> OwnershipObservation:
    """An operator-supplied ownership map (relative paths resolve against the CWD)."""
    return _read_json(path, str(path), "file")


def collect_ownership(
    root: Path, ownership_maps: Sequence[Path] = ()
) -> list[OwnershipObservation]:
    """Every ownership source for a target: its own declaration first, then the operator's."""
    return [
        *read_declared_ownership(root),
        *(read_ownership_map(path) for path in ownership_maps),
    ]
