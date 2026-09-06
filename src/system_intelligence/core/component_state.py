"""Component Update Intelligence — generic Current/Available state model.

This is deliberately independent of `core.entities.Component`: `Component`
describes a unit of *structure* discovered in a repository (a Skill, an
Agent, a package, ...); `ComponentState` describes a *versioned snapshot*
of what that component looks like at one point in time, whether observed
locally (current) or reported by an external source (available). Keeping
these separate avoids adding version/changelog/release fields to every
`Component` subtype regardless of whether update intelligence ever runs
against it.

This model is intentionally generic across every `ComponentKind` — a
Skill's version and an npm package's version are represented identically.
No Skill-specific, npm-specific, or target-specific fields belong here
(ADR-001, ADR-007): ecosystem-specific detail lives in `distribution_source`
as plain data, never as a distinct schema.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.entities import Dependency, Interface
from system_intelligence.core.enums import ComponentKind, Confidence
from system_intelligence.core.evidence import Evidence


class ComponentIdentity(BaseModel):
    """Which component this state describes, and where it comes from.

    `component_id` links back to a `core.entities.Component` already present
    in a Snapshot when one exists; it is optional because an available-state
    lookup can be performed for a component identity that has no local
    `Component` record at all (e.g. a dependency known only by name).
    """

    component_id: str | None = None
    component_kind: ComponentKind
    name: str
    source_repository: str | None = Field(
        default=None, description="git URL or 'owner/repo', if known."
    )
    distribution_source: str | None = Field(
        default=None,
        description="Where this component is distributed from, e.g. 'npm', "
        "'pypi', 'github-release', 'mcp-registry', 'capability-contract'. "
        "Plain data, not a fixed enum — new distribution sources never "
        "require a schema change.",
    )


class ReleaseInfo(BaseModel):
    version: str
    released_at: datetime | None = None
    release_notes_url: str | None = None
    is_prerelease: bool | None = None
    is_yanked: bool | None = Field(
        default=None, description="Withdrawn/yanked by its publisher, if the source reports it."
    )


class ChangelogEntry(BaseModel):
    version: str | None = None
    summary: str
    url: str | None = None


class ComponentState(BaseModel):
    """A single Current or Available state observation for one component.

    Every optional field left `None` and every `Confidence.UNKNOWN` marker
    here means exactly what it says: not observed, not inferred. A provider
    that cannot determine a dimension must leave it unset rather than guess.
    """

    id: str = Field(default_factory=lambda: f"component-state-{uuid4().hex[:12]}")
    identity: ComponentIdentity
    version: str | None = None
    version_confidence: Confidence = Confidence.UNKNOWN
    is_deprecated: bool | None = Field(
        default=None, description="Explicitly reported by the source; None means not reported."
    )
    capabilities: list[str] = Field(
        default_factory=list, description="Capability names this state declares or provides."
    )
    dependencies: list[Dependency] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(
        default_factory=list, description="e.g. 'python>=3.11', 'node>=18'."
    )
    release_info: ReleaseInfo | None = None
    changelog: list[ChangelogEntry] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AvailableState(ComponentState):
    """A `ComponentState` reported by an external source rather than observed locally.

    Adds only provenance of *which* provider produced it; the shape of the
    state itself is identical to `ComponentState` by design, so diffing two
    states never has to special-case which side is "current" vs "available".
    """

    provider: str = Field(description="e.g. 'pypi', 'npm', 'github'.")
