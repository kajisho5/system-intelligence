"""Standard Agent Skill (`SKILL.md`) detection.

Per docs/design/docs/00-research-baseline.md: recognize the standard
`SKILL.md`-based layout where present, but never assume every Skill-like
directory follows it — hence `is_standard_format` is only ever set `True`
when the required frontmatter fields are actually present, and any SKILL.md
found is still reported even if that parsing fails.

The upstream spec's three optional Skill subdirectories -- `scripts/`,
`references/`, and `assets/` (docs/design/docs/00-research-baseline.md;
also docs/design/docs/17-reference-workflows.md's "inspect
scripts/references/assets") -- are each listed independently: a Skill
bundling only `assets/` (images, templates, data files it reads at
runtime) is exactly as valid as one with only `scripts/`.

`tool_names`/`permissions` are only ever populated from an explicit
`allowed-tools:`/`disallowed-tools:` frontmatter field respectively --
both documented Agent Skills frontmatter fields (verified against
code.claude.com/docs/en/skills's own field reference: "Tools Claude can
use without asking permission..."/"Tools removed from Claude's available
pool...", the Skill-level counterpart to `discovery/agents.py`'s
`tools:`/`disallowedTools:`), parsed with the same
`discovery.frontmatter.split_tool_list` paren-aware tokenizer.
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import Skill
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id
from system_intelligence.discovery.frontmatter import parse_frontmatter, split_tool_list
from system_intelligence.discovery.paths import is_excluded

_REQUIRED_FRONTMATTER_FIELDS = ("name", "description")


def _list_relative_files(directory: Path, relative_to: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return [str(p.relative_to(relative_to)) for p in sorted(directory.glob("**/*")) if p.is_file()]


def detect_skills(root: Path) -> list[Skill]:
    """Find `SKILL.md` files under `root` and parse them, if present.

    Excludes VCS/dependency/build directories (see `discovery.paths`) but
    otherwise walks the whole tree, since Skills may live at any depth
    (e.g. `skills/<name>/SKILL.md`, `.claude/skills/<name>/SKILL.md`).
    """
    skills: list[Skill] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        rel_path = skill_md.relative_to(root)
        if is_excluded(rel_path.parts[:-1]):
            continue

        skill_dir = skill_md.parent
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        fields = parse_frontmatter(text)

        found_evidence = Evidence(
            kind=EvidenceKind.FILE,
            source=str(rel_path),
            observation="SKILL.md file found",
            confidence=Confidence.VERIFIED,
        )

        is_standard = fields is not None and all(f in fields for f in _REQUIRED_FRONTMATTER_FIELDS)
        name = fields.get("name") if fields else None
        description = fields.get("description") if fields else None
        allowed_tools_field = fields.get("allowed-tools") if fields else None
        tool_names = split_tool_list(allowed_tools_field) if allowed_tools_field else []
        disallowed_tools_field = fields.get("disallowed-tools") if fields else None
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

        scripts = _list_relative_files(skill_dir / "scripts", skill_dir)
        references = _list_relative_files(skill_dir / "references", skill_dir)
        assets = _list_relative_files(skill_dir / "assets", skill_dir)

        skills.append(
            Skill(
                id=stable_id("skill", str(rel_path)),
                name=name or skill_dir.name,
                path=str(rel_path),
                description=description,
                is_standard_format=is_standard,
                scripts=scripts,
                references=references,
                assets=assets,
                tool_names=tool_names,
                permissions=permissions,
                evidence=evidence,
            )
        )
    return skills
