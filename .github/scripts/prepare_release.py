#!/usr/bin/env python3
"""Decide whether this push to main warrants a release, and if so, bump the
version and generate a CHANGELOG.md entry.

Run by .github/workflows/release.yml, after release-drafter has already
resolved a candidate next version (from merged-PR labels) in dry-run mode.
This script owns the final decision so a manual version bump is never
silently overwritten:

- No git tag exists yet (first release ever): use whatever version is
  already in pyproject.toml as-is. There is no prior release to bump from.
- The current pyproject.toml version already matches the latest tag: no
  manual bump has happened since the last release, so it's safe to apply
  release-drafter's resolved version automatically.
- Otherwise (pyproject.toml's version is already ahead of the latest tag,
  e.g. a human bumped it by hand): respect that value verbatim. Never
  overwrite a deliberate manual bump with a guess.

If the decided version equals the latest tag's version (nothing to
release), this exits with should_release=false and touches no files.

Untrusted-input safety: every string this script deals with (commit
subjects via `git log`, etc.) is read via `subprocess.run([...])` argument
lists -- never through `shell=True` or interpolated into a shell command
string -- and is only ever written to files or GITHUB_OUTPUT, never fed
back into a shell invocation. This avoids the classic GitHub Actions
script-injection pattern of interpolating untrusted text (e.g. a PR title)
directly into a `run:` block.
"""

from __future__ import annotations

import datetime
import os
import re

# Every subprocess.run call below uses a fixed argv list (no shell=True,
# no string interpolation of untrusted data into a command), the same
# pattern cli/main.py's own one call site already documents as safe.
import subprocess
import sys
from pathlib import Path

# No trailing `\s*` before `$`: in MULTILINE mode `\s` also matches `\n`,
# and when this is the file's very last line (as `__init__.py`'s
# `__version__` line below always is), a trailing `\s*$` greedily
# consumes the file's own final newline into the match -- silently
# dropping it from the `.subn()` replacement, which has none of its own.
_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"$', re.MULTILINE)
_TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")


def read_pyproject_version(pyproject_path: Path) -> str:
    text = pyproject_path.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError(f'could not find a version = "..." line in {pyproject_path}')
    return match.group(1)


def write_pyproject_version(pyproject_path: Path, new_version: str) -> None:
    text = pyproject_path.read_text(encoding="utf-8")
    updated, count = _VERSION_RE.subn(f'version = "{new_version}"', text, count=1)
    if count != 1:
        raise ValueError(f'expected exactly one version = "..." line in {pyproject_path}')
    pyproject_path.write_text(updated, encoding="utf-8")


def write_init_version(init_path: Path, new_version: str) -> None:
    text = init_path.read_text(encoding="utf-8")
    # No trailing `\s*` before `$` -- see _VERSION_RE's own comment; this
    # line is always the file's last line, so the risk is not hypothetical.
    pattern = re.compile(r'^__version__\s*=\s*"([^"]+)"$', re.MULTILINE)
    updated, count = pattern.subn(f'__version__ = "{new_version}"', text, count=1)
    if count != 1:
        raise ValueError(f'expected exactly one __version__ = "..." line in {init_path}')
    init_path.write_text(updated, encoding="utf-8")


def get_latest_tag_version(repo_dir: Path) -> str | None:
    """Latest `vX.Y.Z`-shaped tag's version, or None if no such tag exists."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        match = _TAG_RE.match(line.strip())
        if match:
            return match.group(1)
    return None


def decide_new_version(
    current_version: str, latest_tag_version: str | None, resolved_version: str
) -> tuple[str, bool]:
    """Return (new_version, is_auto_bump).

    Pure decision logic, kept separate from all I/O so it can be unit
    tested directly (see the isolated-fixture validation this script's
    own PR describes running before this was ever wired into CI).
    """
    if latest_tag_version is None:
        # Bootstrap: no release has ever been tagged. Respect whatever
        # version is already in pyproject.toml rather than guessing.
        return current_version, False
    if current_version == latest_tag_version:
        # No manual bump since the last release -- safe to auto-bump.
        return resolved_version, True
    # pyproject.toml is already ahead of the latest tag (a manual bump).
    return current_version, False


def generate_changelog_entries(repo_dir: Path, since_tag_version: str | None) -> list[str]:
    """One `- <subject> (<short-sha>)` line per commit since the last
    release (or, on the very first release, every commit reachable from
    HEAD)."""
    range_arg = f"v{since_tag_version}..HEAD" if since_tag_version else "HEAD"
    result = subprocess.run(
        ["git", "log", range_arg, "--pretty=format:- %s (%h)", "--no-merges"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def render_changelog_section(version: str, entries: list[str]) -> str:
    date = datetime.datetime.now(datetime.UTC).date().isoformat()
    body = "\n".join(entries) if entries else "- No changes recorded."
    return f"## v{version} ({date})\n\n{body}\n"


def update_changelog_file(changelog_path: Path, section: str) -> None:
    header = "# Changelog\n\n"
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        if existing.startswith(header):
            existing = existing[len(header) :]
        new_content = header + section + "\n" + existing.lstrip("\n")
    else:
        new_content = header + section
    changelog_path.write_text(new_content, encoding="utf-8")


def _write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(f"{name}={value}")
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    repo_dir = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    pyproject_path = repo_dir / "pyproject.toml"
    init_path = repo_dir / "src" / "system_intelligence" / "__init__.py"
    changelog_path = repo_dir / "CHANGELOG.md"

    resolved_version = os.environ.get("RESOLVED_VERSION", "").strip()
    current_version = read_pyproject_version(pyproject_path)
    latest_tag_version = get_latest_tag_version(repo_dir)

    if not resolved_version:
        # release-drafter had nothing to resolve from (e.g. no merged PRs
        # carrying a version-resolver label yet) -- fall back to the
        # current version so the only path that can still trigger a
        # release is a manual bump.
        resolved_version = current_version

    new_version, is_auto_bump = decide_new_version(
        current_version, latest_tag_version, resolved_version
    )

    if new_version == latest_tag_version:
        print(f"Nothing to release: v{new_version} is already tagged.")
        _write_github_output("should_release", "false")
        return 0

    if is_auto_bump:
        write_pyproject_version(pyproject_path, new_version)
        write_init_version(init_path, new_version)

    entries = generate_changelog_entries(repo_dir, latest_tag_version)
    section = render_changelog_section(new_version, entries)
    update_changelog_file(changelog_path, section)

    # A standalone notes file (just this release's entries, no "## vX.Y.Z"
    # heading duplicated inside the GitHub Release body) for `gh release
    # create --notes-file`.
    release_notes_path = repo_dir / ".github" / "RELEASE_NOTES.md"
    notes_body = "\n".join(entries) if entries else "No changes recorded."
    release_notes_path.write_text(notes_body + "\n", encoding="utf-8")

    _write_github_output("should_release", "true")
    _write_github_output("new_version", new_version)
    _write_github_output("is_auto_bump", "true" if is_auto_bump else "false")
    _write_github_output("release_notes_path", str(release_notes_path.relative_to(repo_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
