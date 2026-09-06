# Analysis Engine

## Pipeline

```text
Discover
  -> Normalize
  -> Parse
  -> Index
  -> Build Graph
  -> Detect
  -> Correlate
  -> Diagnose
```

## Detector families

### Repository
- structure
- language
- package manager
- license
- README quality
- contribution docs
- release metadata

### Agent
- agent instructions
- tool declarations
- model/provider dependencies
- permissions
- memory
- evaluation
- lifecycle

### Skill
- SKILL.md
- metadata
- scripts
- references
- triggers
- capability declarations
- portability

### Architecture
- module boundaries
- dependency direction
- circular dependencies
- layering violations
- duplicated responsibilities
- undocumented architecture decisions

### Quality
- tests
- CI
- linting
- type checking
- coverage where available
- error handling

### Lifecycle
- last modification
- release activity
- dependency freshness
- stale branches
- open PRs/issues

### Documentation
- README completeness
- setup instructions
- examples
- architecture docs
- API/interface docs
- consistency

## Unused detection

Never equate 'not referenced' with 'unused'.

Classify:
- `unreferenced`
- `inactive`
- `potentially_unused`
- `verified_unused`

Verification may require runtime telemetry or explicit user confirmation.

## Gap detection

Compare:
- declared requirements
- desired capabilities
- actual capabilities
- interfaces
- workflows
- test coverage

Output `capability_gap` with evidence and confidence.
