import json

import pytest

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.enums import ComponentKind, Confidence
from system_intelligence.research.providers.crates_io import (
    CratesIoUpdateError,
    CratesIoUpdateProvider,
)

_IDENTITY = ComponentIdentity(
    component_kind=ComponentKind.PACKAGE, name="serde", distribution_source="cargo"
)

# Shape verified live against https://crates.io/api/v1/crates/serde.
_RESPONSE = {
    "crate": {
        "name": "serde",
        "max_version": "1.0.229",
        "max_stable_version": "1.0.229",
        "newest_version": "1.0.229",
        "yanked": False,
    },
    "versions": [
        {"num": "1.0.229", "created_at": "2026-07-18T23:05:13.266456Z", "yanked": False},
        {"num": "1.0.228", "created_at": "2026-07-01T00:00:00.000000Z", "yanked": False},
    ],
}


def _fake_http_get(status: int, body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return status, body

    return _get


def test_fetch_available_state_parses_max_stable_version_and_release_date() -> None:
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(200, json.dumps(_RESPONSE).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "1.0.229"
    assert state.version_confidence == Confidence.VERIFIED
    assert state.provider == "cargo"
    assert state.release_info is not None
    assert state.release_info.released_at is not None
    assert state.release_info.is_yanked is False
    assert state.changelog == []
    assert state.evidence


def test_fetch_available_state_version_not_in_versions_list_still_returns_state() -> None:
    """The top-level `versions` array only carries recent releases; an old
    `max_stable_version` absent from it is still reported, just without
    release-date/yanked detail — never treated as "not found"."""
    response = {"crate": {"max_stable_version": "0.1.0"}, "versions": []}
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(200, json.dumps(response).encode()))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "0.1.0"
    assert state.release_info is not None
    assert state.release_info.released_at is None
    assert state.release_info.is_yanked is None


def test_fetch_available_state_404_returns_none() -> None:
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(404, b"{}"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_fetch_available_state_missing_version_returns_none() -> None:
    response = {"crate": {}}
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(200, json.dumps(response).encode()))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_fetch_available_state_missing_crate_key_returns_none() -> None:
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(200, b"{}"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_http_error_raises_crates_io_update_error() -> None:
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(500, b"error"))

    with pytest.raises(CratesIoUpdateError, match="500"):
        provider.fetch_available_state(_IDENTITY)


def test_network_failure_raises_crates_io_update_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("timeout")

    provider = CratesIoUpdateProvider(http_get=_raise)

    with pytest.raises(CratesIoUpdateError, match="request failed"):
        provider.fetch_available_state(_IDENTITY)


def test_invalid_json_raises_crates_io_update_error() -> None:
    provider = CratesIoUpdateProvider(http_get=_fake_http_get(200, b"not json"))

    with pytest.raises(CratesIoUpdateError, match="invalid JSON"):
        provider.fetch_available_state(_IDENTITY)
