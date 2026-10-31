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

## ADR-012 — Ownership maps: declared jobs, exact names, files only

An ownership map gives each job, named in plain words, to the components that own it; the reference shape is the AI Video Production OS `ecosystem.json` (`components[].{repo or name, owns, status}`). A map may also bind jobs to the capability ids that realize them (`job_capabilities`), because job names and capability ids are different vocabularies and System Intelligence never bridges them by similarity (ADR-002). Sources are files only, never commands: the target's own `.si/ownership.json` (itself an ownership document; its `maps` list names more, by path, confined to the target root) and the operator's `--ownership-map`. Findings: `ownership_overlap` (one job, two or more owners), `ownership_provider_overlap` (a job owned by one component while another component's Capability Contract provides a capability bound to it; the provider is matched to an owner by the contract's identities, including `skill.package`), `ownership_unowned_job` (every owner has an inactive status, or a bound job no map owns), `ownership_map_unavailable` and `ownership_map_invalid` (JSON Pointer). Jobs and owners are compared after NFKC normalization, trimming and case folding, nothing looser. The analyzer knows no ecosystem's statuses: the CLI passes the OS's `planned` from `integrations/ai_video_os/` (ADR-001). Every `provides` entry of a contract that validates becomes a `Capability` (provider: the target repository; status from `lifecycle`; confidence `high`, since it is declared, not run). These join gap detection and the relationship graph but not duplicate detection: two contracts naming one capability is the ecosystem registry's collision question.
