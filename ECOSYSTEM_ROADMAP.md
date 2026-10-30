# Roadmap — system-intelligence

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **統制 (Governance)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR.

## Where it stands

v0.2.2, Python 3.11+. inspect, diagnose, report, watch, dashboard, check-updates, propose, execute, ... 60 test modules, CI on Ubuntu only.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| エコシステム監査 | partial | general-purpose auditor; does not read ecosystem.json ownership or capability contracts |

## Wiring

Used by the OS workflows (ecosystem-audit, dashboard), not by the agent.

## Steps

- [ ] **1. Capability-contract discovery** — run `<skill> contract --json` read-only, validate against the OS schema
  - Done when: artifacts-skill and ingest-skill schema problems appear as findings
- [ ] **2. Ownership-map analyzer** — read ecosystem.json owns; flag overlaps and unowned jobs
  - Done when: finds the publish / ffmpeg-skill platform-table overlap
- [ ] **3. `--read-only` flag** — refuses execute/improve; used by the OS audit
  - Done when: test
- [ ] **4. macOS / Windows CI**
  - Done when: CI green

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (42 tools, treated as complete). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
