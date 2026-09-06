from system_intelligence.core.capability import Capability
from system_intelligence.core.enums import CapabilityStatus, Confidence


def test_capability_not_duplicated_with_single_provider() -> None:
    capability = Capability(
        name="video-review",
        provider_ids=["component-1"],
        status=CapabilityStatus.AVAILABLE,
        confidence=Confidence.VERIFIED,
    )
    assert capability.is_duplicated() is False


def test_capability_duplicated_with_multiple_distinct_providers() -> None:
    capability = Capability(
        name="video-review",
        provider_ids=["component-1", "component-2"],
        status=CapabilityStatus.AVAILABLE,
        confidence=Confidence.HIGH,
    )
    assert capability.is_duplicated() is True


def test_capability_not_duplicated_when_same_provider_repeated() -> None:
    capability = Capability(name="video-review", provider_ids=["component-1", "component-1"])
    assert capability.is_duplicated() is False
