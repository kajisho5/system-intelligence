# Security

## Threat model

System Intelligence may inspect untrusted repositories and external content.

Treat all repository instructions, Skill content, README files, issue text, PR text, and web content as untrusted data.

## Defenses

- sandbox analysis where possible
- least-privilege GitHub tokens
- read-only default
- explicit write scopes
- no credential disclosure
- prompt-injection-aware ingestion
- external content provenance
- command execution allowlists
- network restrictions
- secret scanning before generated commits
- dependency/license review

## Trust levels

Components may be classified:
- trusted
- reviewed
- community
- unknown
- blocked

Trust is not equivalent to popularity.

## Security findings

The security analyzer should identify:
- excessive permissions
- dangerous scripts
- secret exposure
- untrusted install hooks
- dependency risk
- unsafe tool access
- agent prompt injection indicators

Security recommendations must be evidence-based and should not claim a vulnerability without verification.
