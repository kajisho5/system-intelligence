"""Report and dashboard exporters, all consuming the canonical Snapshot.

Phase 4 scope (see docs/design/docs/16-roadmap.md and
docs/design/IMPLEMENTATION_BACKLOG.md, Epic 6):

- `html.generate_html_report`: a single, dependency-free static HTML report
  (overview, components, capability graph, dependency graph, findings; the
  recommendation/research/proposal/verification/history sections are
  explicit "not yet available" placeholders, not silently empty or faked).
- `diff.diff_snapshots`: a deterministic diff between two Snapshots, keyed
  by stable entity id for components/capabilities/dependencies and by
  (category, statement) for findings (which have no persistent id across
  scans).
- `dashboard_data.build_dashboard_data` / `dashboard_html.generate_dashboard_html`:
  the interactive "System Intelligence Console" — `dashboard_data` is the
  read-model/API layer (aggregation only, zero new facts), `dashboard_html`
  only renders it. Distinct from `html.generate_html_report` in role, not
  in source of truth: report is static/export-oriented, dashboard is
  interactive/drill-down-oriented, and both consume the same `Snapshot`.

The canonical JSON snapshot itself (`core.snapshot.Snapshot`) is the
machine-readable export this module renders — no second, incompatible
source of truth is created for the UI.
"""

from system_intelligence.reporting.dashboard_data import DashboardData, build_dashboard_data
from system_intelligence.reporting.dashboard_html import generate_dashboard_html
from system_intelligence.reporting.diff import SnapshotDiff, diff_snapshots
from system_intelligence.reporting.html import generate_html_report

__all__ = [
    "DashboardData",
    "SnapshotDiff",
    "build_dashboard_data",
    "diff_snapshots",
    "generate_dashboard_html",
    "generate_html_report",
]
