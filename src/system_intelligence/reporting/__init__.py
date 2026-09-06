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

The canonical JSON snapshot itself (`core.snapshot.Snapshot`) is the
machine-readable export this module renders — no second, incompatible
source of truth is created for the UI.
"""

from system_intelligence.reporting.diff import SnapshotDiff, diff_snapshots
from system_intelligence.reporting.html import generate_html_report

__all__ = ["SnapshotDiff", "diff_snapshots", "generate_html_report"]
