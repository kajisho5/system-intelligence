"""Research provider abstraction (docs/design/docs/18-extension-points.md,
"Research provider SDK") — the improvement engine (later phases) must depend
on this, never on a specific provider (ADR-007, provider agnostic).

`extract_facts(document)` from the design doc's SDK sketch is not promoted
to this Protocol yet: no provider in this phase needs it (GitHub's search
and repo-detail responses already arrive as structured facts, not documents
to parse), so declaring it here would be speculative. Add it once a
provider actually needs to extract facts from unstructured content (e.g. a
fetched README).
"""

from __future__ import annotations

from typing import Protocol

from system_intelligence.core.research import ResearchResult


class ResearchProvider(Protocol):
    """A read-only external research source. Never performs writes."""

    name: str

    def search(self, query: str, *, limit: int = 10) -> list[ResearchResult]:
        """Search for candidates matching `query`."""
        ...

    def fetch(self, identifier: str) -> ResearchResult:
        """Fetch full detail for one candidate by provider-specific identifier."""
        ...
