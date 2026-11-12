# Roadmap — alpha-skill

Each step below is meant to be one pull request; tick it off by linking the PR.

## Steps

- [x] **1. Contract in the OS schema** — `alpha contract --json` ([#1](https://github.com/example/alpha-skill/pull/1))
  - Done when: the contract validates against the OS schema
- [x] **2. Batch mode** — many inputs in one run
  - Done when: a fixture batch of three inputs gives three outputs
- [ ] **3. Progress events** — JSON lines on stderr; reads beta-skill step 2's events and beta-skill step 9's ETA
  - Done when: a fixture run emits monotonic progress
- [ ] **4. Resume after a stop** — `alpha run --resume` continues from the last verified chunk
  - Done when: a run stopped half way finishes with one output

## Boundaries

Encoding belongs to beta-skill.
