"""Evidence — the provenance backbone for every claim System Intelligence makes.

See docs/design/docs/04-domain-model.md ("Evidence model") and ADR-002
(evidence-first intelligence). Findings, capabilities, and research results
all reference one or more `Evidence` objects instead of asserting facts
directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from system_intelligence.core.enums import Confidence


class EvidenceKind(StrEnum):
    FILE = "file"
    GIT_METADATA = "git_metadata"
    PACKAGE_METADATA = "package_metadata"
    CI_CONFIG = "ci_config"
    AST = "ast"
    STATIC_REFERENCE = "static_reference"
    RUNTIME_TELEMETRY = "runtime_telemetry"
    EXTERNAL_SOURCE = "external_source"
    HUMAN_STATEMENT = "human_statement"


class Evidence(BaseModel):
    """A single observation backing a claim, with explicit provenance.

    `confidence` reflects how strongly this individual observation supports
    the claim it is attached to — it is not automatically inherited by
    claims that cite multiple pieces of evidence with differing confidence.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"evidence-{uuid4().hex[:12]}")
    kind: EvidenceKind
    source: str = Field(description="Human-readable origin, e.g. a file path or URL.")
    locator: str | None = Field(
        default=None,
        description="Precise pointer within the source, e.g. 'README.md#installation'.",
    )
    observation: str = Field(description="What was actually observed, stated factually.")
    confidence: Confidence = Confidence.MEDIUM
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
