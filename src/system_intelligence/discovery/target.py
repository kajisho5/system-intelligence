"""Resolve a user-supplied locator into a `Target` (R1).

Phase 2 only resolves local filesystem paths. GitHub/manifest/ecosystem
targets are future work (see docs/design/docs/02-requirements.md, R1).
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import Target
from system_intelligence.core.enums import TargetKind


class TargetResolutionError(ValueError):
    """Raised when a locator cannot be resolved to a Target."""


def resolve_local_target(locator: str) -> Target:
    """Resolve a local filesystem path into a `Target`.

    Raises `TargetResolutionError` if the path does not exist or is not a
    directory — discovery cannot proceed without a real filesystem root.
    """
    path = Path(locator).expanduser().resolve()
    if not path.exists():
        raise TargetResolutionError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise TargetResolutionError(f"Path is not a directory: {path}")
    return Target(name=path.name, kind=TargetKind.LOCAL_PATH, locator=str(path))
