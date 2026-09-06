import json

import pytest

from system_intelligence.core.enums import Confidence
from system_intelligence.research.github import GitHubResearchError, GitHubResearchProvider

_SEARCH_RESPONSE = {
    "items": [
        {
            "full_name": "psf/black",
            "html_url": "https://github.com/psf/black",
            "license": {"spdx_id": "MIT"},
            "pushed_at": "2026-08-01T00:00:00Z",
            "stargazers_count": 12345,
            "open_issues_count": 10,
            "archived": False,
        },
        {
            "full_name": "someone/abandoned-tool",
            "html_url": "https://github.com/someone/abandoned-tool",
            "license": None,
            "pushed_at": "2015-01-01T00:00:00Z",
            "stargazers_count": 999999,
            "archived": True,
        },
    ]
}


def _fake_http_get(response_status: int, response_body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return response_status, response_body

    return _get


def test_search_parses_license_and_maintenance_signals() -> None:
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = GitHubResearchProvider(http_get=http_get)

    results = provider.search("black formatter")

    assert len(results) == 2
    black = next(r for r in results if r.identifier == "psf/black")
    assert black.license == "MIT"
    assert black.license_confidence == Confidence.VERIFIED
    assert black.maintenance_signals["stargazers_count"] == "12345"
    assert black.maintenance_signals["archived"] == "False"
    assert black.evidence
    assert black.provider == "github"


def test_search_missing_license_is_unknown_confidence() -> None:
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = GitHubResearchProvider(http_get=http_get)

    results = provider.search("abandoned")

    abandoned = next(r for r in results if r.identifier == "someone/abandoned-tool")
    assert abandoned.license is None
    assert abandoned.license_confidence == Confidence.UNKNOWN
    # Never invented: functional/compatibility fit stays unknown.
    assert abandoned.compatibility_confidence == Confidence.UNKNOWN
    assert abandoned.functional_fit_notes is None


def test_search_respects_limit() -> None:
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = GitHubResearchProvider(http_get=http_get)

    results = provider.search("x", limit=1)

    assert len(results) == 1


def test_fetch_single_repository() -> None:
    body = json.dumps(_SEARCH_RESPONSE["items"][0]).encode()
    provider = GitHubResearchProvider(http_get=_fake_http_get(200, body))

    result = provider.fetch("psf/black")

    assert result.identifier == "psf/black"
    assert result.query == "psf/black"


def test_http_error_status_raises_research_error() -> None:
    provider = GitHubResearchProvider(http_get=_fake_http_get(404, b'{"message": "Not Found"}'))

    with pytest.raises(GitHubResearchError, match="404"):
        provider.search("nonexistent")


def test_network_failure_raises_research_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("connection refused")

    provider = GitHubResearchProvider(http_get=_raise)

    with pytest.raises(GitHubResearchError, match="request failed"):
        provider.search("x")


def test_invalid_json_raises_research_error() -> None:
    provider = GitHubResearchProvider(http_get=_fake_http_get(200, b"not json"))

    with pytest.raises(GitHubResearchError, match="invalid JSON"):
        provider.search("x")


def test_non_dict_response_raises_research_error() -> None:
    provider = GitHubResearchProvider(http_get=_fake_http_get(200, b"[1, 2, 3]"))

    with pytest.raises(GitHubResearchError, match="Unexpected GitHub API response shape"):
        provider.search("x")


def test_non_list_items_raises_research_error() -> None:
    provider = GitHubResearchProvider(
        http_get=_fake_http_get(200, json.dumps({"items": "x"}).encode())
    )

    with pytest.raises(GitHubResearchError, match="Unexpected GitHub search response shape"):
        provider.search("x")


def test_noassertion_license_treated_as_unknown() -> None:
    body = json.dumps(
        {"items": [{"full_name": "a/a", "license": {"spdx_id": "NOASSERTION"}}]}
    ).encode()
    provider = GitHubResearchProvider(http_get=_fake_http_get(200, body))

    results = provider.search("x")

    assert results[0].license is None
    assert results[0].license_confidence == Confidence.UNKNOWN


def test_token_sent_as_authorization_header() -> None:
    captured: dict[str, str] = {}

    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        captured.update(headers)
        return 200, json.dumps({"items": []}).encode()

    provider = GitHubResearchProvider(token="ghp_secret", http_get=_get)
    provider.search("x")

    assert captured["Authorization"] == "Bearer ghp_secret"
