"""System Intelligence.

A general-purpose AI system intelligence layer for discovering, understanding,
auditing, researching, designing, improving, and verifying software systems.

See docs/design/ for the architectural source of truth. Package layout
mirrors docs/design/docs/03-architecture.md's architectural layers:

- core            domain model (entities, evidence, findings, snapshot)
- discovery       target/structure discovery adapters
- analysis        deterministic and semantic analyzers
- research        external solution research providers
- intelligence    orchestration over discovery/analysis/research results
- recommendations recommendation engine
- proposals       creation/adoption/refactor proposal generation
- policy          approval and permission-level enforcement
- execution       execution adapters (branch/commit/PR, gated by policy)
- verification    before/after verification of executed changes
- reporting       HTML/JSON report and dashboard export
- integrations    provider-specific adapters (GitHub, etc.) and reference
                   targets (e.g. AI Video Production OS); never imported by
                   core/discovery/analysis/research/intelligence
- cli             command-line interface
"""

__version__ = "0.2.1"
