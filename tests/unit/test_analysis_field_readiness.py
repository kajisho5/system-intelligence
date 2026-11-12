import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from system_intelligence.analysis.field_readiness import (
    ContractDocument,
    FieldReadinessReport,
    ReadinessColumn,
    audit_field_readiness,
    ci_lines,
    format_readiness_table,
)
from system_intelligence.discovery.roadmaps import (
    EcosystemRepository,
    GitHubRoadmapSource,
    LocalRoadmapSource,
    ecosystem_repositories,
)
from system_intelligence.integrations.ai_video_os import FIELD_READINESS_COLUMNS

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "field_readiness"
COLUMN_IDS = [column.id for column in FIELD_READINESS_COLUMNS]


def _repositories() -> list[EcosystemRepository]:
    document = json.loads((FIXTURE / "ecosystem.json").read_text(encoding="utf-8"))
    repositories, problems = ecosystem_repositories(document)
    assert problems == []
    return repositories


def _contracts() -> dict[str, ContractDocument]:
    contracts: dict[str, ContractDocument] = {}
    for path in sorted((FIXTURE / "contracts").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        try:
            contracts[path.stem] = ContractDocument("read", path.name, json.loads(text))
        except json.JSONDecodeError as exc:
            contracts[path.stem] = ContractDocument("unavailable", path.name, error=str(exc))
    return contracts


def _audit(source: LocalRoadmapSource | GitHubRoadmapSource) -> FieldReadinessReport:
    return audit_field_readiness(
        _repositories(),
        source,
        FIELD_READINESS_COLUMNS,
        _contracts(),
        inactive_statuses=("planned",),
    )


def _report() -> FieldReadinessReport:
    return _audit(LocalRoadmapSource(FIXTURE / "checkouts"))


def _values(report: FieldReadinessReport, repo: str) -> dict[str, str]:
    row = next(row for row in report.skills if row.repo == repo)
    return {column: cell.value for column, cell in row.cells.items()}


def test_every_skill_of_the_ecosystem_gets_every_column() -> None:
    report = _report()

    assert [row.repo for row in report.skills] == [
        "alpha-skill",
        "beta-skill",
        "delta-skill",
        "epsilon-skill",
        "gamma-skill",
    ]
    for row in report.skills:
        assert list(row.cells) == COLUMN_IDS
        assert {cell.value for cell in row.cells.values()} <= {"yes", "no", "unknown"}
    assert [column.label for column in report.columns] == [
        "Resume after a stop",
        "Progress events",
        "Error classes",
        "Long-file tests",
        "Hardware encoder use",
        "Alpha output",
        "Loudness output",
    ]


def test_contract_and_ci_statements_fill_the_cells() -> None:
    assert _values(_report(), "alpha-skill") == {
        "resume": "yes",
        "progress_events": "yes",
        "error_classes": "yes",
        "long_file_tests": "yes",
        "hardware_encoder": "no",
        "alpha_output": "unknown",
        "loudness_output": "yes",
    }


def test_each_cell_cites_its_file_and_key() -> None:
    row = _report().skills[0]

    [progress] = row.cells["progress_events"].evidence
    assert (progress.source, progress.key, progress.line, progress.says) == (
        "alpha-skill.json",
        "/progress",
        None,
        "yes",
    )
    [hardware] = row.cells["hardware_encoder"].evidence
    assert (hardware.key, hardware.matched_text, hardware.says) == ("/hardware", "false", "no")
    [long_file] = row.cells["long_file_tests"].evidence
    assert (long_file.source, long_file.key, long_file.line, long_file.matched_text) == (
        "alpha-skill/.github/workflows/ci.yml",
        "run",
        19,
        "python -m pytest -k LongFormTests",
    )
    [loudness] = row.cells["loudness_output"].evidence
    assert (loudness.key, loudness.line) == ("jobs.loudness", 20)
    assert [(e.key, e.line) for e in row.cells["resume"].evidence] == [("name", 16), ("run", 18)]
    assert row.contract_source == "alpha-skill.json"
    assert row.ci_files == ["alpha-skill/.github/workflows/ci.yml"]


def test_what_is_not_stated_is_unknown_never_no() -> None:
    """alpha-skill: `alpha: null`, a colour parameter's alpha, `colors/alpha` and a CI
    comment state nothing about alpha output; epsilon-skill's CI only says
    `--no-progress`, `cancel-in-progress`, 'Long titles' and an ALPHA env value."""
    report = _report()

    assert _values(report, "alpha-skill")["alpha_output"] == "unknown"
    assert set(_values(report, "epsilon-skill").values()) == {"unknown"}
    assert _report().skills[0].cells["alpha_output"].evidence == []


def test_sources_that_disagree_give_unknown_with_both_statements() -> None:
    row = next(row for row in _report().skills if row.repo == "beta-skill")

    resume = row.cells["resume"]
    assert resume.value == "unknown"
    assert resume.note == "the sources say both yes and no"
    assert [(e.key, e.says) for e in resume.evidence] == [
        ("/resume", "no"),
        ("/long_inputs/resume", "yes"),
    ]
    assert row.cells["alpha_output"].value == "yes"
    assert row.ci == "missing"


def test_missing_unreadable_and_planned_skills_are_all_unknown() -> None:
    report = _report()
    rows = {row.repo: row for row in report.skills}

    assert (rows["delta-skill"].contract, rows["delta-skill"].ci) == ("missing", "missing")
    assert rows["epsilon-skill"].contract == "unavailable"
    assert rows["epsilon-skill"].notes[0].startswith("contract epsilon-skill.json: Expecting")
    assert (rows["gamma-skill"].contract, rows["gamma-skill"].ci) == ("not_created", "not_created")
    for name in ("delta-skill", "epsilon-skill", "gamma-skill"):
        assert set(_values(report, name).values()) == {"unknown"}


def test_summary_counts_each_value_per_column() -> None:
    summary = _report().summary

    assert summary["hardware_encoder"] == {"yes": 0, "no": 1, "unknown": 4}
    assert summary["alpha_output"] == {"yes": 1, "no": 0, "unknown": 4}
    assert all(sum(counts.values()) == 5 for counts in summary.values())


def test_report_is_deterministic() -> None:
    first = _report().to_json()

    assert first == _report().to_json()
    assert json.loads(first)["format"] == "system-intelligence/field-readiness@1"


def test_github_source_gives_the_same_rows_as_the_checkouts() -> None:
    def fake(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        parts = urlsplit(url).path.split("/")  # /repos/example/<repo>/contents/<path...>
        path = FIXTURE / "checkouts" / parts[3] / "/".join(parts[5:])
        if path.is_dir():
            listing = [
                {"name": entry.name, "type": "file" if entry.is_file() else "dir"}
                for entry in sorted(path.iterdir())
            ]
            return 200, json.dumps(listing).encode("utf-8")
        if path.is_file():
            return 200, path.read_bytes()
        return 404, b"{}"

    github = _audit(GitHubRoadmapSource("example", http_get=fake))

    assert github.source == "github"
    assert github.skills == _report().skills


def test_table_lists_every_skill_and_the_evidence() -> None:
    table = format_readiness_table(_report())
    lines = table.splitlines()

    assert lines[2].startswith("| Skill | Contract | CI | Resume after a stop | Progress events")
    assert "| alpha-skill | read | read | yes | yes | yes | yes | no | unknown | yes |" in lines
    assert sum(1 for line in lines if line.startswith("| ") and "-skill |" in line) == 5
    assert "- alpha-skill / Hardware encoder use: no — alpha-skill.json /hardware = false" in lines
    assert any(
        line.startswith("- beta-skill / Resume after a stop: unknown (the sources say both")
        for line in lines
    )
    assert "- gamma-skill: status planned: no repository yet" in lines


WORKFLOW = """name: CI
on:
  push:
    branches: [main]
env:
  NAME: not a step
jobs:
  build:
    name: Build and test
    runs-on: ubuntu-latest
    steps:
      - name: 'Quoted step'
        run: echo one
      - run: >-
          folded block
          second line
      # name: a comment
      - name: after the block
  second-job:
    steps:
      - run: |
          literal line
"""


def test_ci_lines_reads_job_ids_names_and_run_commands() -> None:
    lines = ci_lines("wf.yml", WORKFLOW)

    assert [(line.line, line.key, line.text) for line in lines] == [
        (8, "jobs.build", "build"),
        (9, "name", "Build and test"),
        (12, "name", "Quoted step"),
        (13, "run", "echo one"),
        (15, "run", "folded block"),
        (16, "run", "second line"),
        (18, "name", "after the block"),
        (19, "jobs.second-job", "second-job"),
        (22, "run", "literal line"),
    ]


@pytest.mark.parametrize(
    ("value", "says"),
    [
        (True, "yes"),
        (False, "no"),
        (None, None),
        (0, "no"),
        (2, "yes"),
        ("", "no"),
        ("None", "no"),
        ("--work-dir", "yes"),
        ([], "no"),
        ({"a": 1}, "yes"),
    ],
)
def test_contract_values(value: object, says: str | None) -> None:
    column = ReadinessColumn(id="c", label="C", description="", contract_keys=("flag",))
    report = audit_field_readiness(
        [EcosystemRepository("alpha", None)],
        LocalRoadmapSource(FIXTURE / "checkouts"),
        [column],
        {"alpha": ContractDocument("read", "alpha.json", {"flag": value})},
    )

    evidence = report.skills[0].cells["c"].evidence
    assert [item.says for item in evidence] == ([] if says is None else [says])


def test_exact_paths_and_top_level_keys_only() -> None:
    column = ReadinessColumn(
        id="c", label="C", description="", contract_keys=("alpha", "errors/classes")
    )
    document = {
        "Alpha": {"modes": ["straight"]},
        "errors": {"CLASSES": {"E": "input"}, "alpha": True},
        "colors": {"alpha": True},
    }
    report = audit_field_readiness(
        [EcosystemRepository("alpha", None)],
        LocalRoadmapSource(FIXTURE / "checkouts"),
        [column],
        {"alpha": ContractDocument("read", "alpha.json", document)},
    )

    assert [e.key for e in report.skills[0].cells["c"].evidence] == ["/Alpha", "/errors/classes"]


@pytest.mark.parametrize(
    ("column_id", "text", "matches"),
    [
        ("resume", "grep test_resume_after_an_interrupted_chunk", True),
        ("resume", "python -m unittest tests.ResumeTests", True),
        ("resume", "presumed fine", False),
        ("progress_events", "choco install ffmpeg -y --no-progress", False),
        ("progress_events", "NO_PROGRESS=1 python -m pytest", False),
        ("progress_events", "build with no progress bar", False),
        ("progress_events", "cancel-in-progress", False),
        ("progress_events", "ingest offload --progress", True),
        ("long_file_tests", "SegmentCacheLongFormTests", True),
        ("long_file_tests", "a 2-hour fixture", True),
        ("long_file_tests", "Long titles are cut", False),
        ("long_file_tests", "check the longformat output", False),
        ("hardware_encoder", "ffmpeg -c:v h264_videotoolbox", True),
        ("hardware_encoder", "proxy.py --hw", True),
        ("alpha_output", "render with alpha verified", True),
        ("alpha_output", "alphabet soup", False),
        ("loudness_output", "tests/test_loudness_measured.py", True),
        ("error_classes", "check error classes", True),
    ],
)
def test_os_ci_patterns(column_id: str, text: str, matches: bool) -> None:
    column = next(c for c in FIELD_READINESS_COLUMNS if c.id == column_id)
    assert column.ci_pattern is not None

    assert bool(re.search(column.ci_pattern, text, re.IGNORECASE)) is matches


CONTEXT_WORKFLOW = """name: context
on: push
env:
  NAME: top-level env is not read
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      name: an env value is not a step name
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: alpha
      - name: Unit tests
        run: |
          # TODO: add resume tests
          python -m pytest  # a trailing comment stays part of the command
      - uses: some/action@v1
        with:
          run: alpha resume
"""


def test_ci_lines_reads_step_keys_not_action_inputs_env_or_comments() -> None:
    lines = ci_lines("wf.yml", CONTEXT_WORKFLOW)

    assert [(line.line, line.key, line.text) for line in lines] == [
        (6, "jobs.build", "build"),
        (17, "name", "Unit tests"),
        (20, "run", "python -m pytest  # a trailing comment stays part of the command"),
    ]


def test_action_inputs_and_shell_comments_state_nothing(tmp_path: Path) -> None:
    workflows = tmp_path / "alpha" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(CONTEXT_WORKFLOW, encoding="utf-8")

    report = audit_field_readiness(
        [EcosystemRepository("alpha", None)],
        LocalRoadmapSource(tmp_path),
        FIELD_READINESS_COLUMNS,
        {},
    )

    assert set(_values(report, "alpha").values()) == {"unknown"}
