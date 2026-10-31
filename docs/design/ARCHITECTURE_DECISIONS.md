# Initial Architecture Decisions

## ADR-001 — Generic target model

System Intelligence must not encode AI Video Production OS concepts into the core. The video OS is a reference target.

## ADR-002 — Evidence-first intelligence

LLM reasoning must operate over evidence produced by deterministic or source-backed collectors whenever possible.

## ADR-003 — Canonical snapshot

Use a versioned machine-readable snapshot as the canonical state consumed by reports and dashboards.

## ADR-004 — Read-only default

All discovery/analysis/research operations default to read-only.

## ADR-005 — Human approval boundary

Remote write and destructive actions require explicit policy authorization.

## ADR-006 — Modular analyzers

Analysis capabilities must be independently testable and replaceable.

## ADR-007 — Provider agnostic

Do not hard-code a single model vendor, agent harness, or Git hosting provider in the core.

## ADR-008 — Research before creation

A new component should be proposed only after checking existing local and permitted external solutions, unless the user explicitly asks to design something new from scratch.

## ADR-009 — No popularity-only ranking

Stars/downloads/activity are signals, not proof of quality or compatibility.

## ADR-010 — Unused is a confidence classification

Static non-reference is not sufficient to declare a component unused.

## ADR-011 — Capability contracts: static first, commands only on operator opt-in

A component's Capability Contract (its `<tool> contract --json` output) is validated against a JSON Schema and every problem becomes a Finding. Sources, in order of preference: a checked-in `.si/contracts.json` in the target (paths only, confined to the target root, read automatically), an operator-supplied `--contract-file`, and an operator-supplied `--contract-command`. A file in the target can never make System Intelligence run anything. A command runs only when the operator names it, as an argv list with no shell, stdin closed, a timeout, a minimal environment (no credentials) and an empty temporary working directory, never the target checkout. Validation uses a small built-in validator for the keyword subset the schema needs, which refuses any other keyword rather than skipping it; no `jsonschema` dependency. The analyzer knows no schema of its own: the CLI's default is the AI Video Production OS schema, bundled byte for byte in `integrations/ai_video_os/` with its provenance, and `--contract-schema` replaces it (ADR-001).
