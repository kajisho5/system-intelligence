import json

import pytest

from system_intelligence.core.enums import Confidence
from system_intelligence.research.mcp_registry import MCPRegistryError, MCPRegistryResearchProvider

_SEARCH_RESPONSE = {
    "servers": [
        {
            "server": {
                "$schema": "https://static.modelcontextprotocol.io/schemas/2025-09-29/server.schema.json",
                "name": "com.pulsemcp/remote-filesystem",
                "description": "MCP server for remote filesystem operations on cloud storage.",
                "repository": {
                    "url": "https://github.com/pulsemcp/mcp-servers",
                    "source": "github",
                    "subfolder": "experimental/remote-filesystem",
                },
                "version": "0.1.2",
                "packages": [{"registryType": "npm", "identifier": "remote-filesystem-mcp-server"}],
            }
        },
        {
            "server": {
                "name": "io.github.example/no-repo-server",
                "description": "A server with no repository field, only a website.",
                "version": "1.0.0",
                "websiteUrl": "https://example.com/no-repo-server",
            }
        },
    ],
    "metadata": {"nextCursor": "com.pulsemcp/remote-filesystem:0.1.2", "count": 2},
}


def _fake_http_get(response_status: int, response_body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return response_status, response_body

    return _get


def test_search_parses_server_entries() -> None:
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = MCPRegistryResearchProvider(http_get=http_get)

    results = provider.search("filesystem")

    assert len(results) == 2
    fs = next(r for r in results if r.identifier == "com.pulsemcp/remote-filesystem")
    assert fs.source == "https://github.com/pulsemcp/mcp-servers"
    assert fs.provider == "mcp-registry"
    assert fs.evidence


def test_search_falls_back_to_website_url_when_no_repository() -> None:
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = MCPRegistryResearchProvider(http_get=http_get)

    results = provider.search("no-repo")

    no_repo = next(r for r in results if r.identifier == "io.github.example/no-repo-server")
    assert no_repo.source == "https://example.com/no-repo-server"


def test_no_license_or_maintenance_signal_is_ever_invented() -> None:
    """The MCP Registry's own schema has no license/activity field at all —
    this must never be synthesized to look consistent with GitHub results."""
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = MCPRegistryResearchProvider(http_get=http_get)

    results = provider.search("filesystem")

    for result in results:
        assert result.license is None
        assert result.license_confidence == Confidence.UNKNOWN
        assert result.maintenance_signals == {}
        assert result.compatibility_confidence == Confidence.UNKNOWN
        assert result.functional_fit_notes is None


def test_search_respects_limit() -> None:
    http_get = _fake_http_get(200, json.dumps(_SEARCH_RESPONSE).encode())
    provider = MCPRegistryResearchProvider(http_get=http_get)

    results = provider.search("x", limit=1)

    assert len(results) == 1


def test_fetch_single_server() -> None:
    body = json.dumps(
        {"server": _SEARCH_RESPONSE["servers"][0]["server"], "_meta": {"status": "active"}}
    ).encode()
    provider = MCPRegistryResearchProvider(http_get=_fake_http_get(200, body))

    result = provider.fetch("com.pulsemcp/remote-filesystem")

    assert result.identifier == "com.pulsemcp/remote-filesystem"
    assert result.query == "com.pulsemcp/remote-filesystem"


def test_fetch_url_encodes_the_identifier() -> None:
    captured: dict[str, str] = {}

    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        captured["url"] = url
        return 200, json.dumps(
            {"server": {"name": "a/b", "description": "d", "version": "1"}}
        ).encode()

    provider = MCPRegistryResearchProvider(http_get=_get)
    provider.fetch("a/b")

    assert "a%2Fb" in captured["url"]


def test_http_error_status_raises_research_error() -> None:
    provider = MCPRegistryResearchProvider(http_get=_fake_http_get(404, b'{"error": "not found"}'))

    with pytest.raises(MCPRegistryError, match="404"):
        provider.search("nonexistent")


def test_network_failure_raises_research_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("connection refused")

    provider = MCPRegistryResearchProvider(http_get=_raise)

    with pytest.raises(MCPRegistryError, match="request failed"):
        provider.search("x")


def test_invalid_json_raises_research_error() -> None:
    provider = MCPRegistryResearchProvider(http_get=_fake_http_get(200, b"not json"))

    with pytest.raises(MCPRegistryError, match="invalid JSON"):
        provider.search("x")


def test_non_dict_response_raises_research_error() -> None:
    provider = MCPRegistryResearchProvider(http_get=_fake_http_get(200, b"[1, 2, 3]"))

    with pytest.raises(MCPRegistryError, match="Unexpected MCP Registry response shape"):
        provider.search("x")


def test_non_list_servers_raises_research_error() -> None:
    provider = MCPRegistryResearchProvider(
        http_get=_fake_http_get(200, json.dumps({"servers": "x"}).encode())
    )

    with pytest.raises(MCPRegistryError, match="Unexpected MCP Registry search response shape"):
        provider.search("x")


def test_fetch_non_dict_server_field_raises_research_error() -> None:
    provider = MCPRegistryResearchProvider(
        http_get=_fake_http_get(200, json.dumps({"server": "not-an-object"}).encode())
    )

    with pytest.raises(MCPRegistryError, match="Unexpected MCP Registry response shape"):
        provider.fetch("a/b")


def test_search_skips_malformed_entries_without_crashing() -> None:
    body = json.dumps({"servers": [{"server": "not-an-object"}, {"not_server": {}}]}).encode()
    provider = MCPRegistryResearchProvider(http_get=_fake_http_get(200, body))

    assert provider.search("x") == []
