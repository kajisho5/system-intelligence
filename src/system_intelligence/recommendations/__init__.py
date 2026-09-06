"""Recommendation engine: rank findings into actionable Recommendation records.

Phase 6 scope (docs/design/docs/02-requirements.md, R7): rank by severity
and confidence. Ranking additionally by compatibility, effort, license, and
security (the rest of R7's dimensions) needs richer signals than a single
Finding carries and is left for a later phase.

`generate_update_recommendations`/`recommend_from_impact` extend the same
pattern to Component Update Intelligence's `ImpactAssessment` results.
"""

from system_intelligence.recommendations.engine import (
    generate_recommendations,
    generate_update_recommendations,
    recommend_from_finding,
    recommend_from_impact,
)

__all__ = [
    "generate_recommendations",
    "generate_update_recommendations",
    "recommend_from_finding",
    "recommend_from_impact",
]
