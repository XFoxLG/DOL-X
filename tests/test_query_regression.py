"""Pure tests for the exploration query regression runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.query_regression import (
    QueryError,
    classify_payload,
    load_queries,
    main,
    run,
)


def _query(**overrides) -> dict:
    base = {
        "id": "q",
        "kind": "traversal",
        "severity": "release",
        "path": "tracks.natural.actions",
        "op": "gte",
        "value": 1,
    }
    base.update(overrides)
    return base


def test_path_op_evaluation() -> None:
    evidence = {"traversal": [{"tracks": {"natural": {"actions": 5}}}]}
    report = run([_query()], evidence)
    assert report["counts"]["passed"] == 1
    assert report["release_blocking"] == []


def test_failed_release_query_blocks() -> None:
    evidence = {"traversal": [{"tracks": {"natural": {"actions": 0}}}]}
    report = run([_query()], evidence)
    assert report["counts"]["failed"] == 1
    assert report["release_blocking"] == ["q"]


def test_informational_failure_does_not_block() -> None:
    evidence = {"traversal": [{"tracks": {}}]}
    report = run([_query(severity="informational")], evidence)
    assert report["counts"]["failed"] == 1
    assert report["release_blocking"] == []


def test_missing_evidence_and_pending() -> None:
    report = run([_query(), _query(id="p", status="pending", reason="later")], {})
    statuses = {row["id"]: row["status"] for row in report["results"]}
    assert statuses == {"q": "missing_evidence", "p": "pending"}
    assert set(report["release_blocking"]) == {"q", "p"}


def test_au_contract_scope_uses_au_artifacts_only() -> None:
    evidence = {
        "au_contract": [
            [
                {"target": "base.zip", "is_au": False, "au_contract": {"errors": ["irrelevant"]}},
                {
                    "target": "au.zip",
                    "is_au": True,
                    "au_contract": {
                        "schema": "dolx.au_contract.v1",
                        "framework_face_style_src_fn_export_count": 1,
                        "framework_variant_dir_shim_marker_count": 1,
                        "framework_pet_remount_marker_count": 1,
                        "au_payload_logic_observable": False,
                        "runtime_query_required": True,
                        "errors": [],
                    },
                },
            ]
        ]
    }
    queries = [
        _query(id="schema", kind="au_contract", path="schema", op="eq", value="dolx.au_contract.v1"),
        _query(
            id="shim",
            kind="au_contract",
            path="framework_variant_dir_shim_marker_count",
            op="eq",
            value=1,
        ),
        _query(id="errors", kind="au_contract", path="errors", op="empty"),
        _query(id="opaque", kind="au_contract", op="opaque_requires_runtime_query", path=None),
    ]
    report = run(queries, evidence)
    assert report["counts"]["passed"] == 4


def test_au_contract_without_au_artifacts_is_missing_evidence() -> None:
    evidence = {"au_contract": [[{"target": "base.zip", "is_au": False, "au_contract": {}}]]}
    query = _query(id="x", kind="au_contract", path="errors", op="empty")
    report = run([query], evidence)
    assert report["results"][0]["status"] == "missing_evidence"


def test_mod_present_and_story_graph_ops() -> None:
    evidence = {
        "mod_inventory": [
            {"tool": "dol-x-mod-passage-inventory", "mods": [{"name": "More Love Interests Mod"}]}
        ],
        "story_graph": [
            {
                "blocking": {
                    "unclassified_dead_ends": ["Other Place"],
                    "unclassified_undefined_targets": [],
                }
            }
        ],
    }
    report = run(
        [
            _query(id="mod", kind="mod_inventory", op="mod_present", path=None, mod_name="more love"),
            _query(id="dead", kind="story_graph", op="dead_end_classified", path=None, passage="Estate Manor Approach Finish"),
            _query(id="target", kind="story_graph", op="undefined_target_classified", path=None, target="Estate Manor Intro Entrance"),
        ],
        evidence,
    )
    assert report["counts"]["passed"] == 3


def test_symbolic_ops(tmp_path: Path) -> None:
    reachable = {
        "schema": "dolx.symbolic_reachability.v1",
        "verdict": "reachable",
        "targets": [{"target": "Orphanage Intro", "verdict": "reachable"}],
    }
    unavailable = {
        "schema": "dolx.symbolic_reachability.v1",
        "verdict": "solver_unavailable",
        "targets": [],
    }
    queries = [
        _query(id="no-solver", kind="symbolic_reachability", op="no_unreachable_targets", path=None),
        _query(
            id="verdict",
            kind="symbolic_reachability",
            op="target_verdict_in",
            path=None,
            target="Orphanage Intro",
            allowed=["reachable"],
        ),
    ]
    assert run(queries, {"symbolic_reachability": [reachable]})["counts"]["passed"] == 2
    assert run(queries, {"symbolic_reachability": [unavailable]})["counts"]["failed"] == 2


def test_load_queries_rejects_unknown_op_and_stray_path(tmp_path: Path) -> None:
    bad_op = tmp_path / "bad-op.toml"
    bad_op.write_text(
        'schema = "dolx.exploration-queries.v1"\n'
        "[[query]]\n"
        'id = "x"\nkind = "traversal"\nop = "explode"\n',
        encoding="utf-8",
    )
    with pytest.raises(QueryError):
        load_queries(bad_op)
    stray = tmp_path / "stray.toml"
    stray.write_text(
        'schema = "dolx.exploration-queries.v1"\n'
        "[[query]]\n"
        'id = "x"\nkind = "traversal"\nop = "no_unreachable_targets"\npath = "verdict"\n',
        encoding="utf-8",
    )
    with pytest.raises(QueryError):
        load_queries(stray)


def test_strict_mode_exit_code(tmp_path: Path) -> None:
    report = tmp_path / "traversal-stats.json"
    report.write_text(
        json.dumps({"schema": "dolx.traversal-stats.v1", "tracks": {}}),
        encoding="utf-8",
    )
    queries = tmp_path / "queries.toml"
    queries.write_text(
        'schema = "dolx.exploration-queries.v1"\n'
        "[[query]]\n"
        'id = "natural-actions"\n'
        'kind = "traversal"\n'
        'severity = "release"\n'
        'path = "tracks.natural.actions"\n'
        'op = "gte"\n'
        "value = 1\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                str(report),
                "--queries",
                str(queries),
                "--out",
                str(tmp_path / "out"),
                "--strict",
            ]
        )
        == 2
    )
    assert (
        main(
            [
                str(report),
                "--queries",
                str(queries),
                "--out",
                str(tmp_path / "out2"),
            ]
        )
        == 0
    )


def _flow_report(statuses: dict[str, str]) -> dict:
    return {
        "schema": "dolx.flow-assertions.v1",
        "tool": "sweep_flow_assertions",
        "flows": [
            {"flow": name, "status": status} for name, status in statuses.items()
        ],
    }


def test_classify_payload_recognizes_flow_assertion_reports() -> None:
    payload = _flow_report({"au-face-remount": "pass"})
    assert classify_payload(payload) == "flow_assertions"
    assert classify_payload({"tool": "sweep_flow_assertions"}) is None


def test_flow_status_in_operator() -> None:
    query = {
        "id": "remount",
        "kind": "flow_assertions",
        "severity": "release",
        "op": "flow_status_in",
        "flow": "au-face-remount",
        "allowed": ["pass"],
    }
    passed = run(
        [query], {"flow_assertions": [_flow_report({"au-face-remount": "pass"})]}
    )
    assert passed["counts"]["passed"] == 1

    failed = run(
        [query], {"flow_assertions": [_flow_report({"au-face-remount": "fail"})]}
    )
    assert failed["counts"]["failed"] == 1
    assert failed["release_blocking"] == ["remount"]

    absent = run(
        [query], {"flow_assertions": [_flow_report({"mods": "pass"})]}
    )
    assert absent["counts"]["failed"] == 1
    assert "not present" in absent["results"][0]["detail"]


def test_load_queries_accepts_activated_remount_query(tmp_path: Path) -> None:
    path = tmp_path / "queries.toml"
    path.write_text(
        'schema = "dolx.exploration-queries.v1"\n'
        "[[query]]\n"
        'id = "au-pet-remount-survives-reload"\n'
        'kind = "flow_assertions"\n'
        'severity = "release"\n'
        'op = "flow_status_in"\n'
        'flow = "au-face-remount"\n'
        'allowed = ["pass"]\n',
        encoding="utf-8",
    )
    queries = load_queries(path)
    assert queries[0]["kind"] == "flow_assertions"
    assert queries[0]["allowed"] == ["pass"]
