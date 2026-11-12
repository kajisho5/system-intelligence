"""Roadmap drift: an ecosystem's checkbox roadmaps against its merged pull requests (ADR-015).

Each repository of an ecosystem keeps a roadmap of numbered checkbox steps,
one pull request per step, ticked by linking it (`discovery/roadmaps.py`
reads them). Three kinds of drift are reported, each with its repository,
its step number and the evidence (file and line, pull-request number and
URL, the exact text matched):

- **a** `ticked_without_pr_link` -- a ticked step whose block links no pull
  request. Merged pull requests whose titles name the step are attached,
  so the missing link is one look away.
- **b** `unticked_pr_merged` -- an unticked step whose pull request has
  merged: one the step links (any repository of the ecosystem), or one of
  the repository's own pull requests whose title names the step
  ("(roadmap step 8)"). `docs` pull requests are not counted: their step
  numbers are the roadmap text they wrote, not the work.
  **b** `unticked_documented_as_shipped` (candidate only, never certain) --
  no merged pull request names the step, but the repository's SKILL.md or
  CHANGELOG says it shipped: a line naming the roadmap step, or a code
  span from the step's own line (one no other part of the roadmap uses)
  found literally in those documents.
- **c** `unknown_step_reference` -- a step names another repository's step
  ("qc-skill step 9", "subtitle-skill steps 5-6") that its roadmap does
  not have. Repository names are matched exactly (case-insensitively),
  never by similarity, so a short form such as "qc step 9" is not read.

The report is deterministic: no ids, no timestamps, findings sorted by
repository, step and kind; the same inputs give byte-identical JSON. A
repository whose roadmap or pull requests could not be read is listed with
the reason and contributes no finding that would need them -- never a
guessed one. Nothing here writes anywhere.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from system_intelligence.discovery.roadmaps import (
    STEP_LINE_RE,
    EcosystemRepository,
    PullRequest,
    PullRequestList,
    RoadmapSource,
    RoadmapStep,
    SourceFile,
    parse_roadmap,
)

REPORT_FORMAT = "system-intelligence/roadmap-drift@1"
_CONTEXT_CHARS = 240
_MAX_RANGE = 100

Check = Literal["a", "b", "c"]
Kind = Literal[
    "ticked_without_pr_link",
    "unticked_pr_merged",
    "unticked_documented_as_shipped",
    "unknown_step_reference",
]
Relation = Literal[
    "roadmap_line",
    "linked_pull_request",
    "pull_request_title",
    "shipped_document",
    "step_reference",
]


class DriftEvidence(BaseModel):
    """One observation behind a finding: where, and the exact text matched."""

    model_config = ConfigDict(frozen=True)

    relation: Relation
    source: str = Field(description="'<repo>/<file>' or a pull-request URL.")
    line: int | None = Field(default=None, description="1-based line in `source`.")
    matched_text: str
    context: str = Field(description="The whole line or pull-request title, clipped.")
    pr_repo: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    merged_at: str | None = None


class DriftFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    check: Check
    kind: Kind
    certainty: Literal["certain", "candidate"]
    repo: str
    step: int
    step_title: str
    statement: str
    referenced_repo: str | None = None
    referenced_step: int | None = None
    evidence: list[DriftEvidence]
    suggested_action: str


class RepositoryCoverage(BaseModel):
    """What was read for one repository, so a gap is never mistaken for no drift."""

    model_config = ConfigDict(frozen=True)

    repo: str
    status: str | None
    roadmap: Literal["read", "missing", "unavailable", "not_created"]
    steps: int = 0
    ticked: int = 0
    pull_requests: Literal["read", "unavailable", "not_read"] = "not_read"
    merged_pull_requests: int = 0
    shipped_documents: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DriftReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: str = REPORT_FORMAT
    source: str
    roadmap_file: str
    shipped_documents: list[str]
    problems: list[str] = Field(default_factory=list)
    summary: dict[str, int]
    repositories: list[RepositoryCoverage]
    findings: list[DriftFinding]

    def to_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


# --- step references ---------------------------------------------------------

_NUMBERS = (
    r"(?:step\s+(?P<single>\d+)"
    r"|steps\s+(?P<first>\d+)(?P<rest>(?:\s*(?:-|–|—|,|&|\band\b)\s*\d+)*))"
)
_RANGE_TOKEN_RE = re.compile(r"\s*(-|–|—|,|&|and)\s*(\d+)")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_DOCS_TYPE_RE = re.compile(r"^docs(?:\([^)]*\))?!?:", re.IGNORECASE)
_SPAN_RE = re.compile(r"`([^`\n]+)`")
_IDENTIFIER_RE = re.compile(r"[_.\-/@:= ]|^[A-Z][A-Z0-9_]{3,}$")
_MIN_SPAN_CHARS = 5


def _numbers(match: re.Match[str]) -> list[int]:
    if match.group("single") is not None:
        return [int(match.group("single"))]
    previous = int(match.group("first"))
    numbers = {previous}
    for separator, value in _RANGE_TOKEN_RE.findall(match.group("rest") or ""):
        number = int(value)
        if separator in {"-", "–", "—"} and previous < number <= previous + _MAX_RANGE:
            numbers.update(range(previous + 1, number + 1))
        else:
            numbers.add(number)
        previous = number
    return sorted(numbers)


#: Words a step uses to say it is still open although some of it merged
#: ("Partly done (ADR-30), left unchecked", "Status: partial (#38)",
#: "Skill side (#14)", "- [x] Building block: ... (#134)").
_OPEN_MARKER_RE = re.compile(
    r"\b(?:partly done|partially done|status:\s*partial|not met|left unchecked|not ticked"
    r"|stays open|still open|remains open|building block|skill side|agent side|first half"
    r"|second half)\b"
    r"|^\s*[-*+]\s+(?:\[[ xX]\]\s+)?(?:progress|open)\s*[:(]",
    re.IGNORECASE,
)


def _open_marker(step: RoadmapStep) -> tuple[int, str] | None:
    """The first line under the step (never its own line) that says it is still open."""
    for line_number, text in step.lines[1:]:
        match = _OPEN_MARKER_RE.search(text)
        if match:
            return line_number, match.group(0).strip(" -*+:(")
    return None


def _is_docs_entry(text: str) -> bool:
    """A `docs:` pull-request title or changelog entry (list marker allowed)."""
    return bool(_DOCS_TYPE_RE.match(_LIST_MARKER_RE.sub("", text, count=1).strip()))


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _CONTEXT_CHARS else text[: _CONTEXT_CHARS - 1] + "…"


def _step_marker(step: RoadmapStep) -> str:
    """`- [x] **8. Title**`: the part of the step line that makes it a step."""
    match = STEP_LINE_RE.match(step.headline)
    return match.group(0) if match else step.headline.strip()


def _merged_on(evidence: DriftEvidence) -> str:
    return (evidence.merged_at or "")[:10] or "at an unknown time"


def _describe_numbers(numbers: Collection[int]) -> str:
    """`[1, 2, 3, 5]` -> `1-3, 5`."""
    ordered = sorted(set(numbers))
    if not ordered:
        return "none"
    parts: list[str] = []
    start = end = ordered[0]
    for number in ordered[1:]:
        if number == end + 1:
            end = number
            continue
        parts.append(f"{start}-{end}" if end > start else str(start))
        start = end = number
    parts.append(f"{start}-{end}" if end > start else str(start))
    return ", ".join(parts)


@dataclass(frozen=True)
class _Patterns:
    own: re.Pattern[str]
    cross: re.Pattern[str]


def _patterns(repository_names: Collection[str], roadmap_file: str) -> _Patterns:
    alternation = (
        "|".join(re.escape(name) for name in sorted(repository_names, key=lambda n: (-len(n), n)))
        or "(?!)"
    )
    stem = roadmap_file.rsplit(".", 1)[0]
    roadmap_word = rf"(?:{re.escape(roadmap_file)}|{re.escape(stem)}|roadmap)"
    # A repository's own step: "(roadmap step 8)", "ECOSYSTEM_ROADMAP.md step 5",
    # optionally after a repository name (kept only when it is this repository).
    own = re.compile(
        rf"(?<![\w/.-])(?:(?P<repo>{alternation})(?:'s)?\s+)?{roadmap_word}\s+{_NUMBERS}",
        re.IGNORECASE,
    )
    # Another repository's step: "qc-skill step 9", "dubbing-skill's step 9",
    # "thumbnail-skill roadmap step 4", "subtitle-skill steps 5-6".
    cross = re.compile(
        rf"(?<![\w/.-])(?P<repo>{alternation})(?:'s)?(?:\s+{roadmap_word})?\s+{_NUMBERS}",
        re.IGNORECASE,
    )
    return _Patterns(own=own, cross=cross)


def _own_step_mentions(
    text: str, repo: str, patterns: _Patterns
) -> list[tuple[re.Match[str], list[int]]]:
    """Mentions of `repo`'s own roadmap steps in a title or document line."""
    mentions: list[tuple[re.Match[str], list[int]]] = []
    for match in patterns.own.finditer(text):
        named = match.group("repo")
        if named is not None and named.casefold() != repo.casefold():
            continue
        mentions.append((match, _numbers(match)))
    return mentions


# --- the check ---------------------------------------------------------------


@dataclass
class _Repo:
    entry: EcosystemRepository
    roadmap: SourceFile | None = None
    steps: list[RoadmapStep] = field(default_factory=list)
    roadmap_lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class _Check:
    def __init__(
        self,
        repositories: Sequence[EcosystemRepository],
        source: RoadmapSource,
        roadmap_file: str,
        shipped_documents: Sequence[str],
        inactive_statuses: Collection[str],
    ) -> None:
        self.source = source
        self.roadmap_file = roadmap_file
        self.shipped_documents = shipped_documents
        self.inactive = {status.casefold() for status in inactive_statuses}
        self.repos: dict[str, _Repo] = {
            entry.name.casefold(): _Repo(entry)
            for entry in sorted(repositories, key=lambda e: e.name.casefold())
        }
        self.patterns = _patterns([entry.name for entry in repositories], roadmap_file)
        self._pulls: dict[str, PullRequestList] = {}
        self._documents: dict[str, list[SourceFile]] = {}
        self.findings: list[DriftFinding] = []

    # -- reads (each at most once) --

    def is_inactive(self, repo: _Repo) -> bool:
        status = repo.entry.status
        return status is not None and status.casefold() in self.inactive

    def read_roadmaps(self) -> None:
        for repo in self.repos.values():
            if self.is_inactive(repo):
                continue
            repo.roadmap = self.source.read_file(repo.entry.name, self.roadmap_file)
            if repo.roadmap.text is None:
                continue
            repo.roadmap_lines = repo.roadmap.text.splitlines()
            repo.steps = parse_roadmap(repo.roadmap.text)
            seen: dict[int, int] = {}
            for step in repo.steps:
                if step.number in seen:
                    repo.notes.append(
                        f"step {step.number} appears more than once "
                        f"(lines {seen[step.number]} and {step.line})"
                    )
                else:
                    seen[step.number] = step.line

    def pulls(self, repo: _Repo) -> PullRequestList:
        key = repo.entry.name.casefold()
        if key not in self._pulls:
            self._pulls[key] = self.source.pull_requests(repo.entry.name)
        return self._pulls[key]

    def merged_pulls(self, repo: _Repo) -> list[PullRequest]:
        listed = self.pulls(repo)
        return sorted((p for p in listed.pulls if p.merged), key=lambda p: p.number)

    def documents(self, repo: _Repo) -> list[SourceFile]:
        key = repo.entry.name.casefold()
        if key not in self._documents:
            reads: list[SourceFile] = []
            seen: set[str] = set()
            for template in self.shipped_documents:
                path = template.replace("{repo}", repo.entry.name)
                if path in seen:
                    continue
                seen.add(path)
                reads.append(self.source.read_file(repo.entry.name, path))
            self._documents[key] = reads
        return self._documents[key]

    # -- evidence --

    def roadmap_evidence(self, repo: _Repo, step: RoadmapStep) -> DriftEvidence:
        return DriftEvidence(
            relation="roadmap_line",
            source=f"{repo.entry.name}/{self.roadmap_file}",
            line=step.line,
            matched_text=_step_marker(step),
            context=_clip(step.headline),
        )

    def title_mentions(self, repo: _Repo, step: RoadmapStep) -> list[DriftEvidence]:
        """Merged, non-docs pull requests of `repo` whose title names `step`."""
        if self.pulls(repo).status != "read":
            return []
        evidence: list[DriftEvidence] = []
        for pull in self.merged_pulls(repo):
            if _is_docs_entry(pull.title):
                continue
            for match, numbers in _own_step_mentions(pull.title, repo.entry.name, self.patterns):
                if step.number in numbers:
                    evidence.append(
                        DriftEvidence(
                            relation="pull_request_title",
                            source=pull.url,
                            matched_text=match.group(0),
                            context=_clip(pull.title),
                            pr_repo=repo.entry.name,
                            pr_number=pull.number,
                            pr_url=pull.url,
                            merged_at=pull.merged_at,
                        )
                    )
                    break
        return evidence

    def linked_merges(self, repo: _Repo, step: RoadmapStep) -> list[DriftEvidence]:
        """Merged pull requests the step links, looked up in the ecosystem's lists."""
        evidence: list[DriftEvidence] = []
        owner = self.source.owner
        seen: set[tuple[str, int]] = set()
        for link in step.pull_links():
            if (link.repo.casefold(), link.number) in seen:
                continue
            seen.add((link.repo.casefold(), link.number))
            target = self.repos.get(link.repo.casefold())
            if target is None or (owner is not None and link.owner.casefold() != owner.casefold()):
                repo.notes.append(
                    f"step {step.number} links {link.owner}/{link.repo}#{link.number}, "
                    "outside the ecosystem; not looked up"
                )
                continue
            listed = self.pulls(target)
            if listed.status != "read":
                repo.notes.append(
                    f"step {step.number} links {link.repo}#{link.number}; "
                    f"its pull requests could not be read ({listed.error})"
                )
                continue
            pull = next((p for p in listed.pulls if p.number == link.number), None)
            if pull is None or not pull.merged:
                continue
            if pull.url.rstrip("/").casefold() != link.url.casefold():
                # Same number, another pull request: never use it as this link's evidence.
                repo.notes.append(
                    f"step {step.number} links {link.url}, but the saved #{link.number} of "
                    f"{target.entry.name} is {pull.url}; not used"
                )
                continue
            evidence.append(
                DriftEvidence(
                    relation="linked_pull_request",
                    source=f"{repo.entry.name}/{self.roadmap_file}",
                    line=link.line,
                    matched_text=link.url,
                    context=_clip(pull.title),
                    pr_repo=target.entry.name,
                    pr_number=pull.number,
                    pr_url=pull.url,
                    merged_at=pull.merged_at,
                )
            )
        return evidence

    def shipped_mentions(self, repo: _Repo, step: RoadmapStep) -> list[DriftEvidence]:
        """SKILL.md / CHANGELOG lines that say the step shipped (candidate evidence)."""
        own_lines = step.line_numbers
        outside = "\n".join(
            text
            for number, text in enumerate(repo.roadmap_lines, start=1)
            if number not in own_lines
        )
        spans = sorted(
            {
                span
                for span in _SPAN_RE.findall(step.headline)
                if len(span.strip()) >= _MIN_SPAN_CHARS
                and _IDENTIFIER_RE.search(span)
                and span != self.roadmap_file
                and span not in outside
            }
        )
        evidence: list[DriftEvidence] = []
        for document in self.documents(repo):
            if document.text is None:
                continue
            found_spans: set[str] = set()
            for number, line in enumerate(document.text.splitlines(), start=1):
                if _is_docs_entry(line):
                    continue
                for match, numbers in _own_step_mentions(line, repo.entry.name, self.patterns):
                    if step.number in numbers:
                        evidence.append(
                            DriftEvidence(
                                relation="shipped_document",
                                source=document.label,
                                line=number,
                                matched_text=match.group(0),
                                context=_clip(line),
                            )
                        )
                        break
                for span in spans:
                    if span not in found_spans and span in line:
                        found_spans.add(span)
                        evidence.append(
                            DriftEvidence(
                                relation="shipped_document",
                                source=document.label,
                                line=number,
                                matched_text=span,
                                context=_clip(line),
                            )
                        )
        return evidence

    # -- findings --

    def add(self, finding: DriftFinding) -> None:
        self.findings.append(finding)

    def check_ticked(self, repo: _Repo, step: RoadmapStep) -> None:
        if step.pull_links():
            return
        hints = self.title_mentions(repo, step)
        statement = f"Step {step.number} ({step.title}) is ticked but links no pull request."
        if hints:
            numbers = ", ".join(f"#{e.pr_number}" for e in hints)
            statement += f" Merged pull requests whose titles name it: {numbers}."
        self.add(
            DriftFinding(
                check="a",
                kind="ticked_without_pr_link",
                certainty="certain",
                repo=repo.entry.name,
                step=step.number,
                step_title=step.title,
                statement=statement,
                evidence=[self.roadmap_evidence(repo, step), *hints],
                suggested_action="Link the pull request that completed the step"
                + (" (named in the evidence)" if hints else "")
                + ", or untick it if it is not done.",
            )
        )

    def check_unticked(self, repo: _Repo, step: RoadmapStep) -> None:
        merged = [*self.linked_merges(repo, step), *self.title_mentions(repo, step)]
        marker = _open_marker(step)
        if marker is not None:
            # The step says in so many words that it is still open, so a merged
            # pull request or a shipped-document mention is accounted for, not drift.
            shipped = [] if merged else self.shipped_mentions(repo, step)
            accounted = sorted({f"#{e.pr_number}" for e in merged} | {e.source for e in shipped})
            if accounted:
                line_number, text = marker
                repo.notes.append(
                    f"step {step.number} is unticked and says it is still open "
                    f"({text!r}, line {line_number}); {', '.join(accounted)} not counted "
                    "as drift"
                )
            return
        if merged:
            described: dict[tuple[str | None, int | None], str] = {}
            for item in merged:
                how = (
                    "linked from the step"
                    if item.relation == "linked_pull_request"
                    else f"its title says {item.matched_text!r}"
                )
                prefix = "" if item.pr_repo == repo.entry.name else f"{item.pr_repo}"
                described.setdefault(
                    (item.pr_repo, item.pr_number),
                    f"{prefix}#{item.pr_number} ({how}, merged {_merged_on(item)})",
                )
            self.add(
                DriftFinding(
                    check="b",
                    kind="unticked_pr_merged",
                    certainty="certain",
                    repo=repo.entry.name,
                    step=step.number,
                    step_title=step.title,
                    statement=f"Step {step.number} ({step.title}) is unticked, but its pull "
                    f"request has merged: {'; '.join(described.values())}.",
                    evidence=[self.roadmap_evidence(repo, step), *merged],
                    suggested_action="Tick the step with its PR link if the pull request "
                    "completed it; otherwise say in the step what is still open.",
                )
            )
            return
        shipped = self.shipped_mentions(repo, step)
        if not shipped:
            return
        where = ", ".join(f"{e.source}:{e.line} ({e.matched_text!r})" for e in shipped)
        self.add(
            DriftFinding(
                check="b",
                kind="unticked_documented_as_shipped",
                certainty="candidate",
                repo=repo.entry.name,
                step=step.number,
                step_title=step.title,
                statement=f"Step {step.number} ({step.title}) is unticked, and the shipped "
                f"documentation may already describe it: {where}. Candidate only: matched "
                "text, not a merged pull request.",
                evidence=[self.roadmap_evidence(repo, step), *shipped],
                suggested_action="Check whether the step has shipped; if it has, tick it with "
                "its PR link.",
            )
        )

    def check_references(self, repo: _Repo, step: RoadmapStep) -> None:
        missing: dict[tuple[str, int], list[DriftEvidence]] = {}
        reasons: dict[tuple[str, int], str] = {}
        for line_number, text in step.lines:
            for match in self.patterns.cross.finditer(text):
                target = self.repos.get(match.group("repo").casefold())
                if target is None or target is repo:
                    continue
                name = target.entry.name
                for number in _numbers(match):
                    reason = self.missing_reason(repo, step, target, number)
                    if reason is None:
                        continue
                    key = (name, number)
                    reasons[key] = reason
                    missing.setdefault(key, []).append(
                        DriftEvidence(
                            relation="step_reference",
                            source=f"{repo.entry.name}/{self.roadmap_file}",
                            line=line_number,
                            matched_text=match.group(0),
                            context=_clip(text),
                        )
                    )
        for (name, number), evidence in sorted(missing.items()):
            self.add(
                DriftFinding(
                    check="c",
                    kind="unknown_step_reference",
                    certainty="certain",
                    repo=repo.entry.name,
                    step=step.number,
                    step_title=step.title,
                    statement=f"Step {step.number} ({step.title}) names {name} step {number}, "
                    f"which does not exist: {reasons[(name, number)]}.",
                    referenced_repo=name,
                    referenced_step=number,
                    evidence=evidence,
                    suggested_action=f"Point the reference at the {name} step that exists, "
                    f"or add the step to {name}'s roadmap.",
                )
            )

    def missing_reason(
        self, repo: _Repo, step: RoadmapStep, target: _Repo, number: int
    ) -> str | None:
        """Why `target` has no step `number`, or None if it has one (or it is unknown)."""
        name = target.entry.name
        if self.is_inactive(target):
            return f"{name} is {target.entry.status} and has no repository yet"
        if target.roadmap is None or target.roadmap.status == "unavailable":
            note = (
                f"step {step.number} names {name} step {number}; {name}'s roadmap could not be read"
            )
            if note not in repo.notes:
                repo.notes.append(note)
            return None
        if target.roadmap.status == "missing":
            return f"{name} has no {self.roadmap_file}"
        numbers = {s.number for s in target.steps}
        if number in numbers:
            return None
        return f"{name}'s {self.roadmap_file} has steps {_describe_numbers(numbers)}"

    def run(self) -> None:
        self.read_roadmaps()
        for repo in self.repos.values():
            for step in repo.steps:
                if step.ticked:
                    self.check_ticked(repo, step)
                else:
                    self.check_unticked(repo, step)
                self.check_references(repo, step)

    def coverage(self) -> list[RepositoryCoverage]:
        rows: list[RepositoryCoverage] = []
        for repo in self.repos.values():
            notes = list(repo.notes)
            if self.is_inactive(repo):
                rows.append(
                    RepositoryCoverage(
                        repo=repo.entry.name, status=repo.entry.status, roadmap="not_created"
                    )
                )
                continue
            # read_roadmaps read every active repository, so `roadmap` is set here.
            roadmap = repo.roadmap or SourceFile("unavailable", "", error="not read")
            if roadmap.status == "missing":
                notes.insert(0, f"no {self.roadmap_file}")
            elif roadmap.status == "unavailable":
                notes.insert(0, f"{self.roadmap_file} could not be read: {roadmap.error}")
            listed = self._pulls.get(repo.entry.name.casefold())
            if listed is not None and listed.status == "unavailable":
                notes.append(
                    f"pull requests could not be read ({listed.error}); "
                    "the merged-pull-request checks were skipped"
                )
            documents = self._documents.get(repo.entry.name.casefold(), [])
            rows.append(
                RepositoryCoverage(
                    repo=repo.entry.name,
                    status=repo.entry.status,
                    roadmap=roadmap.status,
                    steps=len(repo.steps),
                    ticked=sum(1 for step in repo.steps if step.ticked),
                    pull_requests="not_read" if listed is None else listed.status,
                    merged_pull_requests=sum(1 for p in listed.pulls if p.merged)
                    if listed is not None
                    else 0,
                    shipped_documents=[d.label for d in documents if d.status == "read"],
                    notes=list(dict.fromkeys(notes)),
                )
            )
        return rows


def _sort_key(finding: DriftFinding) -> tuple[str, int, str, str, str, int]:
    return (
        finding.repo.casefold(),
        finding.step,
        finding.check,
        finding.kind,
        (finding.referenced_repo or "").casefold(),
        finding.referenced_step or 0,
    )


def check_roadmap_drift(
    repositories: Sequence[EcosystemRepository],
    source: RoadmapSource,
    *,
    roadmap_file: str,
    shipped_documents: Sequence[str] = (),
    inactive_statuses: Collection[str] = (),
    problems: Sequence[str] = (),
) -> DriftReport:
    """Compare every repository's roadmap with its pull requests and documents.

    `shipped_documents` are paths inside each repository (`{repo}` is
    replaced by its name) that describe what has shipped, e.g. `SKILL.md`
    and `CHANGELOG.md`; they feed the candidate-only check. A repository
    whose status is in `inactive_statuses` has no repository yet: it is
    not read, and a step naming one of its steps is drift (c).
    """
    check = _Check(repositories, source, roadmap_file, shipped_documents, inactive_statuses)
    check.run()
    findings = sorted(check.findings, key=_sort_key)
    summary = {
        "repositories": len(check.repos),
        "roadmaps_read": sum(
            1 for r in check.repos.values() if r.roadmap and r.roadmap.status == "read"
        ),
        "findings": len(findings),
        "a": sum(1 for f in findings if f.check == "a"),
        "b": sum(1 for f in findings if f.check == "b" and f.certainty == "certain"),
        "b_candidate": sum(1 for f in findings if f.check == "b" and f.certainty == "candidate"),
        "c": sum(1 for f in findings if f.check == "c"),
    }
    return DriftReport(
        source=source.kind,
        roadmap_file=roadmap_file,
        shipped_documents=list(shipped_documents),
        problems=list(problems),
        summary=summary,
        repositories=check.coverage(),
        findings=findings,
    )


# --- the readable table --------------------------------------------------------

_KIND_LABELS: dict[str, str] = {
    "ticked_without_pr_link": "ticked, no PR link",
    "unticked_pr_merged": "unticked, PR merged",
    "unticked_documented_as_shipped": "unticked, documented as shipped",
    "unknown_step_reference": "names a step that does not exist",
}


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _evidence_cell(finding: DriftFinding) -> str:
    """Pull requests once each (how they name the step), then file locations."""
    pulls: dict[str, list[str]] = {}
    locations: list[str] = []
    step_lines: list[str] = []
    for item in finding.evidence:
        if item.pr_url is not None:
            how = (
                f"linked at line {item.line}"
                if item.relation == "linked_pull_request"
                else f"title: {item.matched_text!r}"
            )
            pulls.setdefault(f"#{item.pr_number} {item.pr_url}", []).append(how)
        elif item.relation == "roadmap_line":
            step_lines.append(f"{item.source}:{item.line}")
        else:
            locations.append(f"{item.source}:{item.line} ({item.matched_text!r})")
    parts = [f"{pull} ({'; '.join(hows)})" for pull, hows in pulls.items()]
    parts += dict.fromkeys(locations)
    return "; ".join(parts or step_lines)


def format_drift_table(report: DriftReport) -> str:
    """The report as Markdown: a summary line, one table row per finding, and coverage gaps."""
    summary = report.summary
    lines = [
        f"Roadmap drift ({report.source}, {report.roadmap_file}): "
        f"{summary['roadmaps_read']} of {summary['repositories']} roadmaps read, "
        f"{summary['findings']} findings "
        f"(a: {summary['a']}, b: {summary['b']}, b candidates: {summary['b_candidate']}, "
        f"c: {summary['c']})",
        "",
    ]
    if report.findings:
        lines += [
            "| Check | Repository | Step | Certainty | Finding | Evidence |",
            "|---|---|---|---|---|---|",
        ]
        for finding in report.findings:
            what = _KIND_LABELS[finding.kind]
            if finding.referenced_repo is not None:
                what += f": {finding.referenced_repo} step {finding.referenced_step}"
            lines.append(
                "| "
                + " | ".join(
                    _cell(value)
                    for value in (
                        finding.check,
                        finding.repo,
                        str(finding.step),
                        finding.certainty,
                        f"{what} — {finding.step_title}",
                        _evidence_cell(finding),
                    )
                )
                + " |"
            )
    else:
        lines.append("No drift found.")
    gaps: list[str] = []
    for row in report.repositories:
        if row.roadmap == "not_created":
            gaps.append(f"- {row.repo}: status {row.status}, not read")
        elif row.notes:
            gaps.append(f"- {row.repo}: {'; '.join(row.notes)}")
    gaps += [f"- ecosystem file: {problem}" for problem in report.problems]
    if gaps:
        lines += ["", "Notes:", *gaps]
    return "\n".join(lines) + "\n"
