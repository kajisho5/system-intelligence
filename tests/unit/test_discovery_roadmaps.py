import json
from collections.abc import Callable
from pathlib import Path

import pytest

from system_intelligence.discovery.roadmaps import (
    GITHUB_PAGE_SIZE,
    EcosystemRepository,
    GitHubRoadmapSource,
    LocalRoadmapSource,
    PullRequest,
    ecosystem_repositories,
    is_repository_name,
    parse_pull_requests,
    parse_roadmap,
)

ROADMAP = """# Roadmap

Intro text with a fake step in prose: - [x] **9. Not a step**

## Steps

- [x] **1. First step** — done ([#4](https://github.com/acme/alpha/pull/4))
  - Done when: it works

  - Done (ADR-1): continued after a blank line, see https://github.com/acme/beta/pull/12
- [ ] **2. Second step** — `alpha run --resume`
  - [x] Building block: a nested checkbox stays inside step 2
* [X] **3. Star bullet, capital X**

```markdown
- [ ] **4. Inside a code fence, never a step**
```

- [ ] **12. Last** — after the fence

## Boundaries

- [ ] not a numbered step
"""


def test_parse_roadmap_reads_numbered_checkbox_steps_and_their_blocks() -> None:
    steps = parse_roadmap(ROADMAP)

    assert [(s.number, s.ticked, s.title) for s in steps] == [
        (1, True, "First step"),
        (2, False, "Second step"),
        (3, True, "Star bullet, capital X"),
        (12, False, "Last"),
    ]
    first, second, third, last = steps
    assert first.line == 7
    assert [number for number, _ in first.lines] == [7, 8, 9, 10]
    assert first.headline.startswith("- [x] **1. First step**")
    assert [number for number, _ in second.lines] == [11, 12]
    assert third.lines == ((13, "* [X] **3. Star bullet, capital X**"),)
    assert last.line == 19


def test_pull_links_are_every_pull_url_in_the_block_with_its_line() -> None:
    first = parse_roadmap(ROADMAP)[0]

    links = first.pull_links()

    assert [(link.owner, link.repo, link.number, link.line) for link in links] == [
        ("acme", "alpha", 4, 7),
        ("acme", "beta", 12, 10),
    ]
    assert links[0].url == "https://github.com/acme/alpha/pull/4"


def test_parse_roadmap_without_steps_is_empty() -> None:
    assert parse_roadmap("# Nothing here\n\n- plain bullet\n") == []


def _pull(number: int, merged_at: str | None = "2026-10-01T00:00:00Z") -> dict[str, object]:
    return {
        "number": number,
        "title": f"PR {number}",
        "html_url": f"https://github.com/acme/alpha/pull/{number}",
        "merged_at": merged_at,
        "state": "closed",
    }


def test_parse_pull_requests_accepts_a_list_pages_and_concatenated_arrays() -> None:
    single = json.dumps([_pull(1), _pull(2, None)])
    pages = json.dumps([[_pull(1)], [_pull(2, None)]])
    concatenated = json.dumps([_pull(1)]) + "\n" + json.dumps([_pull(2, None)])

    expected = [
        PullRequest(1, "PR 1", "https://github.com/acme/alpha/pull/1", "2026-10-01T00:00:00Z"),
        PullRequest(2, "PR 2", "https://github.com/acme/alpha/pull/2", None),
    ]
    assert parse_pull_requests(single) == expected
    assert parse_pull_requests(pages) == expected
    assert parse_pull_requests(concatenated) == expected
    assert [p.merged for p in expected] == [True, False]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("", "empty"),
        ("{}", "expected a JSON array"),
        ("[1]", "pull-request object"),
        ('[{"number": "1", "title": "t", "html_url": "u"}]', "integer 'number'"),
        ('[{"number": 1, "html_url": "u"}]', "string 'title'"),
        ('[{"number": 1, "title": "t"}]', "string 'html_url'"),
        ('[{"number": 1, "title": "t", "html_url": "u", "merged_at": 5}]', "'merged_at'"),
        ("[", "not valid JSON"),
    ],
)
def test_parse_pull_requests_refuses_other_shapes(text: str, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        parse_pull_requests(text)


def test_ecosystem_repositories_reads_repo_or_name_and_reports_problems() -> None:
    document = {
        "components": [
            {"repo": "alpha", "status": "active"},
            {"name": "beta"},
            {"repo": "Alpha"},
            {"repo": "../escape"},
            "not an object",
            {"status": "planned"},
        ]
    }

    repositories, problems = ecosystem_repositories(document)

    assert repositories == [
        EcosystemRepository("alpha", "active"),
        EcosystemRepository("beta", None),
    ]
    assert problems == [
        "/components/2: Alpha is listed more than once",
        "/components/3: names no repository ('repo' or 'name')",
        "/components/4: expected an object",
        "/components/5: names no repository ('repo' or 'name')",
    ]


@pytest.mark.parametrize(
    ("document", "problem"),
    [([], "/: expected an object"), ({}, "/components: expected an array")],
)
def test_ecosystem_repositories_needs_a_components_array(document: object, problem: str) -> None:
    assert ecosystem_repositories(document) == ([], [problem])


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a b", "../x"])
def test_is_repository_name_refuses_paths(name: str) -> None:
    assert not is_repository_name(name)


def test_local_source_reads_missing_and_unavailable_files(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "ECOSYSTEM_ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    (tmp_path / "alpha" / "CHANGELOG.md").write_bytes(b"\xff\xfe not utf-8")
    source = LocalRoadmapSource(tmp_path)

    read = source.read_file("alpha", "ECOSYSTEM_ROADMAP.md")
    missing = source.read_file("alpha", "SKILL.md")
    undecodable = source.read_file("alpha", "CHANGELOG.md")
    escaping = source.read_file("alpha", "../../outside.md")
    bad_name = source.read_file("..", "ECOSYSTEM_ROADMAP.md")

    assert (read.status, read.label, read.text) == (
        "read",
        "alpha/ECOSYSTEM_ROADMAP.md",
        "# Roadmap\n",
    )
    assert (missing.status, missing.label, missing.text) == ("missing", "alpha/SKILL.md", None)
    assert undecodable.status == "unavailable"
    assert "UnicodeDecodeError" in (undecodable.error or "")
    assert (escaping.status, escaping.error) == ("unavailable", "outside the checkouts directory")
    assert (bad_name.status, bad_name.error) == ("unavailable", "not a repository name")
    assert source.kind == "local"
    assert source.owner is None


def test_local_source_symlink_out_of_the_checkouts_is_refused(
    tmp_path: Path, make_symlink: Callable[[Path, Path], None]
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret\n", encoding="utf-8")
    checkouts = tmp_path / "checkouts"
    (checkouts / "alpha").mkdir(parents=True)
    make_symlink(checkouts / "alpha" / "ECOSYSTEM_ROADMAP.md", outside)

    read = LocalRoadmapSource(checkouts).read_file("alpha", "ECOSYSTEM_ROADMAP.md")

    assert (read.status, read.text) == ("unavailable", None)


def test_local_source_pull_requests(tmp_path: Path) -> None:
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    (pulls / "alpha.json").write_text(json.dumps([_pull(1)]), encoding="utf-8")
    (pulls / "broken.json").write_text("{}", encoding="utf-8")

    read = LocalRoadmapSource(tmp_path, pulls).pull_requests("alpha")
    absent = LocalRoadmapSource(tmp_path, pulls).pull_requests("beta")
    broken = LocalRoadmapSource(tmp_path, pulls).pull_requests("broken")
    none_given = LocalRoadmapSource(tmp_path).pull_requests("alpha")

    assert (read.status, [p.number for p in read.pulls]) == ("read", [1])
    assert (absent.status, absent.error) == ("unavailable", "no saved list beta.json")
    assert broken.status == "unavailable"
    assert "expected a JSON array" in (broken.error or "")
    assert (none_given.status, none_given.error) == (
        "unavailable",
        "no pull-request lists given",
    )


class FakeGitHub:
    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        self.requests.append((url, headers))
        if url not in self.responses:
            return 404, b'{"message": "Not Found"}'
        return self.responses[url]


API = "https://api.github.com/repos/acme"


def test_github_source_reads_raw_files_and_tells_missing_from_unavailable() -> None:
    fake = FakeGitHub(
        {
            f"{API}/alpha/contents/ECOSYSTEM_ROADMAP.md": (200, "# Roadmap — α\n".encode()),
            f"{API}/alpha/contents/CHANGELOG.md": (500, b"oops"),
            f"{API}/alpha/contents/skills/alpha/SKILL.md": (200, b"\xff"),
        }
    )
    source = GitHubRoadmapSource("acme", token="t0ken", http_get=fake)

    read = source.read_file("alpha", "ECOSYSTEM_ROADMAP.md")
    missing = source.read_file("alpha", "SKILL.md")
    failed = source.read_file("alpha", "CHANGELOG.md")
    undecodable = source.read_file("alpha", "skills/alpha/SKILL.md")

    assert (read.status, read.label, read.text) == (
        "read",
        "alpha/ECOSYSTEM_ROADMAP.md",
        "# Roadmap — α\n",
    )
    assert missing.status == "missing"
    assert (failed.status, failed.error) == ("unavailable", "GitHub API returned HTTP 500")
    assert undecodable.status == "unavailable"
    url, headers = fake.requests[0]
    assert headers["Accept"] == "application/vnd.github.raw+json"
    assert headers["Authorization"] == "Bearer t0ken"
    assert source.kind == "github"
    assert source.owner == "acme"


def test_github_source_without_token_sends_no_authorization() -> None:
    fake = FakeGitHub({})
    GitHubRoadmapSource("acme", http_get=fake).read_file("alpha", "SKILL.md")

    assert "Authorization" not in fake.requests[0][1]


def test_github_source_network_error_is_unavailable() -> None:
    def broken(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        raise OSError("connection reset")

    source = GitHubRoadmapSource("acme", http_get=broken)

    assert source.read_file("alpha", "SKILL.md").status == "unavailable"
    listed = source.pull_requests("alpha")
    assert listed.status == "unavailable"
    assert "connection reset" in (listed.error or "")


def test_github_source_pages_pull_requests_by_number() -> None:
    first_page = [_pull(n) for n in range(1, GITHUB_PAGE_SIZE + 1)]
    query = "state=closed&per_page=100"
    fake = FakeGitHub(
        {
            f"{API}/alpha/pulls?{query}&page=1": (200, json.dumps(first_page).encode()),
            f"{API}/alpha/pulls?{query}&page=2": (200, json.dumps([_pull(101, None)]).encode()),
        }
    )

    listed = GitHubRoadmapSource("acme", http_get=fake).pull_requests("alpha")

    assert listed.status == "read"
    assert len(listed.pulls) == GITHUB_PAGE_SIZE + 1
    assert [url for url, _ in fake.requests] == [
        f"{API}/alpha/pulls?{query}&page=1",
        f"{API}/alpha/pulls?{query}&page=2",
    ]


def test_github_source_pull_request_errors_are_unavailable() -> None:
    query = "state=closed&per_page=100&page=1"
    fake = FakeGitHub(
        {
            f"{API}/alpha/pulls?{query}": (403, b"rate limited"),
            f"{API}/beta/pulls?{query}": (200, b"{}"),
        }
    )
    source = GitHubRoadmapSource("acme", http_get=fake)

    assert source.pull_requests("alpha").error == "GitHub API returned HTTP 403"
    assert "page 1" in (source.pull_requests("beta").error or "")
    assert source.pull_requests("..").error == "not a repository name"


def test_github_source_refuses_a_bad_owner() -> None:
    with pytest.raises(ValueError, match="owner"):
        GitHubRoadmapSource("acme/../x")


def test_an_indented_fence_keeps_its_step_open() -> None:
    text = (
        "- [x] **1. With an example**\n"
        "  ```json\n"
        "  - [ ] **2. Not a step, and https://github.com/acme/alpha/pull/99 is not a link**\n"
        "  ```\n"
        "  - Done ([#4](https://github.com/acme/alpha/pull/4))\n"
        "- [ ] **3. Next**\n"
    )

    first, third = parse_roadmap(text)

    assert (first.number, third.number) == (1, 3)
    assert [number for number, _ in first.lines] == [1, 5]
    assert [link.number for link in first.pull_links()] == [4]


def test_a_fence_closes_only_with_the_same_character_and_length() -> None:
    text = (
        "````markdown\n"
        "```\n"
        "- [ ] **1. Inside the four-backtick block**\n"
        "~~~~\n"
        "- [ ] **2. Still inside**\n"
        "```` trailing text is not a closing fence\n"
        "- [ ] **3. Still inside**\n"
        "`````\n"
        "- [ ] **4. After the block**\n"
    )

    assert [step.number for step in parse_roadmap(text)] == [4]


def test_inline_backticks_are_not_a_fence() -> None:
    text = "- [x] **1. A**\n```code``` in prose ends the step\n- [ ] **2. B**\n"

    assert [step.number for step in parse_roadmap(text)] == [1, 2]


def test_saved_pull_request_list_symlinked_out_of_its_directory_is_refused(
    tmp_path: Path, make_symlink: Callable[[Path, Path], None]
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps([_pull(1)]), encoding="utf-8")
    pulls = tmp_path / "pulls"
    pulls.mkdir()
    make_symlink(pulls / "alpha.json", outside)

    listed = LocalRoadmapSource(tmp_path, pulls).pull_requests("alpha")

    assert (listed.status, listed.error) == (
        "unavailable",
        "outside the pull-request lists directory",
    )


def test_local_source_lists_the_files_of_a_directory(tmp_path: Path) -> None:
    workflows = tmp_path / "alpha" / ".github" / "workflows"
    (workflows / "nested").mkdir(parents=True)
    (workflows / "b.yml").write_text("on: push\n", encoding="utf-8")
    (workflows / "a.yaml").write_text("on: push\n", encoding="utf-8")
    source = LocalRoadmapSource(tmp_path)

    listed = source.list_directory("alpha", ".github/workflows")
    missing = source.list_directory("alpha", "docs")
    escaping = source.list_directory("alpha", "../..")
    bad_name = source.list_directory("..", ".github")

    assert (listed.status, listed.label, listed.names) == (
        "read",
        "alpha/.github/workflows",
        ("a.yaml", "b.yml"),
    )
    assert missing.status == "missing"
    assert (escaping.status, escaping.error) == ("unavailable", "outside the checkouts directory")
    assert bad_name.error == "not a repository name"


def test_github_source_lists_a_directory_through_the_contents_api() -> None:
    listing = [
        {"name": "ci.yml", "type": "file"},
        {"name": "nested", "type": "dir"},
        {"name": "a.yml", "type": "file"},
        "junk",
    ]
    fake = FakeGitHub(
        {
            f"{API}/alpha/contents/.github/workflows": (200, json.dumps(listing).encode()),
            f"{API}/beta/contents/.github/workflows": (200, b'{"type": "file"}'),
            f"{API}/gamma/contents/.github/workflows": (500, b""),
            f"{API}/delta/contents/.github/workflows": (200, b"not json"),
        }
    )
    source = GitHubRoadmapSource("acme", http_get=fake)

    listed = source.list_directory("alpha", ".github/workflows")

    assert (listed.status, listed.names) == ("read", ("a.yml", "ci.yml"))
    assert fake.requests[0][1]["Accept"] == "application/vnd.github+json"
    assert source.list_directory("beta", ".github/workflows").error == "not a directory"
    assert source.list_directory("gamma", ".github/workflows").status == "unavailable"
    assert source.list_directory("delta", ".github/workflows").status == "unavailable"
    assert source.list_directory("epsilon", ".github/workflows").status == "missing"
    assert source.list_directory("..", ".github").error == "not a repository name"
