"""External research provider abstraction.

Phase 5 scope (see docs/design/docs/16-roadmap.md, docs/design/docs/06-
research-engine.md, and docs/design/IMPLEMENTATION_BACKLOG.md Epic 5):

- `provider.ResearchProvider`: the search/fetch Protocol every provider
  implements — the improvement engine (later phases) depends on this, not
  on a specific provider (ADR-007).
- `github.GitHubResearchProvider`: search/fetch against the public GitHub
  REST API. Every field not directly present in the API response stays
  `Confidence.UNKNOWN` (the anti-hallucination rule) rather than being
  guessed.
- `scoring.rank_candidates`: ranks candidates by verifiable, non-popularity
  signals (license presence, recent activity, archived status). Star count
  is exposed for display only and never used to rank (ADR-009).
- `cache.ResearchCache`: a TTL'd, file-backed cache keyed by
  (provider, query).

Not yet implemented: package-registry providers (PyPI/npm), standards/
specification lookups, and general web search — docs/06 lists these as
later steps in the search order.
"""

from system_intelligence.research.cache import ResearchCache
from system_intelligence.research.github import GitHubResearchError, GitHubResearchProvider
from system_intelligence.research.provider import ResearchProvider
from system_intelligence.research.scoring import (
    UNSCORABLE_DIMENSIONS,
    CandidateAssessment,
    assess_candidate,
    rank_candidates,
)

__all__ = [
    "UNSCORABLE_DIMENSIONS",
    "CandidateAssessment",
    "GitHubResearchError",
    "GitHubResearchProvider",
    "ResearchCache",
    "ResearchProvider",
    "assess_candidate",
    "rank_candidates",
]
