from system_intelligence.analysis.capabilities import (
    attach_consumers,
    detect_duplicate_capabilities,
    extract_capabilities,
)
from system_intelligence.core.entities import Dependency, Repository, Skill
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


def test_attach_consumers_explicit_dependency_declaration_is_recorded() -> None:
    provider_skill = Skill(id="skill-provider", name="ffmpeg-skill")
    [capability] = extract_capabilities([provider_skill])
    dep = Dependency(id="d1", name="ffmpeg-skill", ecosystem="npm")
    consumer = Repository(id="consumer-1", name="consumer", path=".", dependencies=[dep])

    [updated] = attach_consumers([capability], [provider_skill, consumer])

    assert updated.consumer_ids == ["consumer-1"]
    # Evidence must be traceable back to the actual dependency declaration,
    # not merely asserted.
    assert any(e.source == "consumer-1" for e in updated.evidence)
    assert any("ffmpeg-skill" in e.observation for e in updated.evidence)


def test_attach_consumers_no_matching_dependency_leaves_consumer_ids_empty() -> None:
    provider_skill = Skill(id="skill-provider", name="ffmpeg-skill")
    [capability] = extract_capabilities([provider_skill])
    unrelated_dep = Dependency(id="d1", name="some-other-package", ecosystem="npm")
    other = Repository(id="other-1", name="other", path=".", dependencies=[unrelated_dep])

    [updated] = attach_consumers([capability], [provider_skill, other])

    assert updated.consumer_ids == []
    assert updated.evidence == capability.evidence  # unchanged: nothing to add


def test_attach_consumers_never_infers_from_similar_name_or_description() -> None:
    """Only an exact Dependency.name == Capability.name match counts.

    A component whose *description* happens to mention the capability, or
    whose dependency name is merely similar (not identical), must not be
    recorded as a consumer.
    """
    provider_skill = Skill(id="skill-provider", name="ffmpeg-skill")
    [capability] = extract_capabilities([provider_skill])
    near_miss_dep = Dependency(id="d1", name="ffmpeg-skill-utils", ecosystem="npm")
    consumer = Repository(
        id="consumer-1",
        name="consumer",
        path=".",
        description="Uses ffmpeg-skill under the hood",
        dependencies=[near_miss_dep],
    )

    [updated] = attach_consumers([capability], [provider_skill, consumer])

    assert updated.consumer_ids == []


def test_attach_consumers_provider_is_never_its_own_consumer() -> None:
    dep = Dependency(id="d1", name="ffmpeg-skill", ecosystem="npm")
    provider_skill = Skill(id="skill-provider", name="ffmpeg-skill", dependencies=[dep])
    [capability] = extract_capabilities([provider_skill])

    [updated] = attach_consumers([capability], [provider_skill])

    assert updated.consumer_ids == []


def test_attach_consumers_is_deterministic_and_does_not_duplicate() -> None:
    provider_skill = Skill(id="skill-provider", name="ffmpeg-skill")
    [capability] = extract_capabilities([provider_skill])
    dep = Dependency(id="d1", name="ffmpeg-skill", ecosystem="npm")
    consumer = Repository(id="consumer-1", name="consumer", path=".", dependencies=[dep])

    first = attach_consumers([capability], [provider_skill, consumer])
    second = attach_consumers(first, [provider_skill, consumer])

    assert first[0].consumer_ids == ["consumer-1"]
    assert second[0].consumer_ids == ["consumer-1"]  # re-running does not duplicate the id
