"""Proposal generation: adoption, integration, and creation proposals.

Phase 6 scope: the improvement engine decision tree from
docs/design/docs/07-improvement-engine.md — existing external solution
found? high-quality candidate with confirmed functional fit? adoption;
high-quality but unconfirmed fit, or a lower-quality candidate? integration
(partial); nothing found? creation. Proposals are never auto-executed.

`propose_solution`'s optional `target_kind` (a `core.enums.ComponentKind`)
shapes `test_strategy`/`documentation_requirements` to how that kind of
component is actually verified in practice (e.g. a Skill's contract lives
in its SKILL.md; an Agent is verified by running scenarios, not unit
tests) — see `_TEST_STRATEGY_BY_KIND` in `engine.py`. Not yet implemented:
refactor proposals (need capability-gap/duplicate detection wired to this
engine) and per-kind `interfaces`/`capabilities` *shape* (docs/07's "new
Skill"/"new Agent" templates go further than test/doc wording — both still
need richer input than a bare research result currently provides).

`propose_component_update` is a separate decision (not the adopt/create
tree above): it turns a Component Update Intelligence `ImpactAssessment`
into a `component_update`-kind Proposal, the last step of "Current State
-> Available State -> State Diff -> Impact -> Recommendation -> Proposal".

`change_plan_for_component_update` closes the one deterministic Proposal
-> `execution.plan.ChangePlan` path this project currently has: a `pypi`
exact-pin version bump, where the manifest edit is fully mechanical and
never ambiguous. Every other Proposal kind still needs an external
implementer (human or agent) to turn it into a ChangePlan by hand.
"""

from system_intelligence.proposals.engine import (
    change_plan_for_component_update,
    propose_component_update,
    propose_solution,
)

__all__ = [
    "change_plan_for_component_update",
    "propose_component_update",
    "propose_solution",
]
