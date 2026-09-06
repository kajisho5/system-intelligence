from system_intelligence.analysis.update_intelligence import (
    assess_impact,
    build_current_state,
    check_dependency_updates,
    diff_states,
)
from system_intelligence.core.component_state import AvailableState, ComponentIdentity
from system_intelligence.core.entities import Dependency, Repository
from system_intelligence.core.enums import ComponentKind, Confidence, UpdateVerdict
from system_intelligence.research.update_provider import ComponentUpdateError


def _dependency(**overrides: object) -> Dependency:
    defaults: dict[str, object] = {
        "id": "d1",
        "name": "ffmpeg-skill",
        "ecosystem": "npm",
        "version_constraint": "^0.8.2",
    }
    defaults.update(overrides)
    return Dependency(**defaults)  # type: ignore[arg-type]


def test_build_current_state_range_constraint_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(version_constraint="^0.8.2"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_exact_pin_is_used_at_high_confidence() -> None:
    state = build_current_state(_dependency(version_constraint="==0.8.2"))
    assert state.version == "0.8.2"
    assert state.version_confidence == Confidence.HIGH


def test_build_current_state_resolved_version_wins_at_verified_confidence() -> None:
    dep = _dependency(version_constraint="^0.8.2", resolved_version="0.8.5")
    state = build_current_state(dep)
    assert state.version == "0.8.5"
    assert state.version_confidence == Confidence.VERIFIED


def test_diff_states_no_items_when_versions_match() -> None:
    dep = _dependency(resolved_version="0.9.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")

    diff = diff_states(current, available)

    assert diff.items == []
    assert diff.version_delta is None


def test_diff_states_records_version_change_item() -> None:
    dep = _dependency(resolved_version="0.8.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")

    diff = diff_states(current, available)

    assert diff.version_delta == "0.8.2 -> 0.9.2"
    assert len(diff.items) == 1
    assert diff.items[0].category.value == "changed"


def test_diff_states_records_deprecation_item() -> None:
    dep = _dependency(resolved_version="0.9.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(
        identity=identity, provider="npm", version="0.9.2", is_deprecated=True
    )

    diff = diff_states(current, available)

    assert any(i.category.value == "deprecated" for i in diff.items)


def test_assess_impact_unknown_when_current_version_unresolved() -> None:
    dep = _dependency(version_constraint="^0.8.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [])

    assert assessment.verdict == UpdateVerdict.UNKNOWN


def test_assess_impact_no_update_available_when_versions_match() -> None:
    dep = _dependency(resolved_version="0.9.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [])

    assert assessment.verdict == UpdateVerdict.NO_UPDATE_AVAILABLE


def test_assess_impact_not_advisable_when_available_is_deprecated() -> None:
    dep = _dependency(resolved_version="0.8.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(
        identity=identity, provider="npm", version="0.9.2", is_deprecated=True
    )
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [])

    assert assessment.verdict == UpdateVerdict.NOT_ADVISABLE


def test_assess_impact_never_recommends_update_from_version_alone() -> None:
    """The core anti-single-signal rule: a version delta alone must cap out at REVIEW_REQUIRED."""
    dep = _dependency(resolved_version="0.8.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [])

    assert assessment.verdict == UpdateVerdict.REVIEW_REQUIRED
    assert assessment.unknown_dimensions  # capability/dependency/interface/installation unresolved


def test_assess_impact_finds_affected_components() -> None:
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    current = build_current_state(dep)
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill", distribution_source="npm"
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [repo])

    assert assessment.affected_entity_ids == ["r1"]


class _FakeProvider:
    name = "npm"

    def __init__(self, available: AvailableState | None = None, error: Exception | None = None):
        self._available = available
        self._error = error

    def fetch_available_state(self, identity: ComponentIdentity) -> AvailableState | None:
        if self._error:
            raise self._error
        return self._available


def test_check_dependency_updates_skips_ecosystems_without_provider() -> None:
    dep = _dependency(ecosystem="pypi")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])

    check = check_dependency_updates([repo], providers={})

    assert check.assessments == []
    assert check.unavailable == []


def test_check_dependency_updates_skips_none_results() -> None:
    dep = _dependency()
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])

    check = check_dependency_updates([repo], providers={"npm": _FakeProvider(available=None)})

    assert check.assessments == []
    assert check.unavailable == []


def test_check_dependency_updates_records_provider_errors() -> None:
    dep = _dependency()
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    error = ComponentUpdateError("boom")

    check = check_dependency_updates([repo], providers={"npm": _FakeProvider(error=error)})

    assert check.assessments == []
    assert len(check.unavailable) == 1
    assert check.unavailable[0].ecosystem == "npm"
    assert check.unavailable[0].name == "ffmpeg-skill"


def test_check_dependency_updates_produces_assessment_on_success() -> None:
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")

    check = check_dependency_updates([repo], providers={"npm": _FakeProvider(available=available)})

    assert len(check.assessments) == 1
    assert check.assessments[0].state_diff.identity.name == "ffmpeg-skill"


def test_check_dependency_updates_deduplicates_shared_dependency() -> None:
    dep_a = _dependency(id="a", resolved_version="0.8.2")
    dep_b = _dependency(id="b", resolved_version="0.8.2")
    repo_a = Repository(id="r1", name="repo-a", path="a", dependencies=[dep_a])
    repo_b = Repository(id="r2", name="repo-b", path="b", dependencies=[dep_b])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")

    check = check_dependency_updates(
        [repo_a, repo_b], providers={"npm": _FakeProvider(available=available)}
    )

    assert len(check.assessments) == 1
