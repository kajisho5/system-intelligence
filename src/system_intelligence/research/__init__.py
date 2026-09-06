"""External research provider abstraction.

Not yet implemented. Planned scope: a provider-neutral `search`/`fetch`/
`extract_facts` interface (docs/design/docs/18-extension-points.md,
"Research provider SDK"), a GitHub search adapter first, and a research
cache with TTL. Candidate scoring must never rank by popularity alone
(ADR-009) and must record `unknown` rather than invent unverifiable facts
(docs/design/docs/06-research-engine.md, "Anti-hallucination rule").
"""
