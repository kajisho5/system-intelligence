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


def _find_references(skill: Skill, root: Path) -> list[str]:
    skill_dir_parts = Path(skill.path).parent.parts if skill.path else ()
    referencing_files: list[str] = []

    for path in iter_files(root):
        rel_parts = path.relative_to(root).parts
        if rel_parts[: len(skill_dir_parts)] == skill_dir_parts:
            continue  # skip the Skill's own directory
        if path.suffix not in _SEARCHABLE_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if skill.name in text:
            referencing_files.append(str(path.relative_to(root)))

    return referencing_files


def classify_skill_usage(skill: Skill, root: Path) -> tuple[UsageStatus, list[str]]:
    """Classify a Skill's static-reference status by searching outside its own directory."""
    references = _find_references(skill, root)
    status = UsageStatus.UNREFERENCED if not references else UsageStatus.UNKNOWN
    return status, references


def audit_unused_skills(skills: list[Skill], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for skill in skills:
        status, references = classify_skill_usage(skill, root)
        if status != UsageStatus.UNREFERENCED:
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
