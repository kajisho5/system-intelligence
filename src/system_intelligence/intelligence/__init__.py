"""Orchestration: given an intent, select and run the minimum capability set.

`registry.CAPABILITIES` names every independently-runnable capability,
including the discovery/analysis detectors that `discover_local_repository`/
`analyze_local_repository` always run unconditionally (agent detection, ADR
detection, capability-gap auditing) -- these must stay registered here too,
or `si plan`'s preview and `run_capabilities`'s selective execution silently
diverge from what those two commands actually do.

Phase 7 scope (docs/design/docs/10-plugin-skill-system.md, "Dynamic
selection"; docs/design/IMPLEMENTATION_BACKLOG.md):

- `registry.CAPABILITIES` / `resolve_dependencies`: every independently
  runnable capability and its dependency graph.
- `intents.resolve_intent`: the minimum, dependency-expanded capability set
  for a named intent — a pure planning function that runs nothing.
  `intents.classify_intent` maps free text to a known intent by keyword
  lookup, deliberately not an LLM call (docs/03-architecture.md: the LLM
  is not the only source of truth).
- `orchestrator.run_capabilities`: executes exactly a given capability set.
  A request for `documentation_only`, for example, never scans structure,
  detects Skills, or parses dependencies — those capabilities simply never
  run, not "run but get discarded".

`discovery.discover_local_repository` / `analysis.analyze_local_repository`
remain the direct, well-tested path for the "inspect"/"diagnose" intents
(they already run every capability those intents need); this package adds
the ability to run a narrower, explainable subset for anything else.
"""

from system_intelligence.intelligence.intents import (
    INTENTS,
    UnknownIntentError,
    classify_intent,
    resolve_intent,
)
from system_intelligence.intelligence.orchestrator import run_capabilities
from system_intelligence.intelligence.registry import CAPABILITIES, resolve_dependencies

__all__ = [
    "CAPABILITIES",
    "INTENTS",
    "UnknownIntentError",
    "classify_intent",
    "resolve_dependencies",
    "resolve_intent",
    "run_capabilities",
]
