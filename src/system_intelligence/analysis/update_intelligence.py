"""Component Update Intelligence (Lifecycle detector family, docs/05-analysis-
engine.md: "release activity, dependency freshness").

Flow: current state -> available state -> state diff -> impact -> verdict.
Deliberately never collapses to a version-string comparison — see
`core.enums.UpdateVerdict` and `core.impact.ImpactAssessment`'s validator,
which physically forbids `UPDATE_RECOMMENDED` unless every material
dimension was actually resolved.

Generic across `ComponentKind` and distribution source (ADR-001, ADR-007):
this module knows nothing about any specific package, Skill, or
organization — only about `Dependency`/`Component` records already present
in a Snapshot and whatever `ComponentUpdateProvider` the caller supplies
per ecosystem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.entities import Component, Dependency
from system_intelligence.core.enums import (
    ComponentKind,
    Confidence,
    RelationshipType,
    StateDiffCategory,
    UpdateVerdict,
)
from system_intelligence.core.evidence import Evidence
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.security import SecurityAdvisory
from system_intelligence.core.state_diff import StateDiff, StateDiffItem
from system_intelligence.research.update_provider import (
    ComponentUpdateError,
    ComponentUpdateProvider,
)
from system_intelligence.research.vulnerability_provider import (
    VulnerabilityLookupError,
    VulnerabilityProvider,
)

#: A constraint with no range operator, wildcard, or whitespace-separated
#: alternative is treated as pinning an exact, currently-installed version
#: (e.g. the bare "1.2.3" npm convention, or pypi's "==1.2.3"). Anything
#: else ("^1.2.3", ">=1.0,<2.0", "1.0.0 - 2.0.0") is a range, not a known
#: installed version. The `==?` prefix is optional so a bare version
#: matches too; the character class still allows letters so PEP 440
#: suffixes ("1.2.3rc1", "2.0a1") keep matching as before. The optional
#: `v` prefix is Go's own module-version convention (`v1.2.3`, or a
#: pseudo-version like `v0.0.0-20210101000000-abcdef123456`) -- without
#: it, every Go dependency's constraint would fail to match at all and
#: its current version would stay permanently unresolved.
_EXACT_PIN_RE = re.compile(r"^(?:==?\s*)?v?[0-9][0-9A-Za-z.+_-]*$")

#: Ecosystems whose own manifest convention treats a **bare** version
#: constraint (no operator) as pinning that exact version -- npm's
#: package.json ("18.2.0" means exactly that version), Go's go.mod
#: (every `require` line is already an exact, MVS-resolved version, or a
#: pseudo-version -- Go has no bare-caret-range convention at all, unlike
#: Cargo), and Maven's pom.xml (a literal "1.2.3" is that exact version;
#: `analysis.dependencies._extract_pom_dependencies` already only ever
#: extracts literal versions, never a `${property}` placeholder -- and
#: Maven's own range syntax, e.g. "[1.0,2.0)" or "(,2.0]", starts with a
#: bracket/paren character `_EXACT_PIN_RE` does not match, so it is
#: correctly excluded here without special-casing). Never assumed for an
#: ecosystem where a bare version means something else: Cargo.toml's own
#: convention treats a bare "1.2.3" as a caret requirement (`^1.2.3`, a
#: compatible-updates range), not an exact pin, so a bare Cargo constraint
#: is only ever exact when explicitly prefixed with "=" (Cargo's own
#: exact-pin operator) -- never guessed from the bare form.
_BARE_CONSTRAINT_IS_EXACT_PIN = frozenset({"npm", "go", "maven"})


def _has_wildcard_segment(constraint: str) -> bool:
    """True if any dot-separated segment is npm's wildcard shorthand.

    A segment of exactly "x"/"X" (e.g. "1.x", "1.2.x") or a bare "*" would
    otherwise slip past `_EXACT_PIN_RE` now that a bare version is allowed
    to match — these are ranges, not exact pins, so they are rejected
    explicitly rather than guessed at.
    """
    return any(segment.lower() == "x" or segment == "*" for segment in constraint.split("."))


def _identity_for(dependency: Dependency) -> ComponentIdentity:
    return ComponentIdentity(
        component_id=dependency.id,
        component_kind=ComponentKind.PACKAGE,
        name=dependency.name,
        distribution_source=dependency.ecosystem,
    )


def build_current_state(dependency: Dependency) -> ComponentState:
    """Build the Current State for a declared Dependency.

    Only what the manifest itself proves is populated: a resolved version
    (if the discovery layer ever fills that in) or an exact version pin.
    A range constraint (the common case: "^18.3.1", ">=2") does not tell us
    what is actually installed, so `version` stays `None` rather than being
    guessed from the constraint's lower bound.
    """
    version = dependency.resolved_version
    version_confidence = Confidence.VERIFIED if version else Confidence.UNKNOWN
    if not version and dependency.version_constraint:
        constraint = dependency.version_constraint.strip()
        has_pin_operator = constraint.startswith("=")
        bare_is_exact = dependency.ecosystem in _BARE_CONSTRAINT_IS_EXACT_PIN
        if (
            _EXACT_PIN_RE.match(constraint)
            and not _has_wildcard_segment(constraint)
            and (has_pin_operator or bare_is_exact)
        ):
            version = constraint.lstrip("=").strip()
            version_confidence = Confidence.HIGH

    return ComponentState(
        identity=_identity_for(dependency),
        version=version,
        version_confidence=version_confidence,
        evidence=list(dependency.evidence),
    )


def _version_diff_item(current: ComponentState, available: ComponentState) -> StateDiffItem | None:
    if not current.version or not available.version or current.version == available.version:
        return None
    confidence = (
        Confidence.VERIFIED
        if current.version_confidence == Confidence.VERIFIED
        and available.version_confidence == Confidence.VERIFIED
        else Confidence.HIGH
    )
    return StateDiffItem(
        category=StateDiffCategory.CHANGED,
        description=f"Version changed from {current.version!r} to {available.version!r}.",
        confidence=confidence,
        evidence=[*current.evidence, *available.evidence],
    )


def _deprecation_diff_item(available: AvailableState) -> StateDiffItem | None:
    if available.is_deprecated is True:
        return StateDiffItem(
            category=StateDiffCategory.DEPRECATED,
            description=(
                f"Available version {available.version!r} is marked deprecated by its publisher."
            ),
            confidence=Confidence.VERIFIED,
            evidence=list(available.evidence),
        )
    if available.release_info is not None and available.release_info.is_yanked is True:
        return StateDiffItem(
            category=StateDiffCategory.DEPRECATED,
            description=(
                f"Available version {available.version!r} has been yanked/withdrawn by its "
                "publisher."
            ),
            confidence=Confidence.VERIFIED,
            evidence=list(available.evidence),
        )
    return None


def diff_states(current: ComponentState, available: AvailableState) -> StateDiff:
    """Compare Current State against Available State into classified items.

    Only dimensions actually populated on *both* sides are compared —
    asymmetric data (e.g. available-state dependencies with no current-state
    equivalent because nothing introspected the installed package) is never
    reported as an added/removed/changed item, since that would fabricate a
    diff from missing data rather than an observed change.
    """
    items: list[StateDiffItem] = []
    version_item = _version_diff_item(current, available)
    if version_item:
        items.append(version_item)
    deprecation_item = _deprecation_diff_item(available)
    if deprecation_item:
        items.append(deprecation_item)

    version_delta = None
    if current.version and available.version and current.version != available.version:
        version_delta = f"{current.version} -> {available.version}"

    return StateDiff(
        identity=available.identity,
        from_state=current,
        to_state=available,
        version_delta=version_delta,
        items=items,
    )


def _traverse_affected(start_id: str, relationships: list[Relationship]) -> list[str]:
    """Breadth-first walk of DEPENDS_ON -> PROVIDES -> USES edges from `start_id`.

    `start_id` (the changed identity's own Component/Dependency id) is never
    itself included in the result. Each relationship type only propagates
    impact in the direction its own meaning supports:

    - DEPENDS_ON (`source depends_on target`): a change to an id already
      reached can affect `source_id` wherever `target_id` is that id — the
      direct-dependents hop this function replaces (still exactly 1-hop
      when no PROVIDES/USES edges continue the chain, so existing 1-hop
      behavior is unchanged).
    - PROVIDES (`source provides target`, source=Component,
      target=Capability): a change to a Component already reached can
      affect `target_id` (the Capability it provides).
    - USES (`source uses target`, source=consumer Component,
      target=Capability): a change to a Capability already reached can
      affect `source_id` (its consumer), which may itself provide further
      Capabilities — the walk continues from there.

    Deterministic (each level's newly-reached ids are sorted before being
    added) and cycle-safe: a `visited` set stops any id from being
    re-expanded, however many relationship types loop back to it, and the
    walk always terminates once no new id is reached (bounded by the
    number of distinct entities in the relationship list).

    The result is "entities relationship topology says could be affected",
    not "entities that will break" — `ImpactAssessment.breaking_items`,
    `unknown_dimensions`, and `verdict` are what carry that judgment; this
    function only ever expands *which* ids are worth attaching that
    judgment to.
    """
    by_type: dict[RelationshipType, list[Relationship]] = {}
    for rel in relationships:
        by_type.setdefault(rel.type, []).append(rel)

    visited: set[str] = {start_id}
    frontier: set[str] = {start_id}
    order: list[str] = []

    while frontier:
        next_frontier: set[str] = set()
        for rel in by_type.get(RelationshipType.DEPENDS_ON, ()):
            if rel.target_id in frontier and rel.source_id not in visited:
                next_frontier.add(rel.source_id)
        for rel in by_type.get(RelationshipType.PROVIDES, ()):
            if rel.source_id in frontier and rel.target_id not in visited:
                next_frontier.add(rel.target_id)
        for rel in by_type.get(RelationshipType.USES, ()):
            if rel.target_id in frontier and rel.source_id not in visited:
                next_frontier.add(rel.source_id)

        newly_reached = sorted(next_frontier - visited)
        if not newly_reached:
            break
        visited.update(newly_reached)
        order.extend(newly_reached)
        frontier = set(newly_reached)

    return order


def _affected_by_relationships(
    identity: ComponentIdentity, relationships: list[Relationship]
) -> list[str] | None:
    if identity.component_id is None:
        return None
    return _traverse_affected(identity.component_id, relationships)


def _affected_by_dependency_scan(
    identity: ComponentIdentity, components: list[Component]
) -> list[str]:
    return [
        component.id
        for component in components
        if any(
            dep.name == identity.name and dep.ecosystem == identity.distribution_source
            for dep in component.dependencies
        )
    ]


def assess_impact(
    state_diff: StateDiff,
    components: list[Component],
    relationships: list[Relationship] | None = None,
    *,
    current_advisories: list[SecurityAdvisory] | None = None,
    available_advisories: list[SecurityAdvisory] | None = None,
) -> ImpactAssessment:
    """Assess what a StateDiff would mean for the rest of the observed system.

    When `relationships` is given (a Snapshot with `relationship_graph_
    construction` already run), `affected_entity_ids` is computed from real
    DEPENDS_ON edges keyed by the Dependency's own id — precise even across
    a monorepo with multiple manifests declaring the same package name.
    Without it, this falls back to a same-Snapshot dependency name/ecosystem
    scan, which will under-report indirect/transitive consumers but never
    over-reports.

    `current_advisories`/`available_advisories` (from a `VulnerabilityProvider`,
    optional) are carried straight onto the returned `ImpactAssessment` as
    independent, informational facts — they never change `verdict`. A
    vulnerable current version does not by itself prove capability/
    dependency/interface impact was evaluated, so it still cannot unlock
    `UPDATE_RECOMMENDED` on its own (`ImpactAssessment`'s own validator);
    what an update actually fixes is for the caller/human to read from
    these lists directly.
    """
    identity = state_diff.identity
    affected_entity_ids = (
        _affected_by_relationships(identity, relationships) if relationships is not None else None
    )
    if affected_entity_ids is None:
        affected_entity_ids = _affected_by_dependency_scan(identity, components)

    breaking_items = [i for i in state_diff.items if i.category == StateDiffCategory.BREAKING]
    capability_impact = [
        i for i in state_diff.items if i.category == StateDiffCategory.CAPABILITY_CHANGE
    ]
    dependency_impact = [
        i for i in state_diff.items if i.category == StateDiffCategory.DEPENDENCY_CHANGE
    ]
    interface_impact = [
        i for i in state_diff.items if i.category == StateDiffCategory.INTERFACE_CHANGE
    ]

    from_state, to_state = state_diff.from_state, state_diff.to_state
    unknown_dimensions = tuple(
        dimension
        for dimension, has_both_sides in (
            ("capability", bool(from_state.capabilities and to_state.capabilities)),
            ("dependency", bool(from_state.dependencies and to_state.dependencies)),
            ("interface", bool(from_state.interfaces and to_state.interfaces)),
            (
                "installation",
                bool(from_state.runtime_requirements and to_state.runtime_requirements),
            ),
        )
        if not has_both_sides
    )

    evidence: list[Evidence] = [*from_state.evidence, *to_state.evidence]

    if from_state.version is None:
        verdict = UpdateVerdict.UNKNOWN
        verdict_confidence = Confidence.UNKNOWN
        rationale = "The currently installed version could not be determined from the manifest."
    elif from_state.version == to_state.version:
        verdict = UpdateVerdict.NO_UPDATE_AVAILABLE
        verdict_confidence = Confidence.VERIFIED
        rationale = f"The available version ({to_state.version!r}) matches the current version."
    elif to_state.is_deprecated is True:
        verdict = UpdateVerdict.NOT_ADVISABLE
        verdict_confidence = Confidence.HIGH
        rationale = "The latest available version is itself marked deprecated by its publisher."
    elif to_state.release_info is not None and to_state.release_info.is_yanked is True:
        verdict = UpdateVerdict.NOT_ADVISABLE
        verdict_confidence = Confidence.HIGH
        rationale = "The latest available version has been yanked/withdrawn by its publisher."
    elif breaking_items or unknown_dimensions:
        verdict = UpdateVerdict.REVIEW_REQUIRED
        verdict_confidence = Confidence.MEDIUM
        unresolved = ", ".join(unknown_dimensions) or "none"
        rationale = (
            f"An update from {from_state.version!r} to {to_state.version!r} is available, but "
            f"{len(breaking_items)} breaking item(s) were flagged and/or the following "
            f"dimensions could not be evaluated from available evidence: {unresolved}."
        )
    else:
        verdict = UpdateVerdict.UPDATE_RECOMMENDED
        verdict_confidence = Confidence.HIGH
        rationale = (
            f"An update from {from_state.version!r} to {to_state.version!r} is available; "
            "capability, dependency, and interface impact were all evaluated with no breaking "
            "changes found."
        )

    return ImpactAssessment(
        state_diff=state_diff,
        affected_entity_ids=affected_entity_ids,
        breaking_items=breaking_items,
        capability_impact=capability_impact,
        dependency_impact=dependency_impact,
        interface_impact=interface_impact,
        unknown_dimensions=unknown_dimensions,
        verdict=verdict,
        verdict_confidence=verdict_confidence,
        verdict_rationale=rationale,
        evidence=evidence,
        current_version_advisories=current_advisories or [],
        available_version_advisories=available_advisories or [],
    )


@dataclass(frozen=True)
class UpdateLookupFailure:
    """A lookup that could not be completed — the source was unreachable.

    Distinct from a lookup that completed and found nothing (silently
    skipped, see `check_dependency_updates`): this means the ecosystem
    registry could not be confirmed to lack the package, only that this
    attempt to ask it failed. Never treat this as "up to date" or "not
    found" — the correct status is `SOURCE_UNAVAILABLE`/unknown.
    """

    ecosystem: str
    name: str
    message: str


@dataclass(frozen=True)
class UpdateCheckResult:
    assessments: list[ImpactAssessment]
    unavailable: list[UpdateLookupFailure]


def _fetch_advisories(
    provider: VulnerabilityProvider | None, identity: ComponentIdentity, version: str | None
) -> list[SecurityAdvisory]:
    """Best-effort advisory lookup: no provider, no version, or a failed
    lookup all quietly yield no advisories rather than blocking the update
    check — vulnerability data is supplementary here, not core to it."""
    if provider is None or version is None:
        return []
    try:
        return provider.fetch_advisories(identity, version)
    except VulnerabilityLookupError:
        return []


def check_dependency_updates(
    components: list[Component],
    providers: dict[str, ComponentUpdateProvider],
    relationships: list[Relationship] | None = None,
    vulnerability_providers: dict[str, VulnerabilityProvider] | None = None,
) -> UpdateCheckResult:
    """Run Update Intelligence for every Dependency whose ecosystem has a provider.

    `providers` maps ecosystem name (e.g. "pypi", "npm") to the adapter that
    handles it — dependencies in an ecosystem with no configured provider
    are silently skipped (not reported as findings, and not reported as
    failures), since "no provider available" is a caller configuration
    fact, not a fact about the dependency itself. A provider that raises
    `ComponentUpdateError` (network/HTTP/parse failure) is recorded in
    `UpdateCheckResult.unavailable` rather than aborting the whole check or
    being silently dropped. `relationships` (from `analysis.relationships.
    build_relationships`) is forwarded to `assess_impact` for precise
    affected-component lookup; omit it to fall back to the same-Snapshot
    dependency scan.

    `vulnerability_providers` (same shape as `providers`, optional) adds a
    known-vulnerability lookup for whichever version(s) could be resolved.
    A failed or missing lookup never blocks the freshness check itself —
    see `_fetch_advisories`.
    """
    seen: set[tuple[str, str]] = set()
    assessments: list[ImpactAssessment] = []
    unavailable: list[UpdateLookupFailure] = []
    for component in components:
        for dependency in component.dependencies:
            key = (dependency.ecosystem, dependency.name)
            if key in seen:
                continue
            provider = providers.get(dependency.ecosystem)
            if provider is None:
                continue
            seen.add(key)
            identity = _identity_for(dependency)
            try:
                available = provider.fetch_available_state(identity)
            except ComponentUpdateError as exc:
                unavailable.append(
                    UpdateLookupFailure(
                        ecosystem=dependency.ecosystem, name=dependency.name, message=str(exc)
                    )
                )
                continue
            if available is None:
                continue
            current = build_current_state(dependency)
            diff = diff_states(current, available)

            vulnerability_provider = (vulnerability_providers or {}).get(dependency.ecosystem)
            current_advisories = _fetch_advisories(
                vulnerability_provider, identity, current.version
            )
            available_advisories = (
                current_advisories
                if available.version == current.version
                else _fetch_advisories(vulnerability_provider, identity, available.version)
            )

            assessments.append(
                assess_impact(
                    diff,
                    components,
                    relationships,
                    current_advisories=current_advisories,
                    available_advisories=available_advisories,
                )
            )
    return UpdateCheckResult(assessments=assessments, unavailable=unavailable)
