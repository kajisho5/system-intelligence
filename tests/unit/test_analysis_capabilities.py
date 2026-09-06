from system_intelligence.analysis.capabilities import (
    detect_duplicate_capabilities,
    extract_capabilities,
)
from system_intelligence.core.entities import Skill
from system_intelligence.core.enums import CapabilityStatus


def test_extract_capabilities_standard_skill_is_available() -> None:
    skill = Skill(name="video-review", description="Reviews video", is_standard_format=True)
    capabilities = extract_capabilities([skill])
    assert len(capabilities) == 1
    assert capabilities[0].status == CapabilityStatus.AVAILABLE
    assert capabilities[0].provider_ids == [skill.id]


def test_extract_capabilities_non_standard_skill_is_partial() -> None:
    skill = Skill(name="mystery", is_standard_format=False)
    capabilities = extract_capabilities([skill])
    assert capabilities[0].status == CapabilityStatus.PARTIAL


def test_detect_duplicate_capabilities() -> None:
    skill_a = Skill(name="video-review")
    skill_b = Skill(name="video-review")
    capabilities = extract_capabilities([skill_a, skill_b])

    findings = detect_duplicate_capabilities(capabilities)

    assert len(findings) == 1
    assert findings[0].category == "duplicated_capability"
    assert set(findings[0].affected_entity_ids) == {skill_a.id, skill_b.id}


def test_detect_duplicate_capabilities_no_duplicates() -> None:
    capabilities = extract_capabilities([Skill(name="a"), Skill(name="b")])
    assert detect_duplicate_capabilities(capabilities) == []
