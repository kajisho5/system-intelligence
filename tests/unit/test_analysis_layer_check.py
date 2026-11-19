import json
from pathlib import Path
from typing import Any

import pytest

from system_intelligence.analysis.layer_check import (
    LayerCheckReport,
    LayeringError,
    check_layers,
    component_layers,
    dependency_name,
    format_layer_table,
    parse_layering,
)
from system_intelligence.discovery.contracts import read_saved_contract_directory
from system_intelligence.discovery.roadmaps import ecosystem_repositories
from system_intelligence.integrations.ai_video_os import COMPONENT_NAME_SUFFIXES

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "layer_check"


def _load(name: str) -> Any:
    return json.loads((_FIXTURE / name).read_text(encoding="utf-8"))


def _report(layering: dict[str, Any] | None = None, report_only: bool = False) -> LayerCheckReport:
    document = _load("ecosystem.json")
    repositories, problems = ecosystem_repositories(document)
    return check_layers(
        repositories,
        component_layers(document),
        read_saved_contract_directory(_FIXTURE / "contracts"),
        parse_layering(layering if layering is not None else _load("layering.json")),
        suffixes=COMPONENT_NAME_SUFFIXES,
        report_only=report_only,
        problems=problems,
    )


def _calls(report: LayerCheckReport) -> dict[tuple[str, str], str]:
    return {(call.caller, call.callee): call.result for call in report.calls}


def test_each_declared_call_gets_a_direction_and_a_result() -> None:
    report = _report()

    assert _calls(report) == {
        ("alpha-skill", "beta-skill"): "excepted",
        ("alpha-skill", "engine"): "ok",
        ("beta-skill", "conductor"): "violation",
        ("beta-skill", "gamma-skill"): "violation",
        ("delta-skill", "engine"): "unclassified",
    }
    directions = {(call.caller, call.callee): call.direction for call in report.calls}
    assert directions[("beta-skill", "conductor")] == "up"
    assert directions[("beta-skill", "gamma-skill")] == "same"
    assert not report.passed


def test_the_evidence_is_the_file_and_the_dependency_entry() -> None:
    report = _report()

    up = next(call for call in report.calls if call.callee == "conductor")
    assert (up.source, up.pointer) == ("pins/beta/contract_1.0.0.json", "/dependencies/1")
    excepted = next(call for call in report.calls if call.result == "excepted")
    assert excepted.reason == "alpha's variants are checked by beta"


def test_packages_binaries_and_self_references_are_not_calls() -> None:
    callees = {call.callee for call in _report().calls}

    assert not callees & {"numpy", "ffmpeg"}
    assert ("alpha-skill", "alpha-skill") not in _calls(_report())


def test_a_skill_dependency_that_names_no_component_is_unresolved_not_failed() -> None:
    report = _report()

    assert [(item.name, item.pointer) for item in report.unresolved] == [
        ("ghost", "/dependencies/3")
    ]
    assert report.unattributed == ["stray.json"]


def test_a_component_without_a_known_layer_fails() -> None:
    report = _report()

    delta = next(row for row in report.components if row.repo == "delta-skill")
    assert delta.problem == "no layer"
    assert report.summary["unlayered_components"] == 1

    layering = _load("layering.json")
    layering["layers"] = ["engine", "skill"]
    unknown = _report(layering)
    conductor = next(row for row in unknown.components if row.repo == "conductor")
    assert conductor.problem is not None
    assert "not one of engine, skill" in conductor.problem


def test_an_exception_that_excuses_nothing_is_stale() -> None:
    report = _report()

    assert [(item.caller, item.callee) for item in report.stale_exceptions] == [
        ("gamma-skill", "alpha-skill")
    ]


def test_it_passes_once_every_upward_and_same_layer_call_is_an_exception() -> None:
    layering = _load("layering.json")
    layering["exceptions"] += [
        {"from": "beta-skill", "to": "gamma-skill", "reason": "r"},
        {"from": "beta-skill", "to": "conductor", "reason": "r"},
    ]
    document = _load("ecosystem.json")
    document["components"][4]["layer"] = "skill"
    repositories, problems = ecosystem_repositories(document)

    report = check_layers(
        repositories,
        component_layers(document),
        read_saved_contract_directory(_FIXTURE / "contracts"),
        parse_layering(layering),
        suffixes=COMPONENT_NAME_SUFFIXES,
    )

    assert report.passed
    assert report.summary["excepted"] == 3


def test_report_only_is_recorded_and_the_json_is_deterministic() -> None:
    first, second = _report(report_only=True), _report(report_only=True)

    assert first.to_json() == second.to_json()
    data = json.loads(first.to_json())
    assert data["format"] == "system-intelligence/layer-check@1"
    assert data["report_only"] is True
    assert data["passed"] is False
    assert data["stale_exceptions"][0] == {
        "from": "gamma-skill",
        "to": "alpha-skill",
        "reason": "no such call any more",
    }


def test_the_table_names_each_call_and_each_component() -> None:
    table = format_layer_table(_report(report_only=True))

    assert table.startswith("Layer check FAILED (report only: does not fail the run): 5 declared")
    assert "engine < skill < orchestrator" in table
    assert "| beta-skill (skill) | conductor (orchestrator) | up | violation |" in table
    assert "| delta-skill | - (no layer) |" in table
    assert "exception gamma-skill -> alpha-skill excused nothing (stale)" in table


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"skill_id": "a"}, ("a", True)),
        ({"id": "a", "kind": "skill"}, ("a", True)),
        ({"id": "a", "kind": "app"}, ("a", True)),
        ({"id": "a"}, ("a", False)),
        ({"id": "a", "kind": "python-package"}, (None, False)),
        ({"skill_id": "a", "kind": "python"}, (None, False)),
        ({"id": "a/doc@1", "kind": "schema"}, (None, False)),
        ({"skill_id": "", "id": "a", "kind": "skill"}, ("a", True)),
        ({"kind": "skill"}, (None, False)),
        ({"skill_id": ""}, (None, False)),
        ("a", (None, False)),
    ],
)
def test_dependency_name(entry: Any, expected: tuple[str | None, bool]) -> None:
    assert dependency_name(entry) == expected


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"layers": []}, "/layers"),
        ({"layers": ["a", "A"]}, "named twice"),
        ({"layers": ["a", " "]}, "empty"),
        ({"layers": ["a"], "exceptions": [{"from": "x", "to": "y"}]}, "reason"),
        ({"layers": ["a"], "exceptions": [{"from": "x", "to": "y", "reason": ""}]}, "reason"),
        (
            {
                "layers": ["a"],
                "exceptions": [
                    {"from": "x", "to": "y", "reason": "r"},
                    {"from": "X", "to": "y", "reason": "s"},
                ],
            },
            "listed twice",
        ),
        ({"layers": ["a"], "extra": 1}, "/extra"),
    ],
)
def test_parse_layering_refuses_a_bad_document(document: Any, message: str) -> None:
    with pytest.raises(LayeringError, match=message):
        parse_layering(document)


def test_component_layers_reads_strings_only() -> None:
    document = {
        "components": [
            {"repo": "a", "layer": "skill"},
            {"repo": "b", "layer": 3},
            {"repo": "c"},
            {"repo": "a", "layer": "engine"},
            "not an object",
        ]
    }

    assert component_layers(document) == {"a": "skill", "b": None, "c": None}
    assert component_layers([]) == {}
