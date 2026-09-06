"""Verification — before/after evidence that an approved change worked (R10)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.evidence import Evidence


class Verification(BaseModel):
    id: str = Field(default_factory=lambda: f"verification-{uuid4().hex[:12]}")
    proposal_id: str | None = None
    change_id: str | None = None
    before_snapshot_id: str | None = None
    after_snapshot_id: str | None = None
    tests_run: list[str] = Field(default_factory=list)
    tests_passed: bool | None = None
    regressions_found: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
