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
  a target. Remote writes (branch/commit/Draft PR) and any destructive
  operation require an explicit `Approval` record; merge, close, delete,
  force-push, visibility, credential, and deployment operations are never
  triggered automatically (see `docs/design/docs/08-governance.md`).

## Status

Pre-alpha. Phase 1 (repository foundation and base domain schemas) is in
progress — see `docs/design/docs/16-roadmap.md` for the full roadmap and
`docs/design/IMPLEMENTATION_BACKLOG.md` for the current backlog.

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
