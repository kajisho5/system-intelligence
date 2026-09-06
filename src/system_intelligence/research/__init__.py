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
- `mcp_registry.MCPRegistryResearchProvider`: search/fetch against the
  public official MCP Registry (registry.modelcontextprotocol.io). That
  registry's own `server.json` schema has no license/maintenance/
  popularity field at all, so every `ResearchResult` from it leaves those
  dimensions `Confidence.UNKNOWN` — never synthesized to look consistent
  with the GitHub provider.
- `scoring.rank_candidates`: ranks candidates by verifiable, non-popularity
  signals (license presence, recent activity, archived status). Star count
  is exposed for display only and never used to rank (ADR-009).
- `cache.ResearchCache`: a TTL'd, file-backed cache keyed by
  (provider, query).
- `update_provider.ComponentUpdateProvider`: a narrower Protocol for
  Component Update Intelligence — "what is the latest available state of
  *this* known identity?" rather than a free-text search. `providers/pypi.py`,
  `providers/npm.py`, and `providers/crates_io.py` implement it as pure
  ecosystem adapters.
- `vulnerability_provider.VulnerabilityProvider`: "does this specific,
  already-known version have any known vulnerabilities?" — a per-version
  lookup, distinct from the freshness question `ComponentUpdateProvider`
  answers. `providers/osv.py` implements it against OSV.dev, which covers
  pypi, npm, and crates.io from one ecosystem-agnostic API.

Not yet implemented: standards/specification lookups and general web
search — docs/06 lists these as later steps in the search order.
"""

from system_intelligence.research.cache import ResearchCache
from system_intelligence.research.github import GitHubResearchError, GitHubResearchProvider
from system_intelligence.research.mcp_registry import (
    MCPRegistryError,
    MCPRegistryResearchProvider,
)
from system_intelligence.research.provider import ResearchProvider
from system_intelligence.research.providers import (
    CratesIoUpdateError,
    CratesIoUpdateProvider,
    NpmUpdateError,
    NpmUpdateProvider,
    OSVLookupError,
    OSVVulnerabilityProvider,
    PyPIUpdateError,
    PyPIUpdateProvider,
)
from system_intelligence.research.scoring import (
    UNSCORABLE_DIMENSIONS,
    CandidateAssessment,
    assess_candidate,
    rank_candidates,
)
from system_intelligence.research.update_provider import ComponentUpdateProvider
from system_intelligence.research.vulnerability_provider import (
    VulnerabilityLookupError,
    VulnerabilityProvider,
)

__all__ = [
    "UNSCORABLE_DIMENSIONS",
    "CandidateAssessment",
    "ComponentUpdateProvider",
    "CratesIoUpdateError",
    "CratesIoUpdateProvider",
    "GitHubResearchError",
    "GitHubResearchProvider",
    "MCPRegistryError",
    "MCPRegistryResearchProvider",
    "NpmUpdateError",
    "NpmUpdateProvider",
    "OSVLookupError",
    "OSVVulnerabilityProvider",
    "PyPIUpdateError",
    "PyPIUpdateProvider",
    "ResearchCache",
    "ResearchProvider",
    "VulnerabilityLookupError",
    "VulnerabilityProvider",
    "assess_candidate",
    "rank_candidates",
]
