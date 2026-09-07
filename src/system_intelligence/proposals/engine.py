"""Improvement decision tree (docs/design/docs/07-improvement-engine.md):

    Need detected
        -> existing external solution found?
            -> no  -> creation proposal
            -> yes -> is it a high-quality candidate (license, recently
                      active, not archived) AND has functional fit against
                      the stated requirements actually been confirmed?
                -> yes -> adoption proposal
                -> no  -> integration proposal (partial solution; explains
                          exactly what remains unverified)

Functional/architectural fit cannot be determined from GitHub search
metadata alone (docs/06-research-engine.md's anti-hallucination rule), so
this never returns an adoption proposal on research signals by itself —
`functional_fit_confirmed` must be explicitly asserted by a caller that
verified it (e.g. a human, or a later semantic-analysis phase).

`change_plan_for_component_update` closes the one Proposal shape this
project can currently turn into an executable `execution.plan.ChangePlan`
without guessing at intent: a `pypi`, `npm`, `go`, or `cargo` dependency
whose *currently declared* constraint is an exact pin
(`Confidence.HIGH`/`VERIFIED` on the current `ComponentState`, per
`analysis.update_intelligence.build_current_state`'s own `_EXACT_PIN_RE`).
`pypi` alone spans two manifest syntaxes -- pyproject.toml (both PEP 621's
array and Poetry's native table form) and requirements.txt's bare,
unquoted plain text -- dispatched by `_select_patcher` on the manifest's
own filename, since neither text shape is a fuzzy match for the other.
A range constraint (`>=1.2,<2.0`, `^1.2.3`, `1.x`) is deliberately never
rewritten here — which number to bump is genuinely ambiguous, not a fact
this module can determine. A Cargo dependency using its *table* form
(`name = { version = "=1.2.3" }`) is likewise never rewritten — only the
simple string form (`name = "=1.2.3"`) is (see
`_CARGO_TOML_PIN_RE_TEMPLATE`). `maven` is not supported yet: pom.xml's
XML text-escaping rules would need more care than a plain regex
substitution. Every other Proposal kind (creation/adoption/integration,
and any range-constrained or unsupported-form/ecosystem update) still has
no automatic path to a ChangePlan — the actual code change is a job for
an external implementer (a human, or an agent such as Claude Code), never
this module (ADR-007: no model vendor or agent harness hard-coded here).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from system_intelligence.core.enums import ComponentKind, Confidence, PermissionLevel, UpdateVerdict
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.proposals import Change, Proposal
from system_intelligence.core.research import ResearchResult
from system_intelligence.execution.plan import ChangePlan
from system_intelligence.research.scoring import CandidateAssessment, rank_candidates

_TEST_STRATEGY = "Add tests covering the new/adopted capability's stated requirements."
_DOCUMENTATION_REQUIREMENTS = "Document the capability and how it satisfies each requirement."
_SECURITY_CONSIDERATIONS = (
    "Review any new external dependencies, network access, or credential/permission "
    "grants this introduces."
)
_ROLLBACK_STRATEGY = "Revert the change; no other component depends on it until adopted."

#: Per-`ComponentKind` test/documentation guidance (docs/07-improvement-
#: engine.md's "Creation proposals" list). Each kind is verified and
#: documented differently in practice -- a Skill's contract lives in its
#: SKILL.md, an Agent can't be unit-tested the same way a package's
#: functions can, an MCP server's contract is its tool/resource schema.
#: `None` (the default, and any `ComponentKind` not listed here) keeps the
#: original generic wording so every existing caller is unaffected.
_TEST_STRATEGY_BY_KIND: dict[ComponentKind, str] = {
    ComponentKind.SKILL: (
        "Invoke the Skill through its own declared entry points (per its SKILL.md "
        "contract) with representative inputs and verify the stated capabilities."
    ),
    ComponentKind.AGENT: (
        "Run representative end-to-end task scenarios against the agent (not just unit "
        "tests) and verify it stays within its declared tool/permission grants."
    ),
    ComponentKind.MCP_SERVER: (
        "Validate every exposed tool/resource against its declared schema, then perform "
        "a live round-trip call for each to confirm the contract holds in practice."
    ),
    ComponentKind.TOOL: (
        "Add tests covering the tool's CLI/API contract for each stated requirement, "
        "including its documented error/exit-code behavior."
    ),
    ComponentKind.WORKFLOW: (
        "Run the workflow end-to-end (a dry-run mode first, if one exists) and verify "
        "each stated trigger condition and side effect."
    ),
    ComponentKind.DOCUMENT: (
        "Review for accuracy and completeness against each stated requirement; check "
        "that any links/references it makes actually resolve."
    ),
    ComponentKind.REPOSITORY: (
        "Verify the new repository's own CI passes and its bootstrap instructions work "
        "from a clean checkout."
    ),
}
#: Per-`ComponentKind` security-review guidance (docs/07-improvement-
#: engine.md's "Proposal must contain" list, "security implications" --
#: same required-content status as `test_strategy`/`documentation_
#: requirements`/`rollback_strategy`, all of which already have their own
#: entry here). `None`/any unlisted kind keeps the generic
#: `_SECURITY_CONSIDERATIONS` wording, same fallback convention as the
#: sibling `_BY_KIND` tables above.
_SECURITY_CONSIDERATIONS_BY_KIND: dict[ComponentKind, str] = {
    ComponentKind.SKILL: (
        "Review the Skill's own allowed-tools/disallowed-tools frontmatter for scope "
        "creep beyond what it actually needs."
    ),
    ComponentKind.AGENT: (
        "Review the agent's declared tool/permission grants for scope creep beyond "
        "what it actually needs."
    ),
    ComponentKind.MCP_SERVER: (
        "Review each exposed tool/resource's schema for unintended data or system access."
    ),
    ComponentKind.TOOL: (
        "Review the tool's own permission/credential requirements for least-privilege scope."
    ),
    ComponentKind.WORKFLOW: (
        "Review each side effect for unintended write/network access beyond what's declared."
    ),
    ComponentKind.DOCUMENT: (
        "Confirm it does not disclose sensitive internal details (credentials, internal "
        "hostnames, unpublished plans)."
    ),
    ComponentKind.REPOSITORY: (
        "Confirm its dependencies and CI configuration don't introduce unreviewed "
        "third-party code execution."
    ),
}
_DOCUMENTATION_REQUIREMENTS_BY_KIND: dict[ComponentKind, str] = {
    ComponentKind.SKILL: "Document the capability in the Skill's own SKILL.md.",
    ComponentKind.AGENT: (
        "Document the agent's required tool/permission grants and the scenarios it "
        "was verified against."
    ),
    ComponentKind.MCP_SERVER: "Document every exposed tool/resource and its schema.",
    ComponentKind.TOOL: (
        "Document the tool's CLI/API contract, including its error/exit-code behavior."
    ),
    ComponentKind.WORKFLOW: "Document each trigger condition and side effect.",
    ComponentKind.DOCUMENT: "Note what changed and why, and update any index that references it.",
    ComponentKind.REPOSITORY: "Document bootstrap/setup steps in the new repository's README.",
}

#: Per-`ComponentKind` interface points a Proposal for that kind should name
#: (`Proposal.interfaces`, "Proposal must contain" in docs/07-improvement-
#: engine.md) -- each is the same explicit, verified convention this
#: project already detects for that kind elsewhere (`discovery/skills.py`,
#: `discovery/agents.py`), not a guessed API shape. A kind with no
#: dedicated entry (including `None`/unlisted, and every kind whose
#: "interface" isn't a single well-known convention -- DOCUMENT, PACKAGE,
#: SERVICE, UNKNOWN) gets the empty list, same as every caller saw before
#: this existed, rather than an invented description.
_INTERFACES_BY_KIND: dict[ComponentKind, list[str]] = {
    ComponentKind.SKILL: [
        "SKILL.md front matter (name, description) as the discovery contract (discovery/skills.py)."
    ],
    ComponentKind.AGENT: [
        ".claude/agents/<name>.md front matter (name, description, and any tools/model "
        "grants) as the discovery contract (discovery/agents.py)."
    ],
    ComponentKind.MCP_SERVER: [
        "Each exposed tool/resource's declared JSON schema for its inputs and outputs."
    ],
    ComponentKind.TOOL: ["Its CLI flags/arguments or public API signature."],
    ComponentKind.WORKFLOW: ["Its trigger condition(s) and the side effect(s)/steps it runs."],
    ComponentKind.REPOSITORY: [
        "Its own README/CONTRIBUTING as the entry point for building and running it."
    ],
}


def _test_strategy_for(target_kind: ComponentKind | None) -> str:
    if target_kind is None:
        return _TEST_STRATEGY
    return _TEST_STRATEGY_BY_KIND.get(target_kind, _TEST_STRATEGY)


def _documentation_requirements_for(target_kind: ComponentKind | None) -> str:
    if target_kind is None:
        return _DOCUMENTATION_REQUIREMENTS
    return _DOCUMENTATION_REQUIREMENTS_BY_KIND.get(target_kind, _DOCUMENTATION_REQUIREMENTS)


def _interfaces_for(target_kind: ComponentKind | None) -> list[str]:
    if target_kind is None:
        return []
    return _INTERFACES_BY_KIND.get(target_kind, [])


def _security_considerations_for(target_kind: ComponentKind | None) -> str:
    if target_kind is None:
        return _SECURITY_CONSIDERATIONS
    return _SECURITY_CONSIDERATIONS_BY_KIND.get(target_kind, _SECURITY_CONSIDERATIONS)


_UPDATE_TEST_STRATEGY = (
    "Re-run the existing test suite after updating; add a regression test if the "
    "changelog or interface diff indicates a behavior change."
)
_UPDATE_DOCUMENTATION_REQUIREMENTS = (
    "Note the version bump and any migration steps from the changelog or release notes."
)
_UPDATE_SECURITY_CONSIDERATIONS = (
    "Check the new version's changelog/release notes and any known-vulnerability "
    "advisories (`si check-updates --check-vulnerabilities`) before merging."
)
_UPDATE_ROLLBACK_STRATEGY = (
    "Revert the manifest version constraint change; no code changes are made automatically."
)
#: Verdicts with something to actually propose. NOT_ADVISABLE (the update
#: itself is the risk), NO_UPDATE_AVAILABLE, and UNKNOWN never produce a
#: Proposal — there is no change to propose in any of those cases.
_PROPOSABLE_VERDICTS = frozenset({UpdateVerdict.UPDATE_RECOMMENDED, UpdateVerdict.REVIEW_REQUIRED})

#: Matches a quoted PEP 508 requirement string pinned with `==`/`=` to an
#: exact version, e.g. `"requests==2.31.0"` inside a pyproject.toml
#: `dependencies = [...]` array. Deliberately narrower than PEP 508 itself
#: (no extras, no environment markers, no compound constraints) — anything
#: this doesn't match is left untouched rather than guessed at.
_PYPROJECT_PIN_RE_TEMPLATE = r'(["\'])({name})\s*(==?)\s*{version}\s*\1'

#: Matches Poetry's own native `[tool.poetry.dependencies]` table entry in
#: its simple string form, e.g. `requests = "2.31.0"` -- a bare TOML key
#: (never quoted, unlike the PEP 621 array form above) assigned a quoted
#: version with no `==`/`=` operator character anywhere in the text
#: (`analysis.dependencies._poetry_version_constraint`'s own bare-version-
#: is-an-exact-pin convention, confirmed against Poetry's official docs).
#: Anchored to a line start (`re.MULTILINE`) and requires `=` be followed
#: directly by a quote, which the table form (`requests = { version = ...
#: }`) never satisfies -- that form is left untouched rather than guessed
#: at, same as Cargo.toml's table form.
_POETRY_PYPROJECT_PIN_RE_TEMPLATE = r'^([ \t]*{name}[ \t]*=[ \t]*)(["\']){version}\2[ \t]*$'

#: Matches a bare, unquoted `name==version` line in raw requirements.txt
#: text -- pip's own convention has no surrounding quotes at all, unlike
#: either pyproject.toml form above. Captures everything up to and
#: including the pin operator (group "prefix") and anything trailing the
#: version -- a `;`-prefixed environment marker or a `#` comment (group
#: "suffix") -- so a replacement preserves both exactly, changing only the
#: version itself. Anchored to a line start/end (`re.MULTILINE`).
_REQUIREMENTS_TXT_PIN_RE_TEMPLATE = (
    r"^(?P<prefix>[ \t]*{name}[ \t]*==?[ \t]*){version}(?P<suffix>[ \t]*(?:[;#].*)?)$"
)

#: Matches a `"name": "version"` entry in raw package.json text, capturing
#: everything up to (group 1) and after (group 3) the version digits so a
#: replacement can preserve the original quoting/whitespace exactly and
#: only the version itself changes.
_PACKAGE_JSON_PIN_RE_TEMPLATE = r'("{name}"\s*:\s*")({version})(")'

#: Matches one `require` entry in raw go.mod text -- either the single-line
#: form (`require {name} {version}`) or a line inside a `require (...)`
#: block (just `{name} {version}`, arbitrarily indented) -- capturing
#: everything up to and including the version's own leading whitespace
#: (group "prefix") so a replacement preserves the original "require "
#: keyword (if present), indentation, and any trailing `// indirect`
#: comment exactly, changing only the version itself. Anchored to a line
#: start (`re.MULTILINE`) and requires the version be followed by
#: whitespace or end-of-line so it can never match a version that is
#: merely a prefix of a longer token.
_GO_MOD_PIN_RE_TEMPLATE = r"^(?P<prefix>[ \t]*(?:require[ \t]+)?{name}[ \t]+){version}(?=[ \t]|$)"

#: Matches Cargo.toml's *simple string form* only (`name = "=1.2.3"`),
#: capturing everything up to and including the opening quote (group 1) so
#: a replacement can preserve the original name/whitespace/quote-style
#: exactly. Cargo's own exact-pin operator (`=`, inside the quotes,
#: distinct from TOML's own `=` assignment operator right before the
#: quote) is always present in the matched text -- `build_current_state`
#: only ever derives a `from_version` for `cargo` when the constraint
#: itself started with `=` (`_BARE_CONSTRAINT_IS_EXACT_PIN` deliberately
#: excludes cargo). Cargo's *table* form (`name = { version = "=1.2.3" }`,
#: or a `[dependencies.name]` dotted-table section) never matches this --
#: deliberately, since a value nested inside a table isn't a name-adjacent
#: literal this regex could locate without also matching unrelated
#: same-named keys elsewhere in the file.
_CARGO_TOML_PIN_RE_TEMPLATE = r'({name}\s*=\s*)(["\'])=\s*{version}\s*\2'


def _is_high_quality_candidate(assessment: CandidateAssessment) -> bool:
    return (
        assessment.has_license
        and assessment.is_recently_active is True
        and not assessment.is_archived
    )


def _insufficiency_reason(assessment: CandidateAssessment) -> str:
    reasons: list[str] = []
    if not assessment.has_license:
        reasons.append("no license detected")
    if assessment.is_recently_active is False:
        reasons.append("not recently active")
    if assessment.is_recently_active is None:
        reasons.append("activity could not be determined")
    if assessment.is_archived:
        reasons.append("archived")
    detail = ", ".join(reasons) if reasons else "insufficient evidence to confirm fit"
    return f"{assessment.result.identifier}: {detail}"


def propose_solution(
    problem: str,
    *,
    evidence: list[Evidence] | None = None,
    requirements: list[str] | None = None,
    research_results: list[ResearchResult] | None = None,
    functional_fit_confirmed: bool = False,
    target_kind: ComponentKind | None = None,
) -> Proposal:
    """Turn a stated need into a creation/adoption/integration Proposal.

    `target_kind` (docs/07-improvement-engine.md's "Creation proposals"
    list) shapes `test_strategy`/`documentation_requirements`/
    `security_considerations` to how that kind of component is actually
    verified, documented, and reviewed in practice -- e.g. a Skill's
    contract lives in its SKILL.md, an Agent is verified by running
    scenarios rather than unit tests -- and populates `interfaces` with
    that kind's own explicit, already-detected discovery convention where
    one exists (a Skill's SKILL.md front matter, an Agent's
    `.claude/agents/*.md` front matter, ...). Omit it (the default) to get
    the original generic wording and an empty `interfaces` list, unchanged
    for every existing caller.
    """
    evidence = evidence or []
    requirements = requirements or []
    research_results = research_results or []
    test_strategy = _test_strategy_for(target_kind)
    documentation_requirements = _documentation_requirements_for(target_kind)
    interfaces = _interfaces_for(target_kind)
    security_considerations = _security_considerations_for(target_kind)

    if not research_results:
        return Proposal(
            kind="creation",
            problem=problem,
            evidence=evidence,
            requirements=requirements,
            alternatives_considered=[],
            why_existing_solutions_insufficient=(
                "No candidate solutions were found in the searched external ecosystem."
            ),
            capabilities=list(requirements),
            interfaces=interfaces,
            test_strategy=test_strategy,
            security_considerations=security_considerations,
            documentation_requirements=documentation_requirements,
            rollback_strategy=_ROLLBACK_STRATEGY,
            required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
        )

    ranked = rank_candidates(research_results)
    best = ranked[0]
    alternatives = [a.result.identifier for a in ranked[1:]]

    if _is_high_quality_candidate(best) and functional_fit_confirmed:
        return Proposal(
            kind="adoption",
            problem=problem,
            evidence=[*evidence, *best.result.evidence],
            requirements=requirements,
            alternatives_considered=alternatives,
            proposed_component_name=best.result.identifier,
            capabilities=list(requirements),
            interfaces=interfaces,
            dependencies=[best.result.identifier],
            test_strategy=test_strategy,
            security_considerations=security_considerations,
            documentation_requirements=documentation_requirements,
            rollback_strategy=_ROLLBACK_STRATEGY,
            required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
        )

    if _is_high_quality_candidate(best):
        reason = (
            "Functional fit against the stated requirements has not been "
            "verified; license, activity, and archival status look sufficient."
        )
    else:
        reason = _insufficiency_reason(best)

    return Proposal(
        kind="integration",
        problem=problem,
        evidence=[*evidence, *best.result.evidence],
        requirements=requirements,
        alternatives_considered=alternatives,
        proposed_component_name=best.result.identifier,
        why_existing_solutions_insufficient=reason,
        capabilities=list(requirements),
        interfaces=interfaces,
        dependencies=[best.result.identifier],
        test_strategy=test_strategy,
        security_considerations=security_considerations,
        documentation_requirements=documentation_requirements,
        rollback_strategy=_ROLLBACK_STRATEGY,
        required_permission_level=PermissionLevel.GENERATE_LOCAL_ARTIFACTS,
    )


def _manifest_path_from_evidence(evidence: list[Evidence]) -> str | None:
    """The manifest's own relative path, if this Evidence list came from
    `analysis.dependencies._manifest_evidence` (the only place that
    attaches `EvidenceKind.PACKAGE_METADATA` to a Dependency, always with
    `source` set to that manifest's path). `None` when absent — never
    guessed from the component's name or ecosystem.
    """
    for item in evidence:
        if item.kind == EvidenceKind.PACKAGE_METADATA:
            return item.source
    return None


def propose_component_update(assessment: ImpactAssessment) -> Proposal | None:
    """Turn a Component Update Intelligence `ImpactAssessment` into a concrete Proposal.

    Closes "Current State -> Available State -> State Diff -> Impact ->
    Recommendation -> Proposal" for any component, generically — nothing
    here is specific to any ecosystem, package, or target.

    Returns `None` for `NOT_ADVISABLE`/`NO_UPDATE_AVAILABLE`/`UNKNOWN`
    verdicts: a Proposal describes a concrete change to make, and there is
    none to propose when the update itself is the risk, nothing changed, or
    nothing could be determined.
    """
    if assessment.verdict not in _PROPOSABLE_VERDICTS:
        return None

    diff = assessment.state_diff
    identity = diff.identity
    from_version = diff.from_state.version or "unknown"
    to_version = diff.to_state.version or "unknown"

    problem = (
        f"{identity.name} has an available update ({from_version} -> {to_version}). "
        f"{assessment.verdict_rationale}"
    )
    manifest_path = _manifest_path_from_evidence(diff.from_state.evidence)
    change = Change(
        description=f"Update the version constraint for {identity.name} to {to_version!r}.",
        file_paths=[manifest_path] if manifest_path else [],
        required_permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )

    return Proposal(
        kind="component_update",
        problem=problem,
        evidence=list(assessment.evidence),
        proposed_component_name=identity.name,
        dependencies=[identity.name],
        implementation_stages=[
            "Update the version constraint in the declaring manifest.",
            "Run the existing test suite.",
            "Review the changelog/release notes for breaking changes if any were flagged.",
        ],
        changes=[change],
        test_strategy=_UPDATE_TEST_STRATEGY,
        security_considerations=_UPDATE_SECURITY_CONSIDERATIONS,
        documentation_requirements=_UPDATE_DOCUMENTATION_REQUIREMENTS,
        rollback_strategy=_UPDATE_ROLLBACK_STRATEGY,
        required_permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
    )


def _patch_pyproject_pin(text: str, name: str, from_version: str, to_version: str) -> str | None:
    """Rewrite one exact-pinned dependency's version in raw pyproject.toml text.

    Tries two mutually-exclusive shapes `build_current_state` can derive an
    exact `from_version` from: PEP 621's quoted `dependencies = [...]`
    array entry (`"{name}=={from_version}"`), and Poetry's own native
    `[tool.poetry.dependencies]` table's simple string form
    (`{name} = "{from_version}"`) — never a fuzzy match on name alone in
    either case. Returns `None`, never a best guess, when neither pattern's
    exact text is found (the manifest may have changed since the
    assessment ran) or the combined match count isn't exactly 1 (ambiguous
    which occurrence to rewrite).
    """
    array_pattern = re.compile(
        _PYPROJECT_PIN_RE_TEMPLATE.format(name=re.escape(name), version=re.escape(from_version))
    )
    table_pattern = re.compile(
        _POETRY_PYPROJECT_PIN_RE_TEMPLATE.format(
            name=re.escape(name), version=re.escape(from_version)
        ),
        re.MULTILINE,
    )
    array_matches = list(array_pattern.finditer(text))
    table_matches = list(table_pattern.finditer(text))
    if len(array_matches) + len(table_matches) != 1:
        return None

    if array_matches:
        match = array_matches[0]
        quote, matched_name, operator = match.group(1), match.group(2), match.group(3)
        replacement = f"{quote}{matched_name}{operator}{to_version}{quote}"
        return text[: match.start()] + replacement + text[match.end() :]

    match = table_matches[0]
    prefix, quote = match.group(1), match.group(2)
    replacement = f"{prefix}{quote}{to_version}{quote}"
    return text[: match.start()] + replacement + text[match.end() :]


def _patch_requirements_txt_pin(
    text: str, name: str, from_version: str, to_version: str
) -> str | None:
    """Rewrite one exact-pinned dependency's version in raw requirements.txt text.

    Matches only a bare, unquoted `{name}=={from_version}` (or single `=`)
    line — pip's own requirements-file convention has no surrounding
    quotes at all, unlike either pyproject.toml form `_patch_pyproject_pin`
    handles — optionally followed by a `;`-prefixed environment marker or
    a `#` comment, preserved verbatim. Returns `None`, never a best guess,
    when that exact text isn't found (the manifest may have changed since
    the assessment ran) or appears more than once (ambiguous which
    occurrence to rewrite).
    """
    pattern = re.compile(
        _REQUIREMENTS_TXT_PIN_RE_TEMPLATE.format(
            name=re.escape(name), version=re.escape(from_version)
        ),
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    prefix, suffix = match.group("prefix"), match.group("suffix")
    replacement = f"{prefix}{to_version}{suffix}"
    return text[: match.start()] + replacement + text[match.end() :]


def _patch_package_json_pin(text: str, name: str, from_version: str, to_version: str) -> str | None:
    """Rewrite one exact-pinned dependency's version in raw package.json text.

    Matches only the literal `"{name}": "{from_version}"` entry this exact
    `from_version` was itself derived from (a bare npm version with no
    range operator, per `build_current_state`'s `_EXACT_PIN_RE`) — never a
    fuzzy match on name alone, and never a full JSON parse/re-serialize
    (which would reformat the whole file). Returns `None`, never a best
    guess, when that exact text isn't found (the manifest may have changed
    since the assessment ran) or appears more than once (e.g. the same
    package pinned identically in both `dependencies` and
    `devDependencies` — ambiguous which occurrence to rewrite).
    """
    pattern = re.compile(
        _PACKAGE_JSON_PIN_RE_TEMPLATE.format(name=re.escape(name), version=re.escape(from_version))
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    prefix, suffix = match.group(1), match.group(3)
    replacement = f"{prefix}{to_version}{suffix}"
    return text[: match.start()] + replacement + text[match.end() :]


def _patch_go_mod_pin(text: str, name: str, from_version: str, to_version: str) -> str | None:
    """Rewrite one `require` entry's version in raw go.mod text.

    Matches only the literal `{name} {from_version}` this exact
    `from_version` was itself derived from (go.mod's own convention: every
    `require` line is already an exact, MVS-resolved version, per
    `analysis.dependencies._parse_go_require_entry`) -- in either the
    single-line `require module version` form or a line inside a
    `require (...)` block, preserving indentation and any trailing
    `// indirect` comment exactly. Returns `None`, never a best guess, when
    that exact text isn't found (the manifest may have changed since the
    assessment ran) or appears more than once (ambiguous which occurrence
    to rewrite).
    """
    pattern = re.compile(
        _GO_MOD_PIN_RE_TEMPLATE.format(name=re.escape(name), version=re.escape(from_version)),
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    replacement = f"{match.group('prefix')}{to_version}"
    return text[: match.start()] + replacement + text[match.end() :]


def _patch_cargo_toml_pin(text: str, name: str, from_version: str, to_version: str) -> str | None:
    """Rewrite one exact-pinned dependency's version in raw Cargo.toml text.

    Matches only Cargo's simple string form (`name = "=1.2.3"`) pinned
    with its own `=` exact-pin operator -- the only form
    `build_current_state` ever derives an exact `from_version` from for
    `cargo` (a bare version means a caret range, per
    `_BARE_CONSTRAINT_IS_EXACT_PIN`'s own docstring). The table form
    (`name = { version = "=1.2.3" }`) or a `[dependencies.name]`
    dotted-table section never matches -- returned `None`, same as any
    other case this can't safely rewrite -- since a nested `version` key
    isn't a name-adjacent literal this regex could locate without risking
    a match against an unrelated same-named key elsewhere in the file.
    """
    pattern = re.compile(
        _CARGO_TOML_PIN_RE_TEMPLATE.format(name=re.escape(name), version=re.escape(from_version))
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    prefix, quote = match.group(1), match.group(2)
    replacement = f"{prefix}{quote}={to_version}{quote}"
    return text[: match.start()] + replacement + text[match.end() :]


_Patcher = Callable[[str, str, str, str], str | None]


def _select_patcher(ecosystem: str, manifest_path: str) -> _Patcher | None:
    """Pick the regex patcher for `ecosystem`'s manifest.

    `pypi` alone spans two structurally different manifest syntaxes --
    pyproject.toml's TOML (`_patch_pyproject_pin`, itself already covering
    both PEP 621 and Poetry-native forms) and requirements.txt's bare,
    unquoted plain text (`_patch_requirements_txt_pin`) -- so it dispatches
    on the manifest's own filename rather than the ecosystem string alone.
    Every other ecosystem here has exactly one supported manifest shape.
    """
    if ecosystem == "pypi":
        if Path(manifest_path).name == "requirements.txt":
            return _patch_requirements_txt_pin
        return _patch_pyproject_pin
    return {
        "npm": _patch_package_json_pin,
        "go": _patch_go_mod_pin,
        "cargo": _patch_cargo_toml_pin,
    }.get(ecosystem)


def change_plan_for_component_update(assessment: ImpactAssessment, root: Path) -> ChangePlan | None:
    """Build an executable `ChangePlan` for a component-update `ImpactAssessment`.

    Deterministic, no LLM: succeeds only for a `pypi`, `npm`, `go`, or
    `cargo` dependency whose *current* constraint was confirmed as an
    exact pin (`Confidence.HIGH`/`VERIFIED` on `from_state`, per
    `build_current_state`) and whose declaring manifest still contains
    that exact text on disk. Returns `None` — never a best-effort or
    partial plan — for every other case: a non-actionable verdict (mirrors
    `_PROPOSABLE_VERDICTS`), an ecosystem other than `pypi`/`npm`/`go`/`cargo`
    (other manifests aren't supported yet — see this module's docstring),
    a Cargo dependency using its table form rather than the simple string
    form (see `_CARGO_TOML_PIN_RE_TEMPLATE`), a range constraint, missing
    manifest evidence, an unreadable manifest file, or manifest text that
    no longer matches what the assessment observed.

    A caller that gets `None` back still has the `Proposal` from
    `propose_component_update` (unaffected by this function) describing
    what should change and why — only the automatic "here is the exact
    diff" step is unavailable for that case.
    """
    if assessment.verdict not in _PROPOSABLE_VERDICTS:
        return None

    diff = assessment.state_diff
    identity = diff.identity
    from_state, to_state = diff.from_state, diff.to_state

    if from_state.version_confidence not in (Confidence.HIGH, Confidence.VERIFIED):
        return None
    if not from_state.version or not to_state.version:
        return None

    manifest_path = _manifest_path_from_evidence(from_state.evidence)
    if manifest_path is None:
        return None

    patcher = _select_patcher(identity.distribution_source or "", manifest_path)
    if patcher is None:
        return None

    try:
        original_text = (root / manifest_path).read_text(encoding="utf-8")
    except OSError:
        return None

    patched_text = patcher(original_text, identity.name, from_state.version, to_state.version)
    if patched_text is None:
        return None

    branch_name = f"si/update-{identity.name.lower()}-to-{to_state.version}"
    return ChangePlan(
        branch_name=branch_name,
        commit_message=f"Update {identity.name} to {to_state.version}",
        files={manifest_path: patched_text},
        required_permission_level=PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR,
        description=(
            f"Update the pinned version of {identity.name} from "
            f"{from_state.version} to {to_state.version} in {manifest_path}."
        ),
        evidence_summary=[e.observation for e in assessment.evidence],
    )
