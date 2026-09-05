# Domain Model

## Core entities

- Target
- Repository
- Component
- Software
- Agent
- Skill
- MCPServer
- Tool
- Capability
- Interface
- Dependency
- Workflow
- TestSuite
- Document
- ADR
- CIJob
- PullRequest
- Finding
- Evidence
- Recommendation
- Proposal
- Change
- Approval
- Verification
- ResearchResult
- Snapshot

## Evidence model

Every finding should reference one or more Evidence objects.

```json
{
  "id": "evidence-123",
  "kind": "file",
  "source": "README.md",
  "locator": "README.md#installation",
  "observation": "Package declares capability X",
  "confidence": 1.0,
  "observed_at": "timestamp"
}
```

## Confidence

Use explicit levels:
- `verified`
- `high`
- `medium`
- `low`
- `unknown`

Never silently upgrade an inferred relationship to verified.

## Capability model

```json
{
  "id": "capability.video-review",
  "name": "video-review",
  "providers": ["component-id"],
  "status": "available|partial|missing|deprecated|unknown",
  "evidence": [],
  "confidence": "verified"
}
```

## Finding model

A finding must include:
- severity
- category
- statement
- evidence
- confidence
- affected entities
- suggested actions

## Recommendation model

A recommendation must include:
- objective
- rationale
- alternatives considered
- evidence
- estimated effort
- risk
- expected benefit
- approval requirement
