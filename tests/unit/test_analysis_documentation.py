from system_intelligence.analysis.documentation import audit_documentation
from system_intelligence.core.entities import Document, Repository
from system_intelligence.core.enums import ComponentKind


def test_audit_documentation_flags_all_missing() -> None:
    repository = Repository(name="repo", local_path="/tmp/repo")
    findings = audit_documentation(repository, documents=[])
    categories = {f.category for f in findings}
    assert categories == {"documentation_gap"}
    assert len(findings) == 3


def test_audit_documentation_no_findings_when_all_present() -> None:
    repository = Repository(name="repo", local_path="/tmp/repo")
    documents = [
        Document(name="README.md", kind=ComponentKind.DOCUMENT, document_type="README"),
        Document(name="LICENSE", kind=ComponentKind.DOCUMENT, document_type="LICENSE"),
        Document(name="CONTRIBUTING.md", kind=ComponentKind.DOCUMENT, document_type="CONTRIBUTING"),
    ]
    findings = audit_documentation(repository, documents)
    assert findings == []
