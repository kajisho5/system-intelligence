from pathlib import Path

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Component, Repository, Skill, Target
from system_intelligence.core.enums import (
    CapabilityStatus,
    ComponentKind,
    PermissionLevel,
    TargetKind,
)
from system_intelligence.core.execution_record import ExecutionRecord
from system_intelligence.core.proposals import Proposal
from system_intelligence.core.snapshot import Snapshot


def _target() -> Target:
    return Target(name="system-intelligence", kind=TargetKind.LOCAL_PATH, locator="/repo")


def test_snapshot_round_trips_through_directory(tmp_path: Path) -> None:
    snapshot = Snapshot(
        target=_target(),
        components=[Component(name="core", kind=ComponentKind.PACKAGE, path="src/core")],
        capabilities=[Capability(name="scan", status=CapabilityStatus.PARTIAL)],
    )

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)

    for filename in [
        "manifest.json",
        "components.json",
        "capabilities.json",
        "relationships.json",
        "findings.json",
        "recommendations.json",
        "proposals.json",
        "research.json",
        "approvals.json",
        "verification.json",
        "executions.json",
        "audit_log.json",
        "adrs.json",
    ]:
        assert (out_dir / filename).exists(), f"missing {filename}"

    restored = Snapshot.read_from_directory(out_dir, target=_target())
    assert restored.id == snapshot.id
    assert restored.tool_version == snapshot.tool_version
    assert len(restored.components) == 1
    assert restored.components[0].name == "core"
    assert len(restored.capabilities) == 1
    assert restored.capabilities[0].status == CapabilityStatus.PARTIAL


def test_snapshot_whole_object_json_dump_preserves_component_subclass_fields() -> None:
    """`write_to_directory` dumps each Component individually and was never
    affected, but calling `model_dump_json()` on the whole `Snapshot` (e.g.
    an external consumer wanting one JSON blob instead of the directory
    layout) used to serialize every `components` entry using the base
    `Component` schema, silently dropping subclass-only fields like
    `Repository.url` -- a real pydantic v2 default behavior, fixed via
    `SerializeAsAny`."""
    import json

    snapshot = Snapshot(
        target=_target(),
        components=[Repository(id="r1", name="repo", path=".", url="https://example.com/x.git")],
    )

    payload = json.loads(snapshot.model_dump_json())

    assert payload["components"][0]["url"] == "https://example.com/x.git"


def test_snapshot_manifest_uses_target_locator_as_fingerprint() -> None:
    snapshot = Snapshot(target=_target())
    manifest = snapshot.manifest()
    assert manifest.target_fingerprint == "/repo"
    assert manifest.scan_id == snapshot.id


def test_snapshot_round_trip_preserves_component_subtypes(tmp_path: Path) -> None:
    snapshot = Snapshot(
        target=_target(),
        components=[
            Repository(id="repository:root", name="repo", path=".", languages=["Python"]),
            Skill(id="skill:x", name="x", path="skills/x/SKILL.md", is_standard_format=True),
        ],
    )

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)
    restored = Snapshot.read_from_directory(out_dir)  # no target supplied

    repository = next(c for c in restored.components if isinstance(c, Repository))
    skill = next(c for c in restored.components if isinstance(c, Skill))
    assert repository.languages == ["Python"]
    assert skill.is_standard_format is True
    assert restored.target.locator == "/repo"


def test_snapshot_round_trip_preserves_proposals_and_executions(tmp_path: Path) -> None:
    proposal = Proposal(
        kind="creation",
        problem="Need a thing",
        required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
    )
    execution = ExecutionRecord(
        action="create_local_branch_and_commit",
        target=".",
        applied=True,
        decision_reason="approved",
    )
    snapshot = Snapshot(target=_target(), proposals=[proposal], executions=[execution])

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)
    restored = Snapshot.read_from_directory(out_dir, target=_target())

    assert len(restored.proposals) == 1
    assert restored.proposals[0].problem == "Need a thing"
    assert len(restored.executions) == 1
    assert restored.executions[0].applied is True


def test_snapshot_round_trip_preserves_audit_log(tmp_path: Path) -> None:
    from system_intelligence.core.governance import AuditLogEntry

    entry = AuditLogEntry(
        actor="system:cli",
        intent="ship a fix",
        policy="within default maximum",
        target=".",
        action="create_local_branch_and_commit",
        result="allowed",
        correlation_id="abc123",
    )
    snapshot = Snapshot(target=_target(), audit_log=[entry])

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)

    assert (out_dir / "audit_log.json").exists()
    restored = Snapshot.read_from_directory(out_dir, target=_target())
    assert len(restored.audit_log) == 1
    assert restored.audit_log[0].correlation_id == "abc123"
    assert restored.audit_log[0].result == "allowed"


def test_snapshot_audit_log_defaults_to_empty(tmp_path: Path) -> None:
    snapshot = Snapshot(target=_target())

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)
    restored = Snapshot.read_from_directory(out_dir, target=_target())

    assert restored.audit_log == []


def test_snapshot_round_trip_preserves_adrs(tmp_path: Path) -> None:
    from system_intelligence.core.entities import ADR

    adr = ADR(
        name="First decision",
        number=1,
        status="Accepted",
        path="docs/adr/ADR-001-first-decision.md",
    )
    snapshot = Snapshot(target=_target(), adrs=[adr])

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)

    assert (out_dir / "adrs.json").exists()
    restored = Snapshot.read_from_directory(out_dir, target=_target())
    assert len(restored.adrs) == 1
    assert restored.adrs[0].number == 1
    assert restored.adrs[0].status == "Accepted"


def test_snapshot_adrs_defaults_to_empty(tmp_path: Path) -> None:
    snapshot = Snapshot(target=_target())

    out_dir = tmp_path / snapshot.id
    snapshot.write_to_directory(out_dir)
    restored = Snapshot.read_from_directory(out_dir, target=_target())

    assert restored.adrs == []
