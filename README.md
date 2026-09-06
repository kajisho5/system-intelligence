# System Intelligence

A general-purpose AI system intelligence layer for discovering, understanding,
auditing, researching, designing, improving, and verifying software systems —
ordinary repositories, packages, services, Agents, Agent Skills, MCP servers,
and multi-repository ecosystems.

This is **not** a video-production tool. The AI Video Production OS project
is planned as a reference target used to validate the architecture, not a
source of core assumptions (see `docs/design/ARCHITECTURE_DECISIONS.md`,
ADR-001).

## Design philosophy

```
OBSERVE → UNDERSTAND → ANALYZE → RESEARCH → AUDIT → DESIGN
        → RECOMMEND → PROPOSE → EXECUTE WITH APPROVAL → VERIFY
```

- **Evidence-first.** Every finding, recommendation, and proposal traces back
  to `Evidence` with an explicit confidence level (`verified`, `high`,
  `medium`, `low`, `unknown`). An inferred relationship is never presented as
  a verified fact.
- **Deterministic before semantic.** Parsers, filesystem inspection, git
  metadata, and static analysis produce facts; LLM reasoning interprets
  evidence and proposes hypotheses, it does not manufacture facts.
- **Read-only by default.** Discovery, analysis, and research never write to
  a target. Local writes (branch/commit) and remote writes (pushing that
  branch, opening a Draft PR) each require their own explicit `Approval`
  record — approving one never authorizes the other; merge, close, delete,
  force-push, visibility, credential, and deployment operations are never
  triggered automatically (see `docs/design/docs/08-governance.md`).

## Status

Pre-alpha, but functional. Discovery (local paths and, read-only,
GitHub repositories), deterministic analysis, the Relationship graph,
external research, the recommendation/proposal engines, Component Update
Intelligence, human-approved local and remote execution (branch/commit,
and pushing it as a Draft PR), the static HTML report, and the
interactive Dashboard are all implemented and covered by tests — see
`docs/design/docs/16-roadmap.md` for the full roadmap and
[Commands](#commands) below for what `si` can do today. Not yet
implemented: a plugin loader for external Skills/Agents (the capability
registry is a static Python dict), and package-registry/Capability-Contract
adapters beyond PyPI/npm.

## Commands

Read-only unless noted. Every `<target>` below except `si execute`'s
(which writes a local branch/commit, so it only makes sense against a
real local checkout) accepts a local path or a GitHub repository
(`owner/repo`, or a `https://github.com/...` URL — shallow-cloned
read-only into a temp directory first):

| Command | What it does |
|---|---|
| `si inspect <target>` | Repository/Skill/CI/doc inventory |
| `si diagnose <target>` | Discovery + deterministic analysis → Findings |
| `si report <target>` | Static, offline-viewable HTML report |
| `si dashboard <target>` | Interactive "System Intelligence Console" (see below) |
| `si schema` | Export JSON Schema files for the canonical snapshot format (no target) |
| `si diff <from> <to>` | Diff two canonical snapshot directories |
| `si research <query>` | Search for existing solutions — `--provider github` (default) or `--provider mcp-registry` (network) |
| `si check-updates <target>` | Component Update Intelligence: current vs. available state (network); `--plan-out DIR` writes a ready-to-run `ChangePlan` for a pypi or npm exact-pin bump, no hand-written JSON needed |
| `si improve <target>` | Findings → ranked Recommendations |
| `si propose <problem>` | Adopt/integrate/create decision → a Proposal; `--target <path> --handoff-out FILE` exports a self-contained packet (Proposal + the `ChangePlan` file schema) for a human or an external implementer (e.g. Claude Code) to turn into an executable plan — SI itself never authors that diff |
| `si plan <intent-or-text>` | Preview which capabilities a request would run |
| `si execute <plan> <target>` | Apply a local `ChangePlan` (dry-run unless `--approve`); `--push --repo owner/repo` also pushes and opens a Draft PR, gated by its own separate Approval |
| `si verify <command>` | Run a test command and record pass/fail |
| `si doctor`, `si version` | Environment check, installed version |

`si execute`/`si verify`/`si research`/`si propose`/`si check-updates` all
accept `--record <snapshot-dir>` to attach their result to an existing
canonical snapshot so a later `si dashboard` can show it.

`si dashboard` renders 14 sections (Overview, Findings, Updates,
Recommendations, Proposals, Executions, Components, Capabilities,
Dependencies, Architecture Decisions, Changes, Research, Evidence,
Settings/Governance) from one or more snapshots as a single
dependency-free HTML file — `--compare-with <snapshot-dir>` populates
Changes, `--check-updates` populates Updates. Nothing it renders can
merge, delete, force-push, or write to a remote.

`si design` and `si watch` are registered as explicit placeholders (`si
--help` documents them; running them fails clearly rather than silently
doing nothing) — they are not implemented yet.

## Documentation

The architectural source of truth lives under [`docs/design/`](docs/design/):

- [`docs/design/DESIGN_PLAN.md`](docs/design/DESIGN_PLAN.md) — index and design principle
- [`docs/design/ARCHITECTURE_DECISIONS.md`](docs/design/ARCHITECTURE_DECISIONS.md) — ADRs
- [`docs/design/IMPLEMENTATION_BACKLOG.md`](docs/design/IMPLEMENTATION_BACKLOG.md) — backlog by epic
- [`docs/design/docs/`](docs/design/docs/) — product vision, requirements, architecture,
  domain model, analysis/research/improvement engines, governance,
  visualization, plugin/Skill system, GitHub integration, storage, CLI/UX,
  security, testing, roadmap, reference workflows, extension points, open
  questions, and definition of done.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

si doctor      # environment sanity check
si version
si --help      # lists the full planned command surface;
               # commands not yet implemented say so explicitly
```

## Development

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest
bandit -c pyproject.toml -r src
pip-audit
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the ground rules (evidence-first,
read-only by default, deterministic-first, no video-production assumptions in
core) before adding a new module.

## Safety

System Intelligence never merges a PR, closes a PR, deletes a branch or
repository, force-pushes, changes repository visibility, rotates
credentials, deploys, or publishes a release automatically. See
[`SECURITY.md`](SECURITY.md) and `docs/design/docs/08-governance.md`.

## License

[MIT](LICENSE)
