import pytest

from system_intelligence.intelligence.intents import (
    UnknownIntentError,
    classify_intent,
    resolve_intent,
)


def test_resolve_intent_inspect() -> None:
    resolved = resolve_intent("inspect")
    assert set(resolved) == {
        "git_metadata",
        "structure_scan",
        "skill_detection",
        "ci_docs_detection",
    }


def test_resolve_intent_documentation_only_is_narrow() -> None:
    resolved = resolve_intent("documentation_only")
    assert set(resolved) == {"ci_docs_detection", "documentation_audit"}
    # Crucially, it does NOT pull in structure_scan/skill_detection/etc.
    assert "structure_scan" not in resolved
    assert "skill_detection" not in resolved


def test_resolve_intent_unknown_raises() -> None:
    with pytest.raises(UnknownIntentError, match="nonexistent"):
        resolve_intent("nonexistent")


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("Diagnose this repository.", "diagnose"),
        ("Please inspect the repo", "inspect"),
        ("Is the README up to date?", "documentation_only"),
        ("Do we have a circular import problem?", "circular_imports_only"),
        ("What are our dependencies?", "dependencies_only"),
        ("How can we improve this?", "improve"),
        ("blah blah nothing matches", "diagnose"),
    ],
)
def test_classify_intent(text: str, expected_intent: str) -> None:
    assert classify_intent(text) == expected_intent


def test_classify_intent_is_case_insensitive() -> None:
    assert classify_intent("DIAGNOSE THIS REPOSITORY") == "diagnose"
