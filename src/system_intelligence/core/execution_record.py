"""ExecutionRecord — a persisted audit entry for one `execution.apply_plan` call.

Without this, `si execute`'s result only ever existed for the lifetime of
one CLI invocation: nothing wrote it anywhere a later `si dashboard` or
`si diff` could see it, so a Dashboard "Executions" screen would be
permanently empty by construction rather than by actual history. This
model is the minimal persisted fact set for that screen — it never
recomputes or reinterprets `ExecutionResult`/`PolicyDecision`, only
records what they already said.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class ExecutionRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"execution-{uuid4().hex[:12]}")
    action: str
    target: str
    plan_description: str = ""
    branch_name: str | None = None
    commit_sha: str | None = None
    files_written: list[str] = Field(default_factory=list)
    applied: bool
    decision_reason: str
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
