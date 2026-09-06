"""Improvement decision tree (docs/design/docs/07-improvement-engine.md):

    Need detected
        -> existing external solution found?
            -> no  -> creation proposal
            -> yes -> is it a high-quality candidate (license, recently
                      active, not archived) AND has functional fit against
                      the stated requirements actually been confirmed?
                -> yes -> adoption proposal
                -> no  -> integration proposal (partial solution; explains
                          exactly what remains unverified)

Functional/architectural fit cannot be determined from GitHub search
metadata alone (docs/06-research-engine.md's anti-hallucination rule), so
this never returns an adoption proposal on research signals by itself —
`functional_fit_confirmed` must be explicitly asserted by a caller that
verified it (e.g. a human, or a later semantic-analysis phase).
"""

from __future__ import annotations

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.evidence import Evidence
from system_intelligence.core.proposals import Proposal
from system_intelligence.core.research import ResearchResult
from system_intelligence.research.scoring import CandidateAssessment, rank_candidates

_TEST_STRATEGY = "Add tests covering the new/adopted capability's stated requirements."
_DOCUMENTATION_REQUIREMENTS = "Document the capability and how it satisfies each requirement."
_ROLLBACK_STRATEGY = "Revert the change; no other component depends on it until adopted."


def _is_high_quality_candidate(assessment: CandidateAssessment) -> bool:
    return (
        assessment.has_license
        and assessment.is_recently_active is True
        and not assessment.is_archived
    )


def _insufficiency_reason(assessment: CandidateAssessment) -> str:
    reasons: list[str] = []
    if not assessment.has_license:
        reasons.append("no license detected")
    if assessment.is_recently_active is False:
        reasons.append("not recently active")
    if assessment.is_recently_active is None:
        reasons.append("activity could not be determined")
    if assessment.is_archived:
        reasons.append("archived")
    detail = ", ".join(reasons) if reasons else "insufficient evidence to confirm fit"
    return f"{assessment.result.identifier}: {detail}"


def propose_solution(
    problem: str,
    *,
    evidence: list[Evidence] | None = None,
    requirements: list[str] | None = None,
    research_results: list[ResearchResult] | None = None,
    functional_fit_confirmed: bool = False,
) -> Proposal:
    evidence = evidence or []
    requirements = requirements or []
    research_results = research_results or []

    if not research_results:
        return Proposal(
            kind="creation",
            problem=problem,
            evidence=evidence,
            requirements=requirements,
            alternatives_considered=[],
            why_existing_solutions_insufficient=(
                "No candidate solutions were found in the searched external ecosystem."
            ),
            capabilities=list(requirements),
            test_strategy=_TEST_STRATEGY,
            documentation_requirements=_DOCUMENTATION_REQUIREMENTS,
            rollback_strategy=_ROLLBACK_STRATEGY,
            required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
        )

    ranked = rank_candidates(research_results)
    best = ranked[0]
    alternatives = [a.result.identifier for a in ranked[1:]]

    if _is_high_quality_candidate(best) and functional_fit_confirmed:
        return Proposal(
            kind="adoption",
            problem=problem,
            evidence=[*evidence, *best.result.evidence],
            requirements=requirements,
            alternatives_considered=alternatives,
            proposed_component_name=best.result.identifier,
            capabilities=list(requirements),
            dependencies=[best.result.identifier],
            test_strategy=_TEST_STRATEGY,
            documentation_requirements=_DOCUMENTATION_REQUIREMENTS,
            rollback_strategy=_ROLLBACK_STRATEGY,
            required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
        )

    if _is_high_quality_candidate(best):
        reason = (
            "Functional fit against the stated requirements has not been "
            "verified; license, activity, and archival status look sufficient."
        )
    else:
        reason = _insufficiency_reason(best)

    return Proposal(
        kind="integration",
        problem=problem,
        evidence=[*evidence, *best.result.evidence],
        requirements=requirements,
        alternatives_considered=alternatives,
        proposed_component_name=best.result.identifier,
        why_existing_solutions_insufficient=reason,
        capabilities=list(requirements),
        dependencies=[best.result.identifier],
        test_strategy=_TEST_STRATEGY,
        documentation_requirements=_DOCUMENTATION_REQUIREMENTS,
        rollback_strategy=_ROLLBACK_STRATEGY,
        required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
    )
