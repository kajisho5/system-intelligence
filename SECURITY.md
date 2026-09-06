# Security Policy

System Intelligence inspects third-party repositories, Agent Skills, issue
text, pull request text, and external research content. All such content is
**untrusted** and must be treated as data, never as instructions.

## Reporting a vulnerability

Please open a private security advisory on GitHub
(`Security` tab → `Report a vulnerability`) rather than a public issue.

## Threat model summary

See `docs/design/docs/14-security.md` for the full threat model. In short:

- Repository contents, README/issue/PR text, Skill instructions, and web
  research results are untrusted input.
- The tool defaults to read-only (`docs/design/docs/08-governance.md`,
  permission level 0-3). Remote writes and destructive actions require
  explicit policy authorization (level 4+).
- Merge, close, delete, force-push, visibility, credential, and deployment
  operations are forbidden by default and are never triggered automatically.
