"""Maven Central update provider: release/version lookup for any Maven artifact.

Read-only (ADR-004) — a single GET per lookup, via Maven Central's own
`maven-metadata.xml` (the same file Maven itself consults to resolve
`RELEASE`/`LATEST` version placeholders):
`https://repo1.maven.org/maven2/<group-path>/<artifactId>/maven-metadata.xml`.
Contains no knowledge of any specific Maven coordinate (ADR-007): a pure
ecosystem adapter, exactly like `pypi.PyPIUpdateProvider`,
`npm.NpmUpdateProvider`, `crates_io.CratesIoUpdateProvider`, and
`go_proxy.GoProxyUpdateProvider`.

`<release>` (falling back to `<latest>` when `<release>` is absent — Maven's
metadata spec allows a `latest`-only file when every published version is a
pre-release/snapshot) is the authoritative "latest stable" pointer. Using it
resolves a design question this provider would otherwise have to guess at:
some coordinates (e.g. `com.google.guava:guava`) publish more than one
version *flavor* under the same groupId:artifactId (Guava's `-jre` and
`-android` builds, published independently and interleaved in time) — the
Maven Central Search API's own default sort order (score, then timestamp)
does not reliably pick one, but `<release>` does, since it is set by Maven
Central itself rather than inferred from a sorted list. Verified live
against `https://repo1.maven.org/maven2/com/google/guava/guava/maven-metadata.xml`,
whose `<release>` names one specific flavor (`33.7.1-jre`).

The identity name is the manifest's own `groupId:artifactId` form (see
`analysis.dependencies._extract_pom_dependencies`); a name with no `:`
separator is not a Maven coordinate this provider can look up.

The HTTP layer is injectable (`http_get`), so no test in this codebase
needs a live network connection. Response shape verified live against the
real endpoint (`com.google.guava:guava`, `com.google.code.gson:gson`), not
guessed from documentation.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from defusedxml import ElementTree as SafeElementTree

from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ReleaseInfo,
)
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.research.update_provider import ComponentUpdateError

_API_BASE = "https://repo1.maven.org/maven2"
_USER_AGENT = "system-intelligence-update-check/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://repo1.maven.org/maven2 base (see `_API_BASE`); the only
    # variable part is a urlencoded groupId/artifactId, so this never opens
    # an attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class MavenCentralUpdateError(ComponentUpdateError):
    """Raised when the Maven Central lookup itself fails (network, HTTP, or parse error)."""


def _parse_last_updated(value: str | None) -> datetime | None:
    """Maven's own `yyyyMMddHHmmss` (UTC) `<lastUpdated>` timestamp format."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _element_text(parent: Any, tag: str) -> str | None:
    element = parent.find(tag)
    if element is None or not element.text:
        return None
    return str(element.text).strip()


class MavenCentralUpdateProvider:
    name = "maven"

    def __init__(self, *, http_get: HttpGet | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        group_id, separator, artifact_id = identity.name.partition(":")
        if not separator or not group_id or not artifact_id:
            return None
        group_path = "/".join(urllib.parse.quote(segment) for segment in group_id.split("."))
        url = f"{_API_BASE}/{group_path}/{urllib.parse.quote(artifact_id)}/maven-metadata.xml"
        headers = {"Accept": "application/xml", "User-Agent": _USER_AGENT}
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise MavenCentralUpdateError(
                f"Maven Central request failed for {identity.name!r}: {exc}"
            ) from exc
        if status == 404:
            return None
        if status >= 400:
            raise MavenCentralUpdateError(
                f"Maven Central returned HTTP {status} for {identity.name!r}"
            )
        try:
            root = SafeElementTree.fromstring(body)
        except SafeElementTree.ParseError as exc:
            raise MavenCentralUpdateError(
                f"Maven Central returned invalid XML for {identity.name!r}: {exc}"
            ) from exc

        versioning = root.find("versioning")
        if versioning is None:
            return None
        version = _element_text(versioning, "release") or _element_text(versioning, "latest")
        if not version:
            return None

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=url,
                observation=f"Maven Central metadata for artifact {identity.name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return AvailableState(
            identity=identity,
            provider=self.name,
            version=version,
            version_confidence=Confidence.VERIFIED,
            is_deprecated=None,  # Maven Central's metadata does not report deprecation.
            runtime_requirements=[],
            release_info=ReleaseInfo(
                version=version,
                released_at=_parse_last_updated(_element_text(versioning, "lastUpdated")),
                release_notes_url=None,
                is_prerelease=None,
                is_yanked=None,  # Maven Central has no "yanked" concept.
            ),
            changelog=[],  # Maven Central's metadata carries no structured changelog data.
            evidence=evidence,
        )
