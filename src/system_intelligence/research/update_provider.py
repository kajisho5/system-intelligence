"""Component update provider abstraction.

Distinct from `research.provider.ResearchProvider` (docs/18-extension-
points.md, "Research provider SDK"), which searches for *new* candidate
solutions from a free-text query. This Protocol answers a narrower
question about a component System Intelligence already knows about: "what
is the latest available state of *this specific* identity?" — the lookup
`identity.name`/`identity.distribution_source` already pins down, no
searching involved.

Every implementation must be a pure ecosystem adapter (ADR-007): it may
know about npm, PyPI, GitHub Releases, an MCP registry, or a target's own
Capability Contract format, but it must never know about a specific
package, repository, or organization. Target-specific adapters (e.g. one
project's own internal registry) belong in `system_intelligence.integrations`,
never in `research/providers/`.
"""

from __future__ import annotations

from typing import Protocol

from system_intelligence.core.component_state import AvailableState, ComponentIdentity


class ComponentUpdateError(RuntimeError):
    """Base class for a failed lookup (network, HTTP, or parse error).

    Every provider-specific error (`PyPIUpdateError`, `NpmUpdateError`, ...)
    subclasses this, so callers that need to distinguish "the source
    reported nothing" (a lookup returning `None`) from "the source could
    not be reached" (an exception) can catch this one type regardless of
    which provider raised it — never silently mapped to `None`, which would
    make an unreachable registry indistinguishable from a package that
    genuinely does not exist.
    """


class ComponentUpdateProvider(Protocol):
    """A read-only source of available-state information for one ecosystem."""

    name: str

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        """Look up the latest available state for `identity`.

        Returns `None` when the provider has nothing on record for this
        identity (e.g. package not found) — distinct from raising, which
        signals the lookup itself failed (network error, malformed
        response). Callers must not treat `None` as evidence the component
        does not exist; it only means this provider found nothing.
        """
        ...
