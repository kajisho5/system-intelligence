"""Discovery adapters: resolve a Target into Repositories/Components.

Phase 2 scope (see docs/design/docs/16-roadmap.md and
docs/design/IMPLEMENTATION_BACKLOG.md, Epic 3): local repository scanning,
a read-only GitHub-repository adapter (`discovery.github_target` — shallow
clone, then treated as any other local path), git metadata, standard
`SKILL.md` detection, CI workflow detection, ADR detection, and
root-document detection, and Capability Contract collection
(`discovery.contracts`: a target's static `.si/contracts.json`, plus
operator-supplied contract files/commands, ADR-011), and ownership-map
collection (`discovery.ownership`: a target's static `.si/ownership.json`
and the maps it lists, plus operator-supplied maps; files only, ADR-012),
orchestrated by `discover_local_repository`. `discovery.roadmaps` reads an
ecosystem's checkbox roadmaps and pull-request lists, from local checkouts
or the GitHub API, for `analysis.roadmap_drift` (ADR-015).

Not yet implemented: agent detection beyond the Skill format (no
verified, generic file convention for it has been found).
"""

from system_intelligence.discovery.inventory import DiscoveryResult, discover_local_repository
from system_intelligence.discovery.target import (
    TargetResolutionError,
    resolve_local_target,
    resolve_target,
)

__all__ = [
    "DiscoveryResult",
    "TargetResolutionError",
    "discover_local_repository",
    "resolve_local_target",
    "resolve_target",
]
