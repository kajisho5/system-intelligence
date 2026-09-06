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


def test_audit_recognizes_go_test_files_colocated_with_source(tmp_path: Path) -> None:
    """Go's own testing convention colocates `<name>_test.go` directly next
    to the source file it tests -- never under a `tests/` directory at
    all. A real, fully-tested Go project must not be flagged as having no
    tests just because it has no `tests/` directory."""
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")
    (tmp_path / "main_test.go").write_text(
        'package main\nimport "testing"\nfunc TestMain(t *testing.T) {}\n', encoding="utf-8"
    )
    repository = Repository(name="repo", local_path=str(tmp_path))
    ci_jobs = [CIJob(name="ci", provider="github-actions")]

    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs)

    assert findings == []


def test_audit_recognizes_rust_integration_tests_under_tests_dir(tmp_path: Path) -> None:
    """Every file under Cargo's own `tests/` directory is compiled as its
    own integration-test crate -- a bare `*.rs` there is unambiguously a
    test file, unlike the existing Python/JS/TS-only patterns."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "integration_test.rs").write_text(
        "#[test]\nfn it_works() { assert!(true); }\n", encoding="utf-8"
    )
    repository = Repository(name="repo", local_path=str(tmp_path))
    ci_jobs = [CIJob(name="ci", provider="github-actions")]

    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs)

    assert findings == []


def test_audit_flags_go_project_with_no_test_go_files(tmp_path: Path) -> None:
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")
    repository = Repository(name="repo", local_path=str(tmp_path))
    ci_jobs = [CIJob(name="ci", provider="github-actions")]

    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs)

    assert {f.category for f in findings} == {"test_gap"}


def test_audit_recognizes_maven_layout_test_files(tmp_path: Path) -> None:
    """Maven's own "Standard Directory Layout" places test sources at
    `src/test/java`, never under a root-level `tests/` directory -- a real,
    fully-tested Maven/Gradle Java project must not be flagged as having no
    tests just because it has no `tests/` directory."""
    main_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    main_dir.mkdir(parents=True)
    (main_dir / "App.java").write_text("class App {}\n", encoding="utf-8")
    test_dir = tmp_path / "src" / "test" / "java" / "com" / "example"
    test_dir.mkdir(parents=True)
    (test_dir / "AppTest.java").write_text("class AppTest {}\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
    repository = Repository(name="repo", local_path=str(tmp_path))
    ci_jobs = [CIJob(name="ci", provider="github-actions")]

    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs)

    assert findings == []


def test_audit_flags_maven_project_with_no_src_test_java_files(tmp_path: Path) -> None:
    """A `src/test/java` directory with no actual `.java` files in it (or no
    such directory at all) must still be flagged -- an empty/absent
    directory is not evidence of any real test coverage."""
    main_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    main_dir.mkdir(parents=True)
    (main_dir / "App.java").write_text("class App {}\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
    repository = Repository(name="repo", local_path=str(tmp_path))
    ci_jobs = [CIJob(name="ci", provider="github-actions")]

    findings = audit_ci_and_tests(repository, tmp_path, ci_jobs)

    assert {f.category for f in findings} == {"test_gap"}
