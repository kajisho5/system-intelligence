import json
import random
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from system_intelligence.analysis.roadmap_drift import (
    DriftReport,
    check_roadmap_drift,
    format_drift_table,
)
from system_intelligence.discovery.roadmaps import (
    EcosystemRepository,
    GitHubRoadmapSource,
    LocalRoadmapSource,
    ecosystem_repositories,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "roadmap_drift"
SHIPPED = ("SKILL.md", "skills/{repo}/SKILL.md", "CHANGELOG.md")
ROADMAP = "ECOSYSTEM_ROADMAP.md"


def _fixture_repositories() -> list[EcosystemRepository]:
    document = json.loads((FIXTURE / "ecosystem.json").read_text(encoding="utf-8"))
    repositories, problems = ecosystem_repositories(document)
    assert problems == []
    return repositories


def _check(source: LocalRoadmapSource | GitHubRoadmapSource) -> DriftReport:
    return check_roadmap_drift(
        _fixture_repositories(),
        source,
        roadmap_file=ROADMAP,
        shipped_documents=SHIPPED,
        inactive_statuses=("planned",),
    )


def _fixture_report() -> DriftReport:
    return _check(LocalRoadmapSource(FIXTURE / "checkouts", FIXTURE / "pulls", owner="example"))


def test_fixture_roadmap_with_each_kind_of_drift_gives_three_findings() -> None:
    report = _fixture_report()

    assert [(f.check, f.kind, f.repo, f.step, f.certainty) for f in report.findings] == [
        ("a", "ticked_without_pr_link", "alpha-skill", 2, "certain"),
        ("b", "unticked_pr_merged", "alpha-skill", 3, "certain"),
        ("c", "unknown_step_reference", "alpha-skill", 3, "certain"),
    ]
    assert report.summary == {
        "repositories": 3,
        "roadmaps_read": 2,
        "findings": 3,
        "a": 1,
        "b": 1,
        "b_candidate": 0,
        "c": 1,
    }


def test_ticked_without_link_cites_the_step_line_and_the_pull_request_naming_it() -> None:
    finding = _fixture_report().findings[0]

    step_line, hint = finding.evidence
    assert (step_line.relation, step_line.source, step_line.line, step_line.matched_text) == (
        "roadmap_line",
        "alpha-skill/ECOSYSTEM_ROADMAP.md",
        9,
        "- [x] **2. Batch mode**",
    )
    assert (hint.relation, hint.pr_number, hint.pr_url, hint.matched_text) == (
        "pull_request_title",
        2,
        "https://github.com/example/alpha-skill/pull/2",
        "roadmap step 2",
    )
    assert "#2" in finding.statement
    assert finding.step_title == "Batch mode"


def test_unticked_merged_cites_the_pull_request() -> None:
    finding = _fixture_report().findings[1]

    [_, pull] = finding.evidence
    assert (pull.pr_repo, pull.pr_number, pull.merged_at, pull.context) == (
        "alpha-skill",
        3,
        "2026-10-03T09:00:00Z",
        "Progress events (roadmap step 3)",
    )
    assert "merged 2026-10-03" in finding.statement


def test_unknown_step_reference_names_the_step_and_what_exists() -> None:
    finding = _fixture_report().findings[2]

    assert (finding.referenced_repo, finding.referenced_step) == ("beta-skill", 9)
    [reference] = finding.evidence
    assert (reference.relation, reference.line, reference.matched_text) == (
        "step_reference",
        11,
        "beta-skill step 9",
    )
    assert "beta-skill's ECOSYSTEM_ROADMAP.md has steps 1-2" in finding.statement


def test_docs_and_unmerged_pull_requests_do_not_count() -> None:
    """alpha-skill step 4: PR #4 is docs(roadmap), PR #5 never merged."""
    assert all(f.step != 4 for f in _fixture_report().findings)


def test_report_is_deterministic_whatever_order_the_pull_requests_come_in(
    tmp_path: Path,
) -> None:
    pulls = tmp_path / "pulls"
    shutil.copytree(FIXTURE / "pulls", pulls)
    listed = json.loads((pulls / "alpha-skill.json").read_text(encoding="utf-8"))
    random.Random(7).shuffle(listed)
    (pulls / "alpha-skill.json").write_text(json.dumps(listed), encoding="utf-8")

    first = _fixture_report().to_json()
    again = _fixture_report().to_json()
    shuffled = _check(LocalRoadmapSource(FIXTURE / "checkouts", pulls, owner="example")).to_json()

    assert first == again == shuffled
    assert json.loads(first)["format"] == "system-intelligence/roadmap-drift@1"


def test_github_source_gives_the_same_findings_as_the_checkouts() -> None:
    def fake(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        path = urlsplit(url).path.split("/")  # /repos/example/<repo>/...
        repo = path[3]
        if path[4] == "contents":
            file = FIXTURE / "checkouts" / repo / "/".join(path[5:])
            return (200, file.read_bytes()) if file.is_file() else (404, b"{}")
        pulls = FIXTURE / "pulls" / f"{repo}.json"
        return (200, pulls.read_bytes()) if pulls.is_file() else (404, b"{}")

    github = _check(GitHubRoadmapSource("example", http_get=fake))
    local = _fixture_report()

    assert github.source == "github"
    assert github.findings == local.findings


def _repo(root: Path, name: str, roadmap: str, files: dict[str, str] | None = None) -> None:
    directory = root / "checkouts" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ROADMAP).write_text(roadmap, encoding="utf-8")
    for relative, text in (files or {}).items():
        (directory / relative).parent.mkdir(parents=True, exist_ok=True)
        (directory / relative).write_text(text, encoding="utf-8")


def _pulls(root: Path, name: str, pulls: list[tuple[int, str, str | None]]) -> None:
    (root / "pulls").mkdir(exist_ok=True)
    (root / "pulls" / f"{name}.json").write_text(
        json.dumps(
            [
                {
                    "number": number,
                    "title": title,
                    "html_url": f"https://github.com/acme/{name}/pull/{number}",
                    "merged_at": merged_at,
                }
                for number, title, merged_at in pulls
            ]
        ),
        encoding="utf-8",
    )


def _run(root: Path, names: list[str], statuses: dict[str, str] | None = None) -> DriftReport:
    statuses = statuses or {}
    return check_roadmap_drift(
        [EcosystemRepository(name, statuses.get(name, "active")) for name in names],
        LocalRoadmapSource(root / "checkouts", root / "pulls", owner="acme"),
        roadmap_file=ROADMAP,
        shipped_documents=SHIPPED,
        inactive_statuses=("planned",),
    )


MERGED = "2026-11-01T00:00:00Z"


def test_a_step_linking_a_merged_pull_request_of_another_repository_is_drift(
    tmp_path: Path,
) -> None:
    _repo(
        tmp_path,
        "alpha",
        "- [ ] **1. Agent adapter** — ([beta#7](https://github.com/acme/beta/pull/7))\n",
    )
    _repo(tmp_path, "beta", "- [x] **1. X** ([#7](https://github.com/acme/beta/pull/7))\n")
    _pulls(tmp_path, "alpha", [])
    _pulls(tmp_path, "beta", [(7, "Adapter for alpha", MERGED)])

    [finding] = _run(tmp_path, ["alpha", "beta"]).findings

    assert (finding.kind, finding.repo, finding.step) == ("unticked_pr_merged", "alpha", 1)
    linked = finding.evidence[1]
    assert (linked.relation, linked.pr_repo, linked.pr_number, linked.line) == (
        "linked_pull_request",
        "beta",
        7,
        1,
    )
    assert "beta#7 (linked from the step" in finding.statement


def test_a_link_outside_the_ecosystem_is_noted_not_looked_up(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "alpha",
        "- [ ] **1. A** ([os#127](https://github.com/acme/os-repo/pull/127))\n"
        "- [ ] **2. B** ([x#1](https://github.com/other/alpha/pull/1))\n",
    )
    _pulls(tmp_path, "alpha", [(1, "B", MERGED)])

    report = _run(tmp_path, ["alpha"])

    assert report.findings == []
    assert report.repositories[0].notes == [
        "step 1 links acme/os-repo#127, outside the ecosystem; not looked up",
        "step 2 links other/alpha#1, outside the ecosystem; not looked up",
    ]


def test_a_step_that_says_it_is_still_open_is_not_drift(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "alpha",
        "- [ ] **1. Loops** — loopable beds\n"
        "  - Skill side ([#3](https://github.com/acme/alpha/pull/3)): done\n"
        "- [ ] **2. Partial** — a step\n"
        "  - Partly done (ADR-3), left unchecked\n",
    )
    _pulls(
        tmp_path, "alpha", [(3, "Loops (roadmap step 1)", MERGED), (4, "roadmap step 2", MERGED)]
    )

    report = _run(tmp_path, ["alpha"])

    assert report.findings == []
    assert report.repositories[0].notes == [
        "step 1 is unticked and says it is still open ('Skill side', line 2); "
        "#3 not counted as drift",
        "step 2 is unticked and says it is still open ('Partly done', line 4); "
        "#4 not counted as drift",
    ]


def test_another_repositorys_step_in_a_pull_request_title_is_not_this_one(
    tmp_path: Path,
) -> None:
    _repo(tmp_path, "alpha", "- [ ] **3. Own step**\n")
    _repo(tmp_path, "beta", "- [x] **3. X** ([#1](https://github.com/acme/beta/pull/1))\n")
    _pulls(tmp_path, "alpha", [(9, "beta roadmap step 3 (alpha side)", MERGED)])
    _pulls(tmp_path, "beta", [])

    assert _run(tmp_path, ["alpha", "beta"]).findings == []


@pytest.mark.parametrize(
    ("title", "steps"),
    [
        ("Skeleton and ops (roadmap steps 2-4)", {2, 3, 4}),
        ("Translation and mux (roadmap steps 5 and 6)", {5, 6}),
        ("Wire elements (roadmap step 6 parts 3-4)", {6}),
        ("Runtime declarations (ECOSYSTEM_ROADMAP.md step 5)", {5}),
        ("Roadmap step 4: agent side landed", {4}),
    ],
)
def test_step_numbers_in_pull_request_titles(tmp_path: Path, title: str, steps: set[int]) -> None:
    _repo(tmp_path, "alpha", "".join(f"- [x] **{n}. Step {n}**\n" for n in range(1, 8)))
    _pulls(tmp_path, "alpha", [(1, title, MERGED)])

    report = _run(tmp_path, ["alpha"])

    hinted = {f.step for f in report.findings if len(f.evidence) > 1}
    assert hinted == steps


def test_names_a_planned_or_roadmapless_repository_step(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "alpha",
        "- [ ] **1. A** — needs gamma step 1, delta's step 2 and beta roadmap step 1\n",
    )
    _repo(tmp_path, "beta", "- [x] **1. B** ([#1](https://github.com/acme/beta/pull/1))\n")
    (tmp_path / "checkouts" / "delta").mkdir()
    _pulls(tmp_path, "alpha", [])

    report = _run(tmp_path, ["alpha", "beta", "gamma", "delta"], {"gamma": "planned"})

    assert [(f.referenced_repo, f.referenced_step, f.statement) for f in report.findings] == [
        (
            "delta",
            2,
            "Step 1 (A) names delta step 2, which does not exist: delta has no "
            "ECOSYSTEM_ROADMAP.md.",
        ),
        (
            "gamma",
            1,
            "Step 1 (A) names gamma step 1, which does not exist: gamma is planned "
            "and has no repository yet.",
        ),
    ]


def test_a_reference_to_an_unreadable_roadmap_is_noted_not_reported(tmp_path: Path) -> None:
    _repo(tmp_path, "alpha", "- [ ] **1. A** — needs beta steps 1-2\n")
    (tmp_path / "checkouts" / "beta").mkdir()
    (tmp_path / "checkouts" / "beta" / ROADMAP).write_bytes(b"\xff not utf-8")
    _pulls(tmp_path, "alpha", [])

    report = _run(tmp_path, ["alpha", "beta"])

    assert report.findings == []
    alpha, beta = report.repositories
    assert alpha.notes == [
        "step 1 names beta step 1; beta's roadmap could not be read",
        "step 1 names beta step 2; beta's roadmap could not be read",
    ]
    assert beta.roadmap == "unavailable"


def test_without_pull_requests_ticked_steps_are_still_checked(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "alpha",
        "- [x] **1. A**\n- [ ] **2. B** ([#2](https://github.com/acme/alpha/pull/2))\n",
    )

    report = check_roadmap_drift(
        [EcosystemRepository("alpha", None)],
        LocalRoadmapSource(tmp_path / "checkouts"),
        roadmap_file=ROADMAP,
    )

    assert [(f.check, f.step, len(f.evidence)) for f in report.findings] == [("a", 1, 1)]
    [row] = report.repositories
    assert row.pull_requests == "unavailable"
    assert any("merged-pull-request checks were skipped" in note for note in row.notes)


def test_shipped_documents_give_a_candidate_never_a_certain_finding(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "alpha",
        "- [x] **1. Base** — `alpha base` ([#1](https://github.com/acme/alpha/pull/1))\n"
        "- [ ] **2. Resume** — `alpha run --resume` and `alpha base`\n"
        "- [ ] **3. Vocabulary** — a term list\n"
        "- [ ] **4. Docs only** — written by a docs entry\n",
        {
            "CHANGELOG.md": "- Vocabulary from the programme (roadmap step 3)\n"
            "- docs(roadmap): step 4 (docs only) and review\n",
            "skills/alpha/SKILL.md": "Use `alpha run --resume` after a stop. `alpha base` too.\n",
        },
    )
    _pulls(tmp_path, "alpha", [])

    report = _run(tmp_path, ["alpha"])

    assert [(f.kind, f.step, f.certainty) for f in report.findings] == [
        ("unticked_documented_as_shipped", 2, "candidate"),
        ("unticked_documented_as_shipped", 3, "candidate"),
    ]
    resume, vocabulary = report.findings
    assert [(e.source, e.line, e.matched_text) for e in resume.evidence[1:]] == [
        ("alpha/skills/alpha/SKILL.md", 1, "alpha run --resume"),
    ]
    assert [(e.source, e.line, e.matched_text) for e in vocabulary.evidence[1:]] == [
        ("alpha/CHANGELOG.md", 1, "roadmap step 3"),
    ]
    assert "Candidate only" in resume.statement
    assert report.summary["b_candidate"] == 2
    assert report.summary["b"] == 0


def test_duplicate_step_numbers_are_noted(tmp_path: Path) -> None:
    _repo(tmp_path, "alpha", "- [ ] **1. A**\n- [ ] **1. Again**\n")
    _pulls(tmp_path, "alpha", [])

    [row] = _run(tmp_path, ["alpha"]).repositories

    assert row.notes == ["step 1 appears more than once (lines 1 and 2)"]


def test_table_has_one_row_per_finding_and_the_notes() -> None:
    table = format_drift_table(_fixture_report())

    lines = table.splitlines()
    assert lines[0] == (
        "Roadmap drift (local, ECOSYSTEM_ROADMAP.md): 2 of 3 roadmaps read, 3 findings "
        "(a: 1, b: 1, b candidates: 0, c: 1)"
    )
    assert lines[2] == "| Check | Repository | Step | Certainty | Finding | Evidence |"
    rows = [line for line in lines if line.startswith("| ") and "alpha-skill" in line]
    assert len(rows) == 3
    assert rows[0].startswith("| a | alpha-skill | 2 | certain | ticked, no PR link — Batch mode")
    assert "#2 https://github.com/example/alpha-skill/pull/2 (title: 'roadmap step 2')" in rows[0]
    assert "alpha-skill/ECOSYSTEM_ROADMAP.md:11 ('beta-skill step 9')" in rows[2]
    assert "- gamma-skill: status planned, not read" in lines


def test_table_without_findings(tmp_path: Path) -> None:
    _repo(tmp_path, "alpha", "- [x] **1. A** ([#1](https://github.com/acme/alpha/pull/1))\n")
    _pulls(tmp_path, "alpha", [])

    assert "No drift found." in format_drift_table(_run(tmp_path, ["alpha"]))


def test_table_cells_escape_pipes(tmp_path: Path) -> None:
    _repo(tmp_path, "alpha", "- [x] **1. A | B**\n")
    _pulls(tmp_path, "alpha", [])

    table = format_drift_table(_run(tmp_path, ["alpha"]))

    assert "A \\| B" in table


@pytest.mark.parametrize(
    "line",
    [
        "  - Done when: only the partial segments are re-rendered",
        "  - Progress events are JSON lines",
        "  - Status: done",
    ],
)
def test_ordinary_words_under_a_step_do_not_mark_it_open(tmp_path: Path, line: str) -> None:
    _repo(tmp_path, "alpha", f"- [ ] **1. Partial re-render**\n{line}\n")
    _pulls(tmp_path, "alpha", [(2, "Partial re-render (roadmap step 1)", MERGED)])

    [finding] = _run(tmp_path, ["alpha"]).findings

    assert finding.kind == "unticked_pr_merged"


@pytest.mark.parametrize(
    ("line", "marker"),
    [
        ("  - Status: partial ([#2](https://github.com/acme/alpha/pull/2))", "Status: partial"),
        ("  - Progress ([#2](https://github.com/acme/alpha/pull/2), not ticked)", "Progress"),
        ("  - Open: no real engine output measured yet", "Open"),
        ("  - [x] Building block: word-index plans", "Building block"),
    ],
)
def test_open_markers(tmp_path: Path, line: str, marker: str) -> None:
    _repo(tmp_path, "alpha", f"- [ ] **1. Step**\n{line}\n")
    _pulls(tmp_path, "alpha", [(2, "Step (roadmap step 1)", MERGED)])

    report = _run(tmp_path, ["alpha"])

    assert report.findings == []
    assert f"({marker!r}, line 2)" in report.repositories[0].notes[0]


def test_a_pull_request_linked_twice_is_one_piece_of_evidence(tmp_path: Path) -> None:
    link = "[#2](https://github.com/acme/alpha/pull/2)"
    _repo(tmp_path, "alpha", f"- [ ] **1. A** — {link}\n  - again {link}\n")
    _pulls(tmp_path, "alpha", [(2, "A", MERGED)])

    [finding] = _run(tmp_path, ["alpha"]).findings

    assert [e.relation for e in finding.evidence] == ["roadmap_line", "linked_pull_request"]


def test_a_linked_number_whose_saved_pull_request_is_another_is_not_used(
    tmp_path: Path,
) -> None:
    _repo(tmp_path, "alpha", "- [ ] **1. A** — ([#7](https://github.com/other/alpha/pull/7))\n")
    _pulls(tmp_path, "alpha", [(7, "Something else", MERGED)])

    report = check_roadmap_drift(
        [EcosystemRepository("alpha", None)],
        LocalRoadmapSource(tmp_path / "checkouts", tmp_path / "pulls"),
        roadmap_file=ROADMAP,
    )

    assert report.findings == []
    assert report.repositories[0].notes == [
        "step 1 links https://github.com/other/alpha/pull/7, but the saved #7 of alpha is "
        "https://github.com/acme/alpha/pull/7; not used"
    ]
