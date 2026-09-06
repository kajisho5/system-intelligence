import json

import pytest

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.enums import ComponentKind, Confidence
from system_intelligence.research.providers.pypi import PyPIUpdateError, PyPIUpdateProvider

_IDENTITY = ComponentIdentity(
    component_kind=ComponentKind.PACKAGE, name="pydantic", distribution_source="pypi"
)

_RESPONSE = {
    "info": {
        "version": "2.9.0",
        "requires_python": ">=3.8",
        "yanked": False,
        "project_urls": {"Changelog": "https://example.com/changelog", "Homepage": "https://x"},
    },
    "releases": {"2.9.0": [{"upload_time_iso_8601": "2026-08-01T00:00:00.000000Z"}]},
}


def _fake_http_get(status: int, body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return status, body

    return _get


def test_fetch_available_state_parses_version_and_changelog() -> None:
    provider = PyPIUpdateProvider(http_get=_fake_http_get(200, json.dumps(_RESPONSE).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "2.9.0"
    assert state.version_confidence == Confidence.VERIFIED
    assert state.provider == "pypi"
    assert state.runtime_requirements == ["python>=3.8"]
    assert state.release_info is not None
    assert state.release_info.released_at is not None
    assert state.release_info.is_yanked is False
    assert len(state.changelog) == 1
    assert state.changelog[0].url == "https://example.com/changelog"
    assert state.evidence


def test_fetch_available_state_404_returns_none() -> None:
    provider = PyPIUpdateProvider(http_get=_fake_http_get(404, b"{}"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_fetch_available_state_missing_version_returns_none() -> None:
    provider = PyPIUpdateProvider(http_get=_fake_http_get(200, json.dumps({"info": {}}).encode()))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_http_error_raises_pypi_update_error() -> None:
    provider = PyPIUpdateProvider(http_get=_fake_http_get(500, b"error"))

    with pytest.raises(PyPIUpdateError, match="500"):
        provider.fetch_available_state(_IDENTITY)


def test_network_failure_raises_pypi_update_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("timeout")

    provider = PyPIUpdateProvider(http_get=_raise)

    with pytest.raises(PyPIUpdateError, match="request failed"):
        provider.fetch_available_state(_IDENTITY)


def test_invalid_json_raises_pypi_update_error() -> None:
    provider = PyPIUpdateProvider(http_get=_fake_http_get(200, b"not json"))

    with pytest.raises(PyPIUpdateError, match="invalid JSON"):
        provider.fetch_available_state(_IDENTITY)


def test_no_changelog_url_leaves_changelog_empty() -> None:
    response = {"info": {"version": "1.0.0"}}
    provider = PyPIUpdateProvider(http_get=_fake_http_get(200, json.dumps(response).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.changelog == []
    assert state.runtime_requirements == []
