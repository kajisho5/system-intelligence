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

## ADR-015 — Roadmap drift: steps against merged pull requests, exact references, report only

`si roadmap-drift <ecosystem.json>` compares every repository's roadmap with the pull requests that carried it out. A roadmap is the AI Video Production OS's `ECOSYSTEM_ROADMAP.md`: numbered checkbox steps (`- [x] **6. Title**`), one pull request each, ticked by linking it; a step's block is its own line plus the indented lines under it; fenced code (closed only by the same fence character, at least as long) is never a step nor part of a block, and an indented fence leaves its step open. Sources: local checkouts (`--checkouts DIR`, one directory per repository) with saved pull-request lists (`--pulls DIR`, `<repo>.json` in the GitHub REST shape), so the tests and CI need no network; or `--github`, the same files from each default branch and the closed pull requests through the REST API (GET only, `GITHUB_TOKEN` when set, pages requested by number, never by following `Link` headers). Three kinds of drift, each with its repository, its step and the evidence (file and line, pull-request number and URL, the exact text matched): (a) a ticked step whose block links no pull request, with the merged pull requests whose titles name the step attached; (b) an unticked step whose pull request merged: one the step links (a repository of the ecosystem, same owner), or one of the repository's own whose title names the step (`roadmap step 8`, `ECOSYSTEM_ROADMAP.md step 5`, and ranges or lists only after the plural `steps`). `docs:` pull requests do not count: their step numbers are the roadmap text they wrote, not the work. A step that says in its own words that it is still open (`Partly done`, `Status: partial`, `Skill side`, `Building block`, `left unchecked`, a `Progress (` or `Open:` line, ...) is not drift; its merged pull requests are listed as a note instead. With no merged pull request, a line of the repository's SKILL.md or CHANGELOG naming the step, or a code span from the step's own line (identifier-like, used nowhere else in the roadmap) found literally in them, is reported as a *candidate*, never as certain. (c) A step naming another repository's step that its roadmap lacks (`qc-skill step 9`, `dubbing-skill's step 9`, `subtitle-skill steps 5-6`). Repository names are the map's own, matched exactly after case folding, never by similarity (ADR-002), so a short form such as "qc step 9" is not read; a `planned` repository or one with no roadmap has no steps, and one whose roadmap could not be read is noted, not reported. Whatever could not be read is listed per repository with the reason, so a gap is never mistaken for no drift. The report (`system-intelligence/roadmap-drift@1`) carries no ids or timestamps and is sorted by repository, step and kind, so the same inputs give byte-identical JSON (`--json`, `--out`); the default output is a Markdown table. Nothing is written to any repository: the one file written is the `--out` report, refused inside `--checkouts`; the command runs under `--read-only` (ADR-013). The analyzer knows no file names: the CLI passes the OS's `ECOSYSTEM_ROADMAP.md` and `SKILL.md` / `skills/<repo>/SKILL.md` / `CHANGELOG.md` from `integrations/ai_video_os/` (ADR-001).

## ADR-016 — Field readiness: stated in the contract or the CI, otherwise unknown

`si diagnose --field --ownership-map ecosystem.json (--checkouts DIR | --github) [--contracts DIR]` audits every repository the map lists instead of scanning one target: one row per skill, one cell per column, each `yes`, `no` or `unknown` with its evidence (the file, the JSON Pointer or the CI key and line, the text matched). The columns are the caller's; the CLI passes the AI Video Production OS's from `integrations/ai_video_os/` (the 2026-11-05 field review: resume after a stop, progress events, error classes, long-file tests, hardware encoder use, alpha output, loudness output), each naming the contract keys and the CI pattern that state it. Two sources only. The skill's Capability Contract, as a saved `<tool> contract --json` document (`--contracts DIR`, `<repo>.json`): a skill's contract is produced by running it, which this audit never does (ADR-011). A bare key counts only at the contract's top level and a key with a `/` is one exact path (`errors/classes`, `proxy/hardware`), so a key deeper in the document, such as a colour parameter's `alpha`, is never read; `true` or a non-empty value says yes, `false`, an empty value or `"none"` says no, and `null` says nothing. The CI config (`.github/workflows/*.yml` and `*.yaml`): job ids, job and step names and step `run` commands (block scalars followed by indentation, their shell comments skipped; comments, `env`, action inputs under `with` and every other key are not read), matched as whole words, also inside snake_case, kebab-case and CamelCase identifiers (`test_resume_after_...`, `LongFormTests`); `--no-progress`, `NO_PROGRESS` and `cancel-in-progress` are not progress events. CI only ever says yes. A cell is `yes` when its sources say only yes, `no` when they say only no, and `unknown` otherwise: a capability neither source states is `unknown`, never `no`, and one stated both ways is `unknown` with both statements kept. Nothing is inferred from source code, READMEs, test files or names, and a `planned` component, which has no repository, is all `unknown`. The report (`system-intelligence/field-readiness@1`: `--json`, or `--out DIR` for `DIR/field-readiness.json`, refused inside `--checkouts`) is deterministic; the default output is a Markdown table followed by the evidence behind every cell that has some. It runs under `--read-only` (ADR-013). `--field` takes no target and none of the target scan's contract options; its source options are `si roadmap-drift`'s (ADR-015).
