"""StateDiff — a structured, evidenced difference between two ComponentStates.

A version-number delta (`from_state.version` vs `to_state.version`) is
recorded for display, but it is never treated as proof of anything by
itself: every actual observed difference — an added/removed capability, a
changed dependency, a breaking interface change — is its own `StateDiffItem`
with its own Evidence and Confidence. A diff with a version delta but no
other items means exactly that: no other difference could be determined,
not that none exists.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.component_state import ComponentIdentity, ComponentState
from system_intelligence.core.enums import Confidence, StateDiffCategory
from system_intelligence.core.evidence import Evidence


class StateDiffItem(BaseModel):
    id: str = Field(default_factory=lambda: f"state-diff-item-{uuid4().hex[:12]}")
    category: StateDiffCategory
    description: str
    confidence: Confidence
    evidence: list[Evidence] = Field(default_factory=list)


class StateDiff(BaseModel):
    id: str = Field(default_factory=lambda: f"state-diff-{uuid4().hex[:12]}")
    identity: ComponentIdentity
    from_state: ComponentState
    to_state: ComponentState
    version_delta: str | None = Field(
        default=None,
        description="Display-only, e.g. '0.8.2 -> 0.9.2'. Never the basis for a verdict by itself.",
    )
    items: list[StateDiffItem] = Field(default_factory=list)

    @property
    def has_items(self) -> bool:
        return bool(self.items)
