import json

import pytest

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.enums import ComponentKind, Confidence
from system_intelligence.research.providers.npm import NpmUpdateError, NpmUpdateProvider

_IDENTITY = ComponentIdentity(
    component_kind=ComponentKind.PACKAGE, name="react", distribution_source="npm"
)

_RESPONSE = {
    "dist-tags": {"latest": "18.3.1"},
    "versions": {"18.3.1": {"engines": {"node": ">=14"}}},
    "time": {"18.3.1": "2026-08-01T00:00:00.000Z"},
}


def _fake_http_get(status: int, body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return status, body

    return _get


def test_fetch_available_state_parses_version_and_engines() -> None:
    provider = NpmUpdateProvider(http_get=_fake_http_get(200, json.dumps(_RESPONSE).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "18.3.1"
    assert state.version_confidence == Confidence.VERIFIED
    assert state.provider == "npm"
    assert state.runtime_requirements == ["node>=14"]
    assert state.release_info is not None
    assert state.release_info.released_at is not None
    assert state.is_deprecated is False
    assert state.evidence


def test_deprecated_version_is_flagged() -> None:
    response = {
        "dist-tags": {"latest": "1.0.0"},
        "versions": {"1.0.0": {"deprecated": "use something else"}},
        "time": {"1.0.0": "2020-01-01T00:00:00.000Z"},
    }
    provider = NpmUpdateProvider(http_get=_fake_http_get(200, json.dumps(response).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.is_deprecated is True


def test_fetch_available_state_404_returns_none() -> None:
    provider = NpmUpdateProvider(http_get=_fake_http_get(404, b"{}"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_fetch_available_state_missing_dist_tags_returns_none() -> None:
    provider = NpmUpdateProvider(http_get=_fake_http_get(200, b"{}"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_scoped_package_name_is_preserved_in_url() -> None:
    captured: dict[str, str] = {}

    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        captured["url"] = url
        return 200, json.dumps(_RESPONSE).encode()

    provider = NpmUpdateProvider(http_get=_get)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="@scope/pkg")

    provider.fetch_available_state(identity)

    assert captured["url"].endswith("@scope/pkg")


def test_http_error_raises_npm_update_error() -> None:
    provider = NpmUpdateProvider(http_get=_fake_http_get(500, b"error"))

    with pytest.raises(NpmUpdateError, match="500"):
        provider.fetch_available_state(_IDENTITY)


def test_network_failure_raises_npm_update_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("timeout")

    provider = NpmUpdateProvider(http_get=_raise)

    with pytest.raises(NpmUpdateError, match="request failed"):
        provider.fetch_available_state(_IDENTITY)


def test_invalid_json_raises_npm_update_error() -> None:
    provider = NpmUpdateProvider(http_get=_fake_http_get(200, b"not json"))

    with pytest.raises(NpmUpdateError, match="invalid JSON"):
        provider.fetch_available_state(_IDENTITY)
