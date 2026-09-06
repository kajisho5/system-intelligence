"""Candidate comparison for external research results.

docs/design/docs/06-research-engine.md lists eleven scoring dimensions
(functional fit, architectural fit, maintenance, release health, license
compatibility, security posture, documentation, test maturity, dependency
footprint, community signals, migration cost). A GitHub search/detail
response only ever gives us direct signal for a handful of these
(license presence, recent push activity, archived status); the rest stay
`unknown_dimensions` rather than being silently defaulted to a score of
zero or omitted — the assessment says plainly what it could not determine.

ADR-009: never rank by popularity alone. `stargazer_count` is exposed for
display but is never part of the sort key in `rank_candidates`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from system_intelligence.core.enums import Confidence
from system_intelligence.core.research import ResearchResult

_ACTIVE_WITHIN_DAYS = 365

#: Dimensions docs/06 lists that no GitHub search/detail response can answer.
UNSCORABLE_DIMENSIONS = (
    "functional_fit",
    "architectural_fit",
    "security_posture",
    "documentation_quality",
    "test_maturity",
    "dependency_footprint",
    "migration_cost",
)


@dataclass(frozen=True)
class CandidateAssessment:
    result: ResearchResult
    has_license: bool
    license_confidence: Confidence
    is_recently_active: bool | None  # None: no pushed_at signal to judge from
    is_archived: bool | None
    stargazer_count: int | None  # informational only — never used to rank
    unknown_dimensions: tuple[str, ...] = field(default_factory=lambda: UNSCORABLE_DIMENSIONS)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value == "True"


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _is_recently_active(pushed_at_iso: str | None) -> bool | None:
    if not pushed_at_iso:
        return None
    try:
        pushed_at = datetime.fromisoformat(pushed_at_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(UTC) - pushed_at).days <= _ACTIVE_WITHIN_DAYS


def assess_candidate(result: ResearchResult) -> CandidateAssessment:
    signals = result.maintenance_signals
    return CandidateAssessment(
        result=result,
        has_license=result.license is not None,
        license_confidence=result.license_confidence,
        is_recently_active=_is_recently_active(signals.get("last_push_at")),
        is_archived=_parse_bool(signals.get("archived")),
        stargazer_count=_parse_int(signals.get("stargazers_count")),
    )


def rank_candidates(results: list[ResearchResult]) -> list[CandidateAssessment]:
    """Order candidates by verifiable, non-popularity signals only.

    Sort key (descending): has a license, is recently active (unknown ranks
    between active and inactive), is not archived. Tied candidates keep
    their relative input order (Python's sort is stable).
    """
    assessments = [assess_candidate(r) for r in results]
    active_rank = {True: 2, None: 1, False: 0}

    def sort_key(a: CandidateAssessment) -> tuple[int, int, int]:
        return (
            1 if a.has_license else 0,
            active_rank[a.is_recently_active],
            0 if a.is_archived else 1,
        )

    return sorted(assessments, key=sort_key, reverse=True)
