"""npm update provider: release/version lookup for any npm package.

Read-only (ADR-004) — a single GET per lookup, via the public
`https://registry.npmjs.org/<name>` endpoint. Contains no knowledge of any
specific package name (ADR-007).

The HTTP layer is injectable (`http_get`), so no test in this codebase
needs a live network connection.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime

from system_intelligence.core.component_state import AvailableState, ComponentIdentity, ReleaseInfo
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.research.update_provider import ComponentUpdateError

_API_BASE = "https://registry.npmjs.org"
_USER_AGENT = "system-intelligence-update-check/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://registry.npmjs.org base (see `_API_BASE`); the only
    # variable part is a urlencoded package name, so this never opens an
    # attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class NpmUpdateError(ComponentUpdateError):
    """Raised when the npm lookup itself fails (network, HTTP, or parse error)."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class NpmUpdateProvider:
    name = "npm"

    def __init__(self, *, http_get: HttpGet | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        # '@' and '/' must survive unescaped for scoped packages (@scope/name).
        encoded_name = urllib.parse.quote(identity.name, safe="@/")
        url = f"{_API_BASE}/{encoded_name}"
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise NpmUpdateError(f"npm request failed for {identity.name!r}: {exc}") from exc
        if status == 404:
            return None
        if status >= 400:
            raise NpmUpdateError(f"npm registry returned HTTP {status} for {identity.name!r}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NpmUpdateError(
                f"npm registry returned invalid JSON for {identity.name!r}"
            ) from exc
        if not isinstance(data, dict):
            raise NpmUpdateError(f"Unexpected npm registry response shape for {identity.name!r}")

        dist_tags = data.get("dist-tags") or {}
        latest = dist_tags.get("latest") if isinstance(dist_tags, dict) else None
        if not latest:
            return None

        versions = data.get("versions") or {}
        version_info = versions.get(latest) or {} if isinstance(versions, dict) else {}
        time_info = data.get("time") or {}
        released_at = _parse_iso(time_info.get(latest)) if isinstance(time_info, dict) else None

        is_deprecated = (
            bool(version_info.get("deprecated")) if isinstance(version_info, dict) else None
        )

        runtime_requirements: list[str] = []
        engines = version_info.get("engines") if isinstance(version_info, dict) else None
        if isinstance(engines, dict):
            runtime_requirements = [f"{name}{constraint}" for name, constraint in engines.items()]

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=url,
                observation=f"npm registry response for package {identity.name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return AvailableState(
            identity=identity,
            provider=self.name,
            version=latest,
            version_confidence=Confidence.VERIFIED,
            is_deprecated=is_deprecated,
            runtime_requirements=runtime_requirements,
            release_info=ReleaseInfo(
                version=latest,
                released_at=released_at,
                release_notes_url=None,
                is_prerelease=None,
                is_yanked=None,  # npm has no "yanked" concept distinct from deprecation.
            ),
            changelog=[],  # npm's registry API carries no structured changelog data.
            evidence=evidence,
        )
