"""crates.io update provider: release/version lookup for any Rust crate.

Read-only (ADR-004) — a single GET per lookup, via the public
`https://crates.io/api/v1/crates/<name>` endpoint. Contains no knowledge of
any specific crate name (ADR-007): a pure ecosystem adapter, exactly like
`pypi.PyPIUpdateProvider` and `npm.NpmUpdateProvider`.

The HTTP layer is injectable (`http_get`), so no test in this codebase
needs a live network connection. Response shape verified live against the
real API (`GET /api/v1/crates/serde`), not guessed from documentation.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any

from system_intelligence.core.component_state import AvailableState, ComponentIdentity, ReleaseInfo
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.research.update_provider import ComponentUpdateError

_API_BASE = "https://crates.io/api/v1/crates"
_USER_AGENT = "system-intelligence-update-check/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://crates.io/api/v1/crates base (see `_API_BASE`); the only
    # variable part is a urlencoded crate name, so this never opens an
    # attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class CratesIoUpdateError(ComponentUpdateError):
    """Raised when the crates.io lookup itself fails (network, HTTP, or parse error)."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_version_entry(versions: Any, num: str) -> dict[str, Any] | None:
    """The entry in the response's top-level `versions` list matching `num`.

    That list only carries the crate's most recent versions (a paginated
    view, not the full history), so a match can legitimately be absent for
    an old `max_stable_version` -- callers must treat a `None` result as
    "no extra detail available", not as evidence the version doesn't exist.
    """
    if not isinstance(versions, list):
        return None
    for entry in versions:
        if isinstance(entry, dict) and entry.get("num") == num:
            return entry
    return None


class CratesIoUpdateProvider:
    name = "cargo"

    def __init__(self, *, http_get: HttpGet | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        url = f"{_API_BASE}/{urllib.parse.quote(identity.name)}"
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise CratesIoUpdateError(
                f"crates.io request failed for {identity.name!r}: {exc}"
            ) from exc
        if status == 404:
            return None
        if status >= 400:
            raise CratesIoUpdateError(f"crates.io returned HTTP {status} for {identity.name!r}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CratesIoUpdateError(
                f"crates.io returned invalid JSON for {identity.name!r}"
            ) from exc
        if not isinstance(data, dict):
            raise CratesIoUpdateError(f"Unexpected crates.io response shape for {identity.name!r}")

        crate = data.get("crate")
        if not isinstance(crate, dict):
            return None
        # max_stable_version (not newest_version) is the latest *stable*
        # release -- the same "latest a normal upgrade would land on"
        # meaning as PyPI's `info.version` and npm's `dist-tags.latest`.
        version = crate.get("max_stable_version")
        if not version:
            return None

        version_entry = _find_version_entry(data.get("versions"), version) or {}
        released_at = _parse_iso(version_entry.get("created_at"))

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=url,
                observation=f"crates.io API response for crate {identity.name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return AvailableState(
            identity=identity,
            provider=self.name,
            version=version,
            version_confidence=Confidence.VERIFIED,
            is_deprecated=None,  # crates.io's API does not report crate-level deprecation.
            runtime_requirements=[],
            release_info=ReleaseInfo(
                version=version,
                released_at=released_at,
                release_notes_url=None,
                is_prerelease=None,
                is_yanked=version_entry.get("yanked"),
            ),
            changelog=[],  # crates.io's API carries no structured changelog data.
            evidence=evidence,
        )
