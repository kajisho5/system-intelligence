"""PyPI update provider: release/version lookup for any PyPI package.

Read-only (ADR-004) — a single GET per lookup, via the public
`https://pypi.org/pypi/<name>/json` endpoint. Contains no knowledge of any
specific package name (ADR-007): it is a pure ecosystem adapter, exactly
like `research.github.GitHubResearchProvider` knows nothing about which
repository it is asked to search.

The HTTP layer is injectable (`http_get`), so no test in this codebase
needs a live network connection.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any

from system_intelligence.core.component_state import (
    AvailableState,
    ChangelogEntry,
    ComponentIdentity,
    ReleaseInfo,
)
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.research.update_provider import ComponentUpdateError

_API_BASE = "https://pypi.org/pypi"
_USER_AGENT = "system-intelligence-update-check/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://pypi.org/pypi base (see `_API_BASE`); the only variable
    # part is a urlencoded package name, so this never opens an
    # attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class PyPIUpdateError(ComponentUpdateError):
    """Raised when the PyPI lookup itself fails (network, HTTP, or parse error)."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_changelog(info: dict[str, Any], version: str) -> list[ChangelogEntry]:
    project_urls = info.get("project_urls")
    if not isinstance(project_urls, dict):
        return []
    entries: list[ChangelogEntry] = []
    for label, url in project_urls.items():
        if isinstance(label, str) and "changelog" in label.lower() and url:
            entries.append(
                ChangelogEntry(
                    version=version,
                    summary=f"Changelog link declared in PyPI project metadata ({label!r}).",
                    url=str(url),
                )
            )
    return entries


class PyPIUpdateProvider:
    name = "pypi"

    def __init__(self, *, http_get: HttpGet | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        url = f"{_API_BASE}/{urllib.parse.quote(identity.name)}/json"
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise PyPIUpdateError(f"PyPI request failed for {identity.name!r}: {exc}") from exc
        if status == 404:
            return None
        if status >= 400:
            raise PyPIUpdateError(f"PyPI returned HTTP {status} for {identity.name!r}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise PyPIUpdateError(f"PyPI returned invalid JSON for {identity.name!r}") from exc
        if not isinstance(data, dict):
            raise PyPIUpdateError(f"Unexpected PyPI response shape for {identity.name!r}")

        info = data.get("info") or {}
        version = info.get("version")
        if not version:
            return None

        release_files = (data.get("releases") or {}).get(version) or []
        released_at = None
        if isinstance(release_files, list) and release_files:
            released_at = _parse_iso(release_files[0].get("upload_time_iso_8601"))

        runtime_requirements = []
        requires_python = info.get("requires_python")
        if requires_python:
            runtime_requirements.append(f"python{requires_python}")

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=url,
                observation=f"PyPI JSON API response for package {identity.name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return AvailableState(
            identity=identity,
            provider=self.name,
            version=version,
            version_confidence=Confidence.VERIFIED,
            is_deprecated=None,  # PyPI's JSON API does not report package-level deprecation.
            runtime_requirements=runtime_requirements,
            release_info=ReleaseInfo(
                version=version,
                released_at=released_at,
                release_notes_url=None,
                is_prerelease=None,
                is_yanked=info.get("yanked"),
            ),
            changelog=_extract_changelog(info, version),
            evidence=evidence,
        )
