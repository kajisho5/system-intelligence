"""Snapshot — the single canonical machine-readable state (ADR-003).

Mirrors the file layout from docs/design/docs/12-storage-and-state.md:

    snapshot/
      manifest.json
      components.json
      capabilities.json
      relationships.json
      findings.json
      recommendations.json
      research.json
      approvals.json
      verification.json

`Snapshot` is the in-memory/serialization model; `write_to_directory` /
`read_from_directory` implement that on-disk layout so HTML reports,
dashboards, and diff tooling all consume the same source of truth instead of
each inventing their own (docs/design/docs/09-visualization.md, "Data
contract").
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Component, Target
from system_intelligence.core.findings import Finding
from system_intelligence.core.governance import Approval
from system_intelligence.core.recommendations import Recommendation
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.research import ResearchResult
from system_intelligence.core.verification import Verification

_SNAPSHOT_VERSION = "0.1.0"

_FILES: dict[str, str] = {
    "components": "components.json",
    "capabilities": "capabilities.json",
    "relationships": "relationships.json",
    "findings": "findings.json",
    "recommendations": "recommendations.json",
    "research": "research.json",
    "approvals": "approvals.json",
    "verification": "verification.json",
}


class SnapshotManifest(BaseModel):
    scan_id: str
    target_fingerprint: str
    tool_version: str
    created_at: datetime


class Snapshot(BaseModel):
    id: str = Field(default_factory=lambda: f"snapshot-{uuid4().hex[:12]}")
    target: Target
    tool_version: str = _SNAPSHOT_VERSION
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    components: list[Component] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    research: list[ResearchResult] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    verification: list[Verification] = Field(default_factory=list)

    def manifest(self) -> SnapshotManifest:
        return SnapshotManifest(
            scan_id=self.id,
            target_fingerprint=self.target.locator,
            tool_version=self.tool_version,
            created_at=self.created_at,
        )

    def write_to_directory(self, directory: Path) -> None:
        """Write the canonical on-disk snapshot layout.

        Immutable by convention: callers should write each scan to a fresh
        directory (e.g. named by `self.id`) rather than overwriting a prior
        snapshot in place (docs/design/docs/12-storage-and-state.md,
        "Versioning").
        """
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_text(
            self.manifest().model_dump_json(indent=2), encoding="utf-8"
        )
        for field_name, filename in _FILES.items():
            items = getattr(self, field_name)
            payload = [item.model_dump(mode="json") for item in items]
            (directory / filename).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    @classmethod
    def read_from_directory(cls, directory: Path, target: Target) -> Snapshot:
        """Reconstruct a Snapshot from the on-disk canonical layout.

        `target` must be supplied by the caller: the manifest only stores a
        fingerprint, not the full Target (which may carry evidence not worth
        duplicating on every snapshot).
        """
        manifest_path = directory / "manifest.json"
        manifest = SnapshotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

        def _load(filename: str, model: type[BaseModel]) -> list[BaseModel]:
            path = directory / filename
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [model.model_validate(item) for item in raw]

        return cls(
            id=manifest.scan_id,
            target=target,
            tool_version=manifest.tool_version,
            created_at=manifest.created_at,
            components=_load(_FILES["components"], Component),  # type: ignore[arg-type]
            capabilities=_load(_FILES["capabilities"], Capability),  # type: ignore[arg-type]
            relationships=_load(_FILES["relationships"], Relationship),  # type: ignore[arg-type]
            findings=_load(_FILES["findings"], Finding),  # type: ignore[arg-type]
            recommendations=_load(_FILES["recommendations"], Recommendation),  # type: ignore[arg-type]
            research=_load(_FILES["research"], ResearchResult),  # type: ignore[arg-type]
            approvals=_load(_FILES["approvals"], Approval),  # type: ignore[arg-type]
            verification=_load(_FILES["verification"], Verification),  # type: ignore[arg-type]
        )
