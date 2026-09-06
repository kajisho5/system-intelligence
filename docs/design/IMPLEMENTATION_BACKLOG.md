# Implementation Backlog

Checkboxes below reflect the actual current implementation (verified
against source, not assumed from an earlier plan) — see the file/module
named on each `[x]` line for the actual code, not just the schema.

## Epic 1 — Repository foundation
- [x] create public repository
- [x] choose license — `LICENSE` (MIT)
- [x] configure Python project — `pyproject.toml`
- [x] configure lint/type/test tooling — ruff/mypy/pytest, all in `pyproject.toml`
- [x] add CI — `.github/workflows/ci.yml` (lint/typecheck/test matrix/security jobs; verified actually running and green via the Checks API — the classic commit-status API returns nothing for Actions-based CI, which is easy to mistake for "no CI configured")
- [x] add security scanning — `bandit`/`pip-audit`, wired into the CI `security` job
- [x] add contribution guide — `CONTRIBUTING.md`

## Epic 2 — Domain model
- [x] define JSON schemas — `reporting/schema.py::export_json_schemas`, `si schema [--out DIR]`; one `*.schema.json` per canonical snapshot file plus `dashboard_data`, guarded by a test that fails if a future `Snapshot` field has no matching schema entry
- [x] implement entities — `core/entities.py`
- [x] implement relationships — `core/relationships.py`, `analysis/relationships.py`
- [x] implement evidence — `core/evidence.py`
- [x] implement snapshots — `core/snapshot.py`

## Epic 3 — Discovery
- [x] filesystem scanner — `discovery/structure.py`
- [x] Git scanner — `discovery/git_metadata.py`
- [x] GitHub adapter — `discovery/github_target.py::clone_github_repository`; `owner/repo` shorthand or a `https://github.com/...` URL is shallow-cloned read-only (`git clone --depth 1`) into a temp directory, then resolved exactly like any local path (`discovery/target.py::resolve_target`), so every existing `si` command gained GitHub-target support with no per-command changes
- [x] Agent Skills detector — `discovery/skills.py`
- [ ] agent detector — no discovery code ever instantiates `core.entities.Agent`; nothing populates it from a scan
- [x] package detector — `discovery/structure.py`'s `PACKAGE_MANIFESTS`
- [x] CI detector — `discovery/ci_docs.py::detect_ci_jobs`
- [x] docs/ADR detector — `discovery/adr.py::detect_adrs`; matches the `ADR-<number>` filename convention (verified against `ai-video-production-os`'s `docs/adr/ADR-NNN-slug.md`), parses `Status:` when present, never fabricates `decided_at`; wired into `Snapshot.adrs` and the Dashboard's new "Architecture Decisions" section

## Epic 4 — Analysis
- [x] dependency graph — `analysis/dependencies.py` + `analysis/relationships.py` (DEPENDS_ON, now Component-level, not just Repository-level)
- [x] architecture heuristics — `analysis/architecture.py` (AST-based circular-import detection)
- [x] capability extraction — `analysis/capabilities.py`
- [x] unused candidate analysis — `analysis/unused.py`
- [x] duplication detection — `analysis/capabilities.py::detect_duplicate_capabilities`
- [ ] gap detection — needs a declared requirements/desired-capabilities input this phase does not have (see `analysis/__init__.py`'s own docstring)
- [x] documentation audit — `analysis/documentation.py`
- [x] test/CI audit — `analysis/ci_quality.py`

## Epic 5 — Research
- [x] GitHub search adapter — `research/github.py`
- [x] source provenance — `Evidence` on every `ResearchResult`
- [x] candidate scoring — `research/scoring.py`
- [x] license extraction — `research/github.py`
- [x] maintenance signals — `research/github.py` (push recency, archived, stargazers — informational only, ADR-009)
- [x] research cache — `research/cache.py`

(A second provider, `research/mcp_registry.py` against the official MCP
Registry, was added beyond this epic's original PyPI/npm-agnostic scope.)

- [x] known-vulnerability lookup — `research/vulnerability_provider.py::VulnerabilityProvider` (a per-version "does this have any known advisories?" Protocol, distinct from `ComponentUpdateProvider`'s freshness question) implemented by `research/providers/osv.py::OSVVulnerabilityProvider` against OSV.dev, which covers both pypi and npm from one API. Wired into `analysis/update_intelligence.py::check_dependency_updates`/`ImpactAssessment` as informational `current_version_advisories`/`available_version_advisories` — never changes `UpdateVerdict` (a vulnerable current version does not by itself prove capability/dependency/interface impact was evaluated). `si check-updates --check-vulnerabilities` / `si dashboard --check-updates --check-vulnerabilities` (opt-in: one extra network request per resolved version). Live-validated against the real OSV.dev API (`lodash@4.17.20` correctly returns 5 real GHSA advisories)

## Epic 6 — Reporting
- [x] static HTML generator — `reporting/html.py`
- [x] graph visualization — `reporting/dashboard_html.py`'s capability provider SVG graph subtab
- [x] dashboard JSON export — `reporting/dashboard_data.py::DashboardData`/`build_dashboard_data`; also the documented external consumer boundary (`docs/design/docs/12-storage-and-state.md`)
- [x] snapshot diff — `reporting/diff.py`

## Epic 7 — Improvement
- [x] recommendation engine — `recommendations/engine.py`
- [x] proposal schema — `core/proposals.py`
- [x]/[ ] new Skill proposal / new Agent proposal / new software proposal (partial) — `proposals/engine.py::propose_solution`'s optional `target_kind: ComponentKind` (`si propose --target-kind skill|agent|mcp_server|...`) now shapes `test_strategy`/`documentation_requirements` to how that kind is actually verified in practice (a Skill's contract is its own SKILL.md, an Agent is verified by running scenarios, an MCP server by its tool/resource schema — see `_TEST_STRATEGY_BY_KIND`). Not yet done: per-kind `interfaces`/`capabilities` *shape* (docs/07's "new Skill"/"new Agent" templates go further than test/doc wording, and the Agent case still has no discovery-populated `Agent` instances to draw from — Epic 3's agent detector doesn't exist yet)
- [x] implementation plan generator — `execution/plan.py::ChangePlan` (local branch/commit plan; the remote Draft PR step is `execution/github_pr.py`, see Epic 8)
- [x] Proposal -> ChangePlan (deterministic case only) — `proposals/engine.py::change_plan_for_component_update`; a `pypi` or `npm` dependency whose current constraint is confirmed as an exact pin (`analysis/update_intelligence.py::_EXACT_PIN_RE`, which also recognizes npm's bare-version convention while explicitly rejecting its `x`/`X`/`*` wildcard segments) can be turned into an executable `ChangePlan` with no human/LLM authoring a diff by hand (`si check-updates --plan-out DIR` -> `si execute <file> <target> --approve`)
- [x] Proposal -> external-implementer handoff (every other case) — `execution/handoff.py::build_handoff_packet` (`si propose --target <path> --handoff-out <file>`); a self-contained JSON packet (Proposal + target + the exact `ChangePlan` file schema an implementer must hand back) for creation/adoption/integration Proposals and any range-constrained update, which still have no automatic path to a ChangePlan and never will inside this module — deciding the actual diff remains a job for a human or an external implementer (e.g. Claude Code), never guessed here (ADR-007). See `docs/design/docs/21-external-implementer-handoff.md`

## Epic 8 — Governance
- [x] policy schema — `core/enums.py` (`PermissionLevel`, `FORBIDDEN_BY_DEFAULT_ACTIONS`), `policy/engine.py`
- [x] approval records — `core/governance.py::Approval`
- [x] audit log — `policy/engine.py::audit_log_entry` builds an `AuditLogEntry` per policy decision; `Snapshot.audit_log`/`audit_log.json`; wired into `si execute --record`
- [x] GitHub write scopes — `execution/github_pr.py::push_branch`/`open_draft_pull_request`, gated by `policy.evaluate` under `create_draft_pr` (a distinct action/Approval from the local `create_local_branch_and_commit` step); token via the `GITHUB_TOKEN` environment variable, never a CLI argument
- [x] Draft PR adapter — `execution/github_pr.py::open_draft_pr_for_plan`; pushes the branch `local_git.apply_plan` already created and opens it as a Draft PR via the GitHub REST API. `si execute --push --repo owner/repo`. Live-validated: `push_branch` against a real throwaway branch on this repo (pushed, verified via the GitHub API, branch left for manual cleanup since even a scratch `git push --delete` was blocked by this session's own safety classifier); the REST "open PR" call itself could not be validated live from this sandbox (raw HTTP to `api.github.com` is blocked here), so it's covered by mocked-HTTP unit tests only, matching every other GitHub-API-touching adapter in this codebase

## Epic 9 — Verification
- [x] test runner adapter — `verification/engine.py::run_verification`
- [x] post-change scan — `si diagnose --out` before and after a change, feeding the next two items
- [x] before/after comparison — `si diff <before> <after>` (`reporting/diff.py`)
- [x] regression detection — `si verify --before-snapshot <dir> --after-snapshot <dir>` populates `Verification.regressions_found` from that diff's added findings

## Epic 10 — Reference ecosystem
- [ ] AI Video Production OS fixture — used only as an external, read-only validation target (cloned locally, never committed as a fixture in this repo)
- [ ] multi-repo manifest — one Snapshot is one target repository scan; SI does not aggregate multiple Snapshots into an ecosystem-wide manifest (see `docs/design/docs/12-storage-and-state.md`, "What this boundary does not cover")
- [ ] dashboard integration — the *SI* Dashboard is done (Epic 6); an external ecosystem-level dashboard consuming SI's boundary is a separate, other-repository concern
- [ ] public demo
