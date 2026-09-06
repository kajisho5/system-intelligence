"""Go module proxy update provider: release/version lookup for any Go module.

Read-only (ADR-004) — a single GET per lookup, via the public
`https://proxy.golang.org/<module>/@latest` endpoint (the same proxy `go
get` itself uses). Contains no knowledge of any specific module path
(ADR-007): a pure ecosystem adapter, exactly like `pypi.PyPIUpdateProvider`,
`npm.NpmUpdateProvider`, and `crates_io.CratesIoUpdateProvider`.

The Go module proxy protocol requires escaping every uppercase letter in a
module path as `!<lowercase letter>` (case-insensitive-filesystem safety —
see https://go.dev/ref/mod#module-proxy) — verified live against a real
mixed-case module (`github.com/Masterminds/semver` ->
`github.com/!masterminds/semver`), not guessed from documentation.

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

_API_BASE = "https://proxy.golang.org"
_USER_AGENT = "system-intelligence-update-check/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://proxy.golang.org base (see `_API_BASE`); the only
    # variable part is an escaped module path, so this never opens an
    # attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class GoProxyUpdateError(ComponentUpdateError):
    """Raised when the module proxy lookup itself fails (network, HTTP, or parse error)."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _escape_module_path(module_path: str) -> str:
    """Escape every uppercase letter as `!<lowercase letter>`, per the Go
    module proxy protocol's case-insensitive-filesystem-safety rule."""
    return "".join(f"!{char.lower()}" if char.isupper() else char for char in module_path)


class GoProxyUpdateProvider:
    name = "go"

    def __init__(self, *, http_get: HttpGet | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        escaped_path = _escape_module_path(identity.name)
        encoded_path = urllib.parse.quote(escaped_path, safe="/!")
        url = f"{_API_BASE}/{encoded_path}/@latest"
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise GoProxyUpdateError(
                f"Go module proxy request failed for {identity.name!r}: {exc}"
            ) from exc
        if status == 404:
            return None
        if status >= 400:
            raise GoProxyUpdateError(
                f"Go module proxy returned HTTP {status} for {identity.name!r}"
            )
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GoProxyUpdateError(
                f"Go module proxy returned invalid JSON for {identity.name!r}"
            ) from exc
        if not isinstance(data, dict):
            raise GoProxyUpdateError(
                f"Unexpected Go module proxy response shape for {identity.name!r}"
            )

        version = data.get("Version")
        if not version:
            return None

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=url,
                observation=f"Go module proxy @latest response for module {identity.name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return AvailableState(
            identity=identity,
            provider=self.name,
            version=version,
            version_confidence=Confidence.VERIFIED,
            is_deprecated=None,  # The proxy's @latest endpoint does not report deprecation.
            runtime_requirements=[],
            release_info=ReleaseInfo(
                version=version,
                released_at=_parse_iso(data.get("Time")),
                release_notes_url=None,
                is_prerelease=None,
                is_yanked=None,  # Go has no "yanked" concept distinct from retraction.
            ),
            changelog=[],  # The module proxy carries no structured changelog data.
            evidence=evidence,
        )
