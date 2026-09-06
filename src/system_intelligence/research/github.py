"""GitHub research provider: repository search via the public GitHub REST API.

Read-only (ADR-004) — only ever issues GET requests. Anti-hallucination rule
(docs/design/docs/06-research-engine.md): every `ResearchResult` field not
directly present in the API response is left `Confidence.UNKNOWN` rather
than guessed or invented.

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

_API_BASE = "https://api.github.com"
_USER_AGENT = "system-intelligence-research/0.1"

#: (url, headers) -> (http_status, response_body)
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Fixed https://api.github.com base (see `_API_BASE`); the only variable
    # part is a urlencoded query string, so this never opens an
    # attacker-controlled scheme or host.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


class GitHubResearchError(RuntimeError):
    """Raised when the GitHub API cannot be reached or returns an error status."""


class GitHubResearchProvider:
    name = "github"

    def __init__(self, *, token: str | None = None, http_get: HttpGet | None = None) -> None:
        self._token = token
        self._http_get = http_get or _default_http_get

    def search(self, query: str, *, limit: int = 10) -> list[ResearchResult]:
        params = urllib.parse.urlencode({"q": query, "per_page": min(max(limit, 1), 30)})
        data = self._get_json(f"{_API_BASE}/search/repositories?{params}")
        items = data.get("items", [])
        if not isinstance(items, list):
            raise GitHubResearchError("Unexpected GitHub search response shape")
        return [self._to_research_result(item, query) for item in items[:limit]]

    def fetch(self, identifier: str) -> ResearchResult:
        data = self._get_json(f"{_API_BASE}/repos/{identifier}")
        return self._to_research_result(data, query=identifier)

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            status, body = self._http_get(url, headers)
        except OSError as exc:
            raise GitHubResearchError(f"GitHub API request failed: {exc}") from exc
        if status >= 400:
            raise GitHubResearchError(f"GitHub API returned HTTP {status} for {url}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GitHubResearchError(f"GitHub API returned invalid JSON for {url}") from exc
        if not isinstance(data, dict):
            raise GitHubResearchError(f"Unexpected GitHub API response shape for {url}")
        return data

    def _to_research_result(self, item: dict[str, Any], query: str) -> ResearchResult:
        full_name = str(item.get("full_name") or query)
        license_info = item.get("license") or {}
        license_id = license_info.get("spdx_id") if isinstance(license_info, dict) else None
        if license_id == "NOASSERTION":
            license_id = None

        maintenance_signals: dict[str, str] = {}
        for key in ("pushed_at", "stargazers_count", "open_issues_count", "archived"):
            if key in item and item[key] is not None:
                maintenance_signals["last_push_at" if key == "pushed_at" else key] = str(item[key])

        evidence = [
            Evidence(
                kind=EvidenceKind.EXTERNAL_SOURCE,
                source=str(item.get("html_url") or f"{_API_BASE}/repos/{full_name}"),
                observation=f"GitHub API response for repository {full_name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]

        return ResearchResult(
            id=stable_id("research", "github", full_name),
            query=query,
            provider=self.name,
            source=str(item.get("html_url") or f"{_API_BASE}/repos/{full_name}"),
            identifier=full_name,
            evidence=evidence,
            license=license_id,
            license_confidence=Confidence.VERIFIED if license_id else Confidence.UNKNOWN,
            maintenance_signals=maintenance_signals,
            compatibility_assessment=None,
            compatibility_confidence=Confidence.UNKNOWN,
            functional_fit_notes=None,
        )
