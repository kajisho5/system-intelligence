"""Unused-component analysis for Skills (docs/design/docs/05-analysis-engine.md,
"Unused detection"; ADR-010).

Never equates "no static reference found" with "unused". A Skill with zero
textual references outside its own directory is classified `unreferenced` —
a plain statement of the search result — not `verified_unused`. Reaching
`verified_unused` needs corroborating evidence this analyzer does not have
access to (runtime telemetry, explicit human confirmation).
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import Skill
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


def _find_references(skill: Skill, file_contents: dict[str, str]) -> list[str]:
    """Search an already-read file-content map for occurrences of `skill.name`.

    A Skill's own `SKILL.md` is always excluded (its frontmatter contains
    the Skill's own name, which is not a "consumer" reference). The rest of
    its directory (scripts/, references/, ...) is excluded too, but only
    when that directory is non-empty — a root-level `SKILL.md` has no
    directory of its own to exclude beyond the file itself, and treating an
    empty exclusion prefix as matching every path (as `()[:0] == ()`
    trivially does) would skip the entire repository instead of nothing.
    """
    skill_path = Path(skill.path) if skill.path else None
    skill_dir_parts = skill_path.parent.parts if skill_path else ()

    referencing_files: list[str] = []
    for rel_path_str, text in file_contents.items():
        rel_parts = Path(rel_path_str).parts
        if skill_path is not None and rel_parts == skill_path.parts:
            continue
        if skill_dir_parts and rel_parts[: len(skill_dir_parts)] == skill_dir_parts:
            continue
        if skill.name in text:
            referencing_files.append(rel_path_str)
    return referencing_files


def classify_skill_usage(skill: Skill, root: Path) -> tuple[UsageStatus, list[str]]:
    """Classify a Skill's static-reference status by searching outside its own directory."""
    references = _find_references(skill, _read_searchable_files(root))
    status = UsageStatus.UNREFERENCED if not references else UsageStatus.UNKNOWN
    return status, references


def audit_unused_skills(skills: list[Skill], root: Path) -> list[Finding]:
    file_contents = _read_searchable_files(root)  # read every file once, not once per Skill
    findings: list[Finding] = []
    for skill in skills:
        references = _find_references(skill, file_contents)
        if references:
            continue
        findings.append(
            Finding(
                category="unused_candidate",
                severity=Severity.LOW,
                statement=(
                    f"{skill.name!r} is currently unreferenced by the analyzed consumers. "
                    "Runtime usage could not be verified."
                ),
                confidence=Confidence.MEDIUM,
                affected_entity_ids=[skill.id],
                evidence=[
                    Evidence(
                        kind=EvidenceKind.STATIC_REFERENCE,
                        source=str(root),
                        observation=(
                            f"No occurrence of {skill.name!r} found outside {skill.path} "
                            f"among searchable text files"
                        ),
                        confidence=Confidence.VERIFIED,
                    )
                ],
                suggested_actions=[
                    "Confirm whether this Skill is still needed; consider runtime "
                    "telemetry or asking its owner before removing it."
                ],
            )
        )
    return findings
