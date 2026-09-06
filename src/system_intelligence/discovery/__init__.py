"""Discovery adapters: resolve a Target into Repositories/Components.

Phase 2 scope (see docs/design/docs/16-roadmap.md and
docs/design/IMPLEMENTATION_BACKLOG.md, Epic 3): local repository scanning,
git metadata, standard `SKILL.md` detection, CI workflow detection, and
root-document detection, orchestrated by `discover_local_repository`.

Not yet implemented: a GitHub read adapter, package-manifest dependency
resolution, and agent detection beyond the Skill format.
"""

from system_intelligence.discovery.inventory import DiscoveryResult, discover_local_repository
from system_intelligence.discovery.target import TargetResolutionError, resolve_local_target

__all__ = [
    "DiscoveryResult",
    "TargetResolutionError",
    "discover_local_repository",
    "resolve_local_target",
]
