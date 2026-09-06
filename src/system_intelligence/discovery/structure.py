"""Repository structure scanning: languages and package manifests (R2).

Deliberately simple for Phase 2: an extension histogram for language
signal, and a fixed table of well-known manifest filenames for package
detection. Both are heuristics — see `LANGUAGE_EXTENSIONS` and
`PACKAGE_MANIFESTS` — recorded at `Confidence.HIGH`, not `VERIFIED`, because
a matching extension or filename is a strong but not certain signal (e.g. a
vendored or generated file can match without the repository "being" that
language/ecosystem).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.discovery.paths import iter_files

#: Each extension maps to exactly one language unambiguously, same as the
#: existing entries -- `.php`/`.cs`/`.kt`/`.swift` are single-language
#: extensions with no cross-language ambiguity, and `.c`/`.cpp` cover two
#: more common, previously entirely-unrepresented languages this
#: heuristic would otherwise undercount a real C/C++ repository's file
#: histogram for (`.h`/`.hpp` headers are deliberately excluded -- they are
#: shared between C and C++ and would need more than a filename to
#: disambiguate, unlike every other entry here).
LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".php": "PHP",
    ".c": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".swift": "Swift",
}

#: manifest filename -> (ecosystem, language)
#: Multiple filenames per ecosystem are already the norm here (pypi has
#: both pyproject.toml and setup.py) -- Pipfile (Pipenv's manifest, which
#: has no pyproject.toml/setup.py at all), build.gradle.kts (Gradle's
#: Kotlin DSL form, the default for new Kotlin/Android projects), and
#: requirements.txt (pip's own convention, and the *only* manifest many
#: non-packaged Python projects -- scripts, notebooks, container images --
#: have at all, with no pyproject.toml/setup.py/Pipfile in sight) round out
#: that same pattern for real, common conventions this table would
#: otherwise silently miss. composer.json (Packagist/Composer, PHP's de
#: facto standard package manager -- LANGUAGE_EXTENSIONS already recognizes
#: .php, but this table had no matching manifest) is the same gap for PHP.
PACKAGE_MANIFESTS: dict[str, tuple[str, str]] = {
    "pyproject.toml": ("pypi", "Python"),
    "setup.py": ("pypi", "Python"),
    "Pipfile": ("pypi", "Python"),
    "requirements.txt": ("pypi", "Python"),
    "package.json": ("npm", "JavaScript/TypeScript"),
    "Cargo.toml": ("cargo", "Rust"),
    "go.mod": ("go", "Go"),
    "pom.xml": ("maven", "Java"),
    "build.gradle": ("gradle", "Java"),
    "build.gradle.kts": ("gradle", "Java"),
    "Gemfile": ("rubygems", "Ruby"),
    "composer.json": ("packagist", "PHP"),
}


@dataclass(frozen=True)
class PackageManifest:
    path: str
    ecosystem: str
    language: str


@dataclass(frozen=True)
class StructureScanResult:
    language_file_counts: dict[str, int] = field(default_factory=dict)
    package_manifests: list[PackageManifest] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def languages(self) -> list[str]:
        return sorted(self.language_file_counts, key=lambda lang: -self.language_file_counts[lang])


def scan_structure(root: Path) -> StructureScanResult:
    language_counts: Counter[str] = Counter()
    manifests: list[PackageManifest] = []
    evidence: list[Evidence] = []

    for path in iter_files(root):
        language = LANGUAGE_EXTENSIONS.get(path.suffix)
        if language:
            language_counts[language] += 1

        manifest_info = PACKAGE_MANIFESTS.get(path.name)
        if manifest_info:
            ecosystem, language = manifest_info
            rel_path = str(path.relative_to(root))
            manifests.append(PackageManifest(path=rel_path, ecosystem=ecosystem, language=language))
            observation = (
                f"Package manifest {path.name!r} found, implying the {ecosystem!r} ecosystem"
            )
            evidence.append(
                Evidence(
                    kind=EvidenceKind.FILE,
                    source=rel_path,
                    observation=observation,
                    confidence=Confidence.HIGH,
                )
            )

    for language, count in language_counts.items():
        evidence.append(
            Evidence(
                kind=EvidenceKind.FILE,
                source=str(root),
                observation=f"{count} file(s) with a {language} extension found",
                confidence=Confidence.HIGH,
            )
        )

    return StructureScanResult(
        language_file_counts=dict(language_counts),
        package_manifests=manifests,
        evidence=evidence,
    )
