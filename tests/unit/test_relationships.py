from system_intelligence.core.enums import Confidence, RelationshipType
from system_intelligence.core.relationships import Relationship


def test_relationship_defaults_to_unknown_confidence() -> None:
    relationship = Relationship(
        type=RelationshipType.DEPENDS_ON,
        source_id="component-a",
        target_id="component-b",
    )
    assert relationship.confidence == Confidence.UNKNOWN
    assert relationship.id.startswith("relationship-")
