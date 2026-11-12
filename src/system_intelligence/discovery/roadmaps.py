"""Roadmap discovery: the checkbox roadmaps of an ecosystem and the pull requests behind them.

A roadmap is a Markdown file whose steps are top-level checkbox items
with a bold, numbered title (the AI Video Production OS keeps one per
repository as `ECOSYSTEM_ROADMAP.md`; the file name is the caller's):

```markdown
- [x] **3. MHL output** — one MHL per destination ([#5](https://github.com/o/r/pull/5))
  - Done when: the MHL round-trips
- [ ] **4. Card-aware inventory** — group spanned clips
```

A step's block is its own line plus the indented lines under it. Lines
inside fenced code blocks are never steps and never part of a block; an
indented fence inside a step leaves the step open, a fence at the start
of a line ends it. This module only *reads*:
`parse_roadmap` turns the text into `RoadmapStep`s, `parse_pull_requests`
reads a saved pull-request list, and the two sources below fetch both
for one repository at a time. `analysis/roadmap_drift.py` compares them.

Two sources, both read-only (ADR-004, ADR-015):

- `LocalRoadmapSource`: one checkout per repository under a directory
  (`<checkouts>/<repo>/<file>`), and saved pull-request lists
  (`<pulls>/<repo>.json`, the GitHub REST `pulls` shape). No network: what
  the tests and an offline run use.
- `GitHubRoadmapSource`: the same files from each repository's default
  branch, and its closed pull requests, through the GitHub REST API --
  GET only, `GITHUB_TOKEN` when the caller passes one, the HTTP layer
  injectable like `research/github.py`'s. Pages are requested by number
  (`page=N`), never by following `Link` headers.

A file that does not exist is `missing`; one that could not be read is
`unavailable`, with the reason. Neither is ever guessed at.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from system_intelligence.discovery.contracts import confined_path

#: A roadmap, a SKILL.md or a CHANGELOG is a few hundred KB at most; refuse
#: anything far beyond that rather than read it.
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
#: The GitHub REST API's largest page size.
GITHUB_PAGE_SIZE = 100
#: Stop paging a repository's pull requests after this many pages (10 000 PRs).
GITHUB_MAX_PAGES = 100

_API_BASE = "https://api.github.com"
_USER_AGENT = "system-intelligence-roadmap-drift/1"
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
#: A step line: `- [x] **12. Title**` (the bold title is the match).
STEP_LINE_RE = re.compile(r"^[-*+] \[(?P<mark>[ xX])\] \*\*(?P<number>\d+)\.\s*(?P<title>.*?)\*\*")
#: A fenced code block's opening or closing line: three or more backticks or tildes.
_FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")
#: A link to one pull request: https://github.com/<owner>/<repo>/pull/<number>
PULL_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+)/pull/(?P<number>\d+)"
)

#: (url, headers) -> (http_status, response_body); the same shape as
#: `research/github.py`'s, so one fake serves both in tests.
HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]


def is_repository_name(name: str) -> bool:
    """A GitHub owner or repository name: letters, digits, `.`, `_`, `-`; never `.`/`..`."""
    return bool(_NAME_RE.match(name)) and name not in {".", ".."}


@dataclass(frozen=True)
class PullRequestLink:
    """One pull-request URL inside a roadmap step."""

    owner: str
    repo: str
    number: int
    url: str
    line: int


@dataclass(frozen=True)
class RoadmapStep:
    """One numbered checkbox step and its block, with 1-based line numbers."""

    number: int
    ticked: bool
    title: str
    line: int
    #: The step's own line first, then every indented line under it.
    lines: tuple[tuple[int, str], ...]

    @property
    def headline(self) -> str:
        return self.lines[0][1]

    @property
    def line_numbers(self) -> frozenset[int]:
        return frozenset(number for number, _ in self.lines)

    def pull_links(self) -> list[PullRequestLink]:
        return [
            PullRequestLink(
                owner=match.group("owner"),
                repo=match.group("repo"),
                number=int(match.group("number")),
                url=match.group(0),
                line=number,
            )
            for number, text in self.lines
            for match in PULL_URL_RE.finditer(text)
        ]


def parse_roadmap(text: str) -> list[RoadmapStep]:
    """Every numbered checkbox step of a roadmap, in file order."""
    steps: list[RoadmapStep] = []
    current: list[tuple[int, str]] | None = None
    header: tuple[int, bool, str] | None = None
    #: The open fence's character and length (CommonMark: a closing fence uses
    #: the same character, at least as many of them, and nothing else).
    fence: tuple[str, int] | None = None

    def close() -> None:
        if current is None or header is None:
            return
        while current and not current[-1][1].strip():
            current.pop()
        number, ticked, title = header
        steps.append(RoadmapStep(number, ticked, title, current[0][0], tuple(current)))

    for line_number, line in enumerate(text.splitlines(), start=1):
        fence_line = _FENCE_RE.match(line)
        if fence is not None:
            if (
                fence_line
                and fence_line.group("fence")[0] == fence[0]
                and len(fence_line.group("fence")) >= fence[1]
                and not fence_line.group("rest").strip()
            ):
                fence = None
            continue
        if fence_line and not (
            fence_line.group("fence")[0] == "`" and "`" in fence_line.group("rest")
        ):
            fence = (fence_line.group("fence")[0], len(fence_line.group("fence")))
            if not fence_line.group("indent"):
                close()
                current, header = None, None
            continue
        match = STEP_LINE_RE.match(line)
        if match:
            close()
            header = (
                int(match.group("number")),
                match.group("mark") != " ",
                match.group("title").strip(),
            )
            current = [(line_number, line)]
            continue
        if current is not None and (not line.strip() or line[:1] in {" ", "\t"}):
            current.append((line_number, line))
            continue
        close()
        current, header = None, None
    close()
    return steps


@dataclass(frozen=True)
class PullRequest:
    """The parts of a pull request the drift check reads."""

    number: int
    title: str
    url: str
    merged_at: str | None

    @property
    def merged(self) -> bool:
        return bool(self.merged_at)


def _pull_from_object(item: Any) -> PullRequest:
    if not isinstance(item, Mapping):
        raise ValueError("expected a pull-request object")
    number, title, url = item.get("number"), item.get("title"), item.get("html_url")
    if not isinstance(number, int) or isinstance(number, bool):
        raise ValueError("a pull request has no integer 'number'")
    if not isinstance(title, str):
        raise ValueError(f"pull request {number} has no string 'title'")
    if not isinstance(url, str):
        raise ValueError(f"pull request {number} has no string 'html_url'")
    merged_at = item.get("merged_at")
    if merged_at is not None and not isinstance(merged_at, str):
        raise ValueError(f"pull request {number} has a non-string 'merged_at'")
    return PullRequest(number=number, title=title, url=url, merged_at=merged_at)


def _flatten(value: Any) -> Iterator[Any]:
    if isinstance(value, list):
        for item in value:
            yield from _flatten(item)
    else:
        yield value


def parse_pull_requests(text: str) -> list[PullRequest]:
    """A saved pull-request list: GitHub REST `pulls` objects.

    Accepts one JSON array, an array of pages (`gh api --paginate
    --slurp`), or arrays written one after another (`gh api --paginate`).
    Raises ValueError for anything else.
    """
    decoder = json.JSONDecoder()
    documents: list[Any] = []
    index = 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            document, index = decoder.raw_decode(text, index)
        except json.JSONDecodeError as exc:
            raise ValueError(f"not valid JSON: {exc}") from exc
        if not isinstance(document, list):
            raise ValueError("expected a JSON array of pull requests")
        documents.append(document)
    if not documents:
        raise ValueError("empty: expected a JSON array of pull requests")
    return [_pull_from_object(item) for item in _flatten(documents)]


@dataclass(frozen=True)
class SourceFile:
    """One file of one repository: its text, or why there is none.

    `label` (`<repo>/<path>`) is how findings cite it, the same in every
    source so a local and a GitHub run of the same content compare equal.
    """

    status: Literal["read", "missing", "unavailable"]
    label: str
    text: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PullRequestList:
    """One repository's closed pull requests, or why they could not be read."""

    status: Literal["read", "unavailable"]
    label: str
    pulls: tuple[PullRequest, ...] = ()
    error: str | None = None


class RoadmapSource(Protocol):
    """Where the drift check reads each repository's files and pull requests."""

    @property
    def kind(self) -> str: ...

    @property
    def owner(self) -> str | None: ...

    def read_file(self, repo: str, path: str) -> SourceFile: ...

    def pull_requests(self, repo: str) -> PullRequestList: ...


@dataclass(frozen=True)
class EcosystemRepository:
    """One repository an ownership map lists, with its declared status."""

    name: str
    status: str | None


def ecosystem_repositories(document: Any) -> tuple[list[EcosystemRepository], list[str]]:
    """The repositories of an ownership map (`components[].repo`, else `.name`).

    The reference shape is the AI Video Production OS `ecosystem.json`
    (ADR-012). Returns them in file order, first occurrence kept, and one
    problem per value that could not be used, named by its JSON Pointer.
    """
    if not isinstance(document, Mapping):
        return [], ["/: expected an object"]
    components = document.get("components")
    if not isinstance(components, list):
        return [], ["/components: expected an array"]
    repositories: list[EcosystemRepository] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, component in enumerate(components):
        pointer = f"/components/{index}"
        if not isinstance(component, Mapping):
            problems.append(f"{pointer}: expected an object")
            continue
        name = component.get("repo", component.get("name"))
        if not isinstance(name, str) or not is_repository_name(name.strip()):
            problems.append(f"{pointer}: names no repository ('repo' or 'name')")
            continue
        name = name.strip()
        if name.casefold() in seen:
            problems.append(f"{pointer}: {name} is listed more than once")
            continue
        seen.add(name.casefold())
        status = component.get("status")
        repositories.append(EcosystemRepository(name, status if isinstance(status, str) else None))
    return repositories, problems


def _label(repo: str, path: str) -> str:
    return f"{repo}/{path}"


class LocalRoadmapSource:
    """Local checkouts (`<checkouts>/<repo>/...`) and saved pull-request lists.

    Never runs git or anything else in a checkout, and never reads outside
    `checkouts`/`pulls_dir`.
    """

    kind = "local"

    def __init__(
        self, checkouts: Path, pulls_dir: Path | None = None, *, owner: str | None = None
    ) -> None:
        self._checkouts = checkouts
        self._pulls_dir = pulls_dir
        self._owner = owner

    @property
    def owner(self) -> str | None:
        return self._owner

    def read_file(self, repo: str, path: str) -> SourceFile:
        label = _label(repo, path)
        if not is_repository_name(repo):
            return SourceFile("unavailable", label, error="not a repository name")
        resolved = confined_path(self._checkouts, f"{repo}/{path}")
        if resolved is None:
            return SourceFile("unavailable", label, error="outside the checkouts directory")
        if not resolved.is_file():
            return SourceFile("missing", label)
        return _read_text_file(resolved, label)

    def pull_requests(self, repo: str) -> PullRequestList:
        label = f"{repo}.json"
        if self._pulls_dir is None:
            return PullRequestList("unavailable", label, error="no pull-request lists given")
        if not is_repository_name(repo):
            return PullRequestList("unavailable", label, error="not a repository name")
        path = confined_path(self._pulls_dir, label)
        if path is None:
            return PullRequestList(
                "unavailable", label, error="outside the pull-request lists directory"
            )
        if not path.is_file():
            return PullRequestList("unavailable", label, error=f"no saved list {label}")
        read = _read_text_file(path, label)
        if read.text is None:
            return PullRequestList("unavailable", label, error=read.error)
        try:
            pulls = parse_pull_requests(read.text)
        except ValueError as exc:
            return PullRequestList("unavailable", label, error=f"{label}: {exc}")
        return PullRequestList("read", label, tuple(pulls))


def _read_text_file(path: Path, label: str) -> SourceFile:
    try:
        size = path.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            return SourceFile(
                "unavailable", label, error=f"larger than {MAX_DOCUMENT_BYTES} bytes ({size})"
            )
        return SourceFile("read", label, text=path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return SourceFile("unavailable", label, error=f"{exc.__class__.__name__}: {exc}")


def _default_http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    # Only ever https://api.github.com/... URLs built by GitHubRoadmapSource
    # from names `is_repository_name` accepted; never an arbitrary scheme or host.
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
            return response.status, response.read(MAX_DOCUMENT_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_DOCUMENT_BYTES + 1)


class GitHubRoadmapSource:
    """Each repository's default branch and closed pull requests, via the GitHub REST API."""

    kind = "github"

    def __init__(
        self, owner: str, *, token: str | None = None, http_get: HttpGet | None = None
    ) -> None:
        if not is_repository_name(owner):
            raise ValueError(f"not a GitHub owner name: {owner!r}")
        self._owner = owner
        self._token = token
        self._http_get = http_get or _default_http_get

    @property
    def owner(self) -> str:
        return self._owner

    def _get(self, url: str, accept: str) -> tuple[int, bytes]:
        headers = {
            "Accept": accept,
            "User-Agent": _USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return self._http_get(url, headers)

    def read_file(self, repo: str, path: str) -> SourceFile:
        label = _label(repo, path)
        if not is_repository_name(repo):
            return SourceFile("unavailable", label, error="not a repository name")
        quoted = urllib.parse.quote(path, safe="/")
        url = f"{_API_BASE}/repos/{self._owner}/{repo}/contents/{quoted}"
        try:
            status, body = self._get(url, "application/vnd.github.raw+json")
        except OSError as exc:
            return SourceFile("unavailable", label, error=f"GitHub API request failed: {exc}")
        if status == 404:
            return SourceFile("missing", label)
        if status >= 400:
            return SourceFile("unavailable", label, error=f"GitHub API returned HTTP {status}")
        if len(body) > MAX_DOCUMENT_BYTES:
            return SourceFile("unavailable", label, error=f"larger than {MAX_DOCUMENT_BYTES} bytes")
        try:
            return SourceFile("read", label, text=body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            return SourceFile("unavailable", label, error=f"not UTF-8: {exc}")

    def pull_requests(self, repo: str) -> PullRequestList:
        label = f"{self._owner}/{repo} pull requests"
        if not is_repository_name(repo):
            return PullRequestList("unavailable", label, error="not a repository name")
        pulls: list[PullRequest] = []
        for page in range(1, GITHUB_MAX_PAGES + 1):
            query = urllib.parse.urlencode(
                {"state": "closed", "per_page": GITHUB_PAGE_SIZE, "page": page}
            )
            url = f"{_API_BASE}/repos/{self._owner}/{repo}/pulls?{query}"
            try:
                status, body = self._get(url, "application/vnd.github+json")
            except OSError as exc:
                return PullRequestList("unavailable", label, error=f"request failed: {exc}")
            if status >= 400:
                return PullRequestList(
                    "unavailable", label, error=f"GitHub API returned HTTP {status}"
                )
            try:
                page_pulls = parse_pull_requests(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                return PullRequestList("unavailable", label, error=f"page {page}: {exc}")
            pulls.extend(page_pulls)
            if len(page_pulls) < GITHUB_PAGE_SIZE:
                return PullRequestList("read", label, tuple(pulls))
        return PullRequestList(
            "unavailable", label, error=f"more than {GITHUB_MAX_PAGES} pages of pull requests"
        )
