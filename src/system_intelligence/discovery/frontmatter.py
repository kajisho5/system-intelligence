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
        fields[key.strip()] = value.strip().strip("\"'")
    return fields
