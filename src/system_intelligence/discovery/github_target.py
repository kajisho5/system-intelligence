"""GitHub-repository-as-target resolution (Epic 3's "GitHub adapter" gap).

Read-only: shallow-clones (`git clone --depth 1`, a single-branch checkout,
no push remote ever configured) into a fresh temporary directory. Nothing
downstream needs to know the difference — discovery, analysis, and every
existing `si` command already work on "a local directory" and are
otherwise unchanged.

The cloned directory is intentionally left on disk after the command
finishes, exactly like a user-supplied local path is never deleted either
— cleanup is the caller's concern if it matters, not something this
module or `si` does implicitly on the caller's behalf.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_SHORTHAND_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?/[A-Za-z0-9._-]+$")
_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")


class GitHubTargetError(Exception):
    """Raised when a GitHub repository spec cannot be resolved or cloned."""


def is_github_spec(locator: str) -> bool:
    """True if `locator` names a GitHub repository rather than a local path.

    Accepts `owner/repo` shorthand and `https://github.com/owner/repo[.git]`
    URLs. The URL form is unambiguous. The shorthand form is only accepted
    when no local directory of that exact relative name exists, so an
    ordinary two-level local path (e.g. `build/output`) is never misread
    as a GitHub spec.
    """
    if _URL_RE.match(locator):
        return True
    return bool(_SHORTHAND_RE.match(locator)) and not Path(locator).exists()


def _clone_url(spec: str) -> str:
    match = _URL_RE.match(spec)
    if match:
        owner, repo = match.group(1), match.group(2)
        return f"https://github.com/{owner}/{repo}.git"
    return f"https://github.com/{spec}.git"


def clone_github_repository(spec: str) -> Path:
    """Shallow-clone the GitHub repository `spec` into a fresh temp directory.

    Raises `GitHubTargetError` if `git` is unavailable or the clone fails
    (repository not found, network unreachable, private without
    credentials, ...) — the underlying `git` stderr is surfaced verbatim
    rather than guessed at.
    """
    git_path = shutil.which("git")
    if git_path is None:
        raise GitHubTargetError("git is not installed or not on PATH")

    url = _clone_url(spec)
    dest = Path(tempfile.mkdtemp(prefix="si-github-"))
    # Fixed argv, no shell; `url` is built by `_clone_url` from a spec this
    # module itself validated as a github.com HTTPS URL, never interpolated
    # from an arbitrary untrusted string into a shell command.
    result = subprocess.run(  # nosec B603
        [git_path, "clone", "--depth", "1", "--quiet", url, str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise GitHubTargetError(f"failed to clone {spec!r}: {result.stderr.strip()}")
    return dest
