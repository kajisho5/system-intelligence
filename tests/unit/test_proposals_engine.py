from datetime import UTC, datetime, timedelta

from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.enums import ComponentKind, Confidence, PermissionLevel, UpdateVerdict
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.research import ResearchResult
from system_intelligence.core.state_diff import StateDiff
from system_intelligence.proposals.engine import propose_component_update, propose_solution


def _candidate(
    identifier: str,
    *,
    license: str | None = "MIT",
    pushed_days_ago: int = 5,
    archived: bool = False,
) -> ResearchResult:
    pushed_at = datetime.now(UTC) - timedelta(days=pushed_days_ago)
    return ResearchResult(
        query="q",
        provider="github",
        source=f"https://github.com/{identifier}",
        identifier=identifier,
        license=license,
        license_confidence=Confidence.VERIFIED if license else Confidence.UNKNOWN,
        maintenance_signals={
            "last_push_at": pushed_at.isoformat(),
            "archived": str(archived),
        },
    )


def test_no_research_results_produces_creation_proposal() -> None:
    proposal = propose_solution("Need a markdown renderer", requirements=["renders CommonMark"])

    assert proposal.kind == "creation"
    assert proposal.proposed_component_name is None
    assert "No candidate solutions" in (proposal.why_existing_solutions_insufficient or "")
    assert proposal.required_permission_level == PermissionLevel.GENERATE_LOCAL_ARTIFACTS


def test_high_quality_candidate_without_confirmed_fit_is_integration() -> None:
    candidate = _candidate("psf/markdown-it-py")
    proposal = propose_solution(
        "Need a markdown renderer",
        research_results=[candidate],
        requirements=["renders CommonMark"],
    )

    assert proposal.kind == "integration"
    assert proposal.proposed_component_name == "psf/markdown-it-py"
    assert "not been verified" in (proposal.why_existing_solutions_insufficient or "")


def test_high_quality_candidate_with_confirmed_fit_is_adoption() -> None:
    candidate = _candidate("psf/markdown-it-py")
    proposal = propose_solution(
        "Need a markdown renderer",
        research_results=[candidate],
        requirements=["renders CommonMark"],
        functional_fit_confirmed=True,
    )

    assert proposal.kind == "adoption"
    assert proposal.proposed_component_name == "psf/markdown-it-py"
    assert proposal.why_existing_solutions_insufficient is None
    assert proposal.dependencies == ["psf/markdown-it-py"]


def test_low_quality_candidate_is_integration_with_reason() -> None:
    candidate = _candidate("someone/abandoned", license=None, pushed_days_ago=2000, archived=True)
    proposal = propose_solution(
        "Need a markdown renderer",
        research_results=[candidate],
        functional_fit_confirmed=True,  # even confirmed, low-quality candidate stays integration
    )

    assert proposal.kind == "integration"
    reason = proposal.why_existing_solutions_insufficient or ""
    assert "no license" in reason
    assert "archived" in reason


def test_unknown_activity_reason_when_no_push_signal() -> None:
    candidate = ResearchResult(
        query="q",
        provider="github",
        source="https://github.com/a/a",
        identifier="a/a",
        license=None,
        license_confidence=Confidence.UNKNOWN,
        maintenance_signals={},  # no last_push_at at all
    )

    proposal = propose_solution("Need X", research_results=[candidate])

    reason = proposal.why_existing_solutions_insufficient or ""
    assert "activity could not be determined" in reason


def test_best_candidate_selected_and_alternatives_listed() -> None:
    good = _candidate("good/repo")
    bad = _candidate("bad/repo", license=None, pushed_days_ago=3000, archived=True)

    proposal = propose_solution("Need X", research_results=[bad, good])

    assert proposal.proposed_component_name == "good/repo"
    assert proposal.alternatives_considered == ["bad/repo"]


def test_evidence_from_problem_and_candidate_are_combined() -> None:
    problem_evidence = Evidence(kind=EvidenceKind.FILE, source="x", observation="need detected")
    candidate = _candidate("good/repo")

    proposal = propose_solution("Need X", evidence=[problem_evidence], research_results=[candidate])

    assert problem_evidence in proposal.evidence
    assert len(proposal.evidence) == 1 + len(candidate.evidence)


def _update_assessment(verdict: UpdateVerdict) -> ImpactAssessment:
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    current = ComponentState(identity=identity, version="0.8.2")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    return ImpactAssessment(
        state_diff=diff,
        verdict=verdict,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="rationale text",
    )


def test_propose_component_update_for_review_required() -> None:
    proposal = propose_component_update(_update_assessment(UpdateVerdict.REVIEW_REQUIRED))

    assert proposal is not None
    assert proposal.kind == "component_update"
    assert "ffmpeg-skill" in proposal.problem
    assert "0.8.2" in proposal.problem and "0.9.2" in proposal.problem
    assert proposal.proposed_component_name == "ffmpeg-skill"
    assert proposal.required_permission_level == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR
    assert len(proposal.changes) == 1


def test_propose_component_update_for_update_recommended() -> None:
    proposal = propose_component_update(_update_assessment(UpdateVerdict.UPDATE_RECOMMENDED))
    assert proposal is not None
    assert proposal.kind == "component_update"


def test_propose_component_update_none_for_not_advisable() -> None:
    assert propose_component_update(_update_assessment(UpdateVerdict.NOT_ADVISABLE)) is None


def test_propose_component_update_none_for_no_update_available() -> None:
    assert propose_component_update(_update_assessment(UpdateVerdict.NO_UPDATE_AVAILABLE)) is None


def test_propose_component_update_none_for_unknown() -> None:
    assert propose_component_update(_update_assessment(UpdateVerdict.UNKNOWN)) is None
