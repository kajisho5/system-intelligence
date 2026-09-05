# Reference Workflows

## Workflow A — Diagnose a repository

1. discover target
2. scan structure
3. build graph
4. run relevant analyzers
5. produce findings
6. research important gaps
7. produce recommendations
8. generate HTML report

## Workflow B — Diagnose a Skill

1. detect `SKILL.md`
2. parse metadata
3. inspect scripts/references/assets
4. map capabilities
5. inspect tests
6. inspect consumers
7. check portability
8. report potentially unused/duplicated/gapped capabilities

## Workflow C — Diagnose an Agent

1. inspect agent definition
2. inspect tools/skills
3. map permissions
4. inspect tests/evals
5. inspect failure handling
6. inspect dependencies
7. report architecture and governance findings

## Workflow D — Missing capability

1. requirement discovered
2. capability absent/partial
3. search local components
4. search external ecosystem
5. compare candidates
6. if no fit, propose new component
7. estimate scope/risk
8. ask for approval

## Workflow E — Approved improvement

1. load approved proposal
2. create branch
3. implement
4. run tests
5. update docs
6. generate Draft PR
7. collect CI results
8. re-scan
9. produce before/after verification
10. stop before merge unless separately approved
