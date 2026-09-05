# Extension Points

Future adapters may include:

- GitLab
- Bitbucket
- local Git
- package registries
- Docker/OCI
- Kubernetes
- cloud infrastructure
- MCP registries
- Agent-to-Agent protocols
- observability systems
- security scanners
- test/evaluation frameworks

The core data model must remain provider-neutral.

## Analyzer SDK

An analyzer should declare:

```text
id
version
supported_targets
inputs
outputs
permissions
run()
evidence_schema
```

## Research provider SDK

```text
search(query)
fetch(identifier)
extract_facts(document)
```

## Execution adapter SDK

```text
plan()
preview()
apply()
verify()
rollback()
```

No adapter may bypass the central policy engine.
