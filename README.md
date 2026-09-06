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
adapters beyond PyPI/npm/crates.io/Go (Maven/Gradle, RubyGems).

## Commands

Read-only unless noted. Every `<target>` below except `si execute`'s
(which writes a local branch/commit, so it only makes sense against a
real local checkout) accepts a local path or a GitHub repository
(`owner/repo`, or a `https://github.com/...` URL — shallow-cloned
read-only into a temp directory first):

| Command | What it does |
|---|---|
| `si inspect <target>` | Repository/Skill/Agent (`.claude/agents/*.md`)/CI/doc inventory |
| `si diagnose <target>` | Discovery + deterministic analysis → Findings |
| `si report <target>` | Static, offline-viewable HTML report |
| `si dashboard <target>` | Interactive "System Intelligence Console" (see below) |
| `si schema` | Export JSON Schema files for the canonical snapshot format (no target) |
| `si diff <from> <to>` | Diff two canonical snapshot directories |
| `si research <query>` | Search for existing solutions — `--provider github` (default) or `--provider mcp-registry` (network) |
| `si check-updates <target>` | Component Update Intelligence: current vs. available state for pypi/npm/cargo/go dependencies (network); `--check-vulnerabilities` also looks up known vulnerabilities (OSV.dev) for each resolved version; `--plan-out DIR` writes a ready-to-run `ChangePlan` for a pypi, npm, or go exact-pin bump, no hand-written JSON needed |
| `si improve <target>` | Findings → ranked Recommendations |
| `si propose <problem>` | Adopt/integrate/create decision → a Proposal; `--target-kind skill\|agent\|mcp_server\|...` shapes test/documentation guidance and the declared interface to that kind; `--target <path> --handoff-out FILE` exports a self-contained packet (Proposal + the `ChangePlan` file schema) for a human or an external implementer (e.g. Claude Code) to turn into an executable plan — SI itself never authors that diff |
| `si plan <intent-or-text>` | Preview which capabilities a request would run |
| `si execute <plan> <target>` | Apply a local `ChangePlan` (dry-run unless `--approve`); `--push --repo owner/repo` also pushes and opens a Draft PR, gated by its own separate Approval |
| `si verify <command>` | Run a test command and record pass/fail |
| `si watch <target>` | Drift since the last `si watch` run for this target, via a self-managed `--state-dir` history (no daemon — repeat it yourself, or from cron/CI) |
| `si doctor`, `si version` | Environment check, installed version |

`si execute`/`si verify`/`si research`/`si propose`/`si check-updates` all
accept `--record <snapshot-dir>` to attach their result to an existing
canonical snapshot so a later `si dashboard` can show it.

`si diagnose`/`si report`/`si dashboard` also check for a `.si/requirements.json`
declaring capabilities the target requires by name (`{"capabilities":
[{"name": "pdf export"}]}`) — opt-in only; a target with no such file gets
zero `capability_gap` findings, never an inferred one.

`si dashboard` renders 14 sections (Overview, Findings, Updates,
Recommendations, Proposals, Executions, Components, Capabilities,
Dependencies, Architecture Decisions, Changes, Research, Evidence,
Settings/Governance) from one or more snapshots as a single
dependency-free HTML file — `--compare-with <snapshot-dir>` populates
Changes, `--check-updates` populates Updates. Nothing it renders can
merge, delete, force-push, or write to a remote.

`si design` is registered as an explicit placeholder (`si --help`
documents it; running it fails clearly rather than silently doing
nothing) — it is not implemented yet.

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

## Quickstart

Point it at any repository — your own, or a local clone — no configuration
required beyond the install above. Run these from inside that repository
(the examples below all target it as `.`):

```bash
cd your-repo
si diagnose .                              # read-only: discovery + findings, nothing written
si report . --out ./si-out                 # same, plus a static HTML report at ./si-out/report.html
si check-updates . --plan-out ./si-plans   # network: pypi/npm/cargo/go dependency freshness;
                                            # writes a ready-to-run ChangePlan for any exact-pin bump found
```

A generated `ChangePlan` needs its own permission level (`CREATE_BRANCH_OR_
DRAFT_PR`), above the default ceiling — `si execute --approve` alone is
denied without a matching `Approval` record. `target` in the approval must
match the `<target>` you pass to `si execute` **exactly** (as a literal
string, not a resolved path) — keep both as `.`:

```bash
cat > approval.json <<'EOF'
{"actor": "human:you", "scope": "repository", "action": "create_local_branch_and_commit",
 "target": ".", "permission_level": 4}
EOF
si execute ./si-plans/<file>.json . --approve --approval-file approval.json
```

This only ever creates a local branch and commit — nothing above touches a
remote. Pushing that branch and opening a Draft PR is a separate step,
`si execute ... --push --repo owner/repo`, gated by its own separate
Approval — see [Safety](#safety).

### GitHub authentication (optional, but recommended)

`si research`, `si propose --research-query`, and `si execute --push` all
call the GitHub API. Without a token they still work, but as unauthenticated
requests capped at 60/hour by GitHub — easy to hit during normal use.
`si execute --push` requires a token outright (to actually push a branch
and open a Draft PR).

```bash
export GITHUB_TOKEN=ghp_...   # a fine-grained PAT; public-repo read access is enough
                               # for research/propose. execute --push additionally
                               # pushes a branch and opens a PR, so it needs
                               # "Contents: write" and "Pull requests: write"
                               # on the target repo.
```

Only ever set this as an environment variable — no `si` command accepts a
token as a CLI argument, so it never ends up in shell history or a process
list (`ps`). This is a deliberate, load-bearing design choice, not an
oversight: keep it that way in any change that touches token handling.

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
