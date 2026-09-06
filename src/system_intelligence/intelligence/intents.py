"""Named intents and a deterministic intent classifier.

docs/design/docs/10-plugin-skill-system.md: "Given an intent, select the
minimum capability set required. ... It should not blindly activate every
installed capability." `resolve_intent` is the planning function that
answers that without running anything.

`classify_intent` is a plain keyword lookup, not an LLM call — the core
rule that "the LLM should not be the only source of truth"
(docs/03-architecture.md) applies to intent routing too. It is intentionally
simple and auditable, and falls back to the broadest read-only intent
rather than guessing something narrower that might miss what was asked.
"""

from __future__ import annotations

from system_intelligence.intelligence.registry import resolve_dependencies

_DIAGNOSE_CAPABILITIES: frozenset[str] = frozenset(
    {
        "git_metadata",
        "structure_scan",
        "skill_detection",
        "agent_detection",
        "adr_detection",
        "ci_docs_detection",
        "documentation_audit",
        "ci_test_audit",
        "dependency_extraction",
        "capability_extraction",
        "unused_skill_detection",
        "circular_dependency_detection",
        "relationship_graph_construction",
        "capability_gap_detection",
    }
)

INTENTS: dict[str, frozenset[str]] = {
    "inspect": frozenset(
        {
            "git_metadata",
            "structure_scan",
            "skill_detection",
            "agent_detection",
            "adr_detection",
            "ci_docs_detection",
        }
    ),
    "diagnose": _DIAGNOSE_CAPABILITIES,
    "improve": _DIAGNOSE_CAPABILITIES | {"recommendation_ranking"},
    "documentation_only": frozenset({"ci_docs_detection", "documentation_audit"}),
    "dependencies_only": frozenset({"structure_scan", "dependency_extraction"}),
    "circular_imports_only": frozenset({"circular_dependency_detection"}),
}


class UnknownIntentError(ValueError):
    """Raised when a name isn't a registered intent."""


def resolve_intent(intent: str) -> list[str]:
    """Return the ordered, dependency-expanded capability ids for `intent`."""
    if intent not in INTENTS:
        known = ", ".join(sorted(INTENTS))
        raise UnknownIntentError(f"Unknown intent {intent!r}. Known intents: {known}.")
    return resolve_dependencies(set(INTENTS[intent]))


#: (keywords, intent) pairs, checked in order — first match wins. Ordered
#: narrowest-first so e.g. "diagnose the README" still hits documentation
#: only if "readme" is checked before the broader "diagnose".
_KEYWORD_INTENTS: list[tuple[tuple[str, ...], str]] = [
    (("circular import", "import cycle", "circular dependency"), "circular_imports_only"),
    (("documentation", "docs", "readme"), "documentation_only"),
    (("dependenc",), "dependencies_only"),
    (("improve", "recommend"), "improve"),
    (("inspect", "discover", "inventory"), "inspect"),
    (("diagnose", "health", "audit"), "diagnose"),
]


def classify_intent(text: str) -> str:
    """Map free text to the narrowest matching known intent.

    Falls back to `"diagnose"` — the broadest read-only intent — when no
    keyword matches, rather than guessing a narrower one that might skip
    capabilities the request actually needed.
    """
    lowered = text.lower()
    for keywords, intent in _KEYWORD_INTENTS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "diagnose"
