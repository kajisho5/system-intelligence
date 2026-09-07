from datetime import UTC, datetime, timedelta
from pathlib import Path

from system_intelligence.core.component_state import (
    AvailableState,
    ChangelogEntry,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.enums import (
    ComponentKind,
    Confidence,
    PermissionLevel,
    StateDiffCategory,
    UpdateVerdict,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.research import ResearchResult
from system_intelligence.core.state_diff import StateDiff, StateDiffItem
from system_intelligence.proposals.engine import (
    change_plan_for_component_update,
    propose_component_update,
    propose_solution,
)


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


def test_unknown_archived_status_never_qualifies_as_high_quality() -> None:
    """A candidate with a license and recent activity but an *unknown*
    archived status (e.g. from a provider whose schema has no such field,
    like the MCP registry) must never be silently treated as "verified not
    archived" and promoted to adoption -- "we don't know" is not the same
    fact as "confirmed not archived"."""
    candidate = ResearchResult(
        query="q",
        provider="mcp-registry",
        source="https://example.com/a/a",
        identifier="a/a",
        license="MIT",
        license_confidence=Confidence.VERIFIED,
        maintenance_signals={
            "last_push_at": datetime.now(UTC).isoformat()
        },  # no "archived" key at all
    )

    proposal = propose_solution(
        "Need X", research_results=[candidate], functional_fit_confirmed=True
    )

    assert proposal.kind == "integration"
    reason = proposal.why_existing_solutions_insufficient or ""
    assert "archived status could not be determined" in reason


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


def test_target_kind_omitted_keeps_generic_wording() -> None:
    """Backward compatibility: every existing caller that never passes
    target_kind must see byte-identical wording to before this existed."""
    proposal = propose_solution("Need X", requirements=["r"])
    assert (
        proposal.test_strategy
        == "Add tests covering the new/adopted capability's stated requirements."
    )
    assert (
        proposal.documentation_requirements
        == "Document the capability and how it satisfies each requirement."
    )
    assert proposal.interfaces == []
    assert proposal.interface_fields == []
    assert proposal.security_considerations == (
        "Review any new external dependencies, network access, or credential/permission "
        "grants this introduces."
    )
    assert proposal.implementation_stages == [
        "Implement the capability against the stated requirements.",
        "Add tests per the test strategy.",
        "Document the capability per the documentation requirements.",
    ]


def test_target_kind_skill_shapes_test_and_documentation_strategy() -> None:
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.SKILL)
    assert proposal.test_strategy is not None and "SKILL.md" in proposal.test_strategy
    assert (
        proposal.documentation_requirements
        == "Document the capability in the Skill's own SKILL.md."
    )
    assert len(proposal.interfaces) == 1
    assert "SKILL.md" in proposal.interfaces[0]
    assert proposal.security_considerations is not None
    assert "allowed-tools" in proposal.security_considerations
    assert proposal.implementation_stages
    assert any("SKILL.md" in stage for stage in proposal.implementation_stages)


def test_target_kind_skill_populates_field_level_interface_schema() -> None:
    """`interfaces` only ever names the SKILL.md convention as a whole --
    `interface_fields` is the field-level breakdown (docs/07-improvement-
    engine.md's "Proposal must contain: interface"), grounded in exactly
    what discovery/skills.py actually parses out of SKILL.md frontmatter,
    including which are required vs optional."""
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.SKILL)
    field_names = {f.name for f in proposal.interface_fields}
    assert field_names == {"name", "description", "allowed-tools", "disallowed-tools", "paths"}
    required = {f.name for f in proposal.interface_fields if f.required}
    assert required == {"name", "description"}
    allowed_tools = next(f for f in proposal.interface_fields if f.name == "allowed-tools")
    assert not allowed_tools.required
    assert "tool_names" in allowed_tools.description


def test_target_kind_agent_populates_agent_md_interface() -> None:
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.AGENT)
    assert len(proposal.interfaces) == 1
    assert ".claude/agents" in proposal.interfaces[0]


def test_target_kind_agent_populates_field_level_interface_schema() -> None:
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.AGENT)
    field_names = {f.name for f in proposal.interface_fields}
    assert field_names == {"name", "description", "model", "tools", "disallowedTools"}
    required = {f.name for f in proposal.interface_fields if f.required}
    assert required == {"name", "description"}


def test_target_kind_without_dedicated_interface_stays_empty() -> None:
    """A ComponentKind with no single well-known interface convention
    (e.g. DOCUMENT) must get an empty interfaces list, never a guessed one --
    same discipline applies to interface_fields."""
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.DOCUMENT)
    assert proposal.interfaces == []
    assert proposal.interface_fields == []


def test_target_kind_tool_has_dedicated_documentation_requirements() -> None:
    """TOOL already had dedicated test_strategy/interfaces wording -- its
    documentation_requirements was the one sibling table missing an entry,
    silently falling back to the generic wording despite the other two
    tables treating TOOL as fully first-class."""
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.TOOL)
    assert proposal.documentation_requirements is not None
    assert "CLI/API contract" in proposal.documentation_requirements


def test_target_kind_document_has_dedicated_documentation_requirements() -> None:
    """DOCUMENT already had dedicated test_strategy wording -- its
    documentation_requirements was missing, same gap as TOOL."""
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.DOCUMENT)
    assert proposal.documentation_requirements is not None
    assert proposal.documentation_requirements != (
        "Document the capability and how it satisfies each requirement."
    )


def test_target_kind_agent_shapes_test_and_documentation_strategy() -> None:
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.AGENT)
    assert proposal.test_strategy is not None
    assert "scenario" in proposal.test_strategy
    assert proposal.documentation_requirements is not None
    assert "permission" in proposal.documentation_requirements


def test_target_kind_applies_to_adoption_proposal() -> None:
    candidate = _candidate("psf/markdown-it-py")
    proposal = propose_solution(
        "Need a markdown renderer",
        research_results=[candidate],
        functional_fit_confirmed=True,
        target_kind=ComponentKind.MCP_SERVER,
    )
    assert proposal.kind == "adoption"
    assert proposal.test_strategy is not None and "schema" in proposal.test_strategy
    assert len(proposal.interfaces) == 1 and "JSON schema" in proposal.interfaces[0]


def test_target_kind_applies_to_integration_proposal() -> None:
    candidate = _candidate("someone/abandoned", license=None, archived=True)
    proposal = propose_solution(
        "Need X", research_results=[candidate], target_kind=ComponentKind.WORKFLOW
    )
    assert proposal.kind == "integration"
    assert proposal.test_strategy is not None and "trigger" in proposal.test_strategy


def test_target_kind_interface_fields_applies_to_adoption_proposal() -> None:
    """`interface_fields` must reach the adoption construction site too,
    not just creation -- the same wiring gap `interfaces` itself once had
    before it was threaded through all three Proposal(...) call sites."""
    candidate = _candidate("psf/markdown-it-py")
    proposal = propose_solution(
        "Need X",
        research_results=[candidate],
        functional_fit_confirmed=True,
        target_kind=ComponentKind.SKILL,
    )
    assert proposal.kind == "adoption"
    assert {f.name for f in proposal.interface_fields} == {
        "name",
        "description",
        "allowed-tools",
        "disallowed-tools",
        "paths",
    }


def test_target_kind_interface_fields_applies_to_integration_proposal() -> None:
    candidate = _candidate("someone/abandoned", license=None, archived=True)
    proposal = propose_solution(
        "Need X", research_results=[candidate], target_kind=ComponentKind.AGENT
    )
    assert proposal.kind == "integration"
    assert {f.name for f in proposal.interface_fields} == {
        "name",
        "description",
        "model",
        "tools",
        "disallowedTools",
    }


def test_target_kind_without_specific_wording_falls_back_to_generic() -> None:
    """A ComponentKind with no dedicated guidance (e.g. UNKNOWN, PACKAGE,
    SERVICE) must fall back to the generic wording, not raise or return
    something blank."""
    proposal = propose_solution("Need X", requirements=["r"], target_kind=ComponentKind.PACKAGE)
    assert (
        proposal.test_strategy
        == "Add tests covering the new/adopted capability's stated requirements."
    )
    assert proposal.security_considerations == (
        "Review any new external dependencies, network access, or credential/permission "
        "grants this introduces."
    )
    assert proposal.implementation_stages == [
        "Implement the capability against the stated requirements.",
        "Add tests per the test strategy.",
        "Document the capability per the documentation requirements.",
    ]


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
    assert proposal.security_considerations is not None
    assert "known-vulnerability" in proposal.security_considerations


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


def test_propose_component_update_implementation_stages_cite_changelog_url_when_known() -> None:
    """A pypi package with a real, declared Changelog URL (research/providers/
    pypi.py::_extract_changelog) must have that concrete URL surfaced,
    not the generic "review the changelog" boilerplate."""
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    current = ComponentState(identity=identity, version="0.8.2")
    available = AvailableState(
        identity=identity,
        provider="pypi",
        version="0.9.2",
        changelog=[
            ChangelogEntry(
                version="0.9.2",
                summary="Changelog link declared in PyPI project metadata.",
                url="https://example.com/CHANGELOG.md",
            )
        ],
    )
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    assessment = ImpactAssessment(
        state_diff=diff,
        verdict=UpdateVerdict.REVIEW_REQUIRED,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="rationale text",
    )

    proposal = propose_component_update(assessment)

    assert proposal is not None
    assert any(
        "https://example.com/CHANGELOG.md" in stage for stage in proposal.implementation_stages
    )


def test_propose_component_update_implementation_stages_fall_back_without_changelog() -> None:
    proposal = propose_component_update(_update_assessment(UpdateVerdict.REVIEW_REQUIRED))
    assert proposal is not None
    assert any(
        "Review the changelog/release notes" in stage for stage in proposal.implementation_stages
    )


def _manifest_evidence(rel_path: str, name: str) -> Evidence:
    # Mirrors analysis.dependencies._manifest_evidence exactly -- the real
    # producer of this Evidence shape.
    return Evidence(
        kind=EvidenceKind.PACKAGE_METADATA,
        source=rel_path,
        observation=f"{name!r} declared as a dependency in {rel_path}",
        confidence=Confidence.VERIFIED,
    )


def test_propose_component_update_populates_change_file_paths_from_evidence() -> None:
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="requests", distribution_source="pypi"
    )
    current = ComponentState(
        identity=identity,
        version="1.2.3",
        version_confidence=Confidence.HIGH,
        evidence=[_manifest_evidence("pyproject.toml", "requests")],
    )
    available = AvailableState(identity=identity, provider="pypi", version="2.0.0")
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    assessment = ImpactAssessment(
        state_diff=diff,
        verdict=UpdateVerdict.UPDATE_RECOMMENDED,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )

    proposal = propose_component_update(assessment)

    assert proposal is not None
    assert proposal.changes[0].file_paths == ["pyproject.toml"]


def _pypi_pin_assessment(
    root: Path,
    *,
    name: str = "requests",
    from_version: str = "1.2.3",
    to_version: str = "2.0.0",
    manifest_path: str = "pyproject.toml",
    version_confidence: Confidence = Confidence.HIGH,
    verdict: UpdateVerdict = UpdateVerdict.UPDATE_RECOMMENDED,
    write_manifest: bool = True,
    manifest_text: str | None = None,
) -> ImpactAssessment:
    if write_manifest:
        text = manifest_text or f'[project]\ndependencies = [\n  "{name}=={from_version}",\n]\n'
        (root / manifest_path).write_text(text, encoding="utf-8")
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name=name, distribution_source="pypi"
    )
    current = ComponentState(
        identity=identity,
        version=from_version,
        version_confidence=version_confidence,
        evidence=[_manifest_evidence(manifest_path, name)],
    )
    available = AvailableState(identity=identity, provider="pypi", version=to_version)
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    return ImpactAssessment(
        state_diff=diff,
        verdict=verdict,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )


def test_change_plan_for_component_update_success(tmp_path: Path) -> None:
    assessment = _pypi_pin_assessment(tmp_path)

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.branch_name == "si/update-requests-to-2.0.0"
    assert plan.commit_message == "Update requests to 2.0.0"
    assert plan.files == {
        "pyproject.toml": '[project]\ndependencies = [\n  "requests==2.0.0",\n]\n'
    }
    assert plan.required_permission_level == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR


def test_change_plan_for_component_update_success_for_poetry_native_table(tmp_path: Path) -> None:
    """Poetry's own native `[tool.poetry.dependencies]` table form
    (`requests = "1.2.3"`, no `==` operator, an unquoted TOML key) is a
    real, common, exact pin (analysis.dependencies._poetry_version_constraint,
    confirmed against Poetry's own docs) -- distinct from the PEP 621 array
    form the success test above covers, and previously never matched by
    the patcher's regex at all."""
    assessment = _pypi_pin_assessment(
        tmp_path,
        manifest_text='[tool.poetry.dependencies]\npython = "^3.11"\nrequests = "1.2.3"\n',
    )

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.files == {
        "pyproject.toml": '[tool.poetry.dependencies]\npython = "^3.11"\nrequests = "2.0.0"\n'
    }


def test_change_plan_for_component_update_none_for_poetry_table_form(tmp_path: Path) -> None:
    """Poetry's own `{ version = "...", extras = [...] }` table form is
    never patched -- same "return None rather than guess" discipline as
    Cargo.toml's table form, since a nested `version` key isn't a
    name-adjacent literal this regex could locate safely."""
    assessment = _pypi_pin_assessment(
        tmp_path,
        manifest_text='[tool.poetry.dependencies]\nrequests = { version = "1.2.3" }\n',
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_success_for_requirements_txt(tmp_path: Path) -> None:
    """requirements.txt has no surrounding quotes at all, unlike either
    pyproject.toml form -- arguably the most common pypi pinning
    convention (`pip freeze > requirements.txt`), and previously never
    matched by any patcher at all since `_patch_pyproject_pin` was the
    only one ever selected for the `pypi` ecosystem."""
    assessment = _pypi_pin_assessment(
        tmp_path,
        manifest_path="requirements.txt",
        manifest_text="click==1.0.0\nrequests==1.2.3\nflask==2.0.0\n",
    )

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.files == {"requirements.txt": "click==1.0.0\nrequests==2.0.0\nflask==2.0.0\n"}


def test_change_plan_for_component_update_requirements_txt_preserves_trailing_marker(
    tmp_path: Path,
) -> None:
    """A trailing environment marker or comment is preserved verbatim --
    only the version itself changes."""
    assessment = _pypi_pin_assessment(
        tmp_path,
        manifest_path="requirements.txt",
        manifest_text='requests==1.2.3; python_version >= "3.8"  # pinned\n',
    )

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.files == {
        "requirements.txt": 'requests==2.0.0; python_version >= "3.8"  # pinned\n'
    }


def test_change_plan_for_component_update_none_for_ambiguous_requirements_txt(
    tmp_path: Path,
) -> None:
    """Two lines pinning the same name at the same version (a monorepo's
    combined requirements file, or a duplicate) is ambiguous which
    occurrence to rewrite -- returns None rather than guessing."""
    assessment = _pypi_pin_assessment(
        tmp_path,
        manifest_path="requirements.txt",
        manifest_text="requests==1.2.3\nrequests==1.2.3\n",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_for_non_actionable_verdict(tmp_path: Path) -> None:
    assessment = _pypi_pin_assessment(tmp_path, verdict=UpdateVerdict.NOT_ADVISABLE)
    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_for_unsupported_ecosystem(tmp_path: Path) -> None:
    # rubygems/Gemfile is still genuinely unsupported: Gemfile's executable-
    # Ruby format has no formal grammar a patcher could safely target.
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="rails", distribution_source="rubygems"
    )
    current = ComponentState(
        identity=identity,
        version="1.2.3",
        version_confidence=Confidence.HIGH,
        evidence=[_manifest_evidence("Gemfile", "rails")],
    )
    available = AvailableState(identity=identity, provider="rubygems", version="2.0.0")
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    assessment = ImpactAssessment(
        state_diff=diff,
        verdict=UpdateVerdict.UPDATE_RECOMMENDED,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def _npm_pin_assessment(
    root: Path,
    *,
    name: str = "left-pad",
    from_version: str = "1.2.3",
    to_version: str = "2.0.0",
    manifest_path: str = "package.json",
    version_confidence: Confidence = Confidence.HIGH,
    verdict: UpdateVerdict = UpdateVerdict.UPDATE_RECOMMENDED,
    write_manifest: bool = True,
) -> ImpactAssessment:
    if write_manifest:
        (root / manifest_path).write_text(
            f'{{\n  "dependencies": {{\n    "{name}": "{from_version}"\n  }}\n}}\n',
            encoding="utf-8",
        )
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name=name, distribution_source="npm"
    )
    current = ComponentState(
        identity=identity,
        version=from_version,
        version_confidence=version_confidence,
        evidence=[_manifest_evidence(manifest_path, name)],
    )
    available = AvailableState(identity=identity, provider="npm", version=to_version)
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    return ImpactAssessment(
        state_diff=diff,
        verdict=verdict,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )


def test_change_plan_for_component_update_success_for_npm(tmp_path: Path) -> None:
    assessment = _npm_pin_assessment(tmp_path)

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.branch_name == "si/update-left-pad-to-2.0.0"
    assert plan.commit_message == "Update left-pad to 2.0.0"
    assert plan.files == {
        "package.json": '{\n  "dependencies": {\n    "left-pad": "2.0.0"\n  }\n}\n'
    }
    assert plan.required_permission_level == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR


def test_change_plan_for_component_update_npm_none_for_range_constraint(tmp_path: Path) -> None:
    assessment = _npm_pin_assessment(tmp_path, version_confidence=Confidence.UNKNOWN)
    assert change_plan_for_component_update(assessment, tmp_path) is None


def _cargo_pin_assessment(
    root: Path,
    *,
    name: str = "serde",
    from_version: str = "1.0.219",
    to_version: str = "1.0.220",
    manifest_path: str = "Cargo.toml",
    manifest_text: str | None = None,
    version_confidence: Confidence = Confidence.HIGH,
    verdict: UpdateVerdict = UpdateVerdict.UPDATE_RECOMMENDED,
    write_manifest: bool = True,
) -> ImpactAssessment:
    if write_manifest:
        text = manifest_text or (
            f'[package]\nname = "demo"\n\n[dependencies]\n{name} = "={from_version}"\n'
        )
        (root / manifest_path).write_text(text, encoding="utf-8")
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name=name, distribution_source="cargo"
    )
    current = ComponentState(
        identity=identity,
        version=from_version,
        version_confidence=version_confidence,
        evidence=[_manifest_evidence(manifest_path, name)],
    )
    available = AvailableState(identity=identity, provider="cargo", version=to_version)
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    return ImpactAssessment(
        state_diff=diff,
        verdict=verdict,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )


def test_change_plan_for_component_update_success_for_cargo_simple_string_form(
    tmp_path: Path,
) -> None:
    assessment = _cargo_pin_assessment(tmp_path)

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.branch_name == "si/update-serde-to-1.0.220"
    assert plan.commit_message == "Update serde to 1.0.220"
    assert plan.files == {
        "Cargo.toml": '[package]\nname = "demo"\n\n[dependencies]\nserde = "=1.0.220"\n'
    }
    assert plan.required_permission_level == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR


def test_change_plan_for_component_update_cargo_none_for_bare_version_range(
    tmp_path: Path,
) -> None:
    """A bare Cargo version (no `=`) is a caret range, never confirmed as an
    exact pin by build_current_state -- version_confidence stays UNKNOWN."""
    assessment = _cargo_pin_assessment(tmp_path, version_confidence=Confidence.UNKNOWN)
    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_cargo_none_for_table_form(tmp_path: Path) -> None:
    """The table form is deliberately never rewritten -- only the simple
    string form is a safe, unambiguous regex target."""
    manifest_text = (
        '[package]\nname = "demo"\n\n[dependencies]\n'
        'serde = { version = "=1.0.219", features = ["derive"] }\n'
    )
    assessment = _cargo_pin_assessment(tmp_path, manifest_text=manifest_text)

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_cargo_none_when_manifest_text_has_drifted(
    tmp_path: Path,
) -> None:
    assessment = _cargo_pin_assessment(tmp_path)
    # The manifest changed since the assessment ran -- the exact pinned
    # text this needs to match no longer exists.
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\n\n[dependencies]\nserde = "1.1"\n', encoding="utf-8"
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_cargo_none_when_ambiguous_duplicate(
    tmp_path: Path,
) -> None:
    assessment = _cargo_pin_assessment(tmp_path, write_manifest=False)
    (tmp_path / "Cargo.toml").write_text(
        '[dependencies]\nserde = "=1.0.219"\n\n[dev-dependencies]\nserde = "=1.0.219"\n',
        encoding="utf-8",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_npm_none_when_manifest_text_has_drifted(
    tmp_path: Path,
) -> None:
    assessment = _npm_pin_assessment(tmp_path)
    # The manifest changed since the assessment ran (now a caret range) --
    # the exact pinned text this needs to match no longer exists.
    (tmp_path / "package.json").write_text(
        '{\n  "dependencies": {\n    "left-pad": "^1.2.3"\n  }\n}\n', encoding="utf-8"
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_npm_none_when_ambiguous_duplicate(
    tmp_path: Path,
) -> None:
    """The same package pinned identically in both dependencies and
    devDependencies is ambiguous -- never guess which one to rewrite."""
    assessment = _npm_pin_assessment(tmp_path, write_manifest=False)
    (tmp_path / "package.json").write_text(
        '{\n  "dependencies": {\n    "left-pad": "1.2.3"\n  },\n'
        '  "devDependencies": {\n    "left-pad": "1.2.3"\n  }\n}\n',
        encoding="utf-8",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_for_range_constraint(tmp_path: Path) -> None:
    assessment = _pypi_pin_assessment(tmp_path, version_confidence=Confidence.UNKNOWN)
    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_without_manifest_evidence(tmp_path: Path) -> None:
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="requests", distribution_source="pypi"
    )
    current = ComponentState(
        identity=identity, version="1.2.3", version_confidence=Confidence.HIGH, evidence=[]
    )
    available = AvailableState(identity=identity, provider="pypi", version="2.0.0")
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    assessment = ImpactAssessment(
        state_diff=diff,
        verdict=UpdateVerdict.UPDATE_RECOMMENDED,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_when_manifest_file_missing(tmp_path: Path) -> None:
    assessment = _pypi_pin_assessment(tmp_path, write_manifest=False)
    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_when_available_version_missing(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n  "requests==1.2.3",\n]\n', encoding="utf-8"
    )
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name="requests", distribution_source="pypi"
    )
    current = ComponentState(
        identity=identity,
        version="1.2.3",
        version_confidence=Confidence.HIGH,
        evidence=[_manifest_evidence("pyproject.toml", "requests")],
    )
    # An available-state provider that reports a breaking change but never
    # actually resolved a version number for it.
    available = AvailableState(identity=identity, provider="pypi", version=None)
    diff = StateDiff(
        identity=identity,
        from_state=current,
        to_state=available,
        items=[
            StateDiffItem(
                category=StateDiffCategory.BREAKING,
                description="breaking change flagged",
                confidence=Confidence.HIGH,
            )
        ],
    )
    assessment = ImpactAssessment(
        state_diff=diff,
        verdict=UpdateVerdict.REVIEW_REQUIRED,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="rationale text",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_none_when_manifest_text_has_drifted(
    tmp_path: Path,
) -> None:
    assessment = _pypi_pin_assessment(tmp_path)
    # The manifest changed since the assessment ran -- the exact pinned
    # text this needs to match no longer exists.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n  "requests>=1.0,<2.0",\n]\n', encoding="utf-8"
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def _go_pin_assessment(
    root: Path,
    *,
    name: str = "github.com/pkg/errors",
    from_version: str = "v0.9.0",
    to_version: str = "v0.9.1",
    manifest_path: str = "go.mod",
    manifest_text: str | None = None,
    version_confidence: Confidence = Confidence.HIGH,
    verdict: UpdateVerdict = UpdateVerdict.UPDATE_RECOMMENDED,
    write_manifest: bool = True,
) -> ImpactAssessment:
    if write_manifest:
        text = manifest_text or (
            f"module example.com/demo\n\ngo 1.21\n\nrequire {name} {from_version}\n"
        )
        (root / manifest_path).write_text(text, encoding="utf-8")
    identity = ComponentIdentity(
        component_kind=ComponentKind.PACKAGE, name=name, distribution_source="go"
    )
    current = ComponentState(
        identity=identity,
        version=from_version,
        version_confidence=version_confidence,
        evidence=[_manifest_evidence(manifest_path, name)],
    )
    available = AvailableState(identity=identity, provider="go", version=to_version)
    diff = StateDiff(identity=identity, from_state=current, to_state=available)
    return ImpactAssessment(
        state_diff=diff,
        verdict=verdict,
        verdict_confidence=Confidence.HIGH,
        verdict_rationale="rationale text",
    )


def test_change_plan_for_component_update_success_for_go_single_line(tmp_path: Path) -> None:
    assessment = _go_pin_assessment(tmp_path)

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.branch_name == "si/update-github.com/pkg/errors-to-v0.9.1"
    assert plan.commit_message == "Update github.com/pkg/errors to v0.9.1"
    assert plan.files == {
        "go.mod": "module example.com/demo\n\ngo 1.21\n\nrequire github.com/pkg/errors v0.9.1\n"
    }
    assert plan.required_permission_level == PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR


def test_change_plan_for_component_update_success_for_go_block_form(tmp_path: Path) -> None:
    manifest_text = (
        "module example.com/demo\n\ngo 1.21\n\nrequire (\n"
        "\tgithub.com/pkg/errors v0.9.0\n"
        "\tgolang.org/x/net v0.5.0 // indirect\n"
        ")\n"
    )
    assessment = _go_pin_assessment(tmp_path, manifest_text=manifest_text)

    plan = change_plan_for_component_update(assessment, tmp_path)

    assert plan is not None
    assert plan.files == {
        "go.mod": (
            "module example.com/demo\n\ngo 1.21\n\nrequire (\n"
            "\tgithub.com/pkg/errors v0.9.1\n"
            "\tgolang.org/x/net v0.5.0 // indirect\n"
            ")\n"
        )
    }


def test_change_plan_for_component_update_go_none_for_pseudo_version_drift(
    tmp_path: Path,
) -> None:
    assessment = _go_pin_assessment(tmp_path)
    # The manifest changed since the assessment ran -- the exact pinned
    # text this needs to match no longer exists.
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\n\ngo 1.21\n\nrequire github.com/pkg/errors v1.0.0\n",
        encoding="utf-8",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None


def test_change_plan_for_component_update_go_none_when_ambiguous_duplicate(
    tmp_path: Path,
) -> None:
    assessment = _go_pin_assessment(tmp_path, write_manifest=False)
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\n\ngo 1.21\n\n"
        "require github.com/pkg/errors v0.9.0\n"
        "require github.com/pkg/errors v0.9.0\n",
        encoding="utf-8",
    )

    assert change_plan_for_component_update(assessment, tmp_path) is None
