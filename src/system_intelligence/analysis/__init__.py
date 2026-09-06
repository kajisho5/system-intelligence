"""Deterministic analyzers over discovered evidence.

Phase 3 scope (see docs/design/docs/16-roadmap.md and
docs/design/IMPLEMENTATION_BACKLOG.md, Epic 4), orchestrated by
`analyze_local_repository`:

- documentation gaps (missing README/LICENSE/CONTRIBUTING)
- CI/test presence
- dependency extraction from pyproject.toml/package.json
- capability extraction from Skills and Agents, and duplicate-name detection
- unreferenced Skill/Agent detection (never `verified_unused` from a static
  search alone — see ADR-010)
- circular-import detection across local Python modules (AST-based)
- capability *gap* detection (`gaps.py`) — opt-in: a project declares
  required capabilities in `.si/requirements.json`; a repository with no
  such file contributes zero gap findings, never an inferred one

Not yet implemented: semantic architecture heuristics beyond import
cycles, and documentation *content* quality (only presence/absence is
checked).
"""

from system_intelligence.analysis.engine import AnalysisResult, analyze_local_repository

__all__ = ["AnalysisResult", "analyze_local_repository"]
