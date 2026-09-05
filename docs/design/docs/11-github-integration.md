# GitHub Integration

## Read operations

- repository metadata
- branches
- commits
- files
- README
- releases
- issues
- pull requests
- Actions/CI
- contributors where permitted

## Write operations

Only through explicit policy.

Preferred first write:
- create branch
- create files/commits
- open Draft PR

## PR lifecycle

System Intelligence may recommend:
- fix
- split
- consolidate
- update docs
- add tests
- close as duplicate

But execution of lifecycle-changing actions requires approval.

## Cross-repository analysis

Support a manifest:

```yaml
targets:
  - owner/repo-a
  - owner/repo-b
relationships:
  - from: repo-a
    to: repo-b
    type: depends_on
```

## GitHub research

When searching for alternatives, record exact repository URLs/IDs and timestamped evidence.
