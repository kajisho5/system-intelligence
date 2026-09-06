"""Recommendation engine (R7): rank Findings into `Recommendation` records.

Deliberately conservative: this does not invent information beyond what a
Finding already carries. `rationale` and `evidence` are the Finding's own
statement and evidence; only the objective, effort/risk estimate, and
priority ordering are derived here.
"""

from __future__ import annotations

from system_intelligence.core.enums import Confidence, PermissionLevel, Severity
from system_intelligence.core.findings import Finding
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
