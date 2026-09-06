"""Recommendation engine: rank findings into actionable Recommendation records.

Phase 6 scope (docs/design/docs/02-requirements.md, R7): rank by severity
and confidence. Ranking additionally by compatibility, effort, license, and
security (the rest of R7's dimensions) needs richer signals than a single
Finding carries and is left for a later phase.
"""

from system_intelligence.recommendations.engine import (
    generate_recommendations,
    recommend_from_finding,
)

__all__ = ["generate_recommendations", "recommend_from_finding"]
