import json

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.proposals import Change, Proposal
from system_intelligence.execution.handoff import ChangePlanFile, build_handoff_packet


def _proposal(**overrides: object) -> Proposal:
    defaults: dict[str, object] = {
        "kind": "creation",
        "problem": "Need a markdown renderer",
        "evidence": [
            Evidence(kind=EvidenceKind.FILE, source="x", observation="need detected"),
        ],
        "changes": [Change(description="Add a new module", file_paths=["src/new_module.py"])],
        "required_permission_level": PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
    }
    defaults.update(overrides)
    return Proposal(**defaults)  # type: ignore[arg-type]


def test_build_handoff_packet_contains_full_proposal() -> None:
    proposal = _proposal()

    packet = build_handoff_packet(proposal, "/repo/root")

    assert packet["handoff_version"] == 1
    assert packet["target_root"] == "/repo/root"
    assert packet["proposal"]["kind"] == "creation"
    assert packet["proposal"]["problem"] == "Need a markdown renderer"
    assert packet["proposal"]["id"] == proposal.id


def test_build_handoff_packet_target_root_recorded_verbatim() -> None:
    """Never resolved, cloned, or validated -- recorded exactly as given."""
    packet = build_handoff_packet(_proposal(), "owner/repo")
    assert packet["target_root"] == "owner/repo"


def test_build_handoff_packet_is_json_serializable() -> None:
    packet = build_handoff_packet(_proposal(), "/repo/root")
    # Round-trips with no custom encoder -- proves every value is a plain
    # JSON-compatible type (enums/datetimes already converted by
    # `model_dump(mode="json")`), which is what an external implementer
    # in any language, not just Python, needs to be able to rely on.
    json.dumps(packet)


def test_build_handoff_packet_includes_instructions() -> None:
    packet = build_handoff_packet(_proposal(), "/repo/root")
    instructions = packet["instructions"]
    assert "si execute" in instructions
    assert "Approval" in instructions
    assert "force-push" in instructions


def test_change_plan_file_schema_uses_permission_level_name_not_int() -> None:
    """`ChangePlan.to_plan_file_dict`/`cli.main.execute` read/write
    `required_permission_level` by enum *name* (a string), never by its
    `int` value -- the schema handed to an external implementer must
    describe that real on-disk shape, not the runtime dataclass's own
    (int-valued) field."""
    schema = build_handoff_packet(_proposal(), "/repo/root")["change_plan_file_schema"]

    level_schema = schema["properties"]["required_permission_level"]
    assert level_schema["type"] == "string"
    assert level_schema["enum"] == [level.name for level in PermissionLevel]
    assert level_schema["default"] == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR.name


def test_change_plan_file_accepts_a_real_to_plan_file_dict_output() -> None:
    """The schema this module hands out must actually describe what
    `ChangePlan.to_plan_file_dict` produces -- proven by round-tripping a
    real one through `ChangePlanFile`, not just asserting shapes match."""
    from system_intelligence.execution.plan import ChangePlan

    plan = ChangePlan(
        branch_name="si/update-requests-to-2.0.0",
        commit_message="Update requests to 2.0.0",
        files={"pyproject.toml": 'dependencies = ["requests==2.0.0"]\n'},
        description="Update requests.",
        evidence_summary=["evidence text"],
    )

    parsed = ChangePlanFile.model_validate(plan.to_plan_file_dict())

    assert parsed.branch_name == plan.branch_name
    assert parsed.required_permission_level == "CREATE_BRANCH_OR_DRAFT_PR"


def test_change_plan_file_required_permission_level_defaults_when_omitted() -> None:
    minimal = {
        "branch_name": "si/x",
        "commit_message": "x",
        "files": {"a.txt": "b"},
    }
    parsed = ChangePlanFile.model_validate(minimal)
    assert parsed.required_permission_level == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR.name
