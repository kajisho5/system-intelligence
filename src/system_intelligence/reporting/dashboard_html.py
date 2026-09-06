"""System Intelligence Console: the interactive Dashboard shell.

Renders `dashboard_data.DashboardData` as a single, dependency-free HTML
file (no CDN, no build step, viewable offline via `file://`) — same
constraint as `reporting/html.py`'s static report. The data is embedded as
JSON and rendered client-side by vanilla JS that only builds DOM nodes via
`document.createElement`/`textContent`; it never uses `innerHTML` with
data-derived strings, and it computes no new facts (no health score, no
inferred relationships) — every number and status it shows was already
computed by `dashboard_data.build_dashboard_data`.

Read-heavy by design (docs/03-architecture.md, "Dashboard is read-heavy"):
there is no button anywhere that merges, deletes, force-pushes, or writes
to a remote — this file has no network code and no form that submits
anywhere.
"""

from __future__ import annotations

import json

from system_intelligence.reporting.dashboard_data import DashboardData

_STYLE = """
:root {
  color-scheme: dark;
  --bg: #0b0d10; --bg-raised: #14171c; --bg-hover: #1c2027;
  --fg: #e7e9ec; --muted: #9098a3; --border: #262b33;
  --accent: #5b9dff; --accent-fg: #04101f;
  --success: #35c987; --warning: #e8b339; --critical: #f16565; --neutral: #9098a3;
  --unknown: #b98af0;
  --focus: #5b9dff;
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --bg: #f7f8fa; --bg-raised: #ffffff; --bg-hover: #eef1f5;
    --fg: #14171c; --muted: #5b6472; --border: #dde1e7;
    --accent: #1a5fd6; --accent-fg: #ffffff;
    --success: #157a4d; --warning: #8a6100; --critical: #b3261e; --neutral: #5b6472;
    --unknown: #6a3fa0;
  }
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg: #f7f8fa; --bg-raised: #ffffff; --bg-hover: #eef1f5;
  --fg: #14171c; --muted: #5b6472; --border: #dde1e7;
  --accent: #1a5fd6; --accent-fg: #ffffff;
  --success: #157a4d; --warning: #8a6100; --critical: #b3261e; --neutral: #5b6472;
  --unknown: #6a3fa0;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0b0d10; --bg-raised: #14171c; --bg-hover: #1c2027;
  --fg: #e7e9ec; --muted: #9098a3; --border: #262b33;
  --accent: #5b9dff; --accent-fg: #04101f;
  --success: #35c987; --warning: #e8b339; --critical: #f16565; --neutral: #9098a3;
  --unknown: #b98af0;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
}
a { color: var(--accent); }
button { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

#app { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
nav.sidebar {
  border-right: 1px solid var(--border); padding: 1rem 0.5rem;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
nav.sidebar .brand { padding: 0 0.75rem 1rem; }
nav.sidebar .brand h1 { font-size: 0.95rem; margin: 0; }
nav.sidebar .brand p { margin: 0.2rem 0 0; font-size: 0.75rem; color: var(--muted); }
nav.sidebar ul { list-style: none; margin: 0; padding: 0; }
nav.sidebar button.nav-item {
  display: block; width: 100%; text-align: left; background: none; border: none;
  padding: 0.5rem 0.75rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem;
  color: var(--fg);
}
nav.sidebar button.nav-item:hover { background: var(--bg-hover); }
nav.sidebar button.nav-item[aria-current="page"] {
  background: var(--accent); color: var(--accent-fg); font-weight: 600;
}
nav.sidebar .theme-toggle {
  margin-top: 1rem; padding: 0.4rem 0.75rem; border: 1px solid var(--border);
  border-radius: 6px; background: none; cursor: pointer; width: calc(100% - 0);
}

main { padding: 1.25rem 1.75rem 3rem; min-width: 0; }
main h2 { font-size: 1.1rem; margin: 0 0 0.75rem; }
.section-intro { color: var(--muted); font-size: 0.85rem; margin: -0.4rem 0 1rem; max-width: 60em; }

.card-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.75rem; margin-bottom: 1.5rem;
}
.card {
  background: var(--bg-raised); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.75rem 0.9rem;
}
.card .metric { font-size: 1.5rem; font-weight: 600; }
.card .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }

table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-bottom: 1rem; }
th, td { text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: var(--bg-hover); }
.detail-row td { background: var(--bg-raised); }
.detail-row .detail-block { padding: 0.5rem 0; }
.detail-block h4 { margin: 0.6rem 0 0.3rem; font-size: 0.8rem; color: var(--muted); text-transform: uppercase; }

.badge {
  display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.72rem;
  padding: 0.1rem 0.45rem; border-radius: 999px; border: 1px solid var(--border);
  white-space: nowrap;
}
.badge-success { color: var(--success); border-color: var(--success); }
.badge-warning { color: var(--warning); border-color: var(--warning); }
.badge-critical { color: var(--critical); border-color: var(--critical); }
.badge-neutral { color: var(--neutral); border-color: var(--border); }
.badge-unknown { color: var(--unknown); border-color: var(--unknown); }

.chip {
  display: inline-block; font-size: 0.72rem; padding: 0.05rem 0.4rem; border-radius: 4px;
  background: var(--bg-hover); color: var(--muted); margin: 0 0.25rem 0.25rem 0;
}

.empty-state {
  border: 1px dashed var(--border); border-radius: 8px; padding: 1.25rem;
  color: var(--muted); max-width: 44em;
}
.empty-state p { margin: 0 0 0.4rem; }
.empty-state code {
  background: var(--bg-hover); padding: 0.05rem 0.3rem; border-radius: 4px; font-size: 0.85em;
}

.subtabs { display: flex; gap: 0.4rem; margin-bottom: 0.9rem; }
.subtabs button {
  border: 1px solid var(--border); background: var(--bg-raised); border-radius: 6px;
  padding: 0.3rem 0.7rem; cursor: pointer; font-size: 0.8rem; color: var(--fg);
}
.subtabs button[aria-selected="true"] { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }

.evidence-item { border-bottom: 1px solid var(--border); padding: 0.5rem 0; }
.evidence-item .observation { margin: 0.2rem 0; }
.filter-input {
  display: block; width: 100%; max-width: 24em; margin-bottom: 0.9rem; padding: 0.4rem 0.6rem;
  background: var(--bg-raised); color: var(--fg); border: 1px solid var(--border); border-radius: 6px;
}
svg.graph { width: 100%; height: auto; }
svg.graph .label { font-size: 11px; fill: var(--fg); }
svg.graph .edge { stroke: var(--border); stroke-width: 1; }
svg.graph .node-a { fill: var(--accent); }
svg.graph .node-b { fill: var(--muted); }

footer.app-footer { color: var(--muted); font-size: 0.75rem; margin-top: 2rem; }

@media (max-width: 860px) {
  #app { grid-template-columns: 1fr; }
  nav.sidebar {
    position: static; height: auto; border-right: none; border-bottom: 1px solid var(--border);
    display: flex; overflow-x: auto; padding: 0.5rem;
  }
  nav.sidebar .brand { display: none; }
  nav.sidebar ul { display: flex; gap: 0.25rem; }
  nav.sidebar button.nav-item { white-space: nowrap; }
  nav.sidebar .theme-toggle { display: none; }
  main { padding: 1rem; }
  table, thead, tbody, th, td, tr { display: block; }
  thead tr { position: absolute; left: -9999px; }
  tbody tr { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 0.6rem; padding: 0.4rem 0.6rem; }
  td { border-bottom: none; padding: 0.25rem 0; }
  td::before { content: attr(data-label); display: block; font-size: 0.7rem; color: var(--muted); }
}
"""

# Rendering is intentionally client-side vanilla JS: the embedded JSON is
# the only data source, and every render_* function only builds DOM nodes
# (createElement/textContent) — never innerHTML with data-derived strings.
_SCRIPT = r"""
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("si-dashboard-data").textContent);

  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (attrs[k] == null) return;
        if (k === "class") node.className = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    for (var i = 2; i < arguments.length; i++) {
      appendChild(node, arguments[i]);
    }
    return node;
  }
  function appendChild(node, child) {
    if (child == null) return;
    if (Array.isArray(child)) { child.forEach(function (c) { appendChild(node, c); }); return; }
    node.appendChild(typeof child === "string" || typeof child === "number"
      ? document.createTextNode(String(child)) : child);
  }

  function table(headers, rows) {
    var thead = el("thead", null, el("tr", null, headers.map(function (h) { return el("th", null, h); })));
    var tbody = el("tbody", null, rows.map(function (r) {
      return el("tr", null, r.map(function (cell, i) {
        var td = el("td", { "data-label": headers[i] || "" });
        appendChild(td, cell);
        return td;
      }));
    }));
    return el("table", null, thead, tbody);
  }

  function emptyState(message, hintHtml) {
    var children = [el("p", null, message)];
    if (hintHtml) children.push(el("p", { class: "hint" }, hintHtml));
    return el("div", { class: "empty-state" }, children);
  }

  var BADGE_SYMBOL = { success: "●", warning: "⚠", critical: "!", neutral: "●", unknown: "?" };
  function badge(label, kind) {
    var k = BADGE_SYMBOL[kind] ? kind : "neutral";
    return el("span", { class: "badge badge-" + k, role: "status", "aria-label": label },
      el("span", { "aria-hidden": "true" }, BADGE_SYMBOL[k] + " "), String(label));
  }
  function chip(text) { return el("span", { class: "chip" }, text); }

  function confidenceKind(c) {
    if (c === "verified" || c === "high") return "success";
    if (c === "medium") return "neutral";
    if (c === "low") return "warning";
    return "unknown";
  }
  function severityKind(s) {
    if (s === "critical" || s === "high") return "critical";
    if (s === "medium") return "warning";
    return "neutral";
  }
  function verdictKind(v) {
    if (v === "update_recommended") return "success";
    if (v === "review_required") return "warning";
    if (v === "not_advisable") return "critical";
    if (v === "no_update_available") return "neutral";
    return "unknown";
  }

  function componentName(id) {
    var c = DATA.components.filter(function (x) { return x.id === id; })[0];
    return c ? c.name : id;
  }

  // Mirrors core.enums.PermissionLevel's declaration order — PermissionLevel
  // is an int Enum, so it serializes to JSON as its integer value.
  var PERMISSION_LEVEL_NAMES = ["OBSERVE", "ANALYZE", "RECOMMEND", "GENERATE_LOCAL_ARTIFACTS",
    "CREATE_BRANCH_OR_DRAFT_PR", "MODIFY_REMOTE_REPOSITORY", "RELEASE_OR_DEPLOY"];
  function permissionLevelName(v) { return PERMISSION_LEVEL_NAMES[v] !== undefined ? PERMISSION_LEVEL_NAMES[v] : String(v); }

  // ---- Sections ----

  function renderOverview() {
    var o = DATA.overview;
    var cards = [
      ["Components", o.component_count],
      ["Capabilities", o.capability_count],
      ["Dependencies", o.dependency_count],
      ["Relationships", o.relationship_count],
      ["Findings", o.finding_count],
      ["Recommendations", o.recommendation_count],
      ["Proposals", o.proposal_count],
      ["Executions", o.execution_count],
      ["Verifications", o.verification_count],
      ["Research results", o.research_result_count],
      ["Approvals", o.approval_count],
    ].map(function (pair) {
      return el("div", { class: "card" }, el("div", { class: "metric" }, String(pair[1])),
        el("div", { class: "label" }, pair[0]));
    });

    var facts = el("table", null,
      el("tbody", null, [
        ["Target", o.target_name + " (" + o.target_locator + ")"],
        ["Snapshot", o.snapshot_id],
        ["Generated", o.generated_at],
      ].map(function (r) { return el("tr", null, el("td", null, r[0]), el("td", null, r[1])); })));

    var findingsBySeverity = el("div", null, Object.keys(o.finding_counts_by_severity).map(function (s) {
      return badge(s.toUpperCase() + ": " + o.finding_counts_by_severity[s], severityKind(s));
    }));

    var updatesBlock;
    if (o.has_update_check) {
      updatesBlock = el("div", null, Object.keys(o.update_verdict_counts).map(function (v) {
        return badge(v.replace(/_/g, " ") + ": " + o.update_verdict_counts[v], verdictKind(v));
      }).concat(o.update_unavailable_count
        ? [badge(o.update_unavailable_count + " source(s) unavailable", "unknown")] : []));
    } else {
      updatesBlock = emptyState(
        "Update check not run for this snapshot.",
        "Run si check-updates <target>, then regenerate this dashboard with --check-updates.");
    }

    var changesBlock;
    if (o.has_previous_snapshot) {
      changesBlock = el("p", null, DATA.changes.length + " change(s) detected versus snapshot " + o.previous_snapshot_id + ".");
    } else {
      changesBlock = emptyState(
        "No previous snapshot to compare.",
        "Run si dashboard <target> --compare-with <previous-snapshot-dir> to see drift over time.");
    }

    return el("div", null,
      el("div", { class: "card-grid" }, cards),
      el("h2", null, "Findings by severity"), findingsBySeverity,
      el("h2", null, "Update Intelligence"), updatesBlock,
      el("h2", null, "Changes since previous snapshot"), changesBlock,
      el("h2", null, "Snapshot facts"), facts);
  }

  function renderFindings() {
    if (!DATA.findings.length) return emptyState("No findings recorded for this snapshot.");
    var order = ["critical", "high", "medium", "low", "info"];
    var groups = {};
    DATA.findings.forEach(function (f) { (groups[f.severity] = groups[f.severity] || []).push(f); });
    var out = [];
    order.forEach(function (sev) {
      var items = groups[sev];
      if (!items) return;
      out.push(el("h3", null, badge(sev.toUpperCase() + " (" + items.length + ")", severityKind(sev))));
      out.push(el("ul", null, items.map(function (f) {
        var affected = (f.affected_entity_ids || []).map(componentName);
        return el("li", null,
          badge(f.confidence, confidenceKind(f.confidence)), " ",
          el("strong", null, f.category), ": ", f.statement,
          el("div", null, affected.length ? affected.map(chip) : null),
          el("div", null, f.evidence.length + " evidence item(s)"));
      })));
    });
    return el("div", null, out);
  }

  function renderUpdates() {
    if (!DATA.overview.has_update_check) {
      return emptyState(
        "Update check not run for this snapshot.",
        "Run si check-updates <target> to see current vs. available state, or si dashboard --check-updates.");
    }
    var blocks = DATA.update_assessments.map(function (a) {
      var d = a.state_diff;
      var items = d.items.map(function (it) {
        return el("li", null, badge(it.category, "neutral"), " ", it.description,
          " ", badge(it.confidence, confidenceKind(it.confidence)));
      });
      return el("div", { class: "card", style: "margin-bottom:0.75rem" },
        el("h3", null, d.identity.name + " (" + (d.identity.distribution_source || "unknown source") + ")"),
        el("p", null, "Current: " + (d.from_state.version || "unknown") +
          "  →  Available: " + (d.to_state.version || "unknown")),
        badge(a.verdict.replace(/_/g, " "), verdictKind(a.verdict)), " ",
        badge(a.verdict_confidence, confidenceKind(a.verdict_confidence)),
        el("p", null, a.verdict_rationale),
        a.unknown_dimensions.length
          ? el("p", null, "Unresolved dimensions: " + a.unknown_dimensions.join(", ")) : null,
        a.affected_entity_ids.length
          ? el("p", null, "Affects: ", a.affected_entity_ids.map(componentName).map(chip)) : null,
        items.length ? el("ul", null, items) : el("p", null, "No further evidenced differences beyond the version change."));
    });
    var failures = DATA.update_unavailable.length ? el("div", null,
      el("h3", null, "Sources unavailable"),
      el("ul", null, DATA.update_unavailable.map(function (f) {
        return el("li", null, badge("SOURCE UNAVAILABLE", "unknown"), " " + f.ecosystem + ":" + f.name + " — " + f.message);
      }))) : null;
    return el("div", null,
      blocks.length ? blocks : emptyState("No dependency had both a resolvable ecosystem and a reachable provider."),
      failures);
  }

  function renderRecommendations() {
    if (!DATA.recommendations.length) return emptyState("No recommendations generated for this snapshot.");
    return table(["Objective", "Confidence", "Effort", "Risk", "Approval", "Rationale"],
      DATA.recommendations.map(function (r) {
        return [r.objective, badge(r.confidence, confidenceKind(r.confidence)),
          r.estimated_effort || "unknown", r.risk || "unknown",
          permissionLevelName(r.required_approval_level), r.rationale];
      }));
  }

  function renderProposals() {
    if (!DATA.proposals.length) {
      return emptyState("No proposals recorded for this snapshot.",
        "Run si propose <problem> --record <snapshot-dir> to attach one.");
    }
    return table(["Kind", "Problem", "Required permission", "Why not sufficient as-is"],
      DATA.proposals.map(function (p) {
        return [p.kind, p.problem, permissionLevelName(p.required_permission_level),
          p.why_existing_solutions_insufficient || "—"];
      }));
  }

  function renderExecutions() {
    if (!DATA.executions.length) {
      return emptyState("No executions recorded for this snapshot.",
        "Run si execute <plan> <target> --approve --record <snapshot-dir> to attach one.");
    }
    return table(["Action", "Target", "Branch", "Commit", "Applied", "Decision", "Executed at"],
      DATA.executions.map(function (e) {
        return [e.action, e.target, e.branch_name || "—", e.commit_sha || "—",
          badge(String(e.applied), e.applied ? "success" : "critical"),
          e.decision_reason, e.executed_at];
      }));
  }

  function renderComponents() {
    if (!DATA.components.length) return emptyState("No components discovered in this snapshot.");
    var rows = DATA.components.map(function (c) {
      var capCount = DATA.capabilities.filter(function (cap) { return cap.provider_ids.indexOf(c.id) !== -1; }).length;
      return { c: c, row: [c.name, c.kind, c.path || "—", c.description || "—",
        String(capCount), String(c.dependencies.length), String(c.evidence.length)] };
    });
    var body = table(["Name", "Kind", "Path", "Description", "Capabilities", "Dependencies", "Evidence"],
      rows.map(function (r) { return r.row; }));
    body.querySelectorAll("tbody tr").forEach(function (tr, i) {
      tr.classList.add("clickable");
      tr.tabIndex = 0;
      tr.setAttribute("role", "button");
      var toggle = function () { toggleComponentDetail(tr, rows[i].c); };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(); } });
    });
    return body;
  }

  function toggleComponentDetail(tr, c) {
    var next = tr.nextSibling;
    if (next && next.classList && next.classList.contains("detail-row")) { next.remove(); return; }
    var findings = DATA.findings.filter(function (f) { return (f.affected_entity_ids || []).indexOf(c.id) !== -1; });
    var assessments = DATA.update_assessments.filter(function (a) { return a.state_diff.identity.component_id === c.id; });
    var block = el("div", { class: "detail-block" },
      el("h4", null, "Interfaces"),
      c.interfaces.length ? el("ul", null, c.interfaces.map(function (i) { return el("li", null, i.kind + ": " + (i.description || "")); })) : el("p", null, "None recorded."),
      el("h4", null, "Dependencies"),
      c.dependencies.length ? el("ul", null, c.dependencies.map(function (d) { return el("li", null, d.name + " (" + d.ecosystem + ") " + (d.version_constraint || "")); })) : el("p", null, "None recorded."),
      el("h4", null, "Findings affecting this component"),
      findings.length ? el("ul", null, findings.map(function (f) { return el("li", null, badge(f.severity, severityKind(f.severity)), " " + f.statement); })) : el("p", null, "None."),
      el("h4", null, "Update assessments"),
      assessments.length ? el("ul", null, assessments.map(function (a) { return el("li", null, badge(a.verdict, verdictKind(a.verdict)), " " + a.verdict_rationale); })) : el("p", null, "Not checked."),
      el("h4", null, "Evidence"),
      c.evidence.length ? el("ul", null, c.evidence.map(function (e) { return el("li", null, "[" + e.kind + "] " + e.observation); })) : el("p", null, "None recorded."));
    var td = el("td", { colspan: "7" }, block);
    var row = el("tr", { class: "detail-row" }, td);
    tr.parentNode.insertBefore(row, tr.nextSibling);
  }

  function renderCapabilities() {
    if (!DATA.capabilities.length) return emptyState("No capabilities discovered in this snapshot.");
    var view = "list";
    var container = el("div", null);
    function draw() {
      container.innerHTML = "";
      if (view === "graph") {
        appendChild(container, capabilityGraph());
      } else {
        appendChild(container, table(["Name", "Status", "Confidence", "Providers", "Consumers"],
          DATA.capabilities.map(function (cap) {
            return [cap.name, cap.status, badge(cap.confidence, confidenceKind(cap.confidence)),
              String(cap.provider_ids.length), String(cap.consumer_ids.length)];
          })));
        if (view === "detail") {
          appendChild(container, DATA.capabilities.map(function (cap) {
            return el("div", { class: "card", style: "margin-bottom:0.5rem" },
              el("strong", null, cap.name),
              el("p", null, "Providers: ", cap.provider_ids.map(componentName).map(chip)),
              el("p", null, "Consumers: ", cap.consumer_ids.length ? cap.consumer_ids.map(componentName).map(chip) : "none recorded"),
              el("p", null, cap.evidence.length + " evidence item(s)"));
          }));
        }
      }
    }
    function capabilityGraph() {
      var rowHeight = 32, height = rowHeight * DATA.capabilities.length + 20;
      var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 520 " + height);
      svg.setAttribute("class", "graph");
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", "Capability provider graph");
      DATA.capabilities.forEach(function (cap, i) {
        var y = 20 + i * rowHeight;
        var providerLabel = cap.provider_ids.map(componentName).join(", ");
        svg.appendChild(svgLine(120, y, 260, y));
        svg.appendChild(svgCircle(120, y, "node-a"));
        svg.appendChild(svgText(10, y + 4, providerLabel));
        svg.appendChild(svgCircle(260, y, "node-b"));
        svg.appendChild(svgText(275, y + 4, cap.name + " (" + cap.status + ")"));
      });
      return svg;
    }
    var tabs = el("div", { class: "subtabs", role: "tablist" }, ["list", "detail", "graph"].map(function (v) {
      var btn = el("button", { role: "tab", "aria-selected": String(v === view) }, v);
      btn.addEventListener("click", function () {
        view = v;
        tabs.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-selected", String(b.textContent === v)); });
        draw();
      });
      return btn;
    }));
    draw();
    return el("div", null, tabs, container);
  }

  function svgLine(x1, y, x2, y2) {
    var l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", x1); l.setAttribute("y1", y); l.setAttribute("x2", x2); l.setAttribute("y2", y2);
    l.setAttribute("class", "edge"); return l;
  }
  function svgCircle(x, y, cls) {
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", "5"); c.setAttribute("class", cls); return c;
  }
  function svgText(x, y, text) {
    var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", x); t.setAttribute("y", y); t.setAttribute("class", "label"); t.textContent = text; return t;
  }

  function renderDependencies() {
    if (!DATA.dependencies.length) return emptyState("No dependencies discovered in this snapshot.");
    return table(["Name", "Ecosystem", "Constraint", "Resolved version"],
      DATA.dependencies.map(function (d) {
        return [d.name, d.ecosystem, d.version_constraint || "—", d.resolved_version || "unknown"];
      }));
  }

  function renderChanges() {
    if (!DATA.changes.length) {
      var reasons = [];
      if (!DATA.overview.has_previous_snapshot) reasons.push("no previous snapshot was given (--compare-with)");
      if (!DATA.overview.has_update_check) reasons.push("no update check was run (--check-updates)");
      return emptyState("No changes to show.",
        reasons.length ? "Reason: " + reasons.join(" and ") + "." : "Both comparisons ran and found no differences.");
    }
    return table(["Origin", "Category", "Description", "Confidence"],
      DATA.changes.map(function (c) {
        return [c.origin === "snapshot_diff" ? "vs. previous snapshot" : "update availability",
          c.category, c.description, c.confidence ? badge(c.confidence, confidenceKind(c.confidence)) : "—"];
      }));
  }

  function renderResearch() {
    if (!DATA.research_rankings.length) {
      return emptyState("No research results recorded for this snapshot.",
        "Run si research <query> --record <snapshot-dir> to attach candidates.");
    }
    return table(["Identifier", "Provider", "License", "Recently active", "Archived", "Stars (informational)", "Unresolved dimensions"],
      DATA.research_rankings.map(function (a) {
        return [a.result.identifier, a.result.provider,
          (a.result.license || "unknown") + " (" + a.license_confidence + ")",
          a.is_recently_active === null ? "unknown" : String(a.is_recently_active),
          a.is_archived === null ? "unknown" : String(a.is_archived),
          a.stargazer_count === null ? "unknown" : String(a.stargazer_count),
          a.unknown_dimensions.join(", ") || "none"];
      }));
  }

  function renderEvidence() {
    if (!DATA.evidence.length) return emptyState("No evidence recorded for this snapshot.");
    var wrap = el("div", null);
    var input = el("input", { class: "filter-input", type: "search", placeholder: "Filter evidence (source, observation, kind)...", "aria-label": "Filter evidence" });
    var list = el("div", null);
    function draw(filter) {
      list.innerHTML = "";
      var f = (filter || "").toLowerCase();
      DATA.evidence.filter(function (ref) {
        var e = ref.evidence;
        return !f || (e.source + " " + e.observation + " " + e.kind).toLowerCase().indexOf(f) !== -1;
      }).forEach(function (ref) {
        var e = ref.evidence;
        appendChild(list, el("div", { class: "evidence-item" },
          badge(e.kind, "neutral"), " ", badge(e.confidence, confidenceKind(e.confidence)),
          el("p", { class: "observation" }, e.observation),
          el("p", null, "Source: " + e.source + (e.locator ? " (" + e.locator + ")" : "")),
          el("div", null, ref.referenced_by.map(chip))));
      });
    }
    input.addEventListener("input", function () { draw(input.value); });
    draw("");
    return el("div", null, input, list);
  }

  function renderSettings() {
    var g = DATA.governance;
    var approvals = DATA.approvals.length
      ? table(["Actor", "Scope", "Action", "Target", "Level", "Approved at", "Expires at"],
          DATA.approvals.map(function (a) {
            return [a.actor, a.scope, a.action, a.target, permissionLevelName(a.permission_level),
              a.approved_at, a.expires_at || "never"];
          }))
      : emptyState("No approvals recorded for this snapshot.");
    return el("div", null,
      el("h2", null, "Default policy"),
      el("p", null, "Default maximum permission level: ", el("strong", null, g.default_max_permission_level)),
      el("p", null, "Actions forbidden by default, regardless of any approval:"),
      el("ul", null, g.forbidden_actions.map(function (a) { return el("li", null, a); })),
      el("h2", null, "Approvals on record"),
      approvals);
  }

  var SECTIONS = [
    { id: "overview", label: "Overview", render: renderOverview },
    { id: "findings", label: "Findings", render: renderFindings },
    { id: "updates", label: "Updates", render: renderUpdates },
    { id: "recommendations", label: "Recommendations", render: renderRecommendations },
    { id: "proposals", label: "Proposals", render: renderProposals },
    { id: "executions", label: "Executions", render: renderExecutions },
    { id: "components", label: "Components", render: renderComponents },
    { id: "capabilities", label: "Capabilities", render: renderCapabilities },
    { id: "dependencies", label: "Dependencies", render: renderDependencies },
    { id: "changes", label: "Changes", render: renderChanges },
    { id: "research", label: "Research", render: renderResearch },
    { id: "evidence", label: "Evidence", render: renderEvidence },
    { id: "settings", label: "Settings / System", render: renderSettings },
  ];

  function showSection(id) {
    var section = SECTIONS.filter(function (s) { return s.id === id; })[0] || SECTIONS[0];
    document.querySelectorAll("nav.sidebar button.nav-item").forEach(function (btn) {
      btn.setAttribute("aria-current", btn.dataset.section === section.id ? "page" : "false");
    });
    var main = document.getElementById("view");
    main.innerHTML = "";
    appendChild(main, el("h2", null, section.label));
    appendChild(main, section.render());
    location.hash = section.id;
  }

  function buildNav() {
    var ul = el("ul", null, SECTIONS.map(function (s) {
      var btn = el("button", { class: "nav-item", "data-section": s.id, "aria-current": "false" }, s.label);
      btn.addEventListener("click", function () { showSection(s.id); });
      return el("li", null, btn);
    }));
    document.querySelector("nav.sidebar").appendChild(ul);
  }

  function initTheme() {
    // Dark-first: default to dark on first visit regardless of OS
    // preference, unless this viewer already chose light here before.
    var btn = document.querySelector(".theme-toggle");
    var stored = null;
    try { stored = localStorage.getItem("si-dashboard-theme"); } catch (e) { /* private mode */ }
    document.documentElement.setAttribute("data-theme", stored || "dark");
    btn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme") || "dark";
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("si-dashboard-theme", next); } catch (e) { /* private mode */ }
    });
  }

  buildNav();
  initTheme();
  var initial = location.hash ? location.hash.slice(1) : "overview";
  showSection(initial);
})();
"""


def _json_script(data: DashboardData) -> str:
    payload = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)
    # A literal "</script>" inside the JSON payload would close the tag early.
    return payload.replace("</", "<\\/")


def generate_dashboard_html(data: DashboardData) -> str:
    """Render `data` as a single, self-contained interactive HTML document."""
    title = f"System Intelligence Console — {data.overview.target_name}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<div id="app">
  <nav class="sidebar" aria-label="Dashboard sections">
    <div class="brand">
      <h1>System Intelligence</h1>
      <p>Console — {data.overview.target_name}</p>
    </div>
    <button class="theme-toggle" type="button">Toggle theme</button>
  </nav>
  <main id="view"></main>
</div>
<script type="application/json" id="si-dashboard-data">{_json_script(data)}</script>
<script>{_SCRIPT}</script>
<footer class="app-footer" style="padding: 0 1.75rem 2rem;">
  Snapshot {data.overview.snapshot_id}, generated {data.overview.generated_at}. Read-only console —
  no action here merges, deletes, force-pushes, or writes to any remote.
</footer>
</body>
</html>
"""
