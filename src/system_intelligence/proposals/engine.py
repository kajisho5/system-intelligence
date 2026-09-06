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

from system_intelligence.core.enums import PermissionLevel, UpdateVerdict
from system_intelligence.core.evidence import Evidence
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.proposals import Change, Proposal
from system_intelligence.core.research import ResearchResult
from system_intelligence.research.scoring import CandidateAssessment, rank_candidates

_TEST_STRATEGY = "Add tests covering the new/adopted capability's stated requirements."
_DOCUMENTATION_REQUIREMENTS = "Document the capability and how it satisfies each requirement."
_ROLLBACK_STRATEGY = "Revert the change; no other component depends on it until adopted."

_UPDATE_TEST_STRATEGY = (
    "Re-run the existing test suite after updating; add a regression test if the "
    "changelog or interface diff indicates a behavior change."
)
_UPDATE_DOCUMENTATION_REQUIREMENTS = (
    "Note the version bump and any migration steps from the changelog or release notes."
)
_UPDATE_ROLLBACK_STRATEGY = (
    "Revert the manifest version constraint change; no code changes are made automatically."
)
#: Verdicts with something to actually propose. NOT_ADVISABLE (the update
#: itself is the risk), NO_UPDATE_AVAILABLE, and UNKNOWN never produce a
#: Proposal — there is no change to propose in any of those cases.
_PROPOSABLE_VERDICTS = frozenset({UpdateVerdict.UPDATE_RECOMMENDED, UpdateVerdict.REVIEW_REQUIRED})


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


def propose_component_update(assessment: ImpactAssessment) -> Proposal | None:
    """Turn a Component Update Intelligence `ImpactAssessment` into a concrete Proposal.

    Closes "Current State -> Available State -> State Diff -> Impact ->
    Recommendation -> Proposal" for any component, generically — nothing
    here is specific to any ecosystem, package, or target.

    Returns `None` for `NOT_ADVISABLE`/`NO_UPDATE_AVAILABLE`/`UNKNOWN`
    verdicts: a Proposal describes a concrete change to make, and there is
    none to propose when the update itself is the risk, nothing changed, or
    nothing could be determined.
    """
    if assessment.verdict not in _PROPOSABLE_VERDICTS:
        return None

    diff = assessment.state_diff
    identity = diff.identity
    from_version = diff.from_state.version or "unknown"
    to_version = diff.to_state.version or "unknown"

    problem = (
        f"{identity.name} has an available update ({from_version} -> {to_version}). "
        f"{assessment.verdict_rationale}"
    )
    change = Change(
        description=f"Update the version constraint for {identity.name} to {to_version!r}.",
        required_permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )

    return Proposal(
        kind="component_update",
        problem=problem,
        evidence=list(assessment.evidence),
        proposed_component_name=identity.name,
        dependencies=[identity.name],
        implementation_stages=[
            "Update the version constraint in the declaring manifest.",
            "Run the existing test suite.",
            "Review the changelog/release notes for breaking changes if any were flagged.",
        ],
        changes=[change],
        test_strategy=_UPDATE_TEST_STRATEGY,
        documentation_requirements=_UPDATE_DOCUMENTATION_REQUIREMENTS,
        rollback_strategy=_UPDATE_ROLLBACK_STRATEGY,
        required_permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )
