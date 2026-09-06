"""Generic ecosystem adapters implementing `research.update_provider.ComponentUpdateProvider`.

Every adapter here knows about one package ecosystem's public registry API
and nothing else — no package name, repository, or organization is
hard-coded (ADR-007). Target-specific integrations (a project's own
internal registry or Capability Contract format) belong in
`system_intelligence.integrations`, not here.
"""

from system_intelligence.research.providers.npm import NpmUpdateError, NpmUpdateProvider
from system_intelligence.research.providers.pypi import PyPIUpdateError, PyPIUpdateProvider

__all__ = ["NpmUpdateError", "NpmUpdateProvider", "PyPIUpdateError", "PyPIUpdateProvider"]
