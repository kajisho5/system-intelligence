"""MCP Registry research provider: server search via the public
registry.modelcontextprotocol.io REST API.

Read-only (ADR-004) — only ever issues GET requests. Anti-hallucination
rule (docs/design/docs/06-research-engine.md): every `ResearchResult`
field not directly present in the API response is left `Confidence.UNKNOWN`
rather than guessed or invented.

Verified against the live API (`GET /v0.1/servers`, `GET /v0.1/servers/
{name}/versions/{version}`) and the `server.json` schema during the
External Architecture Research pass: a listed server carries `name`
(reverse-DNS, e.g. "io.github.user/weather"), `description`, `version`,
`repository`, `packages`/`remotes` — and, critically, **no license,
maintenance-activity, or popularity field of any kind**. Being listed
here proves only that the publisher owns the claimed namespace (the
registry's own docs: "namespace authentication and metadata hosting" —
it explicitly does not scan or evaluate the server's code). This provider
must never synthesize a license/maintenance signal to look consistent
with `GitHubResearchProvider`; both stay `Confidence.UNKNOWN` for every
result, always.

The HTTP layer is injectable (`http_get`) so callers — and every test in
this codebase — never need a live network connection.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id
from system_intelligence.core.research import ResearchResult

_API_BASE = "https://registry.modelcontextprotocol.io"
_USER_AGENT = "system-intelligence-research/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://registry.modelcontextprotocol.io base (see `_API_BASE`);
    # the only variable part is a urlencoded query string or path segment,
    # so this never opens an attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class MCPRegistryError(RuntimeError):
    """Raised when the MCP Registry API cannot be reached or returns an error status."""


class MCPRegistryResearchProvider:
    name = "mcp-registry"

    def __init__(self, *, http_get: HttpGet | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def search(self, query: str, *, limit: int = 10) -> list[ResearchResult]:
        params = urllib.parse.urlencode({"search": query, "limit": min(max(limit, 1), 100)})
        data = self._get_json(f"{_API_BASE}/v0.1/servers?{params}")
        items = data.get("servers", [])
        if not isinstance(items, list):
            raise MCPRegistryError("Unexpected MCP Registry search response shape")

        results: list[ResearchResult] = []
        for item in items[:limit]:
            server = item.get("server") if isinstance(item, dict) else None
            if not isinstance(server, dict):
                continue
            results.append(self._to_research_result(server, query))
        return results

    def fetch(self, identifier: str) -> ResearchResult:
        encoded = urllib.parse.quote(identifier, safe="")
        data = self._get_json(f"{_API_BASE}/v0.1/servers/{encoded}/versions/latest")
        server = data.get("server")
        if not isinstance(server, dict):
            raise MCPRegistryError(f"Unexpected MCP Registry response shape for {identifier!r}")
        return self._to_research_result(server, query=identifier)

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise MCPRegistryError(f"MCP Registry request failed: {exc}") from exc
        if status >= 400:
            raise MCPRegistryError(f"MCP Registry returned HTTP {status} for {url}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise MCPRegistryError(f"MCP Registry returned invalid JSON for {url}") from exc
        if not isinstance(data, dict):
            raise MCPRegistryError(f"Unexpected MCP Registry response shape for {url}")
        return data

    def _to_research_result(self, server: dict[str, Any], query: str) -> ResearchResult:
        name = str(server.get("name") or query)
        repository = server.get("repository")
        repo_url = repository.get("url") if isinstance(repository, dict) else None
        website_url = server.get("websiteUrl")
        fallback_source = f"{_API_BASE}/v0.1/servers/{urllib.parse.quote(name, safe='')}"
        source = str(repo_url or website_url or fallback_source)

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=source,
                observation=f"MCP Registry entry for server {name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return ResearchResult(
            id=stable_id("research", "mcp-registry", name),
            query=query,
            provider=self.name,
            source=source,
            identifier=name,
            evidence=evidence,
            # The registry's own server.json schema has no license field —
            # never inferred from the repository host or anything else.
            license=None,
            license_confidence=Confidence.UNKNOWN,
            # Likewise no maintenance/activity/popularity field exists here.
            maintenance_signals={},
            compatibility_assessment=None,
            compatibility_confidence=Confidence.UNKNOWN,
            functional_fit_notes=None,
        )
