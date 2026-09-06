"""OSV.dev vulnerability provider: known-advisory lookup for pypi/npm packages.

Read-only (ADR-004) — a single POST per lookup, via OSV.dev's public
`https://api.osv.dev/v1/query` endpoint (no API key required). Contains no
knowledge of any specific package name (ADR-007); `ecosystem` is passed in
by the caller exactly as OSV.dev itself names it (e.g. "PyPI", "npm" —
case-sensitive, confirmed against the live API, not guessed).

The HTTP layer is injectable (`http_get`), so no test in this codebase
needs a live network connection.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.security import SecurityAdvisory
from system_intelligence.research.vulnerability_provider import VulnerabilityLookupError

_API_URL = "https://api.osv.dev/v1/query"
_USER_AGENT = "system-intelligence-vulnerability-check/0.1"

#: (url, headers, body) -> (http_status, response_body)
HttpPost = Callable[[str, dict[str, str], bytes], tuple[int, bytes]]


def _default_http_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
    # Fixed https://api.osv.dev/v1/query URL (see `_API_URL`) -- the body is
    # the only variable part, so this never opens an attacker-controlled
    # scheme or host.
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class OSVLookupError(VulnerabilityLookupError):
    """Raised when the OSV.dev lookup itself fails (network, HTTP, or parse error)."""


def _advisory_from_vuln(vuln: object) -> SecurityAdvisory | None:
    if not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str):
        return None
    database_specific = vuln.get("database_specific")
    severity = None
    if isinstance(database_specific, dict) and isinstance(database_specific.get("severity"), str):
        severity = database_specific["severity"]
    aliases = vuln.get("aliases")
    references = vuln.get("references")
    url = None
    if isinstance(references, list):
        for reference in references:
            if isinstance(reference, dict) and isinstance(reference.get("url"), str):
                url = reference["url"]
                break
    return SecurityAdvisory(
        id=vuln["id"],
        summary=vuln.get("summary") or vuln.get("details") or "No summary provided by the source.",
        severity=severity,
        aliases=[a for a in aliases if isinstance(a, str)] if isinstance(aliases, list) else [],
        url=url,
    )


class OSVVulnerabilityProvider:
    """OSV.dev adapter for one ecosystem (e.g. `OSVVulnerabilityProvider("pypi", "PyPI")`)."""

    def __init__(self, name: str, osv_ecosystem: str, *, http_post: HttpPost | None = None) -> None:
        self.name = name
        self._osv_ecosystem = osv_ecosystem
        self._http_post = http_post or _default_http_post

    def fetch_advisories(self, identity: ComponentIdentity, version: str) -> list[SecurityAdvisory]:
        package = {"name": identity.name, "ecosystem": self._osv_ecosystem}
        payload = json.dumps({"version": version, "package": package}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        try:
            status, body = self._http_post(_API_URL, headers, payload)
        except OSError as exc:
            raise OSVLookupError(f"OSV.dev request failed for {identity.name!r}: {exc}") from exc
        if status >= 400:
            raise OSVLookupError(f"OSV.dev returned HTTP {status} for {identity.name!r}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OSVLookupError(f"OSV.dev returned invalid JSON for {identity.name!r}") from exc
        if not isinstance(data, dict):
            raise OSVLookupError(f"Unexpected OSV.dev response shape for {identity.name!r}")

        vulns = data.get("vulns")
        if not isinstance(vulns, list):
            return []
        advisories = [_advisory_from_vuln(v) for v in vulns]
        return [a for a in advisories if a is not None]
