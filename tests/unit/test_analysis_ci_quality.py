from pathlib import Path

from system_intelligence.analysis.ci_quality import audit_ci_and_tests
from system_intelligence.core.entities import CIJob, Repository


def test_audit_flags_missing_ci_and_tests(tmp_path: Path) -> None:
    repository = Repository(name="repo", local_path=str(tmp_path))
    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs=[])
    categories = {f.category for f in findings}
    assert categories == {"ci_health", "test_gap"}


def test_audit_no_findings_when_ci_and_tests_present(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_example.py").write_text("", encoding="utf-8")
    repository = Repository(name="repo", local_path=str(tmp_path))
    ci_jobs = [CIJob(name="ci", provider="github-actions")]

    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs)

    assert findings == []
