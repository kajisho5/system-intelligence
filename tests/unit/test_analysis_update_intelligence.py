from system_intelligence.analysis.update_intelligence import (
    assess_impact,
    build_current_state,
    check_dependency_updates,
    diff_states,
)
from system_intelligence.core.component_state import AvailableState, ComponentIdentity
from system_intelligence.core.entities import Dependency, Repository
from system_intelligence.core.enums import (
    ComponentKind,
    Confidence,
    RelationshipType,
    UpdateVerdict,
)
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.security import SecurityAdvisory
from system_intelligence.research.update_provider import ComponentUpdateError
from system_intelligence.research.vulnerability_provider import VulnerabilityLookupError


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


def test_build_current_state_npm_bare_version_is_an_exact_pin() -> None:
    """npm's own convention pins an exact version with no operator at all
    (e.g. `"react": "18.2.0"` in package.json) — unlike pypi, which spells
    the same thing "==18.2.0"."""
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="18.2.0"))
    assert state.version == "18.2.0"
    assert state.version_confidence == Confidence.HIGH


def test_build_current_state_npm_minor_wildcard_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="1.x"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_npm_patch_wildcard_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="1.2.x"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_npm_uppercase_wildcard_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="1.2.X"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_bare_star_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="*"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_npm_caret_range_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="^1.2.3"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_npm_tilde_range_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="~1.2.3"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_npm_hyphen_range_leaves_version_unknown() -> None:
    state = build_current_state(_dependency(ecosystem="npm", version_constraint="1.0.0 - 2.0.0"))
    assert state.version is None
    assert state.version_confidence == Confidence.UNKNOWN


def test_build_current_state_pep440_prerelease_pin_still_matches() -> None:
    """A regression guard: widening the exact-pin regex for npm must not
    stop matching pypi's already-supported bare PEP 440 suffixes."""
    state = build_current_state(_dependency(ecosystem="pypi", version_constraint="==1.2.3rc1"))
    assert state.version == "1.2.3rc1"
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


def test_assess_impact_uses_relationships_when_given() -> None:
    dep = _dependency(resolved_version="0.8.2")
    current = build_current_state(dep)
    # identity.component_id is the dependency id (as _identity_for produces),
    # matching how a real DEPENDS_ON edge's target_id is keyed.
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)
    relationship = Relationship(type=RelationshipType.DEPENDS_ON, source_id="r1", target_id=dep.id)

    assessment = assess_impact(diff, [], relationships=[relationship])

    assert assessment.affected_entity_ids == ["r1"]


def test_assess_impact_relationships_take_precedence_over_dependency_scan() -> None:
    """An empty but *provided* relationship list means "computed, no matches" —
    it must not fall back to the (here, matching) dependency-name scan."""
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    current = build_current_state(dep)
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [repo], relationships=[])

    assert assessment.affected_entity_ids == []


def test_assess_impact_multi_hop_reaches_capability_and_consumer() -> None:
    """Change -> Component (DEPENDS_ON) -> Capability (PROVIDES) ->
    Consumer (USES): a 3-hop chain, using only relationship types the
    pipeline already materializes."""
    dep = _dependency(resolved_version="0.8.2")
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    current = build_current_state(dep)
    diff = diff_states(current, available)

    relationships = [
        Relationship(type=RelationshipType.DEPENDS_ON, source_id="provider-1", target_id=dep.id),
        Relationship(
            type=RelationshipType.PROVIDES, source_id="provider-1", target_id="capability-1"
        ),
        Relationship(type=RelationshipType.USES, source_id="consumer-1", target_id="capability-1"),
    ]

    assessment = assess_impact(diff, [], relationships=relationships)

    # Level-order (BFS), not a global sort: direct dependents first, then
    # the capabilities they provide, then those capabilities' consumers.
    assert assessment.affected_entity_ids == ["provider-1", "capability-1", "consumer-1"]


def test_assess_impact_multi_hop_cascades_through_a_second_capability() -> None:
    """A reached consumer that itself provides a further capability keeps
    the walk going (Component -> Capability -> Consumer -> Capability ->
    further Consumer), not just a fixed number of hops."""
    dep = _dependency(resolved_version="0.8.2")
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    current = build_current_state(dep)
    diff = diff_states(current, available)

    relationships = [
        Relationship(type=RelationshipType.DEPENDS_ON, source_id="mid", target_id=dep.id),
        Relationship(type=RelationshipType.PROVIDES, source_id="mid", target_id="cap-1"),
        Relationship(type=RelationshipType.USES, source_id="downstream", target_id="cap-1"),
        Relationship(type=RelationshipType.PROVIDES, source_id="downstream", target_id="cap-2"),
        Relationship(type=RelationshipType.USES, source_id="far-downstream", target_id="cap-2"),
    ]

    assessment = assess_impact(diff, [], relationships=relationships)

    assert set(assessment.affected_entity_ids) == {
        "mid",
        "cap-1",
        "downstream",
        "cap-2",
        "far-downstream",
    }


def test_assess_impact_multi_hop_is_cycle_safe_and_deterministic() -> None:
    """A cycle (provider <-> capability <-> the same provider as a
    consumer) must not infinite-loop, and results must be reproducible."""
    dep = _dependency(resolved_version="0.8.2")
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    current = build_current_state(dep)
    diff = diff_states(current, available)

    relationships = [
        Relationship(type=RelationshipType.DEPENDS_ON, source_id="a", target_id=dep.id),
        Relationship(type=RelationshipType.PROVIDES, source_id="a", target_id="cap-1"),
        Relationship(type=RelationshipType.USES, source_id="a", target_id="cap-1"),
        # "a" both provides and uses "cap-1" -- a direct cycle back to itself.
    ]

    first = assess_impact(diff, [], relationships=relationships)
    second = assess_impact(diff, [], relationships=relationships)

    assert first.affected_entity_ids == ["a", "cap-1"]
    assert first.affected_entity_ids == second.affected_entity_ids


def test_assess_impact_multi_hop_ignores_unrelated_component() -> None:
    dep = _dependency(resolved_version="0.8.2")
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    current = build_current_state(dep)
    diff = diff_states(current, available)

    relationships = [
        Relationship(type=RelationshipType.DEPENDS_ON, source_id="a", target_id=dep.id),
        # Entirely disconnected from the changed identity or "a".
        Relationship(type=RelationshipType.PROVIDES, source_id="unrelated", target_id="cap-x"),
    ]

    assessment = assess_impact(diff, [], relationships=relationships)

    assert assessment.affected_entity_ids == ["a"]
    assert "unrelated" not in assessment.affected_entity_ids
    assert "cap-x" not in assessment.affected_entity_ids


def test_assess_impact_multi_hop_ignores_unrecognized_relationship_types() -> None:
    """Only DEPENDS_ON/PROVIDES/USES propagate impact — other relationship
    types (e.g. DUPLICATES) must never be treated as an impact path."""
    dep = _dependency(resolved_version="0.8.2")
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    current = build_current_state(dep)
    diff = diff_states(current, available)

    relationships = [
        Relationship(type=RelationshipType.DEPENDS_ON, source_id="a", target_id=dep.id),
        Relationship(type=RelationshipType.DUPLICATES, source_id="a", target_id="b"),
    ]

    assessment = assess_impact(diff, [], relationships=relationships)

    assert assessment.affected_entity_ids == ["a"]


def test_assess_impact_multi_hop_falls_back_when_identity_has_no_component_id() -> None:
    """Even with a non-empty relationship list, a StateDiff whose identity
    never got a `component_id` (e.g. no DEPENDS_ON edge could be keyed to
    it) has nothing to start the graph walk from, so it must fall back to
    the same-Snapshot dependency-name scan rather than silently returning
    no affected entities."""
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    current = build_current_state(dep)
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill", distribution_source="npm"
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)
    relationship = Relationship(type=RelationshipType.DEPENDS_ON, source_id="other", target_id="x")

    assessment = assess_impact(diff, [repo], relationships=[relationship])

    assert assessment.affected_entity_ids == ["r1"]


def test_assess_impact_falls_back_to_dependency_scan_without_relationships() -> None:
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    current = build_current_state(dep)
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill", distribution_source="npm"
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [repo], relationships=None)

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


def test_check_dependency_updates_forwards_relationships_to_impact_assessment() -> None:
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    # Mirrors what `_identity_for(dep)` (called internally) actually
    # produces, since `_FakeProvider` returns this `available` verbatim
    # regardless of the identity it's called with.
    identity = ComponentIdentity(
        component_id=dep.id,
        component_kind=ComponentKind.PACKAGE,
        name="ffmpeg-skill",
        distribution_source="npm",
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    relationship = Relationship(
        type=RelationshipType.DEPENDS_ON, source_id="other-component", target_id=dep.id
    )

    check = check_dependency_updates(
        [repo],
        providers={"npm": _FakeProvider(available=available)},
        relationships=[relationship],
    )

    assert len(check.assessments) == 1
    # The relationship graph says "other-component" depends on this — not
    # "repo" (which would be found by the dependency-name-scan fallback).
    assert check.assessments[0].affected_entity_ids == ["other-component"]


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


def test_assess_impact_carries_advisories_without_changing_verdict() -> None:
    dep = _dependency(resolved_version="0.8.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill", distribution_source="npm"
    )
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)
    advisory = SecurityAdvisory(id="GHSA-xxxx", summary="bad", severity="HIGH")

    assessment = assess_impact(diff, [], current_advisories=[advisory], available_advisories=[])

    assert assessment.current_version_advisories == [advisory]
    assert assessment.available_version_advisories == []
    # A vulnerable current version is informational only -- it does not by
    # itself unlock a better verdict than the unresolved-dimensions case
    # would otherwise produce.
    assert assessment.verdict == UpdateVerdict.REVIEW_REQUIRED


def test_assess_impact_advisories_default_to_empty_when_omitted() -> None:
    dep = _dependency(resolved_version="0.8.2")
    current = build_current_state(dep)
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = diff_states(current, available)

    assessment = assess_impact(diff, [])

    assert assessment.current_version_advisories == []
    assert assessment.available_version_advisories == []


class _FakeVulnerabilityProvider:
    name = "npm"

    def __init__(
        self,
        advisories_by_version: dict[str, list[SecurityAdvisory]] | None = None,
        error: Exception | None = None,
    ):
        self._advisories_by_version = advisories_by_version or {}
        self._error = error
        self.queried_versions: list[str] = []

    def fetch_advisories(self, identity: ComponentIdentity, version: str) -> list[SecurityAdvisory]:
        self.queried_versions.append(version)
        if self._error:
            raise self._error
        return self._advisories_by_version.get(version, [])


def test_check_dependency_updates_populates_advisories_from_vulnerability_provider() -> None:
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    current_advisory = SecurityAdvisory(id="GHSA-old", summary="fixed in the new version")
    vuln_provider = _FakeVulnerabilityProvider({"0.8.2": [current_advisory], "0.9.2": []})

    check = check_dependency_updates(
        [repo],
        providers={"npm": _FakeProvider(available=available)},
        vulnerability_providers={"npm": vuln_provider},
    )

    assert len(check.assessments) == 1
    assert check.assessments[0].current_version_advisories == [current_advisory]
    assert check.assessments[0].available_version_advisories == []
    assert sorted(vuln_provider.queried_versions) == ["0.8.2", "0.9.2"]


def test_check_dependency_updates_reuses_current_advisories_when_versions_match() -> None:
    """Never query the same version twice -- current == available means
    the same advisory set applies to both, with no update available at all."""
    dep = _dependency(resolved_version="0.9.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    advisory = SecurityAdvisory(id="GHSA-still-open", summary="no fix yet")
    vuln_provider = _FakeVulnerabilityProvider({"0.9.2": [advisory]})

    check = check_dependency_updates(
        [repo],
        providers={"npm": _FakeProvider(available=available)},
        vulnerability_providers={"npm": vuln_provider},
    )

    assert check.assessments[0].current_version_advisories == [advisory]
    assert check.assessments[0].available_version_advisories == [advisory]
    assert vuln_provider.queried_versions == ["0.9.2"]


def test_check_dependency_updates_without_vulnerability_providers_leaves_advisories_empty() -> None:
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")

    check = check_dependency_updates([repo], providers={"npm": _FakeProvider(available=available)})

    assert check.assessments[0].current_version_advisories == []
    assert check.assessments[0].available_version_advisories == []


def test_check_dependency_updates_vulnerability_lookup_failure_does_not_block_freshness_check() -> (
    None
):
    dep = _dependency(resolved_version="0.8.2")
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    vuln_provider = _FakeVulnerabilityProvider(error=VulnerabilityLookupError("OSV.dev down"))

    check = check_dependency_updates(
        [repo],
        providers={"npm": _FakeProvider(available=available)},
        vulnerability_providers={"npm": vuln_provider},
    )

    assert len(check.assessments) == 1
    assert check.assessments[0].current_version_advisories == []
    assert check.assessments[0].verdict != UpdateVerdict.UNKNOWN


def test_check_dependency_updates_skips_vulnerability_lookup_when_current_version_unknown() -> None:
    dep = _dependency(version_constraint="^0.8.2")  # a range: current version stays unresolved
    repo = Repository(id="r1", name="repo", path=".", dependencies=[dep])
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    vuln_provider = _FakeVulnerabilityProvider({"0.9.2": [SecurityAdvisory(id="x", summary="y")]})

    check = check_dependency_updates(
        [repo],
        providers={"npm": _FakeProvider(available=available)},
        vulnerability_providers={"npm": vuln_provider},
    )

    assert check.assessments[0].current_version_advisories == []
    assert check.assessments[0].available_version_advisories == [
        SecurityAdvisory(id="x", summary="y")
    ]
    assert vuln_provider.queried_versions == ["0.9.2"]
