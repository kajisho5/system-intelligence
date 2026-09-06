"""External-implementer handoff (ADR-007: no model vendor or agent harness
hard-coded here).

`proposals.engine.change_plan_for_component_update` closes the one
Proposal shape System Intelligence can turn into an executable
`execution.plan.ChangePlan` on its own; every other Proposal kind
(creation/adoption/integration, and any range-constrained update) needs a
human or an external implementer to actually author the diff. Until now,
nothing described *how* that external step should hand its result back —
whoever picked up the work had to already know `ChangePlan.
to_plan_file_dict`'s on-disk shape by reading this project's source.
`build_handoff_packet` and `ChangePlanFile` turn that into an exportable,
self-contained artifact: everything an implementer needs is in the packet,
and the only way back into System Intelligence is a `ChangePlan` JSON file
`si execute` can read.

`ChangePlan.required_permission_level` is a `PermissionLevel` enum at
runtime, but `ChangePlan.to_plan_file_dict`/`cli.main.execute` serialize
and parse it by the member's *name* (e.g. `"CREATE_BRANCH_OR_DRAFT_PR"`),
never its `int` value — so a JSON Schema generated directly from the
`ChangePlan` dataclass would describe an integer field `si execute` does
not actually accept. `ChangePlanFile` models the real on-disk format
instead of the runtime dataclass.

This module never invokes a model, an agent SDK, or any specific tool —
it only builds and serializes a plain JSON packet. Delivering that packet
to a human, Claude Code, Codex, Cursor, or any other implementer, and
getting a `ChangePlan` JSON file back, all happen entirely outside System
Intelligence, and applying that file still goes through `si execute`,
which is gated by policy and a human-provided Approval exactly as any
hand-authored plan would be.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.proposals import Proposal

_INSTRUCTIONS = (
    "This packet describes one System Intelligence Proposal with no deterministic "
    "path to an executable ChangePlan (see 'proposal.kind' and 'proposal.problem'). "
    "An external implementer -- a human, or an agent such as Claude Code, Codex, or "
    "Cursor -- must read 'proposal' and 'target_root', decide what file changes "
    "satisfy the proposal, and write a JSON file matching 'change_plan_file_schema' "
    "(the exact shape 'si execute <file> <target> --approve' reads). System "
    "Intelligence itself never invokes a model or writes code on its own behalf: "
    "producing the ChangePlan file is entirely this implementer's responsibility. "
    "Applying it still goes through 'si execute', which is gated by policy and "
    "requires a human-provided Approval unless the plan's required permission level "
    "is at or below the default maximum. Never merge, close, delete, force-push, or "
    "push to a remote branch as part of implementing this handoff -- those actions, "
    "if wanted at all, require their own separate, explicit Approval."
)


class ChangePlanFile(BaseModel):
    """The exact on-disk shape `si execute <file> <target>` reads back.

    Distinct from `execution.plan.ChangePlan` (the in-memory dataclass):
    matches `ChangePlan.to_plan_file_dict`'s output and `cli.main.execute`'s
    parsing field-for-field, including `required_permission_level` being
    the enum member's *name*, not its `int` value.
    """

    branch_name: str
    commit_message: str
    files: dict[str, str] = Field(
        description="Path relative to the target repository root -> full new file content."
    )
    description: str = ""
    evidence_summary: list[str] = Field(default_factory=list)
    required_permission_level: str = Field(
        default=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR.name,
        description=(
            "Name of a system_intelligence.core.enums.PermissionLevel member "
            "(e.g. 'CREATE_BRANCH_OR_DRAFT_PR'), not its integer value."
        ),
        json_schema_extra={"enum": list(PermissionLevel.__members__)},
    )


def build_handoff_packet(proposal: Proposal, target_root: str) -> dict[str, Any]:
    """Bundle a Proposal with everything an external implementer needs.

    Pure and read-only: never touches the filesystem or a target repository.
    `target_root` is recorded exactly as given, not resolved or validated —
    the same target-resolution rules as every other `si` command apply
    once the implementer, or a later `si execute` call, actually uses it.
    """
    return {
        "handoff_version": 1,
        "proposal": proposal.model_dump(mode="json"),
        "target_root": target_root,
        "change_plan_file_schema": ChangePlanFile.model_json_schema(),
        "instructions": _INSTRUCTIONS,
    }
