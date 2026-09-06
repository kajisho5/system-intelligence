from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.enums import ComponentKind, Confidence, StateDiffCategory
from system_intelligence.core.state_diff import StateDiff, StateDiffItem


def _identity() -> ComponentIdentity:
    return ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="pkg")


def test_state_diff_has_items_reflects_item_list() -> None:
    current = ComponentState(identity=_identity(), version="1.0.0")
    available = AvailableState(identity=_identity(), provider="pypi", version="1.0.0")

    empty_diff = StateDiff(identity=_identity(), from_state=current, to_state=available)
    assert empty_diff.has_items is False

    item = StateDiffItem(
        category=StateDiffCategory.CHANGED, description="x", confidence=Confidence.HIGH
    )
    non_empty_diff = StateDiff(
        identity=_identity(), from_state=current, to_state=available, items=[item]
    )
    assert non_empty_diff.has_items is True


def test_state_diff_version_delta_is_display_only() -> None:
    current = ComponentState(identity=_identity(), version="0.8.2")
    available = AvailableState(identity=_identity(), provider="npm", version="0.9.2")
    diff = StateDiff(
        identity=_identity(),
        from_state=current,
        to_state=available,
        version_delta="0.8.2 -> 0.9.2",
    )
    # version_delta carries no items of its own — it is not proof of any
    # classified difference by itself.
    assert diff.version_delta == "0.8.2 -> 0.9.2"
    assert diff.items == []
