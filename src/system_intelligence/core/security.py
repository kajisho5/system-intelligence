"""SecurityAdvisory — a known vulnerability report for one component version.

Distinct from `core.impact.ImpactAssessment`'s update-freshness judgment
(`UpdateVerdict`): an advisory is a fact reported by an external source
about one specific version, independent of whether any update is even
available. Deliberately minimal and generic across ecosystems (ADR-001,
ADR-007) — no OSV-specific or GHSA-specific fields belong here, only what
every advisory source can report.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SecurityAdvisory(BaseModel):
    """One known vulnerability affecting a specific component version.

    `severity` is left `None` unless the source itself reports a plain
    severity label (e.g. a GitHub Security Advisory's "LOW"/"MODERATE"/
    "HIGH"/"CRITICAL") — a raw CVSS vector string is never parsed/scored
    here, since computing a severity from it would be this module
    asserting a judgment the source itself did not make in that form.
    """

    id: str = Field(description="The advisory's own identifier, e.g. a GHSA or OSV id.")
    summary: str
    severity: str | None = None
    aliases: list[str] = Field(
        default_factory=list, description="Other identifiers for the same advisory, e.g. a CVE id."
    )
    url: str | None = None
