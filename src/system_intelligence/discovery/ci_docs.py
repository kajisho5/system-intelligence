"""CI and top-level documentation detection (R2).

Phase 2 scope: GitHub Actions workflows and well-known root documents
(README, LICENSE, CONTRIBUTING, SECURITY). ADR-specific detection lives in
`discovery.adr` instead (a different filename convention, found at any
depth, not just the repository root). Deeper documentation content audits
(README completeness, etc.) belong to the analysis phase
(docs/design/docs/05-analysis-engine.md, "Documentation" detector family).

`detect_license` additionally classifies a detected root LICENSE
document's own content into an SPDX identifier
(docs/design/docs/05-analysis-engine.md's "Repository" detector family
explicitly lists "license"): a repository's `LICENSE` file existing
proves nothing about *which* license it is on its own, so this never
infers one from the filename, only from an exact match against
`_LICENSE_SIGNATURES`.
"""

from __future__ import annotations

import re
from pathlib import Path

from system_intelligence.core.entities import CIJob, Document
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id

#: Matched case-insensitively against the actual on-disk filename (see
#: `detect_root_documents`) -- a case-sensitive filesystem (Linux) would
#: otherwise report a real `readme.md`/`License` as missing just because
#: its case differs from the table below, which GitHub's own README/
#: LICENSE detection does not do either. Bare `README`/`LICENSE` and
#: `.txt` variants are included alongside the existing `.md`/`.rst`
#: entries for the same reason multiple extensions were already listed
#: per type: each is a real, common convention, not a guess.
#: `CODE_OF_CONDUCT.md` is one of GitHub's own "community health file"
#: conventions (github.com/.github/community-health-files), the same
#: family `CONTRIBUTING.md`/`SECURITY.md` are already drawn from --
#: recorded when present the same as `SECURITY.md` (never turned into a
#: mandatory `documentation_gap` finding when absent; see
#: `analysis/documentation.py::_EXPECTED_DOCUMENT_TYPES`, which
#: deliberately does not include it either).
_ROOT_DOCUMENTS: dict[str, str] = {
    "README.md": "README",
    "README.rst": "README",
    "README.txt": "README",
    "README": "README",
    "LICENSE": "LICENSE",
    "LICENSE.md": "LICENSE",
    "LICENSE.txt": "LICENSE",
    "CONTRIBUTING.md": "CONTRIBUTING",
    "SECURITY.md": "SECURITY",
    "CODE_OF_CONDUCT.md": "CODE_OF_CONDUCT",
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


#: BSD-3-Clause's own third clause names the actual copyright holder in
#: place of a fixed placeholder ("Neither the name of Google Inc. nor the
#: names of its contributors" in protobuf's real LICENSE; "...the NumPy
#: Developers nor the names of any contributors" in NumPy's) -- a real
#: BSD-3-Clause file's own org name (and "its"/"any") varies, so this is
#: a regex, not a literal substring, wide enough to still subsume the
#: generic SPDX placeholder text itself ("the copyright holder").
_BSD_3_CLAUSE_RE = re.compile(r"Neither the name of .+? nor the names of (?:its|any) contributors")

#: Each signature is a distinctive substring (or, for BSD-3-Clause, a
#: regex) of that license's own canonical text (verified live against
#: spdx/license-list-data's own reference texts, plus this repository's
#: own real LICENSE file for MIT and real projects' own root LICENSE
#: files for Apache-2.0/BSD-3-Clause -- see `_normalize_whitespace`/
#: `_BSD_3_CLAUSE_RE`), never a guess from the filename or a partial
#: keyword match (ADR-002). Order matters: a more specific license's text
#: also contains a less specific relative's substring, so the specific
#: one is checked first -- GPL-3.0 ("...Version 3") before GPL-2.0
#: ("...Version 2"), and BSD-3-Clause's own third clause before
#: BSD-2-Clause's shared first two clauses ("Redistributions in binary
#: form..."), which a real BSD-3-Clause file's text also contains.
_LICENSE_SIGNATURES: tuple[tuple[str | re.Pattern[str], str], ...] = (
    ("Mozilla Public License Version 2.0", "MPL-2.0"),
    ("GNU GENERAL PUBLIC LICENSE\nVersion 3", "GPL-3.0"),
    ("GNU GENERAL PUBLIC LICENSE\nVersion 2", "GPL-2.0"),
    (_BSD_3_CLAUSE_RE, "BSD-3-Clause"),
    ("Redistributions in binary form must reproduce the above copyright", "BSD-2-Clause"),
    (
        "Permission to use, copy, modify, and/or distribute this software for any "
        "purpose with or without fee",
        "ISC",
    ),
    ("This is free and unencumbered software released into the public domain.", "Unlicense"),
    ("MIT License", "MIT"),
    ("Apache License\nVersion 2.0", "Apache-2.0"),
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    """Collapse any run of whitespace (including newlines) to a single
    space, so a signature written on one logical line still matches real
    LICENSE file text wrapped/centered with extra spaces or line breaks --
    verified against the real, official Apache Software Foundation text
    (`curl https://www.apache.org/licenses/LICENSE-2.0.txt`), which centers
    "Apache License" / "Version 2.0, January 2004" with ~27 leading spaces
    each, so the literal `"Apache License\\nVersion 2.0"` substring never
    appeared in a real, canonical Apache-2.0 LICENSE file (e.g. Kubernetes'
    own root `LICENSE`) before this normalization.
    """
    return _WHITESPACE_RE.sub(" ", text)


def detect_license(root: Path, documents: list[Document]) -> str | None:
    """Classify the repository's root LICENSE file content into an SPDX
    identifier, from `_LICENSE_SIGNATURES`.

    Never guessed from the filename alone -- a `LICENSE` file could
    contain anything. Returns `None` (never a best guess) when no root
    LICENSE document was detected, its file could not be read, or its
    content matches none of the known signatures.
    """
    license_doc = next((d for d in documents if d.document_type == "LICENSE"), None)
    if license_doc is None or license_doc.path is None:
        return None
    try:
        text = (root / license_doc.path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    normalized_text = _normalize_whitespace(text)
    for signature, identifier in _LICENSE_SIGNATURES:
        if isinstance(signature, re.Pattern):
            if signature.search(normalized_text):
                return identifier
            continue
        if _normalize_whitespace(signature) in normalized_text:
            return identifier
    return None


def detect_root_documents(root: Path) -> list[Document]:
    try:
        root_files = {entry.name.lower(): entry.name for entry in root.iterdir() if entry.is_file()}
    except OSError:
        return []

    documents: list[Document] = []
    for filename, document_type in _ROOT_DOCUMENTS.items():
        actual_name = root_files.get(filename.lower())
        if actual_name is None:
            continue
        documents.append(
            Document(
                id=stable_id("document", actual_name),
                name=actual_name,
                path=actual_name,
                document_type=document_type,
                evidence=[
                    Evidence(
                        kind=EvidenceKind.FILE,
                        source=actual_name,
                        observation=f"{actual_name} found at repository root",
                        confidence=Confidence.VERIFIED,
                    )
                ],
            )
        )
    return documents
