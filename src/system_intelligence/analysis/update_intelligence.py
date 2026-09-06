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
    StateDiffCategory,
    UpdateVerdict,
)
from system_intelligence.core.evidence import Evidence
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.state_diff import StateDiff, StateDiffItem
from system_intelligence.research.update_provider import (
    ComponentUpdateError,
    ComponentUpdateProvider,
)

#: A constraint with no range operator, wildcard, or whitespace-separated
#: alternative is treated as pinning an exact, currently-installed version
#: (e.g. "1.2.3" or "==1.2.3"). Anything else ("^1.2.3", ">=1.0,<2.0") is a
#: range, not a known installed version.
_EXACT_PIN_RE = re.compile(r"^==?\s*[0-9][0-9A-Za-z.+_-]*$")


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
        if _EXACT_PIN_RE.match(constraint):
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
    if available.is_deprecated is not True:
        return None
    return StateDiffItem(
        category=StateDiffCategory.DEPRECATED,
        description=(
            f"Available version {available.version!r} is marked deprecated by its publisher."
        ),
        confidence=Confidence.VERIFIED,
        evidence=list(available.evidence),
    )


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


def assess_impact(state_diff: StateDiff, components: list[Component]) -> ImpactAssessment:
    """Assess what a StateDiff would mean for the rest of the observed system.

    `affected_entity_ids` only ever lists components in `components` that
    declare a matching Dependency in *this same Snapshot* — this is a
    deliberately narrow, deterministic substitute for a full Relationship
    graph (R4), which nothing in this codebase populates yet. It will
    under-report indirect/transitive consumers; it never over-reports.
    """
    identity = state_diff.identity
    affected_entity_ids = [
        component.id
        for component in components
        if any(
            dep.name == identity.name and dep.ecosystem == identity.distribution_source
            for dep in component.dependencies
        )
    ]

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


def check_dependency_updates(
    components: list[Component], providers: dict[str, ComponentUpdateProvider]
) -> UpdateCheckResult:
    """Run Update Intelligence for every Dependency whose ecosystem has a provider.

    `providers` maps ecosystem name (e.g. "pypi", "npm") to the adapter that
    handles it — dependencies in an ecosystem with no configured provider
    are silently skipped (not reported as findings, and not reported as
    failures), since "no provider available" is a caller configuration
    fact, not a fact about the dependency itself. A provider that raises
    `ComponentUpdateError` (network/HTTP/parse failure) is recorded in
    `UpdateCheckResult.unavailable` rather than aborting the whole check or
    being silently dropped.
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
            try:
                available = provider.fetch_available_state(_identity_for(dependency))
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
            assessments.append(assess_impact(diff, components))
    return UpdateCheckResult(assessments=assessments, unavailable=unavailable)
