"""Claude Code subagent (`.claude/agents/**/*.md`) detection.

Closes a documented gap (Epic 3 of `docs/design/IMPLEMENTATION_BACKLOG.md`):
no discovery code ever instantiated `core.entities.Agent`. "Agent" as a
category fragments across ecosystems with no single shared convention
(LangChain/CrewAI/AutoGen/OpenAI Assistants configs, ...), each with its
own schema — detecting all of them would mean guessing at formats this
project has no verified contract for, which ADR-002/ADR-007 forbid. This
module deliberately detects exactly **one** explicit, self-declared
convention instead: Claude Code's own `.claude/agents/<name>.md`
subagent format, whose frontmatter shape (`---`-delimited, `name`/
`description` required) is the same shape `discovery/skills.py` already
parses for `SKILL.md` (see `discovery/frontmatter.py`).

Every field is recorded only when the frontmatter itself states it —
`model_provider` is set to the raw value of the frontmatter's own
`model:` field (e.g. `"sonnet"`, `"opus"`, `"inherit"`) when present,
never inferred or normalized into a vendor name, and `tool_names`/
`permissions` are only ever populated from an explicit `tools:`/
`disallowedTools:` field respectively (both documented Claude Code
subagent frontmatter fields, verified against
code.claude.com/docs/en/sub-agents's own "Supported frontmatter fields"
table), parsed via `discovery.frontmatter.split_tool_list` rather than a
naive comma-split — the same docs describe an `Agent(worker, researcher)`
specifier form whose parenthesized argument list itself contains a
comma, which a plain `.split(",")` would incorrectly break into two
tokens. A file with no frontmatter, or frontmatter missing `name`/
`description`, is still reported (mirroring `detect_skills`'s own "found
but not standard format" handling) rather than silently dropped.
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import Agent
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id
from system_intelligence.discovery.frontmatter import parse_frontmatter, split_tool_list
from system_intelligence.discovery.paths import is_excluded

_REQUIRED_FRONTMATTER_FIELDS = ("name", "description")
_AGENTS_DIR = Path(".claude") / "agents"


def detect_agents(root: Path) -> list[Agent]:
    """Find `.claude/agents/**/*.md` files under `root` and parse them, if present.

    Only under the exact `.claude/agents/` root (not `**/agents/` at
    arbitrary depth elsewhere in the tree, like `detect_skills`'s
    `SKILL.md` search has no root constraint at all) — Claude Code itself
    only ever reads project-level subagents from that fixed root
    directory, so scanning elsewhere in the tree would report files this
    convention does not actually recognize as agents. Within that root,
    though, Claude Code scans recursively (verified against
    code.claude.com/docs/en/sub-agents: "Claude Code scans
    `.claude/agents/`... recursively, so you can organize definitions
    into subfolders such as `agents/review/`"; confirmed as a real,
    commonly-used convention via GitHub code search across public
    `.claude/agents/<subfolder>/*.md` files) — a subagent nested one or
    more directories deep was previously invisible to this detector
    entirely.
    """
    agents_dir = root / _AGENTS_DIR
    if not agents_dir.is_dir():
        return []

    agents: list[Agent] = []
    for agent_md in sorted(agents_dir.rglob("*.md")):
        rel_path = agent_md.relative_to(root)
        if is_excluded(rel_path.parts[:-1]):
            continue

        text = agent_md.read_text(encoding="utf-8", errors="replace")
        fields = parse_frontmatter(text)

        found_evidence = Evidence(
            kind=EvidenceKind.FILE,
            source=str(rel_path),
            observation=".claude/agents/*.md file found",
            confidence=Confidence.VERIFIED,
        )

        is_standard = fields is not None and all(f in fields for f in _REQUIRED_FRONTMATTER_FIELDS)
        name = fields.get("name") if fields else None
        description = fields.get("description") if fields else None
        model = fields.get("model") if fields else None
        tools_field = fields.get("tools") if fields else None
        tool_names = split_tool_list(tools_field) if tools_field else []
        disallowed_tools_field = fields.get("disallowedTools") if fields else None
        permissions = split_tool_list(disallowed_tools_field) if disallowed_tools_field else []

        evidence = [found_evidence]
        if fields is not None:
            if is_standard:
                observation = f"Frontmatter fields present: {sorted(fields)}"
            else:
                observation = (
                    f"Frontmatter present but missing required field(s); found: {sorted(fields)}"
                )
            evidence.append(
                Evidence(
                    kind=EvidenceKind.FILE,
                    source=str(rel_path),
                    locator="frontmatter",
                    observation=observation,
                    confidence=Confidence.VERIFIED,
                )
            )

        agents.append(
            Agent(
                id=stable_id("agent", str(rel_path)),
                name=name or agent_md.stem,
                path=str(rel_path),
                description=description,
                is_standard_format=is_standard,
                model_provider=model,
                tool_names=tool_names,
                permissions=permissions,
                evidence=evidence,
            )
        )
    return agents
