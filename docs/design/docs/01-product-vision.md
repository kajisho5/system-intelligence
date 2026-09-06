# Product Vision

## Problem

As software projects accumulate agents, skills, packages, services, repositories, workflows, documentation, CI pipelines, and external dependencies, the system becomes difficult to understand as a whole.

The user needs an intelligence layer that can answer:

1. What is this?
2. What does it contain?
3. What depends on what?
4. What capabilities exist?
5. What is missing?
6. What is duplicated?
7. What appears unused?
8. What is unhealthy or drifting?
9. What external solutions exist?
10. Should something be adopted, changed, or newly created?
11. What should happen next?
12. Did the change actually improve the system?

## Scope

### In scope
- single repository analysis
- multi-repository analysis
- software architecture
- Agent analysis
- Skill analysis
- MCP/tool integration analysis
- dependency analysis
- documentation analysis
- CI/PR analysis
- capability inventory
- duplication and gap detection
- external research
- improvement planning
- proposal generation
- HTML reports
- dashboard data
- human approval workflow
- optional Draft PR creation
- verification and re-diagnosis

### Out of scope for v1
- autonomous merging
- autonomous production deployment
- credential harvesting
- arbitrary destructive changes
- claiming code quality from superficial heuristics
- treating GitHub stars as a quality metric
- assuming a particular LLM provider

## Product modes

- `inspect` — read-only inventory
- `diagnose` — structured health assessment
- `research` — external solution discovery
- `design` — architecture/design proposals
- `improve` — generate an improvement plan
- `propose` — create concrete change proposals
- `execute` — perform only authorized changes
- `verify` — validate changes and compare before/after state
- `watch` — repeat diagnosis and detect drift
