"""CI and top-level documentation detection (R2).

Phase 2 scope: GitHub Actions workflows and well-known root documents
(README, LICENSE, CONTRIBUTING, SECURITY). Deeper documentation/ADR audits
belong to the analysis phase (docs/design/docs/05-analysis-engine.md,
"Documentation" detector family).
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import CIJob, Document
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id

_ROOT_DOCUMENTS: dict[str, str] = {
    "README.md": "README",
    "README.rst": "README",
    "LICENSE": "LICENSE",
    "LICENSE.md": "LICENSE",
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
    documents: list[Document] = []
    for filename, document_type in _ROOT_DOCUMENTS.items():
        path = root / filename
        if not path.is_file():
            continue
        documents.append(
            Document(
                id=stable_id("document", filename),
                name=filename,
                path=filename,
                document_type=document_type,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.FILE,
                        source=filename,
                        observation=f"{filename} found at repository root",
                        confidence=Confidence.VERIFIED,
                    )
                ],
            )
        )
    return documents
