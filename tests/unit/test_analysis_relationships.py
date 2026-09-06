from system_intelligence.analysis.relationships import build_relationships
from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Dependency, Repository
from system_intelligence.core.enums import CapabilityStatus, Confidence, RelationshipType


def test_build_relationships_depends_on_edge_from_component_dependencies() -> None:
    dep = Dependency(id="d1", name="react", ecosystem="npm")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])

    relationships = build_relationships([repo], [])

    depends_on = [r for r in relationships if r.type == RelationshipType.DEPENDS_ON]
    assert len(depends_on) == 1
    assert depends_on[0].source_id == "r1"
    assert depends_on[0].target_id == "d1"


def test_build_relationships_provides_and_uses_edges_from_capability() -> None:
    capability = Capability(
        id="c1",
        name="cap",
        provider_ids=["p1"],
        consumer_ids=["u1"],
        status=CapabilityStatus.AVAILABLE,
        confidence=Confidence.HIGH,
    )

    relationships = build_relationships([], [capability])

    provides = [r for r in relationships if r.type == RelationshipType.PROVIDES]
    uses = [r for r in relationships if r.type == RelationshipType.USES]
    assert len(provides) == 1
    assert provides[0].source_id == "p1"
    assert provides[0].target_id == "c1"
    assert len(uses) == 1
    assert uses[0].source_id == "u1"
    assert uses[0].target_id == "c1"


def test_build_relationships_duplicates_edge_for_same_named_capabilities() -> None:
    cap_a = Capability(id="c1", name="dup", status=CapabilityStatus.AVAILABLE)
    cap_b = Capability(id="c2", name="dup", status=CapabilityStatus.AVAILABLE)

    relationships = build_relationships([], [cap_a, cap_b])

    duplicates = [r for r in relationships if r.type == RelationshipType.DUPLICATES]
    assert len(duplicates) == 1
    assert {duplicates[0].source_id, duplicates[0].target_id} == {"c1", "c2"}


def test_build_relationships_no_duplicate_edge_for_unique_capability_names() -> None:
    cap_a = Capability(id="c1", name="a", status=CapabilityStatus.AVAILABLE)
    cap_b = Capability(id="c2", name="b", status=CapabilityStatus.AVAILABLE)

    relationships = build_relationships([], [cap_a, cap_b])

    assert not [r for r in relationships if r.type == RelationshipType.DUPLICATES]


def test_build_relationships_is_deterministic_across_calls() -> None:
    dep = Dependency(id="d1", name="react", ecosystem="npm")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    capability = Capability(id="c1", name="cap", provider_ids=["r1"])

    first = build_relationships([repo], [capability])
    second = build_relationships([repo], [capability])

    assert [r.id for r in first] == [r.id for r in second]


def test_build_relationships_empty_inputs_produce_no_edges() -> None:
    assert build_relationships([], []) == []
