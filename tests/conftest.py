"""Shared test helpers."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def make_symlink() -> Callable[[Path, Path], None]:
    """Create `link` pointing at `target`, or skip where the OS refuses (ADR-014).

    Only Windows can refuse: creating a symlink there needs
    SeCreateSymbolicLinkPrivilege (an elevated account or Developer Mode).
    GitHub's Windows runners have it, so CI runs these tests on every OS;
    the skip exists for an unprivileged Windows workstation. On any other
    OS a failure is a real error and is raised.
    """

    def _make(link: Path, target: Path) -> None:
        try:
            link.symlink_to(target)
        except OSError as exc:
            if os.name != "nt":
                raise
            pytest.skip(
                "this Windows account may not create symlinks "
                f"(needs SeCreateSymbolicLinkPrivilege: admin or Developer Mode): {exc}"
            )

    return _make
