"""CI and top-level documentation detection (R2).

Phase 2 scope: GitHub Actions workflows and well-known root documents
(README, LICENSE, CONTRIBUTING, SECURITY). ADR-specific detection lives in
`discovery.adr` instead (a different filename convention, found at any
depth, not just the repository root). Deeper documentation content audits
(README completeness, etc.) belong to the analysis phase
(docs/design/docs/05-analysis-engine.md, "Documentation" detector family).
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import CIJob, Document
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id

#: Matched case-insensitively against the actual on-disk filename (see
#: `detect_root_documents`) -- a case-sensitive filesystem (Linux) would
#: otherwise report a real `readme.md`/`License` as missing just because
#: its case differs from the table below, which GitHub's own README/
#: LICENSE detection does not do either. Bare `README`/`LICENSE` and
#: `.txt` variants are included alongside the existing `.md`/`.rst`
#: entries for the same reason multiple extensions were already listed
#: per type: each is a real, common convention, not a guess.
_ROOT_DOCUMENTS: dict[str, str] = {
    "README.md": "README",
    "README.rst": "README",
    "README.txt": "README",
    "README": "README",
    "LICENSE": "LICENSE",
    "LICENSE.md": "LICENSE",
    "LICENSE.txt": "LICENSE",
    "CONTRIBUTING.md": "CONTRIBUTING",
    "SECURITY.md": "SECURITY",
}


def detect_ci_jobs(root: Path) -> list[CIJob]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []

    jobs: list[CIJob] = []
    for workflow_path in sorted(workflows_dir.glob("*.y*ml")):
        rel_path = str(workflow_path.relative_to(root))
        jobs.append(
            CIJob(
                id=stable_id("cijob", rel_path),
                name=workflow_path.stem,
                provider="github-actions",
                workflow_path=rel_path,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.CI_CONFIG,
                        source=rel_path,
                        observation=f"GitHub Actions workflow file found at {rel_path}",
                        confidence=Confidence.VERIFIED,
                    )
                ],
            )
        )
    return jobs


def detect_root_documents(root: Path) -> list[Document]:
    try:
        root_files = {entry.name.lower(): entry.name for entry in root.iterdir() if entry.is_file()}
    except OSError:
        return []

    documents: list[Document] = []
    for filename, document_type in _ROOT_DOCUMENTS.items():
        actual_name = root_files.get(filename.lower())
        if actual_name is None:
            continue
        documents.append(
            Document(
                id=stable_id("document", actual_name),
                name=actual_name,
                path=actual_name,
                document_type=document_type,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.FILE,
                        source=actual_name,
                        observation=f"{actual_name} found at repository root",
                        confidence=Confidence.VERIFIED,
                    )
                ],
            )
        )
    return documents
