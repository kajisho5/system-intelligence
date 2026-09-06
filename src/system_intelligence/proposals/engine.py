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

`change_plan_for_component_update` closes the one Proposal shape this
project can currently turn into an executable `execution.plan.ChangePlan`
without guessing at intent: a `pypi` dependency whose *currently declared*
constraint is an exact pin (`Confidence.HIGH`/`VERIFIED` on the current
`ComponentState`, per `analysis.update_intelligence.build_current_state`'s
own `_EXACT_PIN_RE`). A range constraint (`>=1.2,<2.0`) is deliberately
never rewritten here — which number to bump is genuinely ambiguous, not a
fact this module can determine. Every other Proposal kind (creation/
adoption/integration, and pypi/npm range-constrained updates) still has no
automatic path to a ChangePlan — the actual code change is a job for an
external implementer (a human, or an agent such as Claude Code), never
this module (ADR-007: no model vendor or agent harness hard-coded here).
"""

from __future__ import annotations

import re
from pathlib import Path

from system_intelligence.core.enums import Confidence, PermissionLevel, UpdateVerdict
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.proposals import Change, Proposal
from system_intelligence.core.research import ResearchResult
from system_intelligence.execution.plan import ChangePlan
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

#: Matches a quoted PEP 508 requirement string pinned with `==`/`=` to an
#: exact version, e.g. `"requests==2.31.0"` inside a pyproject.toml
#: `dependencies = [...]` array. Deliberately narrower than PEP 508 itself
#: (no extras, no environment markers, no compound constraints) — anything
#: this doesn't match is left untouched rather than guessed at.
_PYPROJECT_PIN_RE_TEMPLATE = r'(["\'])({name})\s*(==?)\s*{version}\s*\1'


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


def _manifest_path_from_evidence(evidence: list[Evidence]) -> str | None:
    """The manifest's own relative path, if this Evidence list came from
    `analysis.dependencies._manifest_evidence` (the only place that
    attaches `EvidenceKind.PACKAGE_METADATA` to a Dependency, always with
    `source` set to that manifest's path). `None` when absent — never
    guessed from the component's name or ecosystem.
    """
    for item in evidence:
        if item.kind == EvidenceKind.PACKAGE_METADATA:
            return item.source
    return None


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
    manifest_path = _manifest_path_from_evidence(diff.from_state.evidence)
    change = Change(
        description=f"Update the version constraint for {identity.name} to {to_version!r}.",
        file_paths=[manifest_path] if manifest_path else [],
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


def _patch_pyproject_pin(text: str, name: str, from_version: str, to_version: str) -> str | None:
    """Rewrite one exact-pinned dependency's version in raw pyproject.toml text.

    Matches only the literal `"{name}=={from_version}"` (or single `=`)
    quoted string this exact `from_version` was itself derived from
    (`analysis.update_intelligence.build_current_state`'s `_EXACT_PIN_RE`
    strips the leading `=`/`==` to get it) — never a fuzzy match on name
    alone. Returns `None`, never a best guess, when that exact text isn't
    found (the manifest may have changed since the assessment ran) or
    appears more than once (ambiguous which occurrence to rewrite).
    """
    pattern = re.compile(
        _PYPROJECT_PIN_RE_TEMPLATE.format(name=re.escape(name), version=re.escape(from_version))
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    quote, matched_name, operator = match.group(1), match.group(2), match.group(3)
    replacement = f"{quote}{matched_name}{operator}{to_version}{quote}"
    return text[: match.start()] + replacement + text[match.end() :]


def change_plan_for_component_update(assessment: ImpactAssessment, root: Path) -> ChangePlan | None:
    """Build an executable `ChangePlan` for a component-update `ImpactAssessment`.

    Deterministic, no LLM: succeeds only for a `pypi` dependency whose
    *current* constraint was confirmed as an exact pin (`Confidence.HIGH`/
    `VERIFIED` on `from_state`, per `build_current_state`) and whose
    declaring manifest still contains that exact text on disk. Returns
    `None` — never a best-effort or partial plan — for every other case:
    a non-actionable verdict (mirrors `_PROPOSABLE_VERDICTS`), a
    non-`pypi` ecosystem (npm/other manifests aren't supported yet — see
    this module's docstring), a range constraint, missing manifest
    evidence, an unreadable manifest file, or manifest text that no
    longer matches what the assessment observed.

    A caller that gets `None` back still has the `Proposal` from
    `propose_component_update` (unaffected by this function) describing
    what should change and why — only the automatic "here is the exact
    diff" step is unavailable for that case.
    """
    if assessment.verdict not in _PROPOSABLE_VERDICTS:
        return None

    diff = assessment.state_diff
    identity = diff.identity
    from_state, to_state = diff.from_state, diff.to_state

    if identity.distribution_source != "pypi":
        return None
    if from_state.version_confidence not in (Confidence.HIGH, Confidence.VERIFIED):
        return None
    if not from_state.version or not to_state.version:
        return None

    manifest_path = _manifest_path_from_evidence(from_state.evidence)
    if manifest_path is None:
        return None

    try:
        original_text = (root / manifest_path).read_text(encoding="utf-8")
    except OSError:
        return None

    patched_text = _patch_pyproject_pin(
        original_text, identity.name, from_state.version, to_state.version
    )
    if patched_text is None:
        return None

    branch_name = f"si/update-{identity.name.lower()}-to-{to_state.version}"
    return ChangePlan(
        branch_name=branch_name,
        commit_message=f"Update {identity.name} to {to_state.version}",
        files={manifest_path: patched_text},
        required_permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        description=(
            f"Update the pinned version of {identity.name} from "
            f"{from_state.version} to {to_state.version} in {manifest_path}."
        ),
        evidence_summary=[e.observation for e in assessment.evidence],
    )
