"""Documentation audit: flag missing well-known root documents.

Deliberately narrow for Phase 3: presence/absence of README/LICENSE/
CONTRIBUTING, not content quality (README completeness, examples, etc. —
see docs/design/docs/05-analysis-engine.md, "Documentation" detector
family — is future work).
"""

from __future__ import annotations

from system_intelligence.core.entities import Document, Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding

_EXPECTED_DOCUMENT_TYPES: dict[str, Severity] = {
    "README": Severity.HIGH,
    "LICENSE": Severity.MEDIUM,
    "CONTRIBUTING": Severity.LOW,
}


def audit_documentation(repository: Repository, documents: list[Document]) -> list[Finding]:
    present_types = {d.document_type for d in documents if d.document_type}
    findings: list[Finding] = []

    for document_type, severity in _EXPECTED_DOCUMENT_TYPES.items():
        if document_type in present_types:
            continue
        findings.append(
            Finding(
                category="documentation_gap",
                severity=severity,
                statement=f"No {document_type} file was found at the repository root.",
                confidence=Confidence.HIGH,
                affected_entity_ids=[repository.id],
                evidence=[
                    Evidence(
                        kind=EvidenceKind.FILE,
                        source=repository.local_path or repository.name,
                        observation=f"No file matching {document_type} found at repository root",
                        confidence=Confidence.VERIFIED,
                    )
                ],
                suggested_actions=[f"Add a {document_type} file at the repository root."],
            )
        )
    return findings
