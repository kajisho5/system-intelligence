import pytest

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.enums import ComponentKind, Confidence
from system_intelligence.research.providers.maven_central import (
    MavenCentralUpdateError,
    MavenCentralUpdateProvider,
)

_IDENTITY = ComponentIdentity(
    component_kind=ComponentKind.PACKAGE,
    name="com.google.code.gson:gson",
    distribution_source="maven",
)

# Shape verified live against
# https://repo1.maven.org/maven2/com/google/code/gson/gson/maven-metadata.xml.
_METADATA_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.google.code.gson</groupId>
  <artifactId>gson</artifactId>
  <versioning>
    <latest>2.14.0</latest>
    <release>2.14.0</release>
    <versions>
      <version>2.13.2</version>
      <version>2.14.0</version>
    </versions>
    <lastUpdated>20260423191314</lastUpdated>
  </versioning>
</metadata>
"""


def _fake_http_get(status: int, body: bytes):
    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        return status, body

    return _get


def test_fetch_available_state_parses_release_and_last_updated() -> None:
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(200, _METADATA_XML))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "2.14.0"
    assert state.version_confidence == Confidence.VERIFIED
    assert state.provider == "maven"
    assert state.release_info is not None
    assert state.release_info.released_at is not None
    assert state.release_info.released_at.year == 2026
    assert state.evidence


def test_fetch_available_state_requests_group_path_and_artifact_id() -> None:
    requested_urls: list[str] = []

    def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        requested_urls.append(url)
        return 200, _METADATA_XML

    provider = MavenCentralUpdateProvider(http_get=_get)
    provider.fetch_available_state(_IDENTITY)

    assert requested_urls == [
        "https://repo1.maven.org/maven2/com/google/code/gson/gson/maven-metadata.xml"
    ]


def test_fetch_available_state_falls_back_to_latest_when_release_absent() -> None:
    # Maven's own metadata spec allows a `latest`-only file when every
    # published version is a pre-release/snapshot.
    xml = b"""<?xml version="1.0"?>
<metadata>
  <versioning>
    <latest>1.0.0-beta1</latest>
  </versioning>
</metadata>
"""
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(200, xml))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "1.0.0-beta1"


def test_fetch_available_state_picks_one_guava_style_dual_flavor_version() -> None:
    """A coordinate publishing more than one version *flavor* (Guava's
    `-jre`/`-android` builds under the same groupId:artifactId) is resolved
    by Maven Central's own `<release>` pointer, not guessed by this
    provider from a version list."""
    xml = b"""<?xml version="1.0"?>
<metadata>
  <versioning>
    <latest>33.7.1-jre</latest>
    <release>33.7.1-jre</release>
    <versions>
      <version>33.7.1-android</version>
      <version>33.7.1-jre</version>
    </versions>
  </versioning>
</metadata>
"""
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(200, xml))

    state = provider.fetch_available_state(_IDENTITY)

    assert state is not None
    assert state.version == "33.7.1-jre"


def test_fetch_available_state_name_without_colon_returns_none() -> None:
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE,
        name="not-a-maven-coordinate",
        distribution_source="maven",
    )
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(200, _METADATA_XML))

    assert provider.fetch_available_state(identity) is None


def test_fetch_available_state_404_returns_none() -> None:
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(404, b"not found"))

    assert provider.fetch_available_state(_IDENTITY) is None


def test_fetch_available_state_missing_versioning_returns_none() -> None:
    provider = MavenCentralUpdateProvider(
        http_get=_fake_http_get(200, b"<?xml version='1.0'?><metadata></metadata>")
    )

    assert provider.fetch_available_state(_IDENTITY) is None


def test_http_error_raises_maven_central_update_error() -> None:
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(500, b"error"))

    with pytest.raises(MavenCentralUpdateError, match="500"):
        provider.fetch_available_state(_IDENTITY)


def test_network_failure_raises_maven_central_update_error() -> None:
    def _raise(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("timeout")

    provider = MavenCentralUpdateProvider(http_get=_raise)

    with pytest.raises(MavenCentralUpdateError, match="request failed"):
        provider.fetch_available_state(_IDENTITY)


def test_invalid_xml_raises_maven_central_update_error() -> None:
    provider = MavenCentralUpdateProvider(http_get=_fake_http_get(200, b"not xml"))

    with pytest.raises(MavenCentralUpdateError, match="invalid XML"):
        provider.fetch_available_state(_IDENTITY)
