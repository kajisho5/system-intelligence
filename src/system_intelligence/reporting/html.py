"""Static HTML intelligence report generator (docs/design/docs/09-visualization.md).

Produces a single, dependency-free HTML file from a `Snapshot` — no CDN
scripts, no build step, viewable offline via `file://`. The report and the
canonical JSON snapshot share the same source of truth (`Snapshot`): this
module only renders it, it never computes new facts.

Recommendations/Research/Proposed Changes/Verification render whatever the
given Snapshot actually carries in those lists — `si report` populates
Recommendations from the same Findings it just computed, but Research and
Proposals need an explicit query/problem statement `si report <target>`
does not take, so those sections are commonly empty. An empty section is
labeled with *why* it is empty (not computed vs. computed-and-nothing-
found) rather than a blanket "planned for a later phase", which would
misstate engines that already exist (see `research/`, `recommendations/`,
`proposals/`, `verification/`).
"""

from __future__ import annotations

from html import escape
from typing import Any

from system_intelligence.core.entities import Agent, Document, Repository, Skill
from system_intelligence.core.enums import Severity
from system_intelligence.core.snapshot import Snapshot

_SEVERITY_ORDER = [
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
]


def _e(value: Any) -> str:
    """Escape any value for safe embedding in HTML text content."""
    return escape(str(value))


def _render_overview(snapshot: Snapshot) -> str:
    repository = next((c for c in snapshot.components if isinstance(c, Repository)), None)
    if repository and repository.languages:
        languages = ", ".join(repository.languages)
    else:
        languages = "none detected"
    if repository and repository.is_git_repository:
        git_branch = repository.default_branch or "yes (no remote branch detected)"
    else:
        git_branch = "not a git repository"
    remote_url = (repository.url if repository else None) or "none configured"
    license_str = (repository.license if repository else None) or "unknown"
    last_commit = None
    if repository and repository.last_commit_date:
        dirty_suffix = ", uncommitted changes" if repository.is_dirty else ""
        last_commit = f"{repository.last_commit_date}{dirty_suffix}"
    findings_count = len(snapshot.findings)
    capabilities_count = len(snapshot.capabilities)
    components_count = len(snapshot.components)

    return f"""
    <section id="overview">
      <h2>Overview</h2>
      <dl class="facts">
        <dt>Target</dt><dd>{_e(snapshot.target.locator)}</dd>
        <dt>Snapshot</dt><dd>{_e(snapshot.id)}</dd>
        <dt>Generated</dt><dd>{_e(snapshot.created_at.isoformat())}</dd>
        <dt>Git branch</dt><dd>{_e(git_branch)}</dd>
        <dt>Remote</dt><dd>{_e(remote_url)}</dd>
        <dt>License</dt><dd>{_e(license_str)}</dd>
        {f"<dt>Last commit</dt><dd>{_e(last_commit)}</dd>" if last_commit else ""}
        <dt>Languages</dt><dd>{_e(languages)}</dd>
        <dt>Components</dt><dd>{components_count}</dd>
        <dt>Capabilities</dt><dd>{capabilities_count}</dd>
        <dt>Findings</dt><dd>{findings_count}</dd>
      </dl>
    </section>
    """


def _tool_scope_suffix(tool_names: list[str], permissions: list[str]) -> str:
    """Format a Skill/Agent's `allowed-tools`/`disallowed-tools` (`tool_names`/
    `permissions`) frontmatter, if any, for the Components table's Detail
    column -- already discovered and stored, but never previously rendered
    anywhere a user could see it without opening the raw JSON snapshot."""
    suffix = ""
    if tool_names:
        suffix += f"; tools: {', '.join(tool_names)}"
    if permissions:
        suffix += f"; disallowed: {', '.join(permissions)}"
    return suffix


def _render_components(snapshot: Snapshot) -> str:
    rows = []
    for component in snapshot.components:
        extra = ""
        if isinstance(component, Skill):
            extra = "standard format" if component.is_standard_format else "non-standard format"
            extra += _tool_scope_suffix(component.tool_names, component.permissions)
        elif isinstance(component, Agent):
            extra = "standard format" if component.is_standard_format else "non-standard format"
            if component.model_provider:
                extra += f" (model: {component.model_provider})"
            extra += _tool_scope_suffix(component.tool_names, component.permissions)
        elif isinstance(component, Document):
            extra = component.document_type or ""
        elif isinstance(component, Repository):
            extra = ", ".join(component.languages) or "no languages detected"
        rows.append(
            f"<tr><td>{_e(component.kind.value)}</td><td>{_e(component.name)}</td>"
            f"<td>{_e(component.path or '')}</td><td>{_e(extra)}</td></tr>"
        )
    body = "\n".join(rows) if rows else "<tr><td colspan='4'>No components discovered.</td></tr>"
    return f"""
    <section id="components">
      <h2>Components</h2>
      <table>
        <thead><tr><th>Kind</th><th>Name</th><th>Path</th><th>Detail</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def _render_capability_graph(snapshot: Snapshot) -> str:
    if not snapshot.capabilities:
        return ""
    component_names = {c.id: c.name for c in snapshot.components}
    row_height = 32
    height = row_height * len(snapshot.capabilities) + 20
    nodes = []
    for i, capability in enumerate(snapshot.capabilities):
        y = 20 + i * row_height
        provider_label = ", ".join(component_names.get(pid, pid) for pid in capability.provider_ids)
        nodes.append(
            f'<line x1="120" y1="{y}" x2="260" y2="{y}" class="edge" />'
            f'<circle cx="120" cy="{y}" r="5" class="node-provider" />'
            f'<text x="10" y="{y + 4}" class="label">{_e(provider_label)}</text>'
            f'<circle cx="260" cy="{y}" r="5" class="node-capability" />'
            f'<text x="275" y="{y + 4}" class="label">{_e(capability.name)} '
            f"({_e(capability.status.value)}/{_e(capability.confidence.value)})</text>"
        )
    svg_body = "\n".join(nodes)
    return f"""
    <section id="capability-graph">
      <h2>Capability Graph</h2>
      <svg viewBox="0 0 500 {height}" role="img" aria-label="Capability graph">
        {svg_body}
      </svg>
    </section>
    """


def _render_dependency_graph(snapshot: Snapshot) -> str:
    # Each Dependency is already attributed to the specific Component that
    # actually declares it (`analysis/dependencies.py::
    # attach_dependencies_by_component`) -- a Skill's own manifest is not
    # the Repository's. Labeling every row with the owning component's real
    # name, not a single hard-coded "repository" node, mirrors
    # `_render_capability_graph`'s own already-correct pattern above.
    component_names = {c.id: c.name for c in snapshot.components}
    rows = [
        (component.id, dependency)
        for component in snapshot.components
        for dependency in component.dependencies
    ]
    if not rows:
        return ""
    row_height = 28
    height = row_height * len(rows) + 20
    nodes = []
    for i, (component_id, dependency) in enumerate(rows):
        y = 20 + i * row_height
        owner_label = component_names.get(component_id, component_id)
        label = f"{dependency.name} ({dependency.ecosystem})"
        if dependency.version_constraint:
            label += f" {dependency.version_constraint}"
        if dependency.resolved_version:
            label += f" -> {dependency.resolved_version}"
        nodes.append(
            f'<line x1="60" y1="{y}" x2="220" y2="{y}" class="edge" />'
            f'<circle cx="60" cy="{y}" r="5" class="node-repository" />'
            f'<text x="10" y="{y + 4}" class="label">{_e(owner_label)}</text>'
            f'<circle cx="220" cy="{y}" r="5" class="node-dependency" />'
            f'<text x="235" y="{y + 4}" class="label">{_e(label)}</text>'
        )
    svg_body = "\n".join(nodes)
    return f"""
    <section id="dependency-graph">
      <h2>Dependency Graph</h2>
      <svg viewBox="0 0 500 {max(height, 60)}" role="img" aria-label="Dependency graph">
        {svg_body}
      </svg>
    </section>
    """


def _render_findings(snapshot: Snapshot) -> str:
    by_severity: dict[Severity, list[Any]] = {s: [] for s in _SEVERITY_ORDER}
    for finding in snapshot.findings:
        by_severity[finding.severity].append(finding)

    groups = []
    for severity in _SEVERITY_ORDER:
        findings = by_severity[severity]
        if not findings:
            continue
        items = []
        for finding in findings:
            actions = (
                "<ul class='actions'>"
                + "".join(f"<li>{_e(a)}</li>" for a in finding.suggested_actions)
                + "</ul>"
                if finding.suggested_actions
                else ""
            )
            items.append(
                f"<li class='finding'><span class='badge confidence-{finding.confidence.value}'>"
                f"{_e(finding.confidence.value)}</span> "
                f"<span class='category'>{_e(finding.category)}</span> "
                f"{_e(finding.statement)} "
                f"<span class='evidence-count'>({len(finding.evidence)} evidence)</span>"
                f"{actions}</li>"
            )
        groups.append(
            f"<h3 class='severity-{severity.value}'>{_e(severity.value.upper())} "
            f"({len(findings)})</h3><ul>{''.join(items)}</ul>"
        )

    body = "".join(groups) if groups else "<p>No findings.</p>"
    return f"""
    <section id="findings">
      <h2>Findings</h2>
      {body}
    </section>
    """


def _render_recommendations(snapshot: Snapshot) -> str:
    if not snapshot.recommendations:
        note = "No recommendations were generated for this snapshot."
        return _render_placeholder_section("recommendations", "Recommendations", note)
    items = []
    for rec in snapshot.recommendations:
        items.append(
            f"<li><span class='badge confidence-{rec.confidence.value}'>{_e(rec.confidence.value)}"
            f"</span> {_e(rec.objective)} <span class='evidence-count'>"
            f"(effort: {_e(rec.estimated_effort or 'unknown')}, risk: {_e(rec.risk or 'unknown')})"
            f"</span><p class='rationale'>{_e(rec.rationale)}</p></li>"
        )
    return f"""
    <section id="recommendations">
      <h2>Recommendations</h2>
      <ul>{"".join(items)}</ul>
    </section>
    """


def _render_research(snapshot: Snapshot) -> str:
    if not snapshot.research:
        note = (
            "Not computed for this report — 'si report' does not take a research query. "
            "Run 'si research <query>' separately."
        )
        return _render_placeholder_section("research", "Research", note)
    items = []
    for result in snapshot.research:
        items.append(
            f"<li>{_e(result.identifier)} — <span class='category'>{_e(result.provider)}</span> "
            f"license: {_e(result.license or 'unknown')} "
            f"({_e(result.license_confidence.value)})</li>"
        )
    return f"""
    <section id="research">
      <h2>Research</h2>
      <ul>{"".join(items)}</ul>
    </section>
    """


def _render_proposals(snapshot: Snapshot) -> str:
    if not snapshot.proposals:
        note = (
            "Not computed for this report — 'si report' does not take a problem statement. "
            "Run 'si propose <problem>' separately."
        )
        return _render_placeholder_section("proposed-changes", "Proposed Changes", note)
    items = []
    for proposal in snapshot.proposals:
        items.append(
            f"<li><span class='category'>{_e(proposal.kind)}</span> {_e(proposal.problem)} "
            f"<span class='evidence-count'>(permission: "
            f"{_e(proposal.required_permission_level.name)})</span></li>"
        )
    return f"""
    <section id="proposed-changes">
      <h2>Proposed Changes</h2>
      <ul>{"".join(items)}</ul>
    </section>
    """


def _render_verification(snapshot: Snapshot) -> str:
    if not snapshot.verification:
        note = "No approved changes have been verified against this target yet."
        return _render_placeholder_section("verification", "Verification", note)
    items = []
    for verification in snapshot.verification:
        status = "unknown" if verification.tests_passed is None else str(verification.tests_passed)
        regressions = ""
        if verification.regressions_found:
            regression_items = "".join(f"<li>{_e(r)}</li>" for r in verification.regressions_found)
            regressions = (
                f" — regressions found ({len(verification.regressions_found)}):"
                f"<ul>{regression_items}</ul>"
            )
        items.append(
            f"<li>{_e(', '.join(verification.tests_run) or 'unnamed command')} — "
            f"passed: {_e(status)}{regressions}</li>"
        )
    return f"""
    <section id="verification">
      <h2>Verification</h2>
      <ul>{"".join(items)}</ul>
    </section>
    """


def _render_placeholder_section(section_id: str, title: str, note: str) -> str:
    return f"""
    <section id="{section_id}">
      <h2>{_e(title)}</h2>
      <p class="placeholder">{_e(note)}</p>
    </section>
    """


_STYLE = """
:root {
  color-scheme: light dark;
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b6b6b; --border: #e2e2e2;
  --accent: #2563eb; --edge: #b8c2d0;
  --critical: #b91c1c; --high: #c2410c; --medium: #a16207; --low: #4b5563; --info: #6b7280;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #14161a; --fg: #e8e8e8; --muted: #9a9a9a; --border: #2c2f36; --edge: #4b5563; }
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg);
  font: 15px/1.5 -apple-system, "Segoe UI", sans-serif;
  margin: 0; padding: 2rem 1.5rem 4rem; max-width: 900px; margin-inline: auto;
}
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
h2 {
  font-size: 1.15rem; border-bottom: 1px solid var(--border);
  padding-bottom: 0.4rem; margin-top: 2.5rem;
}
h3 { font-size: 1rem; margin-bottom: 0.3rem; }
.subtitle { color: var(--muted); margin-top: 0; }
dl.facts { display: grid; grid-template-columns: max-content 1fr; gap: 0.3rem 1rem; }
dl.facts dt { color: var(--muted); }
dl.facts dd { margin: 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 600; }
svg { width: 100%; height: auto; }
svg .label { font-size: 11px; fill: var(--fg); }
svg .edge { stroke: var(--edge); stroke-width: 1; }
svg .node-repository, svg .node-provider { fill: var(--accent); }
svg .node-capability, svg .node-dependency { fill: var(--muted); }
ul.actions { margin: 0.2rem 0 0.6rem 1.2rem; color: var(--muted); font-size: 0.9rem; }
li.finding { margin-bottom: 0.6rem; list-style: none; }
#findings ul { padding-left: 0; }
.badge {
  display: inline-block; font-size: 0.7rem; text-transform: uppercase;
  padding: 0.1rem 0.4rem; border-radius: 3px; border: 1px solid var(--border);
  margin-right: 0.3rem;
}
.category { color: var(--muted); font-size: 0.85rem; margin-right: 0.3rem; }
.evidence-count { color: var(--muted); font-size: 0.8rem; }
p.rationale { margin: 0.2rem 0 0.6rem; color: var(--muted); font-size: 0.9rem; }
h3.severity-critical, h3.severity-high { color: var(--high); }
h3.severity-medium { color: var(--medium); }
h3.severity-low, h3.severity-info { color: var(--info); }
p.placeholder { color: var(--muted); font-style: italic; }
footer {
  margin-top: 3rem; color: var(--muted); font-size: 0.8rem;
  border-top: 1px solid var(--border); padding-top: 1rem;
}
"""


def generate_html_report(snapshot: Snapshot) -> str:
    """Render a Snapshot as a single, self-contained HTML document."""
    sections = [
        _render_overview(snapshot),
        _render_components(snapshot),
        _render_capability_graph(snapshot),
        _render_dependency_graph(snapshot),
        _render_findings(snapshot),
        _render_recommendations(snapshot),
        _render_research(snapshot),
        _render_proposals(snapshot),
        _render_verification(snapshot),
        _render_placeholder_section(
            "history",
            "History",
            "This report reflects a single snapshot. Run 'si diff' between two snapshot "
            "directories, or 'si dashboard --compare-with', to compare them over time.",
        ),
    ]
    body = "\n".join(sections)
    title = f"System Intelligence report — {escape(snapshot.target.name)}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{title}</h1>
<p class="subtitle">Evidence-first system intelligence report. Facts are labeled with their
confidence level; nothing here is presented as more certain than the evidence supports.</p>
{body}
<footer>
  Snapshot {_e(snapshot.id)} generated {_e(snapshot.created_at.isoformat())} by
  System Intelligence. Machine-readable data for this report lives alongside it as
  the canonical JSON snapshot (manifest.json, components.json, capabilities.json,
  findings.json, ...).
</footer>
</body>
</html>
"""
