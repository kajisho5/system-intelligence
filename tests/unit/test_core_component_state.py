from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.enums import ComponentKind, Confidence


def _identity() -> ComponentIdentity:
    return ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill", distribution_source="npm"
    )


def test_component_state_defaults_are_unknown_not_guessed() -> None:
    state = ComponentState(identity=_identity())

    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN
    assert state.is_deprecated is None
    assert state.capabilities == []
    assert state.dependencies == []
    assert state.interfaces == []
    assert state.runtime_requirements == []
    assert state.release_info is None
    assert state.changelog == []


def test_component_state_is_timezone_aware() -> None:
    state = ComponentState(identity=_identity())
    assert state.retrieved_at.tzinfo is not None


def test_available_state_requires_provider() -> None:
    available = AvailableState(identity=_identity(), provider="npm", version="0.9.2")
    assert available.provider == "npm"
    assert available.version == "0.9.2"


def test_identity_is_generic_across_component_kinds() -> None:
    skill_identity = ComponentIdentity(component_kind=ComponentKind.SKILL, name="ffmpeg-skill")
    package_identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="react")

    assert skill_identity.component_kind == ComponentKind.SKILL
    assert package_identity.component_kind == ComponentKind.PACKAGE
