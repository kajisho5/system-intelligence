import json

import pytest

from system_intelligence.core.component_state import ComponentIdentity
from system_intelligence.core.enums import ComponentKind
from system_intelligence.research.providers.osv import OSVLookupError, OSVVulnerabilityProvider

_IDENTITY = ComponentIdentity(
    component_kind=ComponentKind.PACKAGE, name="lodash", distribution_source="npm"
)

# A trimmed real OSV.dev response shape (POST /v1/query for lodash@2.0.0),
# captured against the live API -- not guessed.
_RESPONSE = {
    "vulns": [
        {
            "id": "GHSA-35jh-r3h4-6jhm",
            "summary": "Command Injection in lodash",
            "details": "`lodash` versions prior to 4.17.21 are vulnerable to Command Injection.",
            "aliases": ["CVE-2021-23337", "GHSA-r5fr-rjxr-66jc"],
            "database_specific": {"github_reviewed": True, "severity": "HIGH"},
            "references": [
                {"type": "ADVISORY", "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-23337"},
                {"type": "WEB", "url": "https://github.com/lodash/lodash/commit/deadbeef"},
            ],
        },
        {
            "id": "PYSEC-2026-1812",
            "summary": "",
            "details": "Some other issue with no severity or database_specific reported.",
            "aliases": [],
        },
    ]
}


def _fake_http_post(status: int, body: bytes):
    def _post(url: str, headers: dict[str, str], data: bytes) -> tuple[int, bytes]:
        assert headers["User-Agent"]
        assert json.loads(data) == {
            "version": "2.0.0",
            "package": {"name": "lodash", "ecosystem": "npm"},
        }
        return status, body

    return _post


def test_fetch_advisories_parses_full_shape() -> None:
    provider = OSVVulnerabilityProvider(
        "npm", "npm", http_post=_fake_http_post(200, json.dumps(_RESPONSE).encode())
    )

    advisories = provider.fetch_advisories(_IDENTITY, "2.0.0")

    assert len(advisories) == 2
    first = advisories[0]
    assert first.id == "GHSA-35jh-r3h4-6jhm"
    assert first.severity == "HIGH"
    assert first.aliases == ["CVE-2021-23337", "GHSA-r5fr-rjxr-66jc"]
    assert first.url == "https://nvd.nist.gov/vuln/detail/CVE-2021-23337"


def test_fetch_advisories_missing_severity_and_database_specific_stays_none() -> None:
    """Never guess a severity the source itself didn't report."""
    provider = OSVVulnerabilityProvider(
        "npm", "npm", http_post=_fake_http_post(200, json.dumps(_RESPONSE).encode())
    )

    advisories = provider.fetch_advisories(_IDENTITY, "2.0.0")

    second = advisories[1]
    assert second.id == "PYSEC-2026-1812"
    assert second.severity is None
    assert second.url is None
    # `summary` falls back to `details` when the source's own summary is blank.
    assert second.summary == "Some other issue with no severity or database_specific reported."


def test_fetch_advisories_no_vulns_key_returns_empty_list() -> None:
    """OSV.dev returns a bare `{}` (no "vulns" key at all) for a clean
    version -- confirmed against the live API, not assumed to be `{"vulns": []}`."""
    provider = OSVVulnerabilityProvider("npm", "npm", http_post=_fake_http_post(200, b"{}"))

    assert provider.fetch_advisories(_IDENTITY, "2.0.0") == []


def test_fetch_advisories_http_error_raises() -> None:
    provider = OSVVulnerabilityProvider("npm", "npm", http_post=_fake_http_post(500, b""))

    with pytest.raises(OSVLookupError):
        provider.fetch_advisories(_IDENTITY, "2.0.0")


def test_fetch_advisories_invalid_json_raises() -> None:
    provider = OSVVulnerabilityProvider("npm", "npm", http_post=_fake_http_post(200, b"not json"))

    with pytest.raises(OSVLookupError):
        provider.fetch_advisories(_IDENTITY, "2.0.0")


def test_fetch_advisories_network_error_raises() -> None:
    def _post(url: str, headers: dict[str, str], data: bytes) -> tuple[int, bytes]:
        raise OSError("connection refused")

    provider = OSVVulnerabilityProvider("npm", "npm", http_post=_post)

    with pytest.raises(OSVLookupError):
        provider.fetch_advisories(_IDENTITY, "2.0.0")


def test_pypi_ecosystem_name_sent_verbatim() -> None:
    """OSV.dev's ecosystem names are case-sensitive ('PyPI', not 'pypi')."""
    captured: dict[str, object] = {}

    def _post(url: str, headers: dict[str, str], data: bytes) -> tuple[int, bytes]:
        captured["body"] = json.loads(data)
        return 200, b"{}"

    provider = OSVVulnerabilityProvider("pypi", "PyPI", http_post=_post)
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="requests", distribution_source="pypi"
    )

    provider.fetch_advisories(identity, "1.0.0")

    assert captured["body"] == {
        "version": "1.0.0",
        "package": {"name": "requests", "ecosystem": "PyPI"},
    }
