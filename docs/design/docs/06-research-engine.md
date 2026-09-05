# External Research Engine

## Goal

Find existing solutions before recommending new work.

## Search order

1. Existing components in target ecosystem
2. Official project documentation
3. GitHub repositories
4. Package registries
5. Standards/specifications
6. Broader web research

## Candidate scoring

Never use popularity alone.

Suggested weighted dimensions:
- functional fit
- architectural fit
- maintenance
- release health
- license compatibility
- security posture
- documentation
- test maturity
- dependency footprint
- community signals
- migration cost

Scores must remain explainable.

## Research result

```text
Candidate
  -> source
  -> evidence
  -> compatibility
  -> risks
  -> license
  -> maintenance
  -> recommendation
```

## Research cache

Cache search results with:
- query
- provider
- timestamp
- result identifiers
- extracted facts
- TTL

## Anti-hallucination rule

If the external source cannot verify a claim, label it unknown.

Do not invent repository activity, licenses, APIs, compatibility, or security properties.
