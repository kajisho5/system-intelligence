"""Shared YAML-frontmatter parsing for `---`-delimited manifest files.

Used by both `discovery/skills.py` (`SKILL.md`) and `discovery/agents.py`
(`.claude/agents/*.md`) — the two conventions this project detects share
the identical `---\\n<fields>\\n---\\n` shape, so the parsing itself is
extracted here rather than duplicated. Deliberately not a real YAML
parser: only flat `key: value` lines are recognized (no nesting, no
lists), which is all either convention's required fields need — a
project has no YAML dependency today (only pydantic and typer), and
adding one for this would not be justified.
"""

from __future__ import annotations

import re

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _unquote(value: str) -> str:
    """Strip one matching pair of quote characters from `value`'s ends.

    `str.strip('"\\'')` (the previous approach) strips *any run* of either
    quote character from either end, not a matched delimiter pair -- so a
    quoted value whose own content ends with the other quote character
    right at the boundary (e.g. `'Use this for ".json"'`) gets eaten past
    its real closing delimiter, silently truncating real content instead
    of just failing to unescape it. Only strip when the first and last
    characters are the *same* quote character.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Parse the leading `---`-delimited frontmatter block, if present.

    Returns `None` when `text` has no frontmatter block at all — distinct
    from an empty `{}` (a present-but-fieldless block), so callers can
    tell "no frontmatter" from "frontmatter with nothing recognized".
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = _unquote(value.strip())
    return fields


def split_tool_list(value: str) -> list[str]:
    """Split a single-line tool-specifier list on top-level commas/whitespace.

    Used for the `tools`/`disallowedTools` (Claude Code subagent
    frontmatter, code.claude.com/docs/en/sub-agents) and `allowed-tools`/
    `disallowed-tools` (Agent Skills frontmatter,
    code.claude.com/docs/en/skills) fields, all of which accept a comma-
    and/or space-separated list of tool names. A naive `str.split(",")`
    breaks on a real, documented specifier form: `Agent(worker,
    researcher)` (sub-agents docs, "restrict which subagent types it can
    spawn") is *one* specifier whose parenthesized argument list itself
    contains a comma. This tracks paren nesting depth so a comma or
    space inside `(...)` is never treated as a separator, only one
    outside any parentheses is.
    """
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif depth == 0 and (char.isspace() or char == ","):
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return [t.strip() for t in tokens if t.strip()]


def split_glob_list(value: str) -> list[str]:
    """Split a single-line, comma-separated glob-pattern list on top-level commas.

    Used for the `paths` Agent Skills frontmatter field (code.claude.com/
    docs/en/skills: "Glob patterns that limit when this skill is
    activated. Accepts a comma-separated string or a YAML list." -- only
    the comma-separated string form is parseable by this project's flat
    `key: value` frontmatter parser above; the YAML-list form is left
    unparsed, the same documented limitation every other multi-value
    frontmatter field here already has). A naive `str.split(",")` breaks
    brace-expansion glob syntax (`src/**/*.{ts,tsx}`, a standard
    bash/zsh/glob-library convention) whose comma is internal to one
    pattern, not a separator -- mirrors `split_tool_list`'s own
    paren-depth tracking, just for `{...}` instead of `(...)`. Unlike
    `split_tool_list`, only a comma separates patterns, never bare
    whitespace, since the docs describe this field as comma- (not
    space-) separated, and a glob pattern could itself legitimately
    contain a space.
    """
    patterns: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "{":
            depth += 1
            current.append(char)
        elif char == "}":
            depth = max(0, depth - 1)
            current.append(char)
        elif depth == 0 and char == ",":
            if current:
                patterns.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        patterns.append("".join(current))
    return [p.strip() for p in patterns if p.strip()]
