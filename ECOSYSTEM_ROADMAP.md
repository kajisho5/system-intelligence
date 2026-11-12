# Roadmap — system-intelligence

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **統制 (Governance)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR.

## Where it stands

v0.4.0, Python 3.11+. inspect, diagnose, report, watch, dashboard, check-updates, propose, execute, ... 60 test modules, CI on Ubuntu, macOS and Windows.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| エコシステム監査 | partial | general-purpose auditor; reads capability contracts (#121) and ecosystem.json ownership (#122); `--read-only` audit mode (ADR-013); roadmap drift check (#129, ADR-015); field-readiness audit (#130, ADR-016) |

## Wiring

Used by the OS workflows (ecosystem-audit, dashboard), not by the agent.

## Steps

- [x] **1. Capability-contract discovery** — run `<skill> contract --json` read-only, validate against the OS schema ([#121](https://github.com/kajisho5/system-intelligence/pull/121), ADR-011)
  - Done when: artifacts-skill and ingest-skill schema problems appear as findings
- [x] **2. Ownership-map analyzer** — read ecosystem.json owns; flag overlaps and unowned jobs ([#122](https://github.com/kajisho5/system-intelligence/pull/122), ADR-012)
  - Done when: finds the publish / ffmpeg-skill platform-table overlap
- [x] **3. `--read-only` flag** — refuses execute/improve; used by the OS audit ([#123](https://github.com/kajisho5/system-intelligence/pull/123), ADR-013)
  - Done when: test
- [x] **4. macOS / Windows CI** ([#123](https://github.com/kajisho5/system-intelligence/pull/123), ADR-014)
  - Done when: CI green
- [x] **5. Field-readiness audit** — per skill, from contracts and CI: resume after a stop, progress events, error classes, long-file tests, hardware encoder use, alpha and loudness outputs; written as a table for the Control Room. Field review 2026-11-05 (Velisa ROADMAP, third round) ([#130](https://github.com/kajisho5/system-intelligence/pull/130), ADR-016)
  - なぜ要るか：現場で使えるスキルとまだ危ないスキルが、一覧で分かる
  - Done when: `si diagnose --field` lists every skill in `ecosystem.json` with each column filled or `unknown`
  - Done (ADR-016): `si diagnose --field --ownership-map ecosystem.json` from `--checkouts` or `--github`, with each skill's saved contract (`--contracts DIR`, `<repo>.json`); one row per component of `ecosystem.json`, seven columns, each cell `yes` / `no` / `unknown` with its evidence (contract file and JSON Pointer, or CI file, key and line, and the text matched). A contract key counts only at the top level or as one exact path; CI counts job ids, step names and `run` commands; what neither states, or states both ways, is `unknown`. A Markdown table, or a deterministic JSON report (`--json`, `--out DIR`). `tests/fixtures/field_readiness` covers yes, no, unknown and a contradiction
- [x] **6. Roadmap drift check** — `ECOSYSTEM_ROADMAP.md` steps against merged pull requests: a ticked step without a PR link, an unticked step whose PR merged, and a step that names another repository's step that does not exist ([#129](https://github.com/kajisho5/system-intelligence/pull/129), ADR-015)
  - なぜ要るか：多数のリポジトリの進捗表が実態とずれていくのを止められる
  - Done when: a fixture roadmap with each kind of drift gives three findings
  - Done (ADR-015): `si roadmap-drift <ecosystem.json>` from local checkouts (`--checkouts`, `--pulls`: no network) or `--github`; a Markdown table, or a deterministic JSON report (`--json`, `--out`) where each finding has its repository, step and evidence (file and line, PR number and URL, matched text). An unticked step that SKILL.md / CHANGELOG already describe as shipped is a candidate only; a step that says it is still open (`Partly done`, `Status: partial`, ...) is a note, not drift. `tests/fixtures/roadmap_drift` gives exactly three findings (a: alpha-skill step 2, b: step 3, c: beta-skill step 9)
- [ ] **7. The OS contract-shape check, called from Velisa CI** — checking every component's capability contract against the OS shape is this repository's role, and Velisa CI calls it ([Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/blob/main/docs/ecosystem/DECISION_LOG.md)). Contract checking exists (step 1, `--contract-schema`, default the bundled OS schema), but Velisa's workflows call only `si watch` (`scripts/ecosystem-audit.sh`) and `si diagnose .` (`dashboard.yml`). Read the schema from Velisa's `registry/` (the reference definition) instead of a bundled copy, or fail when the copy differs, and give Velisa one command to run over `ecosystem.json`. Side effects, signatures and isolation tests stay skillpact's; runtime version gates stay video-production-agent's
  - Done when: a Velisa CI job runs the check over every component with a contract and fails on a contract that breaks the schema
- [ ] **8. Implemented commands no workflow runs yet** — `si roadmap-drift` (step 6) and `si diagnose --field --ownership-map` (step 5) work, but no Velisa workflow calls them. Both are candidates for the Velisa workflow (the weekly ecosystem audit or the dashboard), read-only
  - Done when: the Velisa workflow runs both, or a decision there says why not

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (42 tools, treated as complete). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
