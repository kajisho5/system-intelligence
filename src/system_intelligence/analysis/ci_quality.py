"""Test/CI presence audit (docs/design/docs/05-analysis-engine.md, "Quality").

Phase 3 scope: whether any CI job was detected and whether any test files
exist under a conventional `tests/` directory, (Go) anywhere in the tree
at all, or (Java/Maven/Gradle) under `src/test/java`. Not in scope:
coverage percentages, lint/type-check configuration quality, or CI run
history — those need richer signals than local discovery provides.
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import CIJob, Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.discovery.paths import iter_files

#: Cargo's own convention: every file under `tests/` is compiled as its
#: own integration-test crate, so a bare `*.rs` there (unlike a source
#: file elsewhere) is unambiguously a test file.
_TEST_FILE_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*.test.ts",
    "*.test.js",
    "*.spec.ts",
    "*.spec.js",
    "*.rs",
)


def _has_directory_test_files(root: Path) -> bool:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return False
    return any(any(tests_dir.rglob(pattern)) for pattern in _TEST_FILE_PATTERNS)


def _has_go_test_files(root: Path) -> bool:
    """Go's own testing convention colocates `<name>_test.go` directly next
    to the source file it tests, never under a `tests/` directory at all --
    so, uniquely among the checks here, this scans the whole tree (still
    excluding vendor/build directories, via `iter_files`, the same as every
    other whole-tree scan) rather than one fixed location.
    """
    return any(iter_files(root, "*_test.go"))


def _has_maven_layout_test_files(root: Path) -> bool:
    """Maven's own "Standard Directory Layout" convention (verified against
    maven.apache.org's own docs) places test sources at `src/test/java`,
    never under a root-level `tests/` directory -- Gradle's Java plugin
    defaults to the same layout. A real Maven/Gradle Java project (already
    a first-class ecosystem here -- `discovery/structure.py` detects
    `pom.xml`/`build.gradle(.kts)`, and `analysis/dependencies.py` parses
    `pom.xml`) with full test coverage under `src/test/java` was previously
    unconditionally flagged with a `test_gap` finding.
    """
    test_dir = root / "src" / "test" / "java"
    return test_dir.is_dir() and any(test_dir.rglob("*.java"))


def _has_test_files(root: Path) -> bool:
    return (
        _has_directory_test_files(root)
        or _has_go_test_files(root)
        or _has_maven_layout_test_files(root)
    )


def audit_ci_and_tests(repository: Repository, root: Path, ci_jobs: list[CIJob]) -> list[Finding]:
    findings: list[Finding] = []

    if not ci_jobs:
        findings.append(
            Finding(
                category="ci_health",
                severity=Severity.MEDIUM,
                statement="No CI configuration (e.g. GitHub Actions workflow) was found.",
                confidence=Confidence.HIGH,
                affected_entity_ids=[repository.id],
                evidence=[
                    Evidence(
                        kind=EvidenceKind.CI_CONFIG,
                        source=str(root),
                        observation="No .github/workflows/*.yml file found",
                        confidence=Confidence.VERIFIED,
                    )
                ],
                suggested_actions=["Add a CI workflow that runs tests on every change."],
            )
        )

    if not _has_test_files(root):
        observation = "No file matching common test naming conventions found under tests/"
        findings.append(
            Finding(
                category="test_gap",
                severity=Severity.HIGH,
                statement="No test files were found under a conventional 'tests/' directory.",
                confidence=Confidence.MEDIUM,
                affected_entity_ids=[repository.id],
                evidence=[
                    Evidence(
                        kind=EvidenceKind.FILE,
                        source=str(root / "tests"),
                        observation=observation,
                        confidence=Confidence.VERIFIED,
                    )
                ],
                suggested_actions=["Add automated tests, or confirm they live outside 'tests/'."],
            )
        )

    return findings
