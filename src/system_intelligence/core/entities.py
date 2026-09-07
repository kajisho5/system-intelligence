"""Core structural entities from docs/design/docs/04-domain-model.md.

Every entity carries an `evidence` list rather than free-standing boolean
flags: whatever a discovery/analysis module claims about an entity should be
traceable to at least one `Evidence` record once that module actually
populates it. Phase 1 only defines the schemas; discovery adapters that
populate them arrive in later phases.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.enums import ComponentKind, TargetKind, TrustLevel
from system_intelligence.core.evidence import Evidence


class Entity(BaseModel):
    """Common base for anything System Intelligence can hold evidence about."""

    id: str = Field(default_factory=lambda: f"entity-{uuid4().hex[:12]}")
    name: str
    evidence: list[Evidence] = Field(default_factory=list)


class Target(Entity):
    """The thing being analyzed, as originally specified by the user/caller.

    A Target is the entry point (R1 in docs/design/docs/02-requirements.md);
    it resolves to one or more Repository entities during discovery.
    """

    kind: TargetKind
    locator: str = Field(description="Local path, git URL, GitHub owner/repo, or manifest path.")


class Interface(Entity):
    """A contract a Component exposes: a CLI, an HTTP API, a function signature, etc."""

    kind: str
    description: str | None = None


class Dependency(Entity):
    ecosystem: str = Field(description="e.g. 'pypi', 'npm', 'cargo'.")
    version_constraint: str | None = None
    resolved_version: str | None = None


class Component(Entity):
    """A unit of functionality within a Repository: package, service, agent, skill, etc."""

    kind: ComponentKind
    repository_id: str | None = None
    path: str | None = None
    description: str | None = None
    interfaces: list[Interface] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    trust_level: TrustLevel = TrustLevel.UNKNOWN


class Repository(Component):
    """The repository itself, represented as the root Component (kind=REPOSITORY)
    so it can live in the same canonical `components.json` list as everything
    it contains, rather than needing a separate top-level snapshot file.
    """

    kind: ComponentKind = ComponentKind.REPOSITORY
    is_git_repository: bool = False
    url: str | None = None
    default_branch: str | None = Field(
        default=None,
        description="The remote's own default branch, if resolvable -- unset for a real, "
        "valid git repository with no configured/fetched remote, distinct from `False`/"
        "'not a git repository' (`is_git_repository`).",
    )
    local_path: str | None = None
    license: str | None = None
    languages: list[str] = Field(default_factory=list)
    last_commit_sha: str | None = None
    last_commit_author: str | None = None
    last_commit_date: str | None = Field(
        default=None, description="ISO 8601 committer date of the last commit (git log's %cI)."
    )
    is_dirty: bool | None = Field(
        default=None, description="Whether the working tree had uncommitted changes."
    )


class Software(Component):
    """An ordinary, non-agentic package or service component."""

    kind: ComponentKind = ComponentKind.PACKAGE


class Agent(Component):
    """A Claude Code subagent (`.claude/agents/*.md`).

    `is_standard_format` mirrors `Skill.is_standard_format`: whether the
    required frontmatter fields (`name`, `description`) were actually
    present, never assumed true for every `.claude/agents/*.md` file found
    (discovery/agents.py).
    """

    kind: ComponentKind = ComponentKind.AGENT
    is_standard_format: bool | None = None
    model_provider: str | None = None
    tool_names: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class Skill(Component):
    """A Skill, ideally following the SKILL.md-based Agent Skills format.

    `is_standard_format` records whether a standard-layout detector matched;
    it must not be assumed true for every Skill-like directory
    (docs/design/docs/00-research-baseline.md).
    """

    kind: ComponentKind = ComponentKind.SKILL
    is_standard_format: bool | None = None
    triggers: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class MCPServer(Component):
    kind: ComponentKind = ComponentKind.MCP_SERVER
    tool_names: list[str] = Field(default_factory=list)


class Tool(Component):
    kind: ComponentKind = ComponentKind.TOOL
    provided_by: str | None = Field(default=None, description="Component id providing this tool.")


class Workflow(Component):
    kind: ComponentKind = ComponentKind.WORKFLOW
    trigger: str | None = None
    steps: list[str] = Field(default_factory=list)


class TestSuite(Entity):
    component_id: str | None = None
    framework: str | None = None
    test_count: int | None = None
    coverage_percent: float | None = None


class Document(Component):
    kind: ComponentKind = ComponentKind.DOCUMENT
    document_type: str | None = Field(
        default=None, description="e.g. 'README', 'ADR', 'architecture-doc'."
    )


class ADR(Entity):
    number: int | None = None
    status: str | None = None
    path: str | None = None
    decided_at: datetime | None = None


class CIJob(Entity):
    provider: str = Field(description="e.g. 'github-actions'.")
    workflow_path: str | None = None
    last_status: str | None = None
    last_run_at: datetime | None = None


class PullRequest(Entity):
    number: int
    repository_id: str | None = None
    state: str | None = None
    is_draft: bool = False
    url: str | None = None
