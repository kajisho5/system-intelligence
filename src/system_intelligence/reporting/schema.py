"""JSON Schema export for the canonical Snapshot directory layout.

Epic 2 of docs/design/IMPLEMENTATION_BACKLOG.md: "define JSON schemas — no
standalone `*.schema.json` artifact exists; the pydantic models in `core/`
are the de facto schema (each can emit one via `model_json_schema()`, but
none is exported/committed today". An external consumer following
docs/design/docs/12-storage-and-state.md's "External consumer boundary"
(a different dashboard, CI tooling, another agent) can validate what it
reads without depending on this project's own Python types.

One `<name>.schema.json` per file in `core.snapshot.Snapshot`'s canonical
directory layout, plus `manifest` (`SnapshotManifest`, written separately
from the rest) and `dashboard_data` (`reporting.dashboard_data.
DashboardData`, the other supported read path). `components` is the one
list this can't reuse a single model for: the file holds whichever
concrete `Component` subtype each item actually is (`Repository`/`Skill`/
`Agent`/...), so its schema is a `Union` of every subtype — a base-
`Component`-only schema would document fields that aren't really there
(every subtype's own fields absent) and validate away real ones.

`test_reporting_schema.py` asserts this module's key set exactly matches
`Snapshot`'s own list-valued fields, so a future field added to `Snapshot`
without a matching schema entry here fails a test instead of silently
becoming an undocumented, unvalidatable file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import (
    ADR,
    Agent,
    Document,
    MCPServer,
    Repository,
    Skill,
    Software,
    Tool,
    Workflow,
)
from system_intelligence.core.execution_record import ExecutionRecord
from system_intelligence.core.findings import Finding
from system_intelligence.core.governance import Approval, AuditLogEntry
from system_intelligence.core.proposals import Proposal
from system_intelligence.core.recommendations import Recommendation
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.research import ResearchResult
from system_intelligence.core.snapshot import SnapshotManifest
from system_intelligence.core.verification import Verification
from system_intelligence.reporting.dashboard_data import DashboardData

_ComponentUnion = Repository | Software | Agent | Skill | MCPServer | Tool | Workflow | Document

#: Keys other than "manifest" and "dashboard_data" must exactly match
#: `Snapshot`'s own list-valued field names (see the module docstring and
#: `test_reporting_schema.py`).
_SCHEMAS: dict[str, TypeAdapter[Any]] = {
    "manifest": TypeAdapter(SnapshotManifest),
    "components": TypeAdapter(list[_ComponentUnion]),
    "capabilities": TypeAdapter(list[Capability]),
    "relationships": TypeAdapter(list[Relationship]),
    "findings": TypeAdapter(list[Finding]),
    "recommendations": TypeAdapter(list[Recommendation]),
    "proposals": TypeAdapter(list[Proposal]),
    "research": TypeAdapter(list[ResearchResult]),
    "approvals": TypeAdapter(list[Approval]),
    "verification": TypeAdapter(list[Verification]),
    "executions": TypeAdapter(list[ExecutionRecord]),
    "audit_log": TypeAdapter(list[AuditLogEntry]),
    "adrs": TypeAdapter(list[ADR]),
    "dashboard_data": TypeAdapter(DashboardData),
}


def export_json_schemas(directory: Path) -> list[Path]:
    """Write one `<name>.schema.json` file per entry in `_SCHEMAS`.

    Deterministic output (sorted keys, sorted dict entries) so a re-export
    of an unchanged model produces a byte-identical file — meaningful for
    diffing across releases.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in sorted(_SCHEMAS):
        schema = _SCHEMAS[name].json_schema()
        path = directory / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written
