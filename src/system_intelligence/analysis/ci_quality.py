"""Test/CI presence audit (docs/design/docs/05-analysis-engine.md, "Quality").

Phase 3 scope: whether any CI job was detected and whether any test files
exist under a conventional `tests/` directory. Not in scope: coverage
percentages, lint/type-check configuration quality, or CI run history —
those need richer signals than local discovery provides.
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import CIJob, Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding

_TEST_FILE_PATTERNS = ("test_*.py", "*_test.py", "*.test.ts", "*.test.js", "*.spec.ts", "*.spec.js")


def _has_test_files(root: Path) -> bool:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return False
    return any(any(tests_dir.rglob(pattern)) for pattern in _TEST_FILE_PATTERNS)


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
