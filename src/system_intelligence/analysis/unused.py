"""Unused-component analysis for Skills/Agents (docs/design/docs/05-analysis-engine.md,
"Unused detection"; ADR-010, phrased generically as "component," not Skill-specific).

Never equates "no static reference found" with "unused". A Skill or Agent
with zero textual references outside its own directory is classified
`unreferenced` — a plain statement of the search result — not
`verified_unused`. Reaching `verified_unused` needs corroborating evidence
this analyzer does not have access to (runtime telemetry, explicit human
confirmation).
"""

from __future__ import annotations

import re
from pathlib import Path

from system_intelligence.core.entities import Agent, Skill
from system_intelligence.core.enums import Confidence, Severity, UsageStatus
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.discovery.paths import iter_files

#: Extensions worth text-searching for a reference. Binary/media files are
#: skipped rather than decoded.
_SEARCHABLE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".cfg",
}


def _read_searchable_files(root: Path) -> dict[str, str]:
    """Read every searchable-text file under `root` exactly once."""
    contents: dict[str, str] = {}
    for path in iter_files(root):
        if path.suffix not in _SEARCHABLE_EXTENSIONS:
            continue
        try:
            contents[str(path.relative_to(root))] = path.read_text(
                encoding="utf-8", errors="ignore"
            )
        except OSError:
            continue
    return contents


def _find_references(component: Skill | Agent, file_contents: dict[str, str]) -> list[str]:
    """Search an already-read file-content map for occurrences of `component.name`.

    A Skill's/Agent's own declaring file (`SKILL.md`/`<name>.md`) is always
    excluded (its frontmatter contains the component's own name, which is
    not a "consumer" reference). The rest of its directory (scripts/,
    references/, ...) is excluded too, but only when that directory is
    non-empty — a root-level `SKILL.md` has no directory of its own to
    exclude beyond the file itself, and treating an empty exclusion prefix
    as matching every path (as `()[:0] == ()` trivially does) would skip
    the entire repository instead of nothing.
    """
    component_path = Path(component.path) if component.path else None
    component_dir_parts = component_path.parent.parts if component_path else ()
    # Word-boundary match, not a bare substring check: a plain `in` test
    # (the previous implementation) treats "read" as "referenced" by
    # matching inside "already", "readme", etc. -- every other name-match
    # in this codebase (`analysis/capabilities.py`'s exact dict-key
    # matches, `proposals/engine.py`'s `\b`-bounded manifest-patcher
    # regexes) already avoids this, so a short/common component name
    # (`read`, `run`, `test`, `docs`, ...) was the one case where this
    # detector could never actually flag an unused component.
    name_pattern = re.compile(r"\b" + re.escape(component.name) + r"\b")

    referencing_files: list[str] = []
    for rel_path_str, text in file_contents.items():
        rel_parts = Path(rel_path_str).parts
        if component_path is not None and rel_parts == component_path.parts:
            continue
        if component_dir_parts and rel_parts[: len(component_dir_parts)] == component_dir_parts:
            continue
        if name_pattern.search(text):
            referencing_files.append(rel_path_str)
    return referencing_files


def classify_skill_usage(skill: Skill | Agent, root: Path) -> tuple[UsageStatus, list[str]]:
    """Classify a Skill's/Agent's static-reference status, searching outside its own directory."""
    references = _find_references(skill, _read_searchable_files(root))
    status = UsageStatus.UNREFERENCED if not references else UsageStatus.UNKNOWN
    return status, references


def audit_unused_skills(components: list[Skill | Agent], root: Path) -> list[Finding]:
    file_contents = _read_searchable_files(root)  # read every file once, not once per component
    findings: list[Finding] = []
    for component in components:
        references = _find_references(component, file_contents)
        if references:
            continue
        findings.append(
            Finding(
                category="unused_candidate",
                severity=Severity.LOW,
                statement=(
                    f"{component.name!r} is currently unreferenced by the analyzed consumers. "
                    "Runtime usage could not be verified."
                ),
                confidence=Confidence.MEDIUM,
                affected_entity_ids=[component.id],
                evidence=[
                    Evidence(
                        kind=EvidenceKind.STATIC_REFERENCE,
                        source=str(root),
                        observation=(
                            f"No occurrence of {component.name!r} found outside "
                            f"{component.path} among searchable text files"
                        ),
                        confidence=Confidence.VERIFIED,
                    )
                ],
                suggested_actions=[
                    "Confirm whether this is still needed; consider runtime "
                    "telemetry or asking its owner before removing it."
                ],
            )
        )
    return findings
