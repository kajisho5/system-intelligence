# Research Baseline — September 2026

This design is informed by a current web/GitHub review.

## Confirmed ecosystem facts

### Agent Skills

The public Agent Skills specification is an important interoperability target. The official `agentskills/agentskills` repository describes Skills as portable folders centered on `SKILL.md`, with optional scripts, references, and assets, and uses progressive disclosure for discovery/activation/execution.

GitHub also documents support for Agent Skills across Copilot surfaces and supports project/personal skill locations.

Implication:
- System Intelligence should recognize standard Skill layouts.
- It must not assume every repository uses the standard.
- It should support custom detectors and adapters.

### Agent sprawl / governance

Current industry discussion increasingly treats agent sprawl, visibility, duplication, permissions, auditability, and governance as system-level problems.

Implication:
- Inventory, dependency mapping, capability overlap, trust, permissions, and audit should be first-class concepts.
- Governance must remain separate from ordinary static analysis.

### Existing adjacent projects

The ecosystem already contains:
- Skill registries and catalogs
- Agent governance projects
- Architecture-analysis tools
- Agent orchestration frameworks
- Repository auditing Skills
- Agent Skills specifications

Implication:
- System Intelligence must not reinvent every specialized analyzer.
- Its differentiator is the cross-domain intelligence/control layer: discover -> understand -> analyze -> research -> recommend -> propose -> verify.

## Important non-claim

This research does NOT establish that System Intelligence is the first or only project of its kind. The implementation must maintain a competitor/adjacent-project registry and continuously re-evaluate the landscape.

## Research adapters

External research should be provider-based:
- GitHub
- package registries
- official documentation
- standards/specifications
- optionally general web search

Every external finding should record:
- source
- timestamp
- evidence
- confidence
- license when relevant
- maintenance signals when relevant
- compatibility assessment
