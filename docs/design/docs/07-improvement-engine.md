# Improvement Engine

## Decision tree

```text
Need detected
    |
    v
Does target already provide it?
    | yes
    v
Can an existing component be improved?
    | no
    v
Search external ecosystem
    |
    +--> compatible solution --> adoption proposal
    |
    +--> partial solution --> integration proposal
    |
    +--> no suitable solution --> creation proposal
```

## Creation proposals

System Intelligence can propose:
- new Skill
- new Agent
- new package
- new service
- new repository
- new capability contract
- architecture refactor
- documentation artifact
- test/evaluation suite

## Proposal must contain

- problem
- evidence
- why existing solutions are insufficient
- proposed component
- interface
- capability contract
- dependencies
- implementation stages
- tests
- security implications
- documentation
- rollback strategy

## Execution

Default:
- proposal only

Optional:
- generate files
- create branch
- create Draft PR

Never default to merge, release, deployment, deletion, or permission escalation.
