"""Recommendation engine (R7): rank Findings into `Recommendation` records.

Deliberately conservative: this does not invent information beyond what a
Finding already carries. `rationale` and `evidence` are the Finding's own
statement and evidence; only the objective, effort/risk estimate, and
priority ordering are derived here.

`recommend_from_impact` extends the same pattern to Component Update
Intelligence's `ImpactAssessment` — the last step of "Current State ->
Available State -> State Diff -> Impact -> Recommendation" the update
intelligence feature was designed around, closing that loop generically
for any component, not just Findings.
"""

from __future__ import annotations

from system_intelligence.core.enums import Confidence, PermissionLevel, Severity, UpdateVerdict
from system_intelligence.core.findings import Finding
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.recommendations import Recommendation

#: Rough effort sizing per finding category, based on what fixing it
#: typically requires. "unknown" for any category this table doesn't cover
#: — never guessed.
_EFFORT_BY_CATEGORY: dict[str, str] = {
    "documentation_gap": "small",
    "ci_health": "small",
    "test_gap": "medium",
    "unused_candidate": "small",
    "duplicated_capability": "medium",
    "circular_dependency": "large",
    "capability_gap": "medium",
    "invalid_requirements_file": "small",
}

_SEVERITY_WEIGHT: dict[Severity, int] = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

_CONFIDENCE_WEIGHT: dict[Confidence, int] = {
    Confidence.VERIFIED: 4,
    Confidence.HIGH: 3,
    Confidence.MEDIUM: 2,
    Confidence.LOW: 1,
    Confidence.UNKNOWN: 0,
}


def _priority_score(finding: Finding) -> int:
    return _SEVERITY_WEIGHT[finding.severity] * 10 + _CONFIDENCE_WEIGHT[finding.confidence]


def recommend_from_finding(finding: Finding) -> Recommendation:
    effort = _EFFORT_BY_CATEGORY.get(finding.category, "unknown")
    risk = "low" if effort in ("small", "unknown") else "medium"
    objective = finding.suggested_actions[0] if finding.suggested_actions else finding.statement
    expected_benefit = f"Resolves a {finding.severity.value}-severity {finding.category} finding."

    return Recommendation(
        objective=objective,
        rationale=finding.statement,
        evidence=list(finding.evidence),
        confidence=finding.confidence,
        estimated_effort=effort,
        risk=risk,
        expected_benefit=expected_benefit,
        required_approval_level=PermissionLevel.RECOMMEND,
    )


def generate_recommendations(findings: list[Finding]) -> list[Recommendation]:
    """Turn Findings into Recommendations, ordered by severity then confidence (R7)."""
    ranked_findings = sorted(findings, key=_priority_score, reverse=True)
    return [recommend_from_finding(f) for f in ranked_findings]


#: Only verdicts with something to act on produce a Recommendation.
#: NO_UPDATE_AVAILABLE and UNKNOWN are deliberately excluded — there is
#: nothing to recommend when nothing changed or nothing could be determined.
_UPDATE_RISK_BY_VERDICT: dict[UpdateVerdict, str] = {
    UpdateVerdict.UPDATE_RECOMMENDED: "low",
    UpdateVerdict.REVIEW_REQUIRED: "medium",
    UpdateVerdict.NOT_ADVISABLE: "high",
}


def recommend_from_impact(assessment: ImpactAssessment) -> Recommendation | None:
    """Turn a Component Update Intelligence `ImpactAssessment` into a Recommendation.

    Returns `None` for `NO_UPDATE_AVAILABLE`/`UNKNOWN` verdicts rather than
    a hollow "everything is fine" recommendation.
    """
    risk = _UPDATE_RISK_BY_VERDICT.get(assessment.verdict)
    if risk is None:
        return None

    diff = assessment.state_diff
    identity = diff.identity
    from_version = diff.from_state.version or "unknown"
    to_version = diff.to_state.version or "unknown"

    if assessment.verdict == UpdateVerdict.NOT_ADVISABLE:
        objective = f"Do not update {identity.name} to {to_version} without further review."
    else:
        objective = f"Update {identity.name} from {from_version} to {to_version}."

    rationale = assessment.verdict_rationale
    changelog_urls = [entry.url for entry in diff.to_state.changelog if entry.url]
    if changelog_urls:
        rationale = f"{rationale} Changelog: {', '.join(changelog_urls)}"

    return Recommendation(
        objective=objective,
        rationale=rationale,
        evidence=list(assessment.evidence),
        confidence=assessment.verdict_confidence,
        estimated_effort="small",
        risk=risk,
        expected_benefit=(
            f"Resolves an available update for {identity.name} "
            f"({identity.distribution_source or 'unknown source'})."
        ),
        required_approval_level=PermissionLevel.RECOMMEND,
    )


def generate_update_recommendations(assessments: list[ImpactAssessment]) -> list[Recommendation]:
    """Turn Update Intelligence assessments into Recommendations, skipping non-actionable ones."""
    recommendations = [recommend_from_impact(a) for a in assessments]
    return [r for r in recommendations if r is not None]
