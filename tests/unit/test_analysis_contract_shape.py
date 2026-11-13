import json
from collections.abc import Callable
from pathlib import Path

import pytest

from system_intelligence.analysis.contract_shape import (
    BaselineError,
    ContractShapeReport,
    attribute_contract,
    check_contract_shape,
    format_shape_table,
    parse_baseline,
)
from system_intelligence.discovery.contracts import (
    ContractObservation,
    read_saved_contract_directory,
)
from system_intelligence.discovery.roadmaps import ecosystem_repositories
from system_intelligence.integrations.ai_video_os import (
    COMPONENT_NAME_SUFFIXES,
    INACTIVE_COMPONENT_STATUSES,
    load_capability_contract_schema,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_shape"


def _report(
    baseline: bool = False, directory: Path = _FIXTURE / "contracts"
) -> ContractShapeReport:
    document = json.loads((_FIXTURE / "ecosystem.json").read_text(encoding="utf-8"))
    repositories, problems = ecosystem_repositories(document)
    known = (
        parse_baseline(json.loads((_FIXTURE / "baseline.json").read_text(encoding="utf-8")))
        if baseline
        else None
    )
    return check_contract_shape(
        repositories,
        read_saved_contract_directory(directory),
        load_capability_contract_schema(),
        schema_source="the OS schema",
        schema_sha256="0" * 64,
        bundled_copy="this schema",
        suffixes=COMPONENT_NAME_SUFFIXES,
        baseline=known,
        inactive_statuses=INACTIVE_COMPONENT_STATUSES,
        problems=problems,
    )


def _results(report: ContractShapeReport) -> dict[str, str]:
    return {row.repo: row.result for row in report.components}


def test_every_component_gets_a_result_and_a_break_fails() -> None:
    report = _report()

    assert _results(report) == {
        "alpha-skill": "ok",
        "beta-skill": "breaks",
        "delta-skill": "no_contract",
        "epsilon-skill": "unreadable",
        "gamma-skill": "not_created",
    }
    assert report.passed is False
    assert report.summary == {
        "ok": 1,
        "breaks": 1,
        "known": 0,
        "unreadable": 1,
        "no_contract": 1,
        "not_created": 1,
        "unattributed": 1,
    }


def test_violations_carry_the_json_pointer_and_the_file() -> None:
    beta = next(check for check in _report().contracts if check.repo == "beta-skill")

    assert beta.source == "pins/beta/contract_1.0.0.json"
    assert beta.attributed_by == "identity"
    assert [(item.pointer, item.message) for item in beta.violations] == [
        ("/skill", "expected object, got string"),
        ("/dependencies/0", "missing required property 'skill_id'"),
    ]


def test_contracts_are_attributed_by_file_name_then_identity() -> None:
    by_source = {check.source: check for check in _report().contracts}

    assert by_source["alpha-skill.json"].attributed_by == "file name"
    assert by_source["epsilon-skill.json"].attributed_by == "file name"
    stray = by_source["stray/contract.json"]
    assert (stray.repo, stray.result) == (None, "ok")
    assert stray.note == "its identities (omega) name no component"


def test_an_unattributed_contract_that_breaks_still_fails(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text('{"provides": "none"}', encoding="utf-8")

    report = _report(directory=tmp_path)

    assert report.passed is False
    assert report.contracts[0].repo is None
    assert report.contracts[0].result == "breaks"


def test_the_baseline_accepts_known_violations_and_reports_stale_entries() -> None:
    report = _report(baseline=True)

    assert _results(report)["beta-skill"] == "known"
    beta = next(check for check in report.contracts if check.repo == "beta-skill")
    assert all(item.known for item in beta.violations)
    assert [(entry.repo, entry.pointer) for entry in report.stale_baseline] == [
        ("alpha-skill", "/provides")
    ]
    # epsilon-skill's file is still not JSON: the baseline never accepts that.
    assert report.passed is False


def test_a_clean_ecosystem_passes(tmp_path: Path) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "alpha-skill.json").write_bytes(
        (_FIXTURE / "contracts" / "alpha-skill.json").read_bytes()
    )

    report = _report(directory=contracts)

    assert report.passed is True
    assert _results(report)["beta-skill"] == "no_contract"


def test_report_is_deterministic() -> None:
    assert _report().to_json() == _report().to_json()


def test_table_lists_every_component_and_each_problem() -> None:
    table = format_shape_table(_report(baseline=True))

    assert table.startswith("Contract shape FAILED: 3 of 5 components have a saved contract")
    assert "| beta-skill | known | pins/beta/contract_1.0.0.json |" in table
    assert "| delta-skill | no_contract | - |" in table
    assert (
        "- beta-skill pins/beta/contract_1.0.0.json /dependencies/0: missing required property "
        "'skill_id' (known: dependencies name the skill under 'id'; fix tracked upstream)"
    ) in table
    assert "- epsilon-skill epsilon-skill.json: unreadable: not valid JSON" in table
    assert "- stray/contract.json: unattributed (its identities (omega) name no component)" in table
    assert "- baseline entry alpha-skill /provides matched nothing (stale)" in table


def _observation(document: object, label: str = "c.json") -> ContractObservation:
    from system_intelligence.core.enums import Confidence
    from system_intelligence.core.evidence import Evidence, EvidenceKind

    evidence = Evidence(
        kind=EvidenceKind.FILE, source=label, observation="read", confidence=Confidence.VERIFIED
    )
    return ContractObservation("file", label, evidence, document=document)


@pytest.mark.parametrize(
    ("document", "names", "repo", "note"),
    [
        ({"skill_id": "qc"}, ["qc-skill"], "qc-skill", None),
        ({"skill": {"package": "ingest-skill"}}, ["ingest-skill"], "ingest-skill", None),
        # An exact name wins over the suffixed one.
        ({"id": "stepcap"}, ["stepcap", "stepcap-skill"], "stepcap", None),
        ({"skill_id": "q"}, ["qc-skill"], None, "its identities (q) name no component"),
        ({"version": "1"}, ["qc-skill"], None, "the contract gives no identity"),
        (
            {"skill_id": "a", "id": "b"},
            ["a-skill", "b-skill"],
            None,
            "its identities (a, b) name several: a-skill, b-skill",
        ),
    ],
)
def test_attribution_by_identity(
    document: object, names: list[str], repo: str | None, note: str | None
) -> None:
    attribution = attribute_contract(
        _observation(document), {name.casefold(): name for name in names}, ("-skill",)
    )

    assert (attribution.repo, attribution.note) == (repo, note)


def test_saved_directory_is_read_in_path_order_with_relative_labels() -> None:
    labels = [item.label for item in read_saved_contract_directory(_FIXTURE / "contracts")]

    assert labels == [
        "alpha-skill.json",
        "epsilon-skill.json",
        "pins/beta/contract_1.0.0.json",
        "stray/contract.json",
    ]


def test_saved_directory_does_not_follow_links_out(
    tmp_path: Path, make_symlink: Callable[[Path, Path], None]
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"skill_id": "x"}', encoding="utf-8")
    directory = tmp_path / "contracts"
    directory.mkdir()
    make_symlink(directory / "link.json", outside)

    [observation] = read_saved_contract_directory(directory)

    assert observation.label == "link.json"
    assert observation.error is not None and "outside the contracts directory" in observation.error


@pytest.mark.parametrize(
    "document",
    [
        {"known_violations": [{"repo": "a", "pointer": "/x"}]},
        {"known_violations": [{"repo": "a", "pointer": "/x", "reason": "r", "extra": 1}]},
        {"other": []},
        [],
    ],
)
def test_baseline_shape_is_checked(document: object) -> None:
    with pytest.raises(BaselineError):
        parse_baseline(document)


def test_a_directory_that_cannot_be_listed_fails_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    contracts = tmp_path / "contracts"
    (contracts / "locked").mkdir(parents=True)
    real_walk = os.walk

    def walk(top, onerror=None, followlinks=False):  # type: ignore[no-untyped-def]
        for entry in real_walk(top, onerror=onerror, followlinks=followlinks):
            if entry[0] == str(contracts):
                entry[1].remove("locked")
                assert onerror is not None
                onerror(PermissionError(13, "Permission denied", str(contracts / "locked")))
            yield entry

    monkeypatch.setattr(os, "walk", walk)

    report = _report(directory=contracts)

    assert report.passed is False
    [check] = report.contracts
    assert (check.source, check.result) == ("locked", "unreadable")
    assert check.error is not None and check.error.startswith("could not be listed")
