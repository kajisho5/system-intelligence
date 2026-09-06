from pathlib import Path

from system_intelligence.discovery.ci_docs import detect_ci_jobs, detect_root_documents


def test_detect_ci_jobs(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    jobs = detect_ci_jobs(tmp_path)

    assert len(jobs) == 1
    assert jobs[0].provider == "github-actions"
    assert jobs[0].workflow_path == ".github/workflows/ci.yml"


def test_detect_ci_jobs_none(tmp_path: Path) -> None:
    assert detect_ci_jobs(tmp_path) == []


def test_detect_root_documents(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")

    documents = detect_root_documents(tmp_path)

    document_types = {d.document_type for d in documents}
    assert document_types == {"README", "LICENSE"}
