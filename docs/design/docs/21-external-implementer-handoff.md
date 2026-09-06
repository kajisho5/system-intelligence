# External Implementer Handoff

## The gap

`proposals/engine.py::change_plan_for_component_update` closes one narrow
Proposal shape deterministically: a `pypi`/`npm` dependency pinned to a
confirmed exact version. Every other Proposal kind — creation, adoption,
integration, and any range-constrained update — has no automatic path to
an `execution.plan.ChangePlan`. Deciding *what code to actually write* is
not a fact this project can derive from evidence; per ADR-007 it must
never be guessed by an embedded model.

Before this document, that gap had no defined boundary: a human (or an
agent someone pointed at the problem) had to already know, from reading
this project's source, the exact on-disk shape `si execute` accepts. That
tribal knowledge is now an exportable artifact.

## The boundary

`execution/handoff.py::build_handoff_packet(proposal, target_root)` is a
pure, read-only function that returns one self-contained JSON packet:

- `proposal` — the full `Proposal`, evidence included.
- `target_root` — recorded exactly as given, never resolved or cloned.
- `change_plan_file_schema` — the JSON Schema of `ChangePlanFile`, the
  *real* on-disk shape `si execute <file> <target> --approve` reads (see
  "A schema detail" below).
- `instructions` — fixed text naming no vendor: "a human, or an agent such
  as Claude Code, Codex, or Cursor."

`si propose <problem> --target <path> --handoff-out <file>` writes it.
Nothing about this call touches a model, an agent SDK, or a specific tool
— it only serializes data already computed by `propose_solution`.

## What happens on each side of the boundary

```text
si propose --handoff-out packet.json --target ./my-repo
        |
        v
   [ outside System Intelligence: a human, or an agent
     of the implementer's choosing, reads packet.json,
     decides what files to write, and produces a
     ChangePlan-shaped JSON file — SI has no part in this ]
        |
        v
si execute <that-file> ./my-repo --approve [--push --repo owner/repo]
```

The right-hand side is not new: it is the same `si execute` path
`change_plan_for_component_update`'s output already goes through, gated
by the same `policy.evaluate` checks and the same `Approval` requirement.
This document only formalizes how a Proposal that has *no* deterministic
`ChangePlan` reaches that same door.

## A schema detail worth stating explicitly

`ChangePlan.required_permission_level` is a `PermissionLevel` enum at
runtime. `ChangePlan.to_plan_file_dict` and `cli.main.execute` serialize
and parse it by the member's **name** (`"CREATE_BRANCH_OR_DRAFT_PR"`),
never by its `int` value. A JSON Schema generated directly from the
`ChangePlan` dataclass would document an integer field — a shape
`si execute` does not actually accept. `execution.handoff.ChangePlanFile`
is a separate model describing the real file format, verified in
`tests/unit/test_execution_handoff.py` by round-tripping an actual
`ChangePlan.to_plan_file_dict()` output through it.

## What this does not do

- It does not invoke any model, agent, or tool. System Intelligence's own
  process ends at writing the packet.
- It does not provision credentials for whatever implements the handoff —
  Open Question 5 ("How should credentials be provisioned across Claude
  Code/Codex/Cursor?") stays open; this boundary is deliberately
  credential-agnostic, since the implementer runs entirely outside SI.
- It does not change `si execute`'s semantics, `si plan`'s intent
  classification, or any policy/Approval rule. A `ChangePlan` produced
  this way is indistinguishable, at the `si execute` boundary, from one a
  human hand-authored or `change_plan_for_component_update` generated.
- It does not attempt to select or recommend a specific implementer — the
  choice of "a human, Claude Code, Codex, Cursor, or anything else" is
  left entirely to whoever runs `si propose --handoff-out`.
