import json

from system_intelligence.core.entities import Repository, Target
from system_intelligence.core.enums import TargetKind
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.reporting.dashboard_data import build_dashboard_data
from system_intelligence.reporting.dashboard_html import generate_dashboard_html


def _target() -> Target:
    return Target(name="my-repo", kind=TargetKind.LOCAL_PATH, locator="/repo")


def test_generate_dashboard_html_is_valid_shell() -> None:
    snapshot = Snapshot(target=_target())
    data = build_dashboard_data(snapshot)

    html = generate_dashboard_html(data)

    assert html.startswith("<!doctype html>")
    assert "<title>" in html
    assert "my-repo" in html
    assert 'id="si-dashboard-data"' in html


def test_generate_dashboard_html_embeds_valid_and_complete_json() -> None:
    repository = Repository(id="r1", name="repo-name-marker", path=".")
    snapshot = Snapshot(target=_target(), components=[repository])
    data = build_dashboard_data(snapshot)

    html = generate_dashboard_html(data)

    start = html.index('id="si-dashboard-data">') + len('id="si-dashboard-data">')
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])

    assert payload["overview"]["component_count"] == 1
    assert payload["components"][0]["name"] == "repo-name-marker"


def test_generate_dashboard_html_escapes_closing_script_tag_in_data() -> None:
    malicious_name = "</script><script>alert(1)</script>"
    repository = Repository(id="r1", name=malicious_name, path=".")
    snapshot = Snapshot(target=_target(), components=[repository])
    data = build_dashboard_data(snapshot)

    html = generate_dashboard_html(data)

    assert "</script><script>alert(1)</script>" not in html
    # The JSON payload still round-trips to the original string once parsed.
    start = html.index('id="si-dashboard-data">') + len('id="si-dashboard-data">')
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert payload["components"][0]["name"] == malicious_name


def test_generate_dashboard_html_escapes_target_name_in_shell() -> None:
    """`Target.name` is not sanitized by anything upstream -- a local
    directory's basename, or the raw GitHub locator string on the CLI, is
    interpolated directly into the outer HTML shell (the `<title>` and
    the sidebar `<p>` line), not just the JSON payload the previous test
    already covers. Unescaped, this breaks out of both tags: a directory
    literally named `<img src=x onerror=alert(1)>` previously executed
    the moment the generated dashboard.html was opened in a browser."""
    malicious_name = "<img src=x onerror=alert(1)>"
    target = Target(name=malicious_name, kind=TargetKind.LOCAL_PATH, locator="/repo")
    data = build_dashboard_data(Snapshot(target=target))

    html = generate_dashboard_html(data)

    start = html.index('id="si-dashboard-data">') + len('id="si-dashboard-data">')
    end = html.index("</script>", start)
    shell = html[:start] + html[end:]
    payload = json.loads(html[start:end])

    assert malicious_name not in shell
    assert "&lt;img src=x onerror=alert(1)&gt;" in shell
    # The JSON payload still round-trips to the original, unescaped string.
    assert payload["overview"]["target_name"] == malicious_name


def test_generate_dashboard_html_wires_proposal_detail_toggle() -> None:
    """The Proposals table renders capabilities/interfaces/test_strategy/etc.
    (all already on `Proposal`) via a click-to-expand detail row, the same
    pattern already used for Components -- confirmed interactively with a
    real browser (Playwright/Chromium) during development, since this
    project's test suite doesn't execute the embedded JavaScript itself."""
    snapshot = Snapshot(target=_target())
    data = build_dashboard_data(snapshot)

    html = generate_dashboard_html(data)

    assert "toggleProposalDetail" in html


def test_generate_dashboard_html_never_touches_a_remote() -> None:
    snapshot = Snapshot(target=_target())
    data = build_dashboard_data(snapshot)

    html = generate_dashboard_html(data)

    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    assert "WebSocket" not in html
    assert "<form" not in html
