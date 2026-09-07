"""Core domain model: entities, evidence, capabilities, findings, and the
canonical snapshot. This package has no dependency on discovery, analysis,
research, or execution — everything downstream depends on `core`, not the
other way around.
"""

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import (
    ADR,
    Agent,
    CIJob,
    Component,
    Dependency,
    Document,
    Entity,
    Interface,
    MCPServer,
    PullRequest,
    Repository,
    Skill,
    Software,
    Target,
    TestSuite,
    Tool,
    Workflow,
)
from system_intelligence.core.enums import (
    DEFAULT_MAX_PERMISSION_LEVEL,
    FORBIDDEN_BY_DEFAULT_ACTIONS,
    CapabilityStatus,
    ComponentKind,
    Confidence,
    PermissionLevel,
    RelationshipType,
    Severity,
    TargetKind,
    TrustLevel,
    UsageStatus,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.governance import Approval, AuditLogEntry
from system_intelligence.core.proposals import Change, InterfaceField, Proposal
from system_intelligence.core.recommendations import Recommendation
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.research import ResearchResult
from system_intelligence.core.snapshot import Snapshot, SnapshotManifest
from system_intelligence.core.verification import Verification

__all__ = [
    "ADR",
    "DEFAULT_MAX_PERMISSION_LEVEL",
    "FORBIDDEN_BY_DEFAULT_ACTIONS",
    "Agent",
    "Approval",
    "AuditLogEntry",
    "CIJob",
    "Capability",
    "CapabilityStatus",
    "Change",
    "Component",
    "ComponentKind",
    "Confidence",
    "Dependency",
    "Document",
    "Entity",
    "Evidence",
    "EvidenceKind",
    "Finding",
    "Interface",
    "InterfaceField",
    "MCPServer",
    "PermissionLevel",
    "Proposal",
    "PullRequest",
    "Recommendation",
    "Relationship",
    "RelationshipType",
    "Repository",
    "ResearchResult",
    "Severity",
    "Skill",
    "Snapshot",
    "SnapshotManifest",
    "Software",
    "Target",
    "TargetKind",
    "TestSuite",
    "Tool",
    "TrustLevel",
    "UsageStatus",
    "Verification",
    "Workflow",
]
