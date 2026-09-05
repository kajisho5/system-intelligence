# Governance and Approval

## Permission levels

| Level | Action |
|---|---|
| 0 | Observe |
| 1 | Analyze |
| 2 | Recommend |
| 3 | Generate local artifacts |
| 4 | Create branch / Draft PR |
| 5 | Modify remote repository |
| 6 | Release / deploy |

Default maximum: Level 3.

Level 4+ requires explicit approval or a preconfigured policy.

## Forbidden by default

- merge PR
- close PR
- delete branch
- delete repository
- force push
- change repository visibility
- rotate credentials
- change production infrastructure
- publish release
- modify permissions

## Approval object

```json
{
  "actor": "human",
  "scope": "repository",
  "action": "create_draft_pr",
  "target": "repo",
  "approved_at": "timestamp",
  "expires_at": "timestamp"
}
```

## Audit log

Every action records:
- actor
- intent
- policy
- target
- evidence
- action
- result
- timestamp
- correlation ID
