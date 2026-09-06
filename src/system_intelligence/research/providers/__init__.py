"""Generic ecosystem adapters implementing `research.update_provider.ComponentUpdateProvider`
and `research.vulnerability_provider.VulnerabilityProvider`.

Every adapter here knows about one package ecosystem's (or, for
`osv.OSVVulnerabilityProvider`, one ecosystem-agnostic vulnerability
database's) public API and nothing else — no package name, repository, or
organization is hard-coded (ADR-007). Target-specific integrations (a
project's own internal registry or Capability Contract format) belong in
`system_intelligence.integrations`, not here.
"""

from system_intelligence.research.providers.npm import NpmUpdateError, NpmUpdateProvider
from system_intelligence.research.providers.osv import OSVLookupError, OSVVulnerabilityProvider
from system_intelligence.research.providers.pypi import PyPIUpdateError, PyPIUpdateProvider

__all__ = [
    "NpmUpdateError",
    "NpmUpdateProvider",
    "OSVLookupError",
    "OSVVulnerabilityProvider",
    "PyPIUpdateError",
    "PyPIUpdateProvider",
]
