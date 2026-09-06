"""Shared filesystem-walking rules for discovery detectors.

Every detector that walks a repository tree must exclude VCS internals,
dependency caches, and build output — otherwise a local virtualenv or
`node_modules` can leak third-party files (e.g. a vendored package's own
`SKILL.md`) into the discovered inventory as if they belonged to the
target repository.
"""

from __future__ import annotations

from pathlib import Path

#: Directories never descended into. Not user-configurable in Phase 2.
#: `vendor` (Go's `go mod vendor` / PHP Composer's own vendoring
#: convention -- a full copy of every dependency's source tree, complete
#: with its own go.mod/README/LICENSE files, checked in verbatim) is the
#: single most direct example of this module's own docstring concern
#: ("a vendored package's own SKILL.md" leaking into the discovered
#: inventory) that wasn't actually excluded. `.tox` (Python's tox, same
#: full-virtualenv shape as the already-excluded `.venv`/`venv`) and
#: `target` (Rust/Cargo's and Maven's build-output directory) round out
#: the same "dependency cache / build output" categories this frozenset
#: already covers for other ecosystems, for two ecosystems this project
#: now also discovers dependencies for (Cargo.toml, go.mod).
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        "target",
        "vendor",
        ".eggs",
    }
)


def is_excluded(relative_parts: tuple[str, ...]) -> bool:
    """True if any directory component in `relative_parts` should be skipped."""
    return any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in relative_parts)


def iter_files(root: Path, pattern: str = "*") -> list[Path]:
    """Yield files under `root` matching `pattern`, skipping excluded directories."""
    files: list[Path] = []
    for path in root.rglob(pattern):
        if not path.is_file():
            continue
        if is_excluded(path.relative_to(root).parts[:-1]):
            continue
        files.append(path)
    return files
