"""Proposal generation: adoption, integration, and creation proposals.

Phase 6 scope: the improvement engine decision tree from
docs/design/docs/07-improvement-engine.md — existing external solution
found? high-quality candidate with confirmed functional fit? adoption;
high-quality but unconfirmed fit, or a lower-quality candidate? integration
(partial); nothing found? creation. Proposals are never auto-executed.

Not yet implemented: refactor proposals (need capability-gap/duplicate
detection wired to this engine) and the "new Skill"/"new Agent" proposal
templates docs/07 also lists — both need richer input than a bare research
result currently provides.
"""

from system_intelligence.proposals.engine import propose_solution

__all__ = ["propose_solution"]
