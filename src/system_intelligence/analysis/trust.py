"""Component.trust_level derivation from research signals already on record.

`TrustLevel` (docs/design/docs/14-security.md: "trust is not equivalent to
popularity") has existed on `Component` since Phase 1 but nothing has ever
set it beyond its `UNKNOWN` default. This module closes that gap narrowly:
it only ever promotes a Component's `trust_level` when a `ResearchResult`
already present in the same Snapshot's `research` list can be tied to that
Component by an exact, unambiguous identifier match — never from
`stargazer_count`, search relevance, or any single popularity signal
(ADR-009), and never from a fuzzy name/description similarity.

Absence of a match, or a match with insufficient signal, leaves
`trust_level` exactly as it was (`UNKNOWN` by default) — that is a report
of "no evidence found", never a claim that the component is untrustworthy.

Deliberately NOT done here: promoting to `TrustLevel.REVIEWED`/`TRUSTED`
from a human `Approval`. `Approval.target` is a free-form action/target
string (a proposal id, a branch name, ...), not a verified reference to a
`Component.id` — asserting that link would be a guess, not a fact, so this
module leaves that promotion path unimplemented rather than fabricate the
mapping. See docs/design's Update Intelligence research report for this
limitation.
"""

from __future__ import annotations

from system_intelligence.core.entities import Component
from system_intelligence.core.enums import Confidence, TrustLevel
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.research import ResearchResult
from system_intelligence.research.scoring import assess_candidate


def _identifiers(result: ResearchResult) -> set[str]:
    """Exact identifiers a Component's own `name` may legitimately match.

    `result.identifier` is compared verbatim, plus — for an "owner/repo"
    style identifier (e.g. "psf/markdown-it-py") — its final path segment,
    since a locally discovered Component's `name` is its own short name
    ("markdown-it-py"), not the owner-qualified form. Both are exact,
    deterministic string comparisons; neither is a fuzzy match.
    """
    identifiers = {result.identifier}
    if "/" in result.identifier:
        identifiers.add(result.identifier.rsplit("/", 1)[-1])
    return identifiers


def infer_trust_levels(
    components: list[Component], research: list[ResearchResult]
) -> list[Component]:
    """Derive `Component.trust_level` from same-Snapshot research signals only.

    A Component already at a non-`UNKNOWN` `trust_level` is left untouched —
    this function only ever fills in an absence, never overrides an
    existing value (including a manually-set `BLOCKED`).

    Mapping (deliberately conservative):
    - No `ResearchResult` identifies this Component: `UNKNOWN` (unchanged).
    - A matching result exists but has no recorded license, or is marked
      archived: `UNKNOWN` (unchanged) — an absent or negative signal is not
      evidence of active review, only the absence of the positive signal
      that would justify `COMMUNITY`.
    - A matching result has a recorded license and is not archived
      (`research.scoring.assess_candidate`): `TrustLevel.COMMUNITY`.
    - `TrustLevel.REVIEWED`/`TrustLevel.TRUSTED` are never assigned here —
      see the module docstring.
    """
    by_identifier: dict[str, ResearchResult] = {}
    for result in research:
        for identifier in _identifiers(result):
            by_identifier.setdefault(identifier, result)

    updated: list[Component] = []
    for component in components:
        if component.trust_level != TrustLevel.UNKNOWN:
            updated.append(component)
            continue
        match = by_identifier.get(component.name)
        if match is None:
            updated.append(component)
            continue

        assessment = assess_candidate(match)
        if not assessment.has_license or assessment.is_archived is True:
            updated.append(component)
            continue

        evidence = Evidence(
            kind=EvidenceKind.EXTERNAL_SOURCE,
            source=match.source,
            observation=(
                f"A research result identified as {match.identifier!r} — matching this "
                "component's name — has a recorded license and is not marked archived."
            ),
            confidence=Confidence.MEDIUM,
        )
        updated.append(
            component.model_copy(
                update={
                    "trust_level": TrustLevel.COMMUNITY,
                    "evidence": [*component.evidence, evidence],
                }
            )
        )
    return updated
