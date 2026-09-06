# Contributing to System Intelligence

Thank you for your interest in contributing.

## Ground rules

- **Evidence-first**: every finding, recommendation, or proposal produced by
  the tool must trace back to `Evidence`. Do not add code paths that assert a
  fact without a supporting observation.
- **Read-only by default**: new capabilities must not perform remote writes
  or destructive operations unless gated behind the policy/approval layer
  described in `docs/design/docs/08-governance.md`.
- **Deterministic first**: prefer parsers, filesystem inspection, git
  metadata, and static analysis over LLM inference. LLM reasoning should
  interpret evidence, not manufacture it.
- **No video-production assumptions in core**: the core packages
  (`core`, `discovery`, `analysis`, `research`, `intelligence`,
  `recommendations`, `proposals`, `policy`, `execution`, `verification`,
  `reporting`) must remain generic. Domain-specific integrations belong in
  `integrations/`.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

Run the same checks CI runs:

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest
bandit -c pyproject.toml -r src
pip-audit
```

## Design documentation

The architectural source of truth lives under `docs/design/`. Read the
relevant document before adding a new module, entity, or capability. If your
change diverges from the design, update the design docs in the same PR and
explain why in the PR description.

## Commit and PR conventions

- Keep commits focused; one logical change per commit.
- Describe *why* a change was made, not just what changed.
- Add or update tests for any behavioral change.
- Update `docs/design/` when architecture decisions change.
