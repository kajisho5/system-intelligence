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
  proposals.json
  research.json
  approvals.json
  verification.json
  executions.json
```

(`proposals.json` and `executions.json` were added once the Proposal and
human-approved local execution phases landed — `Snapshot._FILES` in
`core/snapshot.py` is the authoritative list if this ever drifts again.)

## Versioning

Snapshots should be immutable by ID.

Use:
- target fingerprint
- scan ID
- timestamp
- tool version

`Snapshot.tool_version` (`core/snapshot.py`) is this compatibility marker
today. There is no second, independently-versioned export schema — see
"External consumer boundary" below.

## Incremental analysis

Re-analyze only changed portions when safe.

Always support full re-scan to recover from stale state.

## External consumer boundary

A consumer outside System Intelligence's own Python process — a
different dashboard, CI tooling, another agent, or an ecosystem-level
control plane such as AI Video Production OS's own (a **reference
consumer, never a hard dependency** of SI) — should read one of these,
never SI's internal Python classes:

1. **The canonical snapshot directory** above (`Snapshot.write_to_directory`
   / `read_from_directory`), for the raw per-category JSON files, or
2. **`reporting.dashboard_data.DashboardData`** (`build_dashboard_data`,
   also what `si dashboard`'s embedded JSON and `dashboard_html.py` render),
   for the same state already aggregated with the counts, research
   rankings, and evidence cross-references a UI would otherwise have to
   re-derive itself.

Both read the same `Snapshot` state; neither is a second, competing
source of truth, and no separate "export" schema/version/CLI command
exists beyond these — `Snapshot.tool_version` (surfaced on
`DashboardData.overview.tool_version` too) is the one compatibility
marker for both.

### Distinguishing what kind of claim something is

A consumer must not flatten these into one generic "status" — each is a
structurally distinct list in both representations above, corresponding
to a specific stage of `OBSERVE → ... → VERIFY` (docs/design/DESIGN_PLAN.md):

| List | Stage | Meaning |
|---|---|---|
| `components`, `capabilities`, `relationships`, `dependencies` | OBSERVE/UNDERSTAND | What was discovered, with its own `evidence` |
| `findings` | ANALYZE/AUDIT | An interpretation of evidence, with its own `confidence` |
| `research` | RESEARCH | An external candidate SI looked up, not a fact about the target |
| `recommendations` | RECOMMEND | A suggested objective — not yet a concrete plan |
| `proposals` | PROPOSE | A concrete adopt/integrate/create decision — not yet approved |
| `approvals` | (governance) | A human's explicit sign-off — never inferred from a Proposal's existence |
| `executions` | EXECUTE | What actually ran locally (branch/commit) — never inferred from an Approval's existence |
| `verification`/`verifications` | VERIFY | An actual test run's pass/fail — never inferred from an Execution's existence |

A Proposal existing is not an Approval. An Approval existing is not an
Execution. An Execution existing is not a Verification. Each transition
needs its own record with its own evidence; a consumer must not treat one
stage's presence as proof of the next.

### Component subtypes, read generically

`components` holds `Component` and its subtypes (`Repository`, `Skill`,
`Agent`, `Software`, `MCPServer`, `Tool`, `Workflow`, `Document`) as one
polymorphic list, discriminated by each entry's own `kind` field. Reading
the JSON directly (any language) gets every field of whatever concrete
object was present. Reconstructing the exact Python subclass from generic
`Snapshot.model_validate_json`/`DashboardData.model_validate_json` does
not — only `Snapshot.read_from_directory` dispatches on `kind` for that;
this is a Python-SDK nicety, not a contract requirement other consumers
need.

### What this boundary does not cover

- **Cross-repository aggregation.** One Snapshot is one target repository
  scan; a relationship between Skills that live in *different*
  repositories cannot be established from a single Snapshot, and SI does
  not infer one. A caller needing an ecosystem-wide view combines
  multiple Snapshots itself; SI does not do this today.
- **Federation or a persistent registry.** No network service, no
  cross-instance discovery.
- **Automatic execution.** Nothing above ever merges, approves, installs,
  or applies a Proposal on its own — see `08-governance.md`.
