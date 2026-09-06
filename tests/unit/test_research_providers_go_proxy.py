import json

import pytest

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.enums import ComponentKind, Confidence
from system_intelligence.research.providers.go_proxy import (
    GoProxyUpdateError,
    GoProxyUpdateProvider,
    _escape_module_path,
)

_IDENTITY = ComponentIdentity(
    component_kind=ComponentKind.PACKAGE,
    name="golang.org/x/crypto",
    distribution_source="go",
)

# Shape verified live against https://proxy.golang.org/golang.org/x/crypto/@latest.
_RESPONSE = {
    "Version": "v0.56.0",
    "Time": "2026-09-02T18:02:47Z",
    "Origin": {"VCS": "git", "URL": "https://go.googlesource.com/crypto"},
}


def _fake_http_get(status: int, body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return status, body

    return _get


def test_escape_module_path_lowercases_and_escapes_uppercase_letters() -> None:
    # Verified live: github.com/Masterminds/semver -> github.com/!masterminds/semver
    assert _escape_module_path("github.com/Masterminds/semver") == "github.com/!masterminds/semver"
    assert _escape_module_path("golang.org/x/crypto") == "golang.org/x/crypto"


def test_fetch_available_state_parses_version_and_release_date() -> None:
    provider = GoProxyUpdateProvider(http_get=_fake_http_get(200, json.dumps(_RESPONSE).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "v0.56.0"
    assert state.version_confidence == Confidence.VERIFIED
    assert state.provider == "go"
    assert state.release_info is not None
    assert state.release_info.released_at is not None
    assert state.evidence


def test_fetch_available_state_requests_escaped_module_path() -> None:
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE,
        name="github.com/Masterminds/semver",
        distribution_source="go",
    )
    requested_urls: list[str] = []

    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        requested_urls.append(url)
        return 200, json.dumps({"Version": "v1.5.0"}).encode()

    provider = GoProxyUpdateProvider(http_get=_get)
    provider.fetch_available_state(identity)

    assert requested_urls == ["https://proxy.golang.org/github.com/!masterminds/semver/@latest"]


def test_fetch_available_state_404_returns_none() -> None:
    provider = GoProxyUpdateProvider(http_get=_fake_http_get(404, b"not found"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_fetch_available_state_missing_version_returns_none() -> None:
    provider = GoProxyUpdateProvider(http_get=_fake_http_get(200, b"{}"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_http_error_raises_go_proxy_update_error() -> None:
    provider = GoProxyUpdateProvider(http_get=_fake_http_get(500, b"error"))

    with pytest.raises(GoProxyUpdateError, match="500"):
        provider.fetch_available_state(_IDENTITY)


def test_network_failure_raises_go_proxy_update_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("timeout")

    provider = GoProxyUpdateProvider(http_get=_raise)

    with pytest.raises(GoProxyUpdateError, match="request failed"):
        provider.fetch_available_state(_IDENTITY)


def test_invalid_json_raises_go_proxy_update_error() -> None:
    provider = GoProxyUpdateProvider(http_get=_fake_http_get(200, b"not json"))

    with pytest.raises(GoProxyUpdateError, match="invalid JSON"):
        provider.fetch_available_state(_IDENTITY)
