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
