"""Provider- and target-specific integrations.

`ai_video_os` holds the AI Video Production OS reference integration
(docs/design/docs/17-reference-workflows.md): its bundled Capability
Contract schema, the CLI's default for contract validation (ADR-011), and
the `ecosystem.json` statuses that mean a component does not exist yet
(ADR-012). Still planned: a read-heavy GitHub adapter
(docs/design/docs/11-github-integration.md). Nothing here may be imported
by core, discovery, analysis, research, intelligence, recommendations,
proposals, policy, execution, verification, or reporting — dependencies
point inward only; the CLI is the one place that wires an integration in.
"""
