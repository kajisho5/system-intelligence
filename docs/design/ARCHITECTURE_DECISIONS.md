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

## ADR-013 — `--read-only` stops at findings

`si --read-only` (or `SI_READ_ONLY=1`, for a script or workflow that cannot change the command line) is the mode an automated audit runs in. It refines ADR-004 from "read-only by default" to "read-only guaranteed": discovery, analysis, research and reporting run unchanged (`inspect`, `diagnose`, `report`, `dashboard`, `watch`, `diff`, `schema`, `research`, `plan`, `check-updates` without its improvement options, `doctor`, `version`), and the improvement and execution stages are refused before they start, with the reason on stderr and exit status 1: `improve` (findings into an improvement plan), `propose` (proposals and implementer handoff packets), `execute` (branches, commits, pushes), `verify` (runs a command inside the target checkout), and `check-updates --propose`/`--plan-out` (update proposals, and ChangePlans for `execute`). The refusal is decided by the command or option named, never by what a run would turn out to do, so it holds before any argument is read. Writing the run's own results (`--out`, `--state-dir`, `--record`) is allowed: that is the audit's output, not a change to the target. `--contract-command` stays allowed: ADR-011 already confines it to an operator-named argv in an empty temporary directory, never the target checkout.

## ADR-014 — One behaviour on Linux, macOS and Windows

CI runs the test suite on ubuntu, macos and windows runners (Python 3.11 and 3.12), so a platform difference is a test failure, not a user report. Rules the code keeps: every text read and write names `encoding="utf-8"`, and so does every subprocess decoded as text (git prints UTF-8; Windows' locale is cp1252), with `errors="replace"` for output System Intelligence does not control; CI sets `PYTHONWARNDEFAULTENCODING=1` and pytest turns `EncodingWarning` into an error, so a missing `encoding=` fails on every OS, not only Windows, and `PYTHONUTF8` is deliberately not set. Files System Intelligence writes (snapshots, reports, ChangePlans, and the files `execute` applies) are written with `newline="\n"`, so they are byte-identical across OSes and a plan never rewrites a target's line endings. Paths stored in a snapshot (evidence sources, component paths, ids derived from them) are relative and `/`-separated (`as_posix()`), so ids and diffs do not depend on the OS that produced them. `.gitattributes` keeps text files LF in every checkout. A test is skipped on an OS only when it cannot apply there, with the reason in the skip and here; there is one: creating a symlink on Windows needs SeCreateSymbolicLinkPrivilege (an elevated account or Developer Mode). The symlink-escape tests use a `make_symlink` fixture that skips only when Windows actually refuses, and raises on any other OS; GitHub's Windows runners grant the privilege, so CI runs those tests on all three OSes.
