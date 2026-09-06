"""Architecture Decision Record (ADR) detection.

Recognizes the Nygard-style ADR file naming convention used across the
kajisho5 ecosystem (verified against `ai-video-production-os`'s
`docs/adr/ADR-NNN-slug.md` files) — a filename containing `ADR-<number>`,
found anywhere in the tree, not only under `docs/adr/`. Deliberately does
not also match bare-numeric filenames (e.g. `0001-slug.md`, used by some
`adr-tools` setups) since that pattern alone is not distinguishable from
an unrelated numbered file (a migration, a changelog entry) without
assuming a specific directory name — this detector only ever claims
"ADR" for content that says so in its own filename.

`status` is parsed from a `Status: <value>` line if present (the
convention every discovered ADR in this ecosystem follows); when absent,
it stays `None` rather than a fabricated default. `decided_at` is never
populated by this detector — none of the source files carry a date, and
guessing one from file mtime would be a filesystem artifact, not a fact
about when the decision was made.
"""

from __future__ import annotations

import re
from pathlib import Path

from system_intelligence.core.entities import ADR
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id
from system_intelligence.discovery.paths import iter_files

_FILENAME_RE = re.compile(r"ADR-(\d+)", re.IGNORECASE)
_STATUS_RE = re.compile(r"^Status:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_HEADING_RE = re.compile(r"^#\s*ADR-\d+:?\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def detect_adrs(root: Path) -> list[ADR]:
    """Find ADR files under `root` by filename convention.

    Excludes VCS/dependency/build directories (see `discovery.paths`) but
    otherwise walks the whole tree, since ADRs may live at any depth
    (e.g. `docs/adr/ADR-003-x.md`, `docs/decisions/ADR-12-y.md`).
    """
    adrs: list[ADR] = []
    for path in sorted(iter_files(root, "*.md")):
        rel_path = path.relative_to(root)
        match = _FILENAME_RE.search(path.name)
        if not match:
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        status_match = _STATUS_RE.search(text)
        heading_match = _HEADING_RE.search(text)

        evidence = [
            Evidence(
                kind=EvidenceKind.FILE,
                source=str(rel_path),
                observation="ADR file found",
                confidence=Confidence.VERIFIED,
            )
        ]
        if status_match:
            evidence.append(
                Evidence(
                    kind=EvidenceKind.FILE,
                    source=str(rel_path),
                    locator="Status",
                    observation=f"Status line found: {status_match.group(1).strip()!r}",
                    confidence=Confidence.VERIFIED,
                )
            )

        adrs.append(
            ADR(
                id=stable_id("adr", str(rel_path)),
                name=heading_match.group(1).strip() if heading_match else path.stem,
                number=int(match.group(1)),
                status=status_match.group(1).strip() if status_match else None,
                path=str(rel_path),
                evidence=evidence,
            )
        )
    return adrs
