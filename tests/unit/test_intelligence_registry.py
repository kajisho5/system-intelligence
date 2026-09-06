import pytest

from system_intelligence.intelligence.registry import CAPABILITIES, resolve_dependencies


def test_all_capability_dependencies_are_registered() -> None:
    for capability in CAPABILITIES.values():
        for dependency in capability.requires:
            assert dependency in CAPABILITIES, f"{capability.id} requires unknown {dependency!r}"


def test_resolve_dependencies_includes_transitive_requirements() -> None:
    resolved = resolve_dependencies({"documentation_audit"})
    assert resolved == ["ci_docs_detection", "documentation_audit"]


def test_resolve_dependencies_deduplicates_shared_dependencies() -> None:
    # capability_extraction and unused_skill_detection both need skill_detection.
    resolved = resolve_dependencies({"capability_extraction", "unused_skill_detection"})
    assert resolved.count("skill_detection") == 1
    assert resolved.index("skill_detection") < resolved.index("capability_extraction")
    assert resolved.index("skill_detection") < resolved.index("unused_skill_detection")


def test_resolve_dependencies_no_requirements() -> None:
    resolved = resolve_dependencies({"circular_dependency_detection"})
    assert resolved == ["circular_dependency_detection"]


def test_resolve_dependencies_recommendation_ranking_pulls_everything_it_needs() -> None:
    resolved = resolve_dependencies({"recommendation_ranking"})
    for required in [
        "ci_docs_detection",
        "documentation_audit",
        "ci_test_audit",
        "skill_detection",
        "capability_extraction",
        "unused_skill_detection",
        "circular_dependency_detection",
        "recommendation_ranking",
    ]:
        assert required in resolved
    assert resolved[-1] == "recommendation_ranking"


def test_resolve_dependencies_unknown_capability_raises() -> None:
    with pytest.raises(KeyError):
        resolve_dependencies({"nonexistent"})
