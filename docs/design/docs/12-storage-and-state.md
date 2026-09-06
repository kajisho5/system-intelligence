# Storage and Canonical State

## Principle

One canonical machine-readable snapshot.

Recommended initial format:
- JSON for machine interchange
- Markdown/HTML for human presentation

## Snapshot

```text
snapshot/
  manifest.json
  components.json
  capabilities.json
  relationships.json
  findings.json
  recommendations.json
  research.json
  approvals.json
  verification.json
```

## Versioning

Snapshots should be immutable by ID.

Use:
- target fingerprint
- scan ID
- timestamp
- tool version

## Incremental analysis

Re-analyze only changed portions when safe.

Always support full re-scan to recover from stale state.
