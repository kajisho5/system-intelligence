# System Intelligence — Large-Scale Design Plan

> A general-purpose AI system intelligence layer for discovering, understanding, auditing, researching, designing, improving, and verifying software systems.

This document is the implementation blueprint for `system-intelligence`.

The project is intentionally broader than an Agent/Skill manager. It should be able to inspect a single repository, a Skill, an Agent, an ordinary software project, a service, or a multi-repository ecosystem.

## Design principle

**Observe first. Recommend second. Change only with explicit authority.**

System Intelligence must distinguish:
- verified facts
- inferred relationships
- recommendations
- proposed changes
- approved changes
- executed changes
- verification results

It must never silently turn an inference into a fact, and it must never perform destructive GitHub operations merely because an improvement appears obvious.

## Initial reference implementation

The AI Video Production OS will be the first serious reference environment, not a hard-coded dependency. The core must remain generic.

## External standards and ecosystem assumptions

Agent Skills should follow the open Agent Skills format where applicable. The current public specification uses a `SKILL.md` file with metadata and instructions, with optional scripts/references/assets. GitHub documents support for project and personal skills as well. These standards should be treated as integration targets rather than assumptions that every target project uses them.

See `docs/00-research-baseline.md` for the current external landscape that informed this plan.

## Documents

- `docs/01-product-vision.md` — product definition and scope
- `docs/02-requirements.md` — functional and non-functional requirements
- `docs/03-architecture.md` — target architecture
- `docs/04-domain-model.md` — entities and relationships
- `docs/05-analysis-engine.md` — discovery and analysis pipeline
- `docs/06-research-engine.md` — external research and solution discovery
- `docs/07-improvement-engine.md` — recommendation and creation proposals
- `docs/08-governance.md` — permissions, approvals, audit trail
- `docs/09-visualization.md` — HTML/report/dashboard design
- `docs/10-plugin-skill-system.md` — internal/external capability model
- `docs/11-github-integration.md` — GitHub operations and safety boundaries
- `docs/12-storage-and-state.md` — canonical state model
- `docs/13-cli-and-ux.md` — CLI and natural-language UX
- `docs/14-security.md` — security and trust model
- `docs/15-testing-and-evaluation.md` — test strategy
- `docs/16-roadmap.md` — phased implementation roadmap
- `docs/17-reference-workflows.md` — end-to-end workflows
- `docs/18-extension-points.md` — future extensibility
- `docs/19-open-questions.md` — unresolved design decisions
- `docs/20-definition-of-done.md` — release gates

## North-star interaction

A user should eventually be able to say:

> Diagnose this project.

or:

> Make this system better.

System Intelligence should determine what it needs to inspect, research, and evaluate, then return a structured diagnosis and an actionable improvement plan.

It should also be able to say:

> The required capability does not appear to exist in this system. I searched the permitted external sources and found no sufficiently compatible solution. I recommend creating a new component because …

The creation of a new Skill, Agent, package, service, or repository remains an explicit proposal unless the user has granted an execution policy that permits it.
