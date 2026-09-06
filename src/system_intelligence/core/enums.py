"""Shared enumerations for the domain model.

These enums encode vocabulary that the rest of the design documents rely on
verbatim (see docs/design/docs/04-domain-model.md, 05-analysis-engine.md,
and 08-governance.md). Keeping them centralized avoids each module inventing
its own status strings.
"""

from __future__ import annotations

from enum import Enum, StrEnum


class Confidence(StrEnum):
    """How strongly a claim is backed by evidence.

    Never upgrade a claim's confidence without new evidence — see
    ADR-002 (evidence-first intelligence) and ADR-010 (unused is a
    confidence classification).
    """

    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    """Edge types in the component/capability relationship graph."""

    USES = "uses"
    PROVIDES = "provides"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    DUPLICATES = "duplicates"
    CONFLICTS_WITH = "conflicts_with"
    SUPERSEDES = "supersedes"
    REFERENCED_BY = "referenced_by"
    TESTED_BY = "tested_by"
    DOCUMENTED_BY = "documented_by"
    DEPLOYED_BY = "deployed_by"


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    DEPRECATED = "deprecated"
    UNKNOWN = "unknown"


class UsageStatus(StrEnum):
    """Classification for "is this component used" questions.

    Static non-reference is never sufficient on its own to declare
    something `verified_unused` (ADR-010). Reaching `verified_unused`
    requires corroborating evidence beyond a missing static reference,
    e.g. runtime telemetry or explicit human confirmation.
    """

    UNREFERENCED = "unreferenced"
    INACTIVE = "inactive"
    POTENTIALLY_UNUSED = "potentially_unused"
    VERIFIED_UNUSED = "verified_unused"
    ACTIVE = "active"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PermissionLevel(int, Enum):
    """Approval ladder from docs/design/docs/08-governance.md.

    Default maximum is OBSERVE..GENERATE_LOCAL_ARTIFACTS (0-3). Anything
    at CREATE_BRANCH_OR_DRAFT_PR (4) or above requires an explicit
    Approval record.
    """

    OBSERVE = 0
    ANALYZE = 1
    RECOMMEND = 2
    GENERATE_LOCAL_ARTIFACTS = 3
    CREATE_BRANCH_OR_DRAFT_PR = 4
    MODIFY_REMOTE_REPOSITORY = 5
    RELEASE_OR_DEPLOY = 6


DEFAULT_MAX_PERMISSION_LEVEL = PermissionLevel.GENERATE_LOCAL_ARTIFACTS

#: Actions that must never be executed automatically, regardless of policy
#: configuration (docs/design/docs/08-governance.md, "Forbidden by default").
FORBIDDEN_BY_DEFAULT_ACTIONS: frozenset[str] = frozenset(
    {
        "merge_pull_request",
        "close_pull_request",
        "delete_branch",
        "delete_repository",
        "force_push",
        "change_repository_visibility",
        "rotate_credentials",
        "change_production_infrastructure",
        "publish_release",
        "modify_permissions",
    }
)


class TargetKind(StrEnum):
    LOCAL_PATH = "local_path"
    GIT_REPOSITORY = "git_repository"
    GITHUB_REPOSITORY = "github_repository"
    REPOSITORY_LIST = "repository_list"
    MANIFEST = "manifest"
    ECOSYSTEM_MANIFEST = "ecosystem_manifest"


class ComponentKind(StrEnum):
    REPOSITORY = "repository"
    PACKAGE = "package"
    SERVICE = "service"
    AGENT = "agent"
    SKILL = "skill"
    MCP_SERVER = "mcp_server"
    TOOL = "tool"
    WORKFLOW = "workflow"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class TrustLevel(StrEnum):
    """docs/design/docs/14-security.md — trust is not equivalent to popularity."""

    TRUSTED = "trusted"
    REVIEWED = "reviewed"
    COMMUNITY = "community"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
