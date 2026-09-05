# Requirements

## Functional requirements

### R1 — Target discovery
The system must discover a target from:
- local path
- Git repository
- GitHub repository
- repository list
- explicit manifest
- ecosystem manifest

### R2 — Structure discovery
Detect, where present:
- source code
- packages
- services
- agents
- skills
- MCP servers
- tools
- workflows
- tests
- docs
- ADRs
- CI
- deployment configuration

### R3 — Capability mapping
Map declared and inferred capabilities to providers/components.

Every capability record must include provenance and confidence.

### R4 — Relationship graph
Represent:
- uses
- provides
- depends_on
- implements
- duplicates
- conflicts_with
- supersedes
- referenced_by
- tested_by
- documented_by
- deployed_by

### R5 — Health diagnosis
Detect:
- unused candidates
- orphaned components
- duplicated capabilities
- missing capabilities
- dependency risks
- documentation gaps
- test gaps
- architecture drift
- stale components
- inconsistent contracts
- CI health issues

### R6 — External research
Search permitted sources for:
- existing solutions
- alternatives
- standards
- libraries
- Skills
- Agents
- reference architectures

### R7 — Recommendation
Rank recommendations by:
- impact
- confidence
- compatibility
- effort
- risk
- maintenance
- license
- security

### R8 — Creation proposal
If no suitable solution exists, propose:
- component type
- name
- purpose
- capabilities
- interfaces
- dependencies
- test strategy
- documentation requirements
- repository strategy

### R9 — Change execution
Only execute actions permitted by policy.

### R10 — Verification
After approved changes:
- run configured tests
- re-scan
- compare state
- report regressions
- update evidence

### R11 — Visualization
Generate:
- overview HTML
- architecture graph
- dependency graph
- capability map
- findings
- recommendations
- change history

### R12 — Explainability
Every important finding must be traceable to evidence.

## Non-functional requirements

- provider agnostic
- deterministic analyzers where possible
- idempotent scans
- incremental scans
- offline-capable local analysis where possible
- machine-readable state
- human-readable reports
- secure by default
- extensible detector architecture
- testable without a live LLM
