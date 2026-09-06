"""Resolve a user-supplied locator into a `Target` (R1).

Two locator shapes are recognized: a local filesystem path, and a GitHub
repository (`owner/repo` shorthand or a `https://github.com/...` URL —
see `discovery.github_target`), which is shallow-cloned read-only into a
temporary directory and then resolved exactly like any local path.
Manifest/ecosystem targets remain future work (see
docs/design/docs/02-requirements.md, R1).
"""

from __future__ import annotations

from pathlib import Path

from system_intelligence.core.entities import Target
from system_intelligence.core.enums import TargetKind
from system_intelligence.discovery.github_target import (
    GitHubTargetError,
    clone_github_repository,
    is_github_spec,
)


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


def resolve_target(locator: str) -> Target:
    """Resolve `locator` into a `Target`, whether it's a local path or a
    GitHub repository spec.

    A GitHub spec (`discovery.github_target.is_github_spec`) is
    shallow-cloned first, then resolved exactly like any local path but
    with `kind=GITHUB_REPOSITORY` and `name` set to the original spec
    (e.g. `octocat/Hello-World`) rather than a temp-directory basename.
    Raises `TargetResolutionError` either way — a failed clone (network,
    a private/nonexistent repository, no `git` on PATH) is a resolution
    failure exactly like a missing local path, so every existing caller
    only ever needs to catch the one exception type.
    """
    if is_github_spec(locator):
        try:
            clone_path = clone_github_repository(locator)
        except GitHubTargetError as exc:
            raise TargetResolutionError(str(exc)) from exc
        target = resolve_local_target(str(clone_path))
        return target.model_copy(update={"kind": TargetKind.GITHUB_REPOSITORY, "name": locator})
    return resolve_local_target(locator)
