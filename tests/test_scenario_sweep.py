"""tools/scenario_sweep.py（剧情轴扫描）的单元测试。

这些测试刻意不依赖浏览器、网络与 82MB 产物，只覆盖纯逻辑：
- 清单行分类（可点击行 vs 只渲染文字的标题行）与统计
- 静态 debugmenu 源码解析（字面量行 + 函数行）与运行时/静态交叉核对
- getNameAndPassage 结果解析与不可解析目标的判定
- 不变量电池结果评估 + 合成变量 dict 的深度扫描
- 场景专属断言的硬/软失败聚合
- 五档判定聚合与基线 diff（新回归/修复/新场景）
- dayloop 关键词匹配、fallback/stalled 状态语义、时间推进与假通过回归
- CLI 参数默认值与报告写出
"""

from __future__ import annotations

import inspect
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import tools.scenario_sweep as scenario_sweep
from tools.scenario_sweep import (
    DAYLOOP_CLICK,
    DAYLOOP_CLICK_STATUSES,
    DAYLOOP_COMBAT_CLICK,
    DAYLOOP_COMBAT_OPTIONS,
    DAYLOOP_FALLBACK_KEYWORDS,
    DAYLOOP_PREP,
    DAYLOOP_PROBE,
    DAYLOOP_STEPS,
    DEFAULT_FIXTURE,
    DEFAULT_MANIFEST_OUT,
    EXPECTED_MANIFEST,
    ROUNDTRIP_VOLATILE_KEYS,
    SCENARIO_SPECS,
    VERDICTS,
    aggregate_scenario_verdict,
    baseline_path,
    classify_interaction,
    classify_unresolvable,
    cross_check_manifest,
    dayloop_combat_choice,
    dayloop_click_status,
    dayloop_clock_moved,
    dayloop_lesson_continuation_pick,
    dayloop_lesson_subject,
    dayloop_match,
    dayloop_missing_step_record,
    dayloop_pick,
    dayloop_route_target_pick,
    dayloop_scripted_pick,
    dayloop_school_event_pick,
    dayloop_home_route_pick,
    dayloop_school_exit_pick,
    dayloop_swimwear_self_status,
    dayloop_swimming_continuation_pick,
    dayloop_time_advance,
    default_out_dir,
    diff_scenarios,
    evaluate_invariants,
    evaluate_spec_report,
    is_unregistered_debug_macro,
    manifest_baseline_path,
    manifest_drift,
    manifest_summary,
    normalize_manifest_row,
    parse_args,
    parse_name_and_passage_result,
    parse_static_debug_menu,
    roundtrip_digest_diff,
    run_dayloop,
    scan_variables,
    select_rows,
    summarize_assignment_checks,
    write_report,
)


# --------------------------------------------------------------------------- #
# Manifest rows
# --------------------------------------------------------------------------- #


def test_normalize_manifest_row_classifies_clickable_and_separator() -> None:
    link = normalize_manifest_row(
        {
            "section": "Events",
            "index": 45,
            "kind": "link",
            "label": "被黑狼威胁",
            "target": "Forest Wolf Molestation",
            "widgets": 3,
            "target_is_function": False,
        }
    )
    assert link["kind"] == "link"
    assert link["target"] == "Forest Wolf Molestation"
    assert link["widgets"] == 3

    separator = normalize_manifest_row(
        {"section": "Main", "index": 51, "kind": "separator", "label": None}
    )
    assert separator["kind"] == "separator"
    assert separator["target"] is None


def test_normalize_manifest_row_promotes_unknown_with_target() -> None:
    row = normalize_manifest_row(
        {"section": "Main", "index": 1, "kind": "unknown", "target": "Test"}
    )
    assert row["kind"] == "link"
    empty = normalize_manifest_row({"section": "Main", "index": 2, "kind": "unknown"})
    assert empty["kind"] == "separator"


def test_manifest_summary_matches_ground_truth_shape() -> None:
    rows = [
        {"section": "Main", "index": 0, "kind": "link", "target_is_function": False},
        {"section": "Main", "index": 1, "kind": "link", "target_is_function": True},
        {"section": "Main", "index": 2, "kind": "separator"},
        {"section": "Events", "index": 0, "kind": "link", "target_is_function": True},
    ]
    summary = manifest_summary(rows)

    assert summary["rows"] == 4
    assert summary["clickable"] == 3
    assert summary["separators"] == 1
    assert summary["by_section"] == {"Main": 3, "Events": 1}
    assert summary["by_section_clickable"] == {"Main": 2, "Events": 1}
    assert summary["dynamic_targets"] == 2
    assert summary["literal_targets"] == 1


def test_manifest_drift_reports_added_and_removed_rows() -> None:
    summary = {
        "rows": 364,
        "clickable": 332,
        "separators": 32,
        "by_section": {"Main": 93, "Events": 137, "Character": 134, "Favourites": 0},
    }
    drift = manifest_drift(summary, EXPECTED_MANIFEST)

    assert drift["ok"] is False
    kinds = {(item["kind"], item["name"]) for item in drift["differences"]}
    assert ("total", "rows") in kinds
    assert ("total", "clickable") in kinds
    assert ("section", "Main") in kinds

    clean = manifest_drift(
        {
            "rows": 363,
            "clickable": 331,
            "separators": 32,
            "by_section": dict(EXPECTED_MANIFEST["sections"]),
        },
        EXPECTED_MANIFEST,
    )
    assert clean["ok"] is True
    assert clean["differences"] == []


# --------------------------------------------------------------------------- #
# Static debugmenu parsing + cross-check
# --------------------------------------------------------------------------- #


FAKE_DEBUG_MENU = r"""
// a comment that mentions link: [nope, nope]
setup.debugMenu.eventList = {
	Main: [
		{
			link: [`家`, `Bedroom`],
			widgets: [`<<set $x to 1>>`],
		},
		{
			link: [`测试`, `Test`],
			widgets: [],
		},
		{
			link: [`经过1小时`, stayOnPassageFn],
			widgets: [`<<set _t to [1, 2, 3]>>`, `<<run window.tick()>>`],
		},
	],
	Events: [
		{
			link: [`狼`, `Forest Wolf Molestation`],
			widgets: [`<<set $combat to 1>>`],
		},
		{
			link: [`箭头`, () => "Somewhere" + "]"],
			widgets: [],
		},
	],
	Character: [],
	Favourites: [],
};
"""


def test_parse_static_debug_menu_literals_and_functions() -> None:
    parsed = parse_static_debug_menu(FAKE_DEBUG_MENU)

    assert parsed["ok"] is True
    assert parsed["rows"] == 5
    assert parsed["literal_targets"] == 3
    assert parsed["dynamic_targets"] == 2
    assert parsed["sections"] == {
        "Main": 3,
        "Events": 2,
        "Character": 0,
        "Favourites": 0,
    }

    main = parsed["section_entries"]["Main"]
    assert [entry["label"] for entry in main] == ["家", "测试", "经过1小时"]
    assert [entry["target"] for entry in main] == ["Bedroom", "Test", None]
    assert main[2]["target_is_function"] is True

    events = parsed["section_entries"]["Events"]
    assert events[1]["target_is_function"] is True
    assert events[1]["target"] is None


def test_parse_static_debug_menu_handles_nested_widget_brackets() -> None:
    parsed = parse_static_debug_menu(FAKE_DEBUG_MENU)
    main = parsed["section_entries"]["Main"]

    # 第三个 Main 行的 widgets 内嵌了 [1, 2, 3]，解析不能在这里提前结束
    assert len(main) == 3
    assert main[2]["target_is_function"] is True
    events = parsed["section_entries"]["Events"]
    # 箭头函数体里带 "]"，平衡扫描必须正确收口
    assert len(events) == 2


def test_parse_static_debug_menu_missing_marker_is_reported() -> None:
    parsed = parse_static_debug_menu("no menu here")
    assert parsed["ok"] is False
    assert "not found" in parsed["error"]
    assert parsed["entries"] == []


def _runtime_rows(parsed: dict) -> list[dict]:
    rows: list[dict] = []
    for entry in parsed["entries"]:
        rows.append(
            {
                "section": entry["section"],
                "index": entry["index"],
                "kind": "link",
                "target": entry["target"],
                "target_is_function": entry["target_is_function"],
            }
        )
    return rows


def test_cross_check_manifest_ok_when_counts_match() -> None:
    parsed = parse_static_debug_menu(FAKE_DEBUG_MENU)
    result = cross_check_manifest(_runtime_rows(parsed), parsed)

    assert result["ok"] is True
    assert result["counts_match"] is True
    assert result["drift"] == []
    assert result["runtime"]["clickable"] == 5
    assert result["static"]["dynamic_targets"] == 2


def test_cross_check_manifest_fails_when_runtime_missing_rows() -> None:
    parsed = parse_static_debug_menu(FAKE_DEBUG_MENU)
    runtime = _runtime_rows(parsed)[:-1]

    result = cross_check_manifest(runtime, parsed)

    assert result["ok"] is False
    assert result["counts_match"] is False
    counts = [d for d in result["drift"] if d["kind"] == "section_count"]
    assert any(d["section"] == "Events" and d["static"] == 2 and d["runtime"] == 1 for d in counts)


def test_cross_check_manifest_reports_literal_target_drift() -> None:
    parsed = parse_static_debug_menu(FAKE_DEBUG_MENU)
    runtime = _runtime_rows(parsed)
    runtime[0]["target"] = "Renamed Bedroom"

    result = cross_check_manifest(runtime, parsed)

    assert result["ok"] is False
    drift = [d for d in result["drift"] if d["kind"] == "target_drift"]
    assert drift == [
        {
            "kind": "target_drift",
            "section": "Main",
            "index": 0,
            "static": "Bedroom",
            "runtime": "Renamed Bedroom",
        }
    ]


def test_cross_check_manifest_without_static_parse_is_not_ok() -> None:
    result = cross_check_manifest([], {"ok": False, "error": "boom"})
    assert result["ok"] is False
    assert result["reason"] == "boom"


# --------------------------------------------------------------------------- #
# getNameAndPassage result parsing
# --------------------------------------------------------------------------- #


def test_parse_name_and_passage_result_ok() -> None:
    parsed = parse_name_and_passage_result(
        {
            "ok": True,
            "link_name": "被黑狼威胁",
            "link_passage": "Forest Wolf Molestation",
        }
    )
    assert parsed == {
        "ok": True,
        "link_name": "被黑狼威胁",
        "link_passage": "Forest Wolf Molestation",
    }


@pytest.mark.parametrize(
    "payload,needle",
    [
        ({"ok": False, "error": "row not found"}, "row not found"),
        ({"ok": True, "link_name": "", "link_passage": "Test"}, "link_name"),
        ({"ok": True, "link_name": "名", "link_passage": ""}, "link_passage"),
        (
            {"ok": True, "link_name": "名", "link_passage": "Test", "target_error": "'x' is not defined"},
            "is not defined",
        ),
    ],
)
def test_parse_name_and_passage_result_rejects_broken_payloads(payload: dict, needle: str) -> None:
    parsed = parse_name_and_passage_result(payload)
    assert parsed["ok"] is False
    assert needle in parsed["error"]


def test_classify_unresolvable_paths() -> None:
    assert classify_unresolvable("") == "not_applicable"
    assert classify_unresolvable("link_passage missing/empty") == "not_applicable"
    assert classify_unresolvable("TargetName is not defined") == "fixture_insufficient"
    assert classify_unresolvable("Cannot read properties of undefined") == "fixture_insufficient"
    assert classify_unresolvable("unexpected internal explosion") == "hard_fail"


# --------------------------------------------------------------------------- #
# Invariant battery + variable scan
# --------------------------------------------------------------------------- #


def _clean_battery() -> dict:
    return {
        "checks": [
            {"name": "required_core_keys", "ok": True, "detail": "all present"},
            {"name": "core_numeric_bounds", "ok": True, "detail": "in range"},
            {"name": "deep_numeric_scan", "ok": True, "detail": "nodes=100 nan=0 inf=0"},
        ],
        "violations": [],
        "stats": {"nodes": 100, "truncated": False},
    }


def test_evaluate_invariants_ok() -> None:
    report = evaluate_invariants(_clean_battery())
    assert report["ok"] is True
    assert report["failed_checks"] == []
    assert report["stats"]["nodes"] == 100


def test_evaluate_invariants_flags_failed_check_and_violations() -> None:
    battery = _clean_battery()
    battery["checks"][1] = {"name": "core_numeric_bounds", "ok": False, "detail": "pain=NaN"}
    battery["violations"] = ["core numeric out of range: pain=NaN"]

    report = evaluate_invariants(battery)

    assert report["ok"] is False
    assert report["failed_checks"][0]["name"] == "core_numeric_bounds"
    assert "pain=NaN" in report["detail"]
    assert report["violations"] == ["core numeric out of range: pain=NaN"]


def test_evaluate_invariants_empty_battery_is_not_ok() -> None:
    assert evaluate_invariants({})["ok"] is False
    assert evaluate_invariants(None)["ok"] is False


def test_scan_variables_flags_nan_and_infinity() -> None:
    variables = {
        "pain": 10,
        "nested": {"list": [1.0, float("nan")], "deep": {"inf": float("inf")}},
    }
    report = scan_variables(variables)

    assert report["ok"] is False
    assert any("NaN at nested.list[1]" == item for item in report["violations"])
    assert any("Infinity at nested.deep.inf" == item for item in report["violations"])
    assert report["stats"]["nan"] == 1
    assert report["stats"]["infinity"] == 1


def test_scan_variables_is_clean_for_finite_state() -> None:
    report = scan_variables({"money": 500, "worn": {"upper": {"integrity": 100}}})
    assert report["ok"] is True
    assert report["violations"] == []


def test_scan_variables_respects_depth_limit() -> None:
    variables = {"a": {"b": {"c": {"d": {"e": float("nan")}}}}}

    shallow = scan_variables(variables, depth_limit=3)
    assert shallow["ok"] is True  # NaN 在 depth 5，超出 depth_limit=3

    deep = scan_variables(variables, depth_limit=8)
    assert deep["ok"] is False
    assert "NaN at a.b.c.d.e" in deep["violations"][0]


def test_scan_variables_survives_cycles() -> None:
    cyclic: dict = {"money": 1}
    cyclic["self"] = cyclic

    report = scan_variables(cyclic)
    assert report["ok"] is True
    assert report["stats"]["nodes"] < 10


def test_scan_variables_respects_node_limit() -> None:
    variables = {"i": list(range(5000))}
    report = scan_variables(variables, depth_limit=6, node_limit=100)

    assert report["stats"]["truncated"] is True
    assert report["stats"]["nodes"] <= 101


# --------------------------------------------------------------------------- #
# Scenario spec evaluation
# --------------------------------------------------------------------------- #


def test_evaluate_spec_report_missing_key_is_hard() -> None:
    spec = {
        "required_globals": [],
        "required_keys": ["edengarden"],
        "changed_keys": [],
        "checks": [],
    }
    raw = {
        "globals": [],
        "keys": [{"name": "edengarden", "ok": False, "type": "undefined"}],
        "changed": [],
        "exprs": [],
    }
    report = evaluate_spec_report(raw, spec)

    assert report["ok"] is False
    assert report["hard_failures"] == ["key missing: edengarden"]


def test_evaluate_spec_report_unchanged_keys_is_soft() -> None:
    spec = {"required_keys": [], "changed_keys": ["combat", "enemytype"], "checks": []}
    raw = {
        "changed": [
            {"name": "combat", "changed": False, "detail": "0 -> 0"},
            {"name": "enemytype", "changed": False, "detail": "null -> null"},
        ],
        "exprs": [],
    }
    report = evaluate_spec_report(raw, spec)

    assert report["ok"] is False
    assert report["hard_failures"] == []
    assert "no observed state change" in report["soft_failures"][0]


@pytest.mark.parametrize(
    "severity,expected_bucket",
    [("hard", "hard_failures"), ("soft", "soft_failures")],
)
def test_evaluate_spec_report_expr_severity(severity: str, expected_bucket: str) -> None:
    spec = {"checks": [{"name": "combat_on", "expr": "V.combat === 1", "severity": severity}]}
    raw = {"exprs": [{"name": "combat_on", "ok": False, "value": "false"}]}

    report = evaluate_spec_report(raw, spec)

    assert report["ok"] is False
    assert report[expected_bucket] == ["combat_on: false"]
    other = "soft_failures" if expected_bucket == "hard_failures" else "hard_failures"
    assert report[other] == []


def test_evaluate_spec_report_passes_when_everything_holds() -> None:
    spec = {
        "required_globals": ["Time"],
        "required_keys": ["averydate"],
        "changed_keys": ["averydate"],
        "checks": [{"name": "location", "expr": 'V.location === "town"', "severity": "hard"}],
    }
    raw = {
        "globals": [{"name": "Time", "type": "object", "ok": True}],
        "keys": [{"name": "averydate", "type": "number", "ok": True}],
        "changed": [{"name": "averydate", "changed": True, "detail": "absent -> 1"}],
        "exprs": [{"name": "location", "ok": True, "value": "true"}],
    }

    report = evaluate_spec_report(raw, spec)
    assert report["ok"] is True
    assert report["hard_failures"] == []
    assert report["soft_failures"] == []
    assert report["evidence"]["keys"][0]["name"] == "averydate"


def test_scenario_specs_cover_at_least_20_real_targets() -> None:
    assert len(SCENARIO_SPECS) >= 20
    known_real_targets = {
        "Eden Cabin",
        "Forest Hunter Intro",
        "Kylar Basement Rape",
        "Street Kylar Sex",
        "Bed Robin Sex",
        "Robin Pillory Watch",
        "Orphanage",
        "Underground Intro",
        "Domus Street",
        "Test",
        "Moor",
        "Police Cell",
        "Police Prison Intro Bailey",
        "Police Pillory Start",
        "Street Police Extreme",
        "Hospital Foyer",
        "Hospital Bed",
        "Ambulance rescue",
        "Asylum Intro",
        "Estate",
        "Livestock Intro",
        "School Detention",
        "History Lesson Pillory",
        "Maths Lesson Gang Bang",
        "Temple",
        "Museum",
        "Forest",
        "Forest Wolf Molestation",
        "Forest Bear Molestation",
        "Forest Boar Rape",
        "Street Dogs",
        "Meadow Cave Sex",
        "Beach Cave",
        "Sea Tentacles",
        "Monster Test",
        "Wraith Test Start",
        "Possessed Fight Test",
        "Brothel Dance",
        "The Pod",
        "Struggle",
    }
    assert set(SCENARIO_SPECS) <= known_real_targets
    for target, spec in SCENARIO_SPECS.items():
        assert spec.get("changed_keys") or spec.get("required_keys"), target
        assert any(check.get("expr") for check in spec.get("checks") or []), target
        # passage 名不来自翻译，必须是 ASCII 原文
        assert target == target.strip()


# --------------------------------------------------------------------------- #
# Verdict aggregation (five tiers)
# --------------------------------------------------------------------------- #


def _clean_probe(**overrides: object) -> dict:
    probe = {
        "passage": "Forest Wolf Molestation",
        "done": True,
        "errors": [],
        "textLen": 400,
        "linkCount": 6,
        "childCount": 3,
        "hasPassageNode": True,
    }
    probe.update(overrides)
    return probe


def test_aggregate_verdict_ok() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={"widgets": 3, "delta": [{"path": "combat"}], "widgets_error": None},
        invariant_report={"ok": True, "detail": ""},
        spec_report={"ok": True, "hard_failures": [], "soft_failures": []},
    )
    assert verdict == "ok"
    assert detail == ""


def test_aggregate_verdict_hard_on_landing_mismatch() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(passage="Somewhere Else"),
        target="Forest Wolf Molestation",
        row_report={"widgets": 0, "delta": []},
        invariant_report={"ok": True},
    )
    assert verdict == "hard_fail"
    assert "landed on 'Somewhere Else'" in detail


def test_aggregate_verdict_state_op_without_delta_is_ok_with_note() -> None:
    """A stay-on-passage click is not required to move a variable."""
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={"widgets": 3, "delta": [], "widgets_error": None},
        invariant_report={"ok": True},
        interaction="state",
    )
    assert verdict == "ok"
    assert "no observable variable delta" in detail


def test_aggregate_verdict_deep_delta_is_recorded_as_note() -> None:
    """Nested writes (museum antiques etc.) are real evidence, not a delta miss."""
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={
            "widgets": 2,
            "delta": [],
            "deep_delta": [{"path": "$.museumAntiques", "before": "a", "after": "b"}],
            "widgets_error": None,
        },
        invariant_report={"ok": True},
        interaction="state",
    )
    assert verdict == "ok"
    assert "deep snapshot" in detail


def test_aggregate_verdict_soft_on_failed_assignment_check() -> None:
    """A parseable ``<<set $x to <literal>>`` that did not land stays visible."""
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={
            "widgets": 1,
            "delta": [],
            "widgets_error": None,
            "assignment_checks": [
                {
                    "path": "sea",
                    "op": "to",
                    "checked": True,
                    "ok": False,
                    "expected": 0,
                    "actual": 3,
                }
            ],
        },
        invariant_report={"ok": True},
        interaction="state",
    )
    assert verdict == "soft_fail"
    assert "assignment check failed: $sea" in detail
    assert "expected 0" in detail


def test_aggregate_verdict_ignores_unchecked_assignments() -> None:
    """Non-literal RHS is 'cannot verify', never a failure by itself."""
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={
            "widgets": 1,
            "delta": [],
            "widgets_error": None,
            "assignment_checks": [
                {"path": "rng", "op": "to", "checked": False, "reason": "non-literal rhs"}
            ],
        },
        invariant_report={"ok": True},
        interaction="state",
    )
    assert verdict == "ok"


def test_aggregate_verdict_function_widgets_are_not_statically_checked() -> None:
    """String(function) is source code; it must never manufacture a check."""
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={
            "widgets": 1,
            "delta": [],
            "widgets_error": None,
            "assignment_checks": [],
            "function_widgets": 1,
        },
        invariant_report={"ok": True},
        interaction="state",
    )
    assert verdict == "ok"
    assert "not statically checkable" in detail


def test_classify_interaction_display_state_scene() -> None:
    assert (
        classify_interaction(
            location_before="Orphanage Intro",
            target="Wardrobe",
            target_is_function=False,
            widgets_list=[""],
        )
        == "display"
    )
    assert (
        classify_interaction(
            location_before="Orphanage Intro",
            target="Orphanage Intro",
            target_is_function=True,
            widgets_list=["<<set $consensual to 0>>"],
        )
        == "state"
    )
    assert (
        classify_interaction(
            location_before="Orphanage Intro",
            target="Alley Dog",
            target_is_function=False,
            widgets_list=["<<endcombat>>"],
        )
        == "scene"
    )
    # A dynamic target that resolved elsewhere is a real jump, not a stay.
    assert (
        classify_interaction(
            location_before="Orphanage Intro",
            target="Somewhere Else",
            target_is_function=True,
            widgets_list=["<<set $x to 1>>"],
        )
        == "scene"
    )
    # Missing signals never silently upgrade: the default stays "scene".
    assert (
        classify_interaction(
            location_before=None, target=None, target_is_function=False, widgets_list=["<<set $x to 1>>"]
        )
        == "scene"
    )


def test_summarize_assignment_checks_splits_checked_failed_unchecked() -> None:
    summary = summarize_assignment_checks(
        [
            {"path": "a", "op": "to", "checked": True, "ok": True, "expected": 1, "actual": 1},
            {"path": "b", "op": "to", "checked": True, "ok": False, "expected": 2, "actual": 5},
            {"path": "c", "op": "to", "checked": False, "reason": "non-literal rhs"},
            "not-a-dict",
        ]
    )
    assert summary["total"] == 3
    assert summary["checked"] == 2
    assert summary["failed"] == [
        {"path": "b", "op": "to", "expected": 2, "actual": 5}
    ]
    assert summary["unchecked"] == [
        {"path": "c", "op": "to", "reason": "non-literal rhs"}
    ]


def test_aggregate_verdict_hard_on_invariant_violation() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={"widgets": 0, "delta": []},
        invariant_report={"ok": False, "detail": "core_numeric_bounds: pain=NaN"},
    )
    assert verdict == "hard_fail"
    assert "invariant battery" in detail


def test_aggregate_verdict_hard_on_exception_without_fixture_markers() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={"widgets": 1, "widgets_error": "unexpected internal explosion"},
        invariant_report={"ok": True},
    )
    assert verdict == "hard_fail"
    assert "unexpected internal explosion" in detail


def test_aggregate_verdict_fixture_insufficient_wins_over_soft() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(
            errors=[{"kind": "engine.play.throw", "message": "'someVar' is not defined"}]
        ),
        target="Forest Wolf Molestation",
        row_report={"widgets": 1, "widgets_error": "'otherVar' is not defined"},
        invariant_report={"ok": True},
    )
    assert verdict == "fixture_insufficient"
    assert "is not defined" in detail


def test_aggregate_verdict_fixture_insufficient_on_set_undefined() -> None:
    """A debug row writing into fixture-missing state is a fixture boundary."""
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="Forest Wolf Molestation",
        row_report={
            "widgets": 1,
            "widgets_error": (
                "0.5.11.9 出错 (:: Orphanage Intro): <<set>>: bad evaluation: "
                "TypeError: Cannot set properties of undefined (setting 'type')"
            ),
        },
        invariant_report={"ok": True},
    )
    assert verdict == "fixture_insufficient"
    assert "Cannot set properties" in detail


def test_aggregate_verdict_soft_on_unregistered_debug_macro() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(passage="Orphanage Intro"),
        target="Orphanage Intro",
        row_report={
            "widgets": 1,
            "widgets_list": ["<<parasiteProgressDay>>"],
            "widgets_error": (
                "0.5.11.9 出错 (:: Orphanage Intro): macro "
                "<<parasiteProgressDay>> does not exist"
            ),
        },
        invariant_report={"ok": True},
    )
    assert verdict == "soft_fail"
    assert "upstream debug-menu defect" in detail


def test_unregistered_macro_requires_row_widget_to_invoke_it() -> None:
    error = "macro <<someGhostMacro>> does not exist"
    assert is_unregistered_debug_macro(error, ["<<someGhostMacro>>"]) is True
    assert is_unregistered_debug_macro(error, ["<<other>>"]) is False
    assert is_unregistered_debug_macro("unexpected boom", ["<<someGhostMacro>>"]) is False


def test_evaluate_invariants_notes_do_not_fail_the_battery() -> None:
    battery = _clean_battery()
    battery["notes"] = [
        "intentional out-of-range: awareness=-200 (written by this debug row)"
    ]
    report = evaluate_invariants(battery)
    assert report["ok"] is True
    assert report["notes"]


def test_aggregate_verdict_not_applicable_short_circuits() -> None:
    verdict, detail = aggregate_scenario_verdict(
        probe=_clean_probe(),
        target="",
        not_applicable="row resolves to an empty target passage",
    )
    assert verdict == "not_applicable"
    assert "empty target" in detail


def test_verdict_counts_cover_five_tiers() -> None:
    results = [
        {"verdict": "ok"},
        {"verdict": "soft_fail"},
        {"verdict": "hard_fail"},
        {"verdict": "fixture_insufficient"},
        {"verdict": "not_applicable"},
        {"verdict": "ok"},
    ]
    counts = Counter(r["verdict"] for r in results)
    assert set(counts) == set(VERDICTS)
    assert counts["ok"] == 2


# --------------------------------------------------------------------------- #
# Baseline diff
# --------------------------------------------------------------------------- #


def test_diff_scenarios_reports_regressions_fixed_changed_and_new() -> None:
    baseline = {
        "manifest": {"summary": {"rows": 363, "clickable": 331}},
        "results": [
            {"section": "Events", "index": 45, "target": "Forest Wolf Molestation", "verdict": "ok"},
            {"section": "Events", "index": 36, "target": "Kylar Basement Rape", "verdict": "hard_fail"},
            {"section": "Main", "index": 1, "target": "Test", "verdict": "soft_fail"},
        ],
    }
    report = {
        "manifest": {"summary": {"rows": 364, "clickable": 332}},
        "results": [
            {"section": "Events", "index": 45, "target": "Forest Wolf Molestation", "verdict": "hard_fail"},
            {"section": "Events", "index": 36, "target": "Kylar Basement Rape", "verdict": "ok"},
            {"section": "Main", "index": 1, "target": "Test", "verdict": "not_applicable"},
            {"section": "Events", "index": 99, "target": "Wolf Pack", "verdict": "ok"},
        ],
    }

    diff = diff_scenarios(report, baseline)

    assert [item["key"] for item in diff["new_regressions"]] == ["Events#45"]
    assert diff["new_regressions"][0]["was"] == "ok"
    assert diff["new_regressions"][0]["now"] == "hard_fail"
    assert [item["key"] for item in diff["fixed"]] == ["Events#36"]
    assert [item["key"] for item in diff["changed"]] == ["Main#1"]
    assert [item["key"] for item in diff["new_scenarios"]] == ["Events#99"]
    assert diff["manifest"]["changed"] is True


def test_diff_scenarios_ignores_unchanged_rows() -> None:
    baseline = {
        "results": [
            {"section": "Main", "index": 0, "target": "Bedroom", "verdict": "soft_fail"},
            {"section": "Main", "index": 1, "target": "Test", "verdict": "ok"},
        ]
    }
    report = {"results": list(baseline["results"])}

    diff = diff_scenarios(report, baseline)

    assert diff["new_regressions"] == []
    assert diff["fixed"] == []
    assert diff["changed"] == []
    assert diff["new_scenarios"] == []


# --------------------------------------------------------------------------- #
# Dayloop helpers
# --------------------------------------------------------------------------- #


def test_dayloop_match_is_case_insensitive_and_keyword_ordered() -> None:
    assert dayloop_match("(5) 浴室 (0:01)", ["浴室", "bathroom"]) == "浴室"
    assert dayloop_match("Enter the BATHROOM now", ["bathroom"]) == "bathroom"
    assert dayloop_match("无关文本", ["bathroom", "厨房"]) is None


def test_dayloop_pick_skips_invisible_and_returns_match() -> None:
    links = [
        {"text": "导出", "visible": False},
        {"text": "(5) 浴室 (0:01)", "visible": True, "data": "Bathroom"},
        {"text": "(6) 厨房 (0:01)", "visible": True, "data": "Kitchen"},
    ]
    pick = dayloop_pick(links, ("bathroom", "浴室"))

    assert pick is not None
    assert pick["index"] == 1
    assert pick["matched"] == "浴室"
    assert pick["data_passage"] == "Bathroom"
    assert dayloop_pick(links, ("school", "学校")) is None


def test_dayloop_missing_step_record_is_not_applicable_with_reason() -> None:
    record = dayloop_missing_step_record("洗漱", ("浴室", "bathroom"), "Waiting Room")

    assert record["status"] == "not_applicable"
    assert record["step"] == "洗漱"
    assert record["keyword_hits"] == []
    assert record["passage_before"] == record["passage_after"] == "Waiting Room"
    assert "Waiting Room" in record["detail"]
    assert "浴室" in record["detail"]
    assert record["clicked_text"] is None


def test_dayloop_time_advance_prefers_date_ms() -> None:
    report = dayloop_time_advance(
        {"dateMs": 1_000_000, "dayOfYear": 10, "secondsSinceMidnight": 0},
        {"dateMs": 1_000_000 + 16 * 3_600_000, "dayOfYear": 10, "secondsSinceMidnight": 57600},
    )
    assert report["ok"] is True
    assert report["hours"] == pytest.approx(16.0)
    assert report["method"] == "Time.date.getTime()"


def test_dayloop_time_advance_falls_back_to_day_of_year() -> None:
    report = dayloop_time_advance(
        {"dayOfYear": 300, "secondsSinceMidnight": 28800},
        {"dayOfYear": 301, "secondsSinceMidnight": 0},
    )
    assert report["ok"] is True
    assert report["hours"] == pytest.approx(16.0)
    assert report["method"] == "dayOfYear+secondsSinceMidnight"


def test_dayloop_time_advance_reports_missing_basis() -> None:
    report = dayloop_time_advance({}, {})
    assert report["ok"] is False
    assert report["hours"] is None
    assert "unavailable" in report["error"]


def test_dayloop_fallback_keywords_stay_inside_the_house() -> None:
    # 早餐步骤从浴室出发时必须能“返回卧室”，但不能匹配“离开孤儿院”跑出家门
    assert "返回" in DAYLOOP_FALLBACK_KEYWORDS
    assert "back" in DAYLOOP_FALLBACK_KEYWORDS
    assert not any("离开" in keyword or "leave" in keyword for keyword in DAYLOOP_FALLBACK_KEYWORDS)
    # 通用的“继续”会让自循环 passage（combat Tutorial）伪装成已完成步骤
    assert "继续" not in DAYLOOP_FALLBACK_KEYWORDS
    assert "continue" not in DAYLOOP_FALLBACK_KEYWORDS


def test_dayloop_click_status_requires_own_keyword_and_progress() -> None:
    assert (
        dayloop_click_status(clicked_ok=True, waited=True, fallback=False, moved=True)
        == "ok"
    )
    assert (
        dayloop_click_status(clicked_ok=True, waited=True, fallback=True, moved=True)
        == "fallback"
    )
    assert (
        dayloop_click_status(clicked_ok=True, waited=True, fallback=False, moved=False)
        == "stalled"
    )
    # 点击本身失败 / :passagedisplay 钩子没触发，无论是否移动都是 soft_fail
    assert (
        dayloop_click_status(clicked_ok=False, waited=False, fallback=False, moved=True)
        == "soft_fail"
    )
    assert (
        dayloop_click_status(clicked_ok=True, waited=False, fallback=False, moved=True)
        == "soft_fail"
    )
    assert set(DAYLOOP_CLICK_STATUSES) == {
        "ok",
        "fallback",
        "stalled",
        "progress",
        "unknown",
        "soft_fail",
        "not_applicable",
    }


def test_dayloop_clock_moved_compares_each_clock_basis() -> None:
    assert dayloop_clock_moved(
        {"secondsSinceMidnight": 100}, {"secondsSinceMidnight": 160}
    ) is True
    assert dayloop_clock_moved({"dayOfYear": 10}, {"dayOfYear": 11}) is True
    assert dayloop_clock_moved({"dateMs": 1000.0}, {"dateMs": 2000.0}) is True
    assert dayloop_clock_moved({"dayOfYear": 10}, {"dayOfYear": 10}) is False
    assert dayloop_clock_moved(None, None) is False


def test_dayloop_lesson_continuation_resolves_self_event_only_as_last_resort() -> None:
    """Maths 课尾只剩自循环“继续”时，先解析事件，再回到正常课链。"""
    exact = [
        {"text": "(1) 继续", "visible": True, "data": "Maths Lesson Focus", "cls": ""},
        {"text": "(2) 返回课程", "visible": True, "data": "Maths Lesson", "cls": ""},
    ]
    assert dayloop_lesson_continuation_pick(exact, "Maths Lesson Focus")[
        "data_passage"
    ] == "Maths Lesson"

    cross_page_event = [
        {"text": "(1) 继续", "visible": True, "data": "Maths Lesson Focus", "cls": ""},
        {"text": "(2) 事件", "visible": True, "data": "Maths Event Blackboard", "cls": ""},
    ]
    assert dayloop_lesson_continuation_pick(
        cross_page_event, "Maths Lesson Focus"
    )["data_passage"] == "Maths Event Blackboard"

    self_event = [
        {"text": "(1) 继续", "visible": True, "data": "Maths Lesson Focus", "cls": ""}
    ]
    pick = dayloop_lesson_continuation_pick(self_event, "Maths Lesson Focus")
    assert pick is not None
    assert pick["data_passage"] == "Maths Lesson Focus"
    assert pick["event_self"] is True

    # 非课程页与不可见自循环都不归这个兜底管。
    assert dayloop_lesson_continuation_pick(self_event, "Hallways") is None
    assert dayloop_lesson_continuation_pick(
        [{"text": "(1) 继续", "visible": False, "data": "Maths Lesson Focus"}],
        "Maths Lesson Focus",
    ) is None


def test_dayloop_lesson_continuation_resolves_swimming_event_page() -> None:
    """Swimming Lesson Focus 的 Events 页也要能回到正常课链。"""
    harass_event = [
        {
            "text": "(1) 游离",
            "visible": True,
            "data": "Events Swimming Swim Away",
            "cls": "",
        },
        {
            "text": "(2) 忍受",
            "visible": True,
            "data": "Events Swimming Swim Endure",
            "cls": "",
        },
    ]
    assert (
        dayloop_lesson_continuation_pick(
            harass_event, "Swimming Lesson Focus"
        )["data_passage"]
        == "Events Swimming Swim Endure"
    )
    assert dayloop_lesson_subject("Events Swimming Swim Away") == "Swimming"

    spare = [
        {
            "text": "(1) 换衣服",
            "visible": True,
            "data": "School Pool Crossdress",
            "cls": "",
        },
        {
            "text": "(2) 逃课 (0:05)",
            "visible": True,
            "data": "School Pool Refuse",
            "cls": "",
        },
    ]
    assert dayloop_lesson_continuation_pick(spare, "School Pool Spare") is None
    assert (
        dayloop_swimming_continuation_pick(spare, "School Pool Spare")[
            "data_passage"
        ]
        == "School Pool Crossdress"
    )

    event_page = [
        {
            "text": "(1) 无视跟踪者",
            "visible": True,
            "data": "Events Swimming Stalk Ignore",
            "cls": "",
        },
        {
            "text": "(2) 对峙",
            "visible": True,
            "data": "Events Swimming Stalk Confront",
            "cls": "",
        }
    ]
    pick = dayloop_lesson_continuation_pick(event_page, "Swimming Lesson Focus")
    assert pick is not None
    assert pick["data_passage"] == "Events Swimming Stalk Confront"

    unrelated_event = [
        {
            "text": "(1) 接受",
            "visible": True,
            "data": "Events Panty Accept",
            "cls": "",
        }
    ]
    assert (
        dayloop_lesson_continuation_pick(
            unrelated_event, "Swimming Lesson Focus"
        )
        is None
    )


def test_dayloop_route_target_pick_does_not_consume_self_event() -> None:
    """route_targets 不能把当前页的自循环事件当成路线跳点。"""
    links = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "School Front Courtyard",
            "cls": "",
        },
        {
            "text": "(2) 进入学校",
            "visible": True,
            "data": "Hallways",
            "cls": "",
        },
    ]
    assert (
        dayloop_route_target_pick(
            links, ("School Front Courtyard", "Hallways"), "School Front Courtyard"
        )["data_passage"]
        == "Hallways"
    )
    assert (
        dayloop_route_target_pick(
            links, ("School Front Courtyard",), "School Front Courtyard"
        )
        is None
    )


def test_dayloop_school_step_treats_oxford_street_as_a_waypoint() -> None:
    """上学路上的牛津街自事件也要能被解析，不能把整天卡在街口。"""
    step = next(step for step in DAYLOOP_STEPS if step.name == "上课")
    assert "Oxford Street" in step.waypoints


def test_dayloop_school_event_pick_returns_to_hallways() -> None:
    """Hallways 事件页要能回到 Hallways，不能把上课卡死在事件里。"""
    event_page = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "Hallways",
            "cls": "",
        }
    ]
    assert (
        dayloop_school_event_pick(
            event_page, "Hallways Locker Struggle Free Attempt"
        )["data_passage"]
        == "Hallways"
    )

    self_event = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "Hallways Locker Struggle Free Attempt",
            "cls": "",
        }
    ]
    pick = dayloop_school_event_pick(
        self_event, "Hallways Locker Struggle Free Attempt"
    )
    assert pick is not None
    assert pick["event_self"] is True
    assert dayloop_school_event_pick(self_event, "Hallways") is None

    unstructured_continue = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "",
            "cls": "macro-link",
        }
    ]
    text_pick = dayloop_school_event_pick(
        unstructured_continue, "Hallways Locker Struggle Free Attempt"
    )
    assert text_pick is not None
    assert text_pick["data_passage"] is None

    catcall = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "Hallways Cupboard Sex",
            "cls": "",
        },
        {
            "text": "(2) 推开",
            "visible": True,
            "data": "Hallways Cupboard Refuse 2",
            "cls": "",
        },
    ]
    assert (
        dayloop_school_event_pick(catcall, "Hallways Catcall Flirt")[
            "data_passage"
        ]
        == "Hallways Cupboard Refuse 2"
    )


def test_dayloop_home_step_leaves_school_before_taking_the_bus() -> None:
    """回家时如果还在学校里，先走学校出口，再上公交。"""
    source = inspect.getsource(run_dayloop)
    assert 'step.name not in ("上学", "上课")' in source
    assert "current_passage in DAYLOOP_SCHOOL_EXIT_ROUTE" in source
    assert 'step.name in ("回家", "睡觉")' in source
    assert "current_passage in DAYLOOP_HOME_ROUTE" in source
    assert 'pick.get("clothing_self")' in source
    assert "clothing_attempted_passages" in source
    assert '"exposed_before": exposed_before' in source
    assert '"exposed_after": exposed_after' in source
    assert '"worn_before": worn_before' in source
    assert '"worn_after": worn_after' in source
    assert 'outcome.get("worn_changed")' in source
    assert "changing_room_gender=current.get" in source
    assert "swimwear_attempted_passages" in source
    assert "dayloop_swimwear_self_status" in source
    assert "clothes_restored" in source


def test_dayloop_swimming_continuation_follows_structured_pool_chain() -> None:
    """第五节游泳课先换泳衣、进池、上课，不能停在更衣室。"""
    changing_room = [
        {"text": "(1) 穿上泳衣", "visible": True, "data": "School Girl Changing Room", "cls": ""},
        {"text": "(2) 进入游泳馆", "visible": True, "data": "School Pool", "cls": ""},
    ]
    first = dayloop_swimming_continuation_pick(changing_room, "School Girl Changing Room")
    assert first is not None
    assert first["data_passage"] == "School Girl Changing Room"
    assert first["swimwear_self"] is True
    assert (
        dayloop_swimming_continuation_pick(
            changing_room,
            "School Girl Changing Room",
            swimwear_attempted=True,
        )["data_passage"]
        == "School Pool"
    )

    no_swimwear = [
        {"text": "(1) 进入游泳馆", "visible": True, "data": "School Pool", "cls": ""}
    ]
    assert (
        dayloop_swimming_continuation_pick(no_swimwear, "School Girl Changing Room")
        is None
    )

    pool = [
        {"text": "(1) 说你没有东西可换", "visible": True, "data": "School Pool Spare", "cls": ""},
        {"text": "(2) 说你只有一件男孩的泳衣", "visible": True, "data": "School Pool Wrong", "cls": ""},
    ]
    assert dayloop_swimming_continuation_pick(pool, "School Pool")[
        "data_passage"
    ] == "School Pool Spare"

    lesson = [
        {"text": "(1) 专注课程", "visible": True, "data": "Swimming Lesson Focus", "cls": ""}
    ]
    assert dayloop_swimming_continuation_pick(lesson, "Swimming Lesson")[
        "data_passage"
    ] == "Swimming Lesson Focus"
    assert dayloop_swimming_continuation_pick(lesson, "Hallways") is None


def test_dayloop_swimwear_self_status_requires_the_real_school_swimsuit() -> None:
    """换泳衣是原地动作：判定依据是穿着槽位，不是 passage 或时钟。"""
    pick = {"matched": "(3) 穿上泳衣"}
    changed = dayloop_swimwear_self_status(
        pick,
        {
            "worn_before": {
                "upper": "school shirt",
                "lower": "school skirt",
                "under_upper": "naked",
                "under_lower": "plain panties",
            },
            "worn_after": {
                "upper": "naked",
                "lower": "naked",
                "under_upper": "school swimsuit",
                "under_lower": "school swimsuit bottom",
            },
            "worn_changed": True,
        },
    )
    assert changed[0] == "fallback"
    assert "changed into school swimwear" in changed[1]

    unchanged = dayloop_swimwear_self_status(
        pick,
        {
            "worn_before": {"under_upper": "naked"},
            "worn_after": {"under_upper": "naked"},
            "worn_changed": False,
        },
    )
    assert unchanged[0] == "stalled"
    assert "did not equip" in unchanged[1]


def test_dayloop_swimming_never_selects_pool_refuse() -> None:
    """逃课链接不是游泳课的安全续接，哪怕它是唯一选项。"""
    links = [
        {
            "text": "(1) 逃课 (0:05)",
            "visible": True,
            "data": "School Pool Refuse",
            "cls": "",
        }
    ]
    assert dayloop_swimming_continuation_pick(links, "School Pool Spare") is None
    assert dayloop_school_event_pick(links, "School Pool Spare") is None


def test_dayloop_school_exit_leaves_pool_instead_of_reentering_it() -> None:
    """放学从更衣室走 Leave 到入口，再回 Hallways，不能点回泳池。"""
    restore_clothes = [
        {"text": "(4) 穿上便服", "visible": True, "data": "School Boy Changing Room", "cls": ""},
        {"text": "(2) 离开", "visible": True, "data": "School Pool Entrance", "cls": ""},
    ]
    restored = dayloop_school_exit_pick(
        restore_clothes, "School Boy Changing Room"
    )
    assert restored is not None
    assert restored["data_passage"] == "School Boy Changing Room"
    assert restored["clothing_self"] is True
    assert (
        dayloop_school_exit_pick(
            restore_clothes,
            "School Boy Changing Room",
            clothing_attempted=True,
        )["data_passage"]
        == "School Pool Entrance"
    )

    both_changing_rooms = [
        {
            "text": "(1) 男更衣室",
            "visible": True,
            "data": "School Boy Changing Room",
            "cls": "",
        },
        {
            "text": "(2) 女更衣室",
            "visible": True,
            "data": "School Girl Changing Room",
            "cls": "",
        },
    ]
    assert (
        dayloop_school_exit_pick(
            both_changing_rooms,
            "Swimming Lesson Focus",
            changing_room_gender="girls",
        )["data_passage"]
        == "School Girl Changing Room"
    )
    assert (
        dayloop_school_exit_pick(
            both_changing_rooms,
            "School Pool Entrance",
            exposed=1,
            changing_room_gender="girls",
        )["data_passage"]
        == "School Girl Changing Room"
    )

    uniform = {
        "upper": "school shirt",
        "lower": "school skirt",
        "under_upper": "naked",
        "under_lower": "plain panties",
    }
    assert (
        dayloop_school_exit_pick(
            restore_clothes,
            "School Boy Changing Room",
            worn=uniform,
        )["data_passage"]
        == "School Pool Entrance"
    )

    swimwear_worn = {
        "upper": "naked",
        "lower": "naked",
        "under_upper": "school swimsuit",
        "under_lower": "school swimsuit bottom",
    }
    changed = dayloop_school_exit_pick(
        restore_clothes,
        "School Boy Changing Room",
        worn=swimwear_worn,
    )
    assert changed is not None
    assert changed["data_passage"] == "School Boy Changing Room"
    assert changed["clothing_self"] is True

    both_normal_sets = [
        {
            "text": "(5) 穿上便服",
            "visible": True,
            "data": "School Girl Changing Room",
            "cls": "",
        },
        {
            "text": "(6) 穿上校服",
            "visible": True,
            "data": "School Girl Changing Room",
            "cls": "",
        },
    ]
    school_set = dayloop_school_exit_pick(
        both_normal_sets,
        "School Girl Changing Room",
        worn=swimwear_worn,
    )
    assert school_set is not None
    assert school_set["text"] == "(6) 穿上校服"
    assert school_set["clothing_self"] is True

    swimwear = [
        {"text": "(3) 穿上泳衣", "visible": True, "data": "School Boy Changing Room", "cls": ""}
    ]
    assert dayloop_school_exit_pick(swimwear, "School Boy Changing Room") is None

    changing_room = [
        {"text": "(1) 进入游泳馆", "visible": True, "data": "School Pool", "cls": ""},
        {"text": "(2) 离开", "visible": True, "data": "School Pool Entrance", "cls": ""},
    ]
    assert dayloop_school_exit_pick(
        changing_room, "School Boy Changing Room"
    )["data_passage"] == "School Pool Entrance"

    entrance = [
        {"text": "(1) 男更衣室", "visible": True, "data": "School Boy Changing Room", "cls": ""},
        {"text": "(5) 离开 (0:01)", "visible": True, "data": "Hallways", "cls": ""},
    ]
    assert dayloop_school_exit_pick(entrance, "School Pool Entrance")[
        "data_passage"
    ] == "Hallways"

    # Verified in the 0.5.11.9 HTML: an exposed Hallways page hides the front
    # courtyard and only offers the rear courtyard. The real exit chain is
    # Rear -> Front -> Oxford, not Rear -> Hallways -> Front.
    exposed_hallways = [
        {
            "text": "(1) 偷偷溜到后操场 (0:05)",
            "visible": True,
            "data": "School Rear Courtyard",
            "cls": "",
        }
    ]
    assert dayloop_school_exit_pick(
        exposed_hallways, "Hallways"
    )["data_passage"] == "School Rear Courtyard"

    rear = [
        {
            "text": "(1) 前操场 (0:02)",
            "visible": True,
            "data": "School Front Courtyard",
            "cls": "",
        },
        {
            "text": "(2) 进入学校 (0:01)",
            "visible": True,
            "data": "Hallways",
            "cls": "",
        },
    ]
    assert dayloop_school_exit_pick(rear, "School Rear Courtyard")[
        "data_passage"
    ] == "School Front Courtyard"

    front = [
        {
            "text": "(1) 溜到学校后面 (0:05)",
            "visible": True,
            "data": "School Rear Courtyard",
            "cls": "",
        },
        {
            "text": "(2) 离开学校 (0:01)",
            "visible": True,
            "data": "Oxford Street",
            "cls": "",
        }
    ]
    assert dayloop_school_exit_pick(front, "School Front Courtyard")[
        "data_passage"
    ] == "Oxford Street"

    exhibitionism = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "School Pool Entrance",
            "cls": "",
        }
    ]
    assert dayloop_school_exit_pick(
        exhibitionism, "School Pool Entrance Exhibitionism"
    )["data_passage"] == "School Pool Entrance"

    rear_event = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "School Rear Courtyard",
            "cls": "",
        }
    ]
    event_pick = dayloop_school_exit_pick(rear_event, "School Rear Courtyard")
    assert event_pick is not None
    assert event_pick["data_passage"] == "School Rear Courtyard"
    assert event_pick["event_self"] is True
    assert dayloop_school_exit_pick(entrance, "Domus Street") is None

    exposed_hallways_links = [
        {
            "text": "(1) 偷偷溜到泳池",
            "visible": True,
            "data": "School Pool Entrance",
            "cls": "",
        },
        {
            "text": "(2) 偷偷溜到后操场",
            "visible": True,
            "data": "School Rear Courtyard",
            "cls": "",
        },
    ]
    assert (
        dayloop_school_exit_pick(
            exposed_hallways_links, "Hallways", exposed=1
        )["data_passage"]
        == "School Pool Entrance"
    )

    exposed_rear_links = [
        {
            "text": "(1) 偷偷溜进学校",
            "visible": True,
            "data": "Hallways",
            "cls": "",
        },
        {
            "text": "(2) 偷偷溜到学校前院",
            "visible": True,
            "data": "School Front Courtyard",
            "cls": "",
        },
    ]
    assert (
        dayloop_school_exit_pick(
            exposed_rear_links, "School Rear Courtyard", exposed=1
        )["data_passage"]
        == "Hallways"
    )

    exposed_pool_links = [
        {
            "text": "(1) 男更衣室",
            "visible": True,
            "data": "School Boy Changing Room",
            "cls": "",
        },
        {
            "text": "(5) 离开",
            "visible": True,
            "data": "Hallways",
            "cls": "",
        },
    ]
    assert (
        dayloop_school_exit_pick(
            exposed_pool_links, "School Pool Entrance", exposed=1
        )["data_passage"]
        == "School Boy Changing Room"
    )

    exposed_front_links = [
        {
            "text": "(1) 偷偷溜到后操场",
            "visible": True,
            "data": "School Rear Courtyard",
            "cls": "",
        }
    ]
    assert (
        dayloop_school_exit_pick(
            exposed_front_links, "School Front Courtyard", exposed=1
        )["data_passage"]
        == "School Rear Courtyard"
    )

    exposed_changing_room = [
        {
            "text": "(1) 试图逃跑",
            "visible": True,
            "data": "School Changing Room Escape",
            "cls": "",
        },
        {
            "text": "(2) 离开",
            "visible": True,
            "data": "School Pool Entrance",
            "cls": "",
        },
    ]
    assert (
        dayloop_school_exit_pick(
            exposed_changing_room, "School Boy Changing Room", exposed=1
        )["data_passage"]
        == "School Changing Room Escape"
    )

    caught_changing_room = [
        {
            "text": "(1) 试图逃跑",
            "visible": True,
            "data": "School Changing Room Escape",
            "cls": "",
        }
    ]
    assert (
        dayloop_school_exit_pick(
            caught_changing_room, "School Boy Changing Room"
        )["data_passage"]
        == "School Changing Room Escape"
    )

    escape = [
        {
            "text": "(1) 脱衣",
            "visible": True,
            "data": "School Changing Room Strip",
            "cls": "",
        }
    ]
    assert (
        dayloop_school_exit_pick(escape, "School Changing Room Escape")[
            "data_passage"
        ]
        == "School Changing Room Strip"
    )

    strip = [
        {
            "text": "(2) 拒绝",
            "visible": True,
            "data": "School Changing Room Naked Refuse",
            "cls": "",
        }
    ]
    assert (
        dayloop_school_exit_pick(strip, "School Changing Room Strip")[
            "data_passage"
        ]
        == "School Changing Room Naked Refuse"
    )

    naked_refuse = [
        {
            "text": "(1) 继续",
            "visible": True,
            "data": "Oxford Street",
            "cls": "",
        }
    ]
    assert (
        dayloop_school_exit_pick(
            naked_refuse, "School Changing Room Naked Refuse"
        )["data_passage"]
        == "Oxford Street"
    )


def test_dayloop_home_route_takes_the_real_bus_chain_home() -> None:
    """放学后从牛津街坐公交回宅邸街，再进孤儿院和卧室。"""
    oxford = [
        {
            "text": "(1) 学校 (0:02)",
            "visible": True,
            "data": "School Front Courtyard",
            "cls": "",
        },
        {
            "text": "(5) 等待公交车 (0:02)",
            "visible": True,
            "data": "Bus",
            "cls": "",
        },
    ]
    assert dayloop_home_route_pick(oxford, "Oxford Street")[
        "data_passage"
    ] == "Bus"

    bus = [
        {
            "text": "(1) 购买到宅邸街的车票",
            "visible": True,
            "data": "Bus seat",
            "cls": "",
        },
        {
            "text": "(2) 购买到牛津街的车票",
            "visible": True,
            "data": "Bus seat",
            "cls": "",
        },
    ]
    assert dayloop_home_route_pick(bus, "Bus")["text"].startswith("(1)")

    bus_seat = [
        {
            "text": "(1) 宅邸街",
            "visible": True,
            "data": "Domus Street",
            "cls": "",
        }
    ]
    assert dayloop_home_route_pick(bus_seat, "Bus seat")[
        "data_passage"
    ] == "Domus Street"

    domus = [
        {
            "text": "(1) 回家 (0:01)",
            "visible": True,
            "data": "Orphanage",
            "cls": "",
        }
    ]
    assert dayloop_home_route_pick(domus, "Domus Street")[
        "data_passage"
    ] == "Orphanage"

    orphanage = [
        {
            "text": "(1) 卧室",
            "visible": True,
            "data": "Bedroom",
            "cls": "",
        }
    ]
    assert dayloop_home_route_pick(orphanage, "Orphanage")[
        "data_passage"
    ] == "Bedroom"


class _DayloopFakePage:
    """run_dayloop 的无浏览器替身：按 graph 前进 passage 与时钟。"""

    def __init__(
        self,
        passage: str,
        graph: dict[str, tuple[str, str]],
        *,
        advance_seconds: float = 0.0,
        school_day: bool = True,
        prep_jump_seconds: float = 0.0,
    ) -> None:
        self.passage = passage
        self.graph = graph
        self.advance_seconds = advance_seconds
        self.school_day = school_day
        self.prep_jump_seconds = prep_jump_seconds
        self.seconds_since_midnight = 0.0
        self.clicked: list[str] = []

    def _links(self) -> list[dict[str, Any]]:
        entry = self.graph.get(self.passage)
        if not entry:
            return []
        label, target = entry
        return [{"text": label, "visible": True, "data": target, "cls": ""}]

    def evaluate(self, script: Any, payload: Any = None) -> Any:
        if script is DAYLOOP_PROBE:
            return {
                "passage": self.passage,
                "combat": 0,
                "time": {
                    "dayOfYear": 10,
                    "secondsSinceMidnight": self.seconds_since_midnight,
                    "schoolDay": self.school_day,
                },
                "links": self._links(),
                "node": "#passage-content",
                "errors": [],
            }
        if script is DAYLOOP_PREP:
            before = {
                "dayOfYear": 10,
                "secondsSinceMidnight": self.seconds_since_midnight,
                "schoolDay": self.school_day,
            }
            self.seconds_since_midnight += self.prep_jump_seconds
            self.school_day = True
            after = {
                "dayOfYear": 10,
                "secondsSinceMidnight": self.seconds_since_midnight,
                "schoolDay": True,
            }
            return {
                "ok": True,
                "via": "fake prep",
                "before": before,
                "after": after,
                "errors": [],
            }
        if script is DAYLOOP_CLICK:
            label, target = self.graph[self.passage]
            self.clicked.append(label)
            self.passage = target
            self.seconds_since_midnight += self.advance_seconds
            return {"ok": True, "text": label, "passage_before": None, "error": None}
        raise AssertionError("unexpected dayloop script")

    def wait_for_function(self, expression: str, timeout: int | None = None) -> bool:
        return True

    def wait_for_timeout(self, milliseconds: int) -> None:
        return None


class _DayloopSwimwearFakePage:
    """复现 effect 阶段的原地换泳衣：passage/时钟不动，但穿着槽位变化。"""

    def __init__(self) -> None:
        self.passage = "School Girl Changing Room"
        self.seconds_since_midnight = 14 * 3600
        self.click_count = 0

    def _worn(self) -> dict[str, str]:
        if self.click_count:
            return {
                "upper": "naked",
                "lower": "naked",
                "under_upper": "school swimsuit",
                "under_lower": "school swimsuit bottom",
            }
        return {
            "upper": "school shirt",
            "lower": "school skirt",
            "under_upper": "naked",
            "under_lower": "plain panties",
        }

    def _links(self) -> list[dict[str, Any]]:
        if self.click_count == 0:
            return [
                {
                    "text": "(3) 穿上泳衣",
                    "visible": True,
                    "data": "School Girl Changing Room",
                    "cls": "",
                }
            ]
        if self.click_count == 1:
            return [
                {
                    "text": "(1) 进入游泳馆",
                    "visible": True,
                    "data": "School Pool",
                    "cls": "",
                }
            ]
        if self.click_count:
            return []

    def evaluate(self, script: Any, payload: Any = None) -> Any:
        if script is DAYLOOP_PROBE:
            return {
                "passage": self.passage,
                "combat": 0,
                "time": {
                    "dayOfYear": 10,
                    "secondsSinceMidnight": self.seconds_since_midnight,
                    "schoolDay": True,
                },
                "links": self._links(),
                "node": "#passage-content",
                "errors": [],
                "exposed": 0,
                "worn": self._worn(),
            }
        if script is DAYLOOP_PREP:
            time = {
                "dayOfYear": 10,
                "secondsSinceMidnight": self.seconds_since_midnight,
                "schoolDay": True,
            }
            return {
                "ok": True,
                "via": "fake prep",
                "before": time,
                "after": time,
                "errors": [],
            }
        if script is DAYLOOP_CLICK:
            if payload.get("index") != 0:
                return {"ok": False, "error": "bad index"}
            if self.click_count == 0:
                self.click_count = 1
            else:
                self.passage = "School Pool"
                self.click_count = 2
            return {
                "ok": True,
                "text": "(3) 穿上泳衣" if self.click_count == 1 else "(1) 进入游泳馆",
                "passage_before": self.passage,
                "error": None,
            }
        raise AssertionError("unexpected dayloop script")

    def wait_for_function(self, expression: str, timeout: int | None = None) -> bool:
        return True

    def wait_for_timeout(self, milliseconds: int) -> None:
        return None


def test_dayloop_effect_phase_accepts_real_swimwear_change_without_clock_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上课 effect 阶段不能把已成功的换泳衣误判成 stalled。"""
    step = scenario_sweep.DayloopStep(
        "上课",
        ("上课",),
        target_passages=("School Girl Changing Room",),
        # The real lesson effect keywords do not match the swimwear link;
        # the structured swimming continuation must select and mark it.
        action_keywords=("专注",),
        # Keep this below the click's zero-minute delta so the earlier
        # "landed target but partial effect" branch cannot consume the click.
        min_minutes=0,
        completion="effect",
    )
    monkeypatch.setattr(scenario_sweep, "DAYLOOP_STEPS", (step,))
    page = _DayloopSwimwearFakePage()

    report = run_dayloop(page, max_clicks_per_step=2, timeout_ms=50, settle_ms=0)

    record = report["records"][0]
    assert record["phase"] == "effect"
    assert record["status"] == "fallback"
    assert record["worn_changed"] is True
    assert "changed into school swimwear" in record["detail"]
    pool_record = report["records"][1]
    assert pool_record["data_passage"] == "School Pool"
    assert report["stalled_clicks"] == 0


def test_dayloop_self_looping_continue_is_never_ok() -> None:
    """combat Tutorial 只有一个自循环的“(1) 继续”，不能算任何一步完成。"""
    page = _DayloopFakePage("Tutorial", {"Tutorial": ("(1) 继续", "Tutorial")})

    report = run_dayloop(page, max_clicks_per_step=2, timeout_ms=50, settle_ms=0)

    assert report["ok_clicks"] == 0
    # 起床自己的关键词里含“继续”，但 passage 与时钟都没动 -> stalled
    assert report["records"][0]["step"] == "起床"
    assert report["records"][0]["status"] == "stalled"
    assert {r["status"] for r in report["records"][1:]} == {"not_applicable"}
    assert report["stalled_clicks"] == 1
    assert report["time_advance_hours"] == 0
    steps_assertion = next(
        a for a in report["assertions"] if a["name"] == "steps_completed>=1"
    )
    assert steps_assertion["ok"] is False
    assert report["verdict"] == "soft_fail"


def test_dayloop_fallback_hops_are_recorded_but_never_ok() -> None:
    """一路“返回”只产生 fallback/not_applicable 记录：地点切换再多也不能判 ok。

    “上课”没有固定 target passage（课时 passage 因课程/日期而异），它要求
    现场存在一条真正的上课动作链接；假页面只提供“返回”，所以它是
    not_applicable 而不是 fallback。
    """
    graph = {
        "A": ("返回 B", "B"),
        "B": ("返回 C", "C"),
        "C": ("返回 D", "D"),
        "D": ("返回 A", "A"),
    }
    page = _DayloopFakePage("A", graph)

    report = run_dayloop(page, max_clicks_per_step=1, timeout_ms=50, settle_ms=0)

    statuses = [r["status"] for r in report["records"]]
    # The multi-hop navigation walk can spend more than one click per step; the
    # invariant is that no click is ever counted as step completion.
    assert report["ok_clicks"] == 0
    assert report["clicks"] >= len(DAYLOOP_STEPS)
    assert report["fallback_clicks"] >= len(DAYLOOP_STEPS) - 1
    # Every step is offered a fallback hop (the fake page only knows "返回"),
    # and none of those hops may ever be promoted to completion. A step whose
    # target is not even reachable (the fake "上课" has no fixed passage) may
    # also be reported as not_applicable.
    assert set(statuses) <= {"fallback", "not_applicable"}
    assert statuses.count("fallback") >= len(DAYLOOP_STEPS) - 1
    assert all(
        ("fallback" in r["detail"] or "navigation only" in r["detail"] or "no action matched" in r["detail"])
        and r["status"] in {"fallback", "not_applicable"}
        for r in report["records"]
    )
    assert report["location_switches"] >= 3
    assert report["verdict"] == "soft_fail"


def test_dayloop_in_place_step_with_clock_advance_can_still_be_ok() -> None:
    """同 passage 内推进但时钟前进的步骤（如上课）仍可判 ok。"""
    page = _DayloopFakePage(
        "Lesson", {"Lesson": ("上课", "Lesson")}, advance_seconds=1200
    )

    report = run_dayloop(page, max_clicks_per_step=1, timeout_ms=50, settle_ms=0)

    assert report["ok_clicks"] == 1
    ok_record = next(r for r in report["records"] if r["status"] == "ok")
    assert ok_record["step"] == "上课"
    assert ok_record["keyword_hits"] == ["上课"]
    # 上课 requires >=15 in-game minutes, so 1200s is the smallest honest pass.
    assert report["time_advance_hours"] == pytest.approx(1200 / 3600)


def test_dayloop_prep_time_jump_is_never_counted_as_day_time() -> None:
    """准备阶段的时间跳跃（周二/学期起点）不得计入 >=16h 的日循环断言。"""
    page = _DayloopFakePage(
        "Tutorial",
        {"Tutorial": ("(1) 继续", "Tutorial")},
        school_day=False,
        prep_jump_seconds=360000.0,
    )

    report = run_dayloop(page, max_clicks_per_step=1, timeout_ms=50, settle_ms=0)

    assert report["prep"]["ran"] is True
    assert report["prep"]["ok"] is True
    assert report["time_start"]["schoolDay"] is True
    # 100h of preparation must not leak into the measured day.
    assert report["time_advance_hours"] == 0
    time_assertion = next(
        a for a in report["assertions"] if a["name"] == "time_advance>=16h"
    )
    assert time_assertion["ok"] is False


class _DayloopEncounterFakePage:
    """复现 Domus Street 教程遭遇：动作单选 + 两页脚本续接。

    只实现 run_dayloop 真正调用的四个脚本（PROBE/PREP/COMBAT_OPTIONS/
    COMBAT_CLICK）与普通 CLICK，且 `$tutorial` 只触发一次：教程结束后
    Domus Street 换成真实的街道链接，避免把驱动器拖进无限重进教程。
    """

    def __init__(self) -> None:
        self.passage = "Domus Street"
        self.combat = 0
        self.tutorial_done = False
        self.seconds_since_midnight = 25200.0
        self.clicked: list[str] = []
        self.radio_clicks: list[str] = []

    def _links(self) -> list[dict[str, Any]]:
        if self.passage == "Domus Street":
            if self.tutorial_done:
                return [
                    {"text": "倒钩街 (0:05)", "visible": True, "data": "Barb Street", "cls": ""}
                ]
            return [
                {"text": "(1) 继续", "visible": True, "data": "Tutorial", "cls": ""}
            ]
        if self.passage == "Tutorial Finish":
            return [
                {"text": "(1) 调情", "visible": True, "data": "Tutorial Flirt", "cls": ""},
                {"text": "(2) 谢谢他", "visible": True, "data": "Tutorial Thank", "cls": ""},
            ]
        if self.passage == "Tutorial Flirt":
            return [
                {"text": "(1) 继续", "visible": True, "data": "Domus Street", "cls": ""}
            ]
        return []

    def _time(self) -> dict[str, Any]:
        return {
            "dayOfYear": 10,
            "secondsSinceMidnight": self.seconds_since_midnight,
            "schoolDay": True,
        }

    def evaluate(self, script: Any, payload: Any = None) -> Any:
        if script is DAYLOOP_PROBE:
            return {
                "passage": self.passage,
                "combat": self.combat,
                "time": self._time(),
                "links": self._links(),
                "node": "#passage-content",
                "errors": [],
            }
        if script is DAYLOOP_PREP:
            return {
                "ok": True,
                "via": "fake prep",
                "before": self._time(),
                "after": self._time(),
                "logout_pending": False,
                "errors": [],
            }
        if script is DAYLOOP_COMBAT_OPTIONS:
            if self.combat and self.passage == "Tutorial":
                return {
                    "passage": "Tutorial",
                    "combat": 1,
                    "options": [
                        {"id": "radio-rest", "label": "休息", "checked": False},
                        {"id": "radio-scream", "label": "尖叫", "checked": False},
                    ],
                    "next": "(1) 继续",
                    "errors": [],
                }
            return {
                "passage": self.passage,
                "combat": self.combat,
                "options": [],
                "next": None,
                "errors": [],
            }
        if script is DAYLOOP_COMBAT_CLICK:
            radio_id = str((payload or {}).get("id") or "")
            self.radio_clicks.append(radio_id)
            label = "休息" if radio_id == "radio-rest" else "尖叫"
            if radio_id == "radio-scream":
                self.passage = "Tutorial Finish"
                self.combat = 0
                self.seconds_since_midnight += 30
            return {
                "ok": True,
                "id": radio_id,
                "radio_clicked": True,
                "next_clicked": True,
                "text": label,
                "error": None,
            }
        if script is DAYLOOP_CLICK:
            link = self._links()[int((payload or {}).get("index") or 0)]
            self.clicked.append(str(link["text"]))
            target = str(link["data"])
            if target == "Tutorial":
                self.passage = "Tutorial"
                self.combat = 1
            else:
                self.passage = target
                if target == "Domus Street" and self.combat == 0:
                    self.tutorial_done = True
            return {
                "ok": True,
                "text": link["text"],
                "passage_before": None,
                "error": None,
            }
        raise AssertionError("unexpected dayloop script")

    def wait_for_function(self, expression: str, timeout: int | None = None) -> bool:
        return True

    def wait_for_timeout(self, milliseconds: int) -> None:
        return None


def test_dayloop_combat_choice_prefers_escape_over_attack() -> None:
    options = [
        {"id": "r-rest", "label": "休息 |"},
        {"id": "r-attack", "label": "攻击 |"},
        {"id": "r-scream", "label": "尖叫 |"},
    ]

    # The scripted Tutorial is the only encounter rescued by screaming.
    assert dayloop_combat_choice(options, tutorial=True)["id"] == "r-scream"
    # Random encounters must make progress; screaming at the rear-courtyard dog
    # leaves combat live for the whole round budget.
    assert dayloop_combat_choice(options)["id"] == "r-attack"
    # Man-combat encounters expose struggle/defiant actions before screaming.
    struggle_options = [
        {"id": "r-struggle", "label": "挣扎 |"},
        {"id": "r-scream", "label": "尖叫 |"},
    ]
    assert dayloop_combat_choice(struggle_options)["id"] == "r-struggle"
    hit_options = [
        {"id": "r-hit", "label": "击打 |"},
        {"id": "r-scream", "label": "尖叫 |"},
    ]
    assert dayloop_combat_choice(hit_options)["id"] == "r-hit"
    # Re-clicking the pre-checked default radio is a DOM no-op, so prefer an
    # unchecked control even when it appears later in the DOM.
    checked_first = [
        {"id": "r-attack-checked", "label": "攻击 |", "checked": True},
        {"id": "r-attack", "label": "攻击 |", "checked": False},
    ]
    assert dayloop_combat_choice(checked_first)["id"] == "r-attack"
    assert dayloop_combat_choice([{"id": "r1", "label": "Attack"}] )["id"] == "r1"
    assert dayloop_combat_choice([{"id": "", "label": "尖叫"}]) is None
    assert dayloop_combat_choice([]) is None


def test_dayloop_scripted_pick_follows_the_tutorial_chain() -> None:
    finish = [
        {"text": "无关", "visible": True, "data": "Elsewhere", "cls": ""},
        {"text": "(1) 调情", "visible": True, "data": "Tutorial Flirt", "cls": ""},
    ]
    assert dayloop_scripted_pick("Tutorial Finish", finish)["data_passage"] == "Tutorial Flirt"

    exit_links = [
        {"text": "(1) 继续", "visible": True, "data": "Domus Street", "cls": ""}
    ]
    assert dayloop_scripted_pick("Tutorial Flirt", exit_links)["data_passage"] == "Domus Street"
    # 普通 passage 与尚未打完的 Tutorial 战斗页都不归它管。
    assert dayloop_scripted_pick("Domus Street", exit_links) is None
    assert dayloop_scripted_pick("Tutorial", exit_links) is None
    assert dayloop_scripted_pick("Tutorial Finish", []) is None


def test_dayloop_prep_uses_the_string_combat_control_mode() -> None:
    """``$options.combatControls`` 是控制类型字符串，写成数字会让动作列表整页报错。"""
    assert 'V.options.combatControls = "radio"' in DAYLOOP_PREP
    assert "combatControls = 0" not in DAYLOOP_PREP


def test_dayloop_prep_uses_next_school_term_getter_not_bare_function() -> None:
    """``getNextSchoolTermStartDate(date)`` 需要参数；无参调用会落到 year 1。"""
    assert "T.nextSchoolTermStartDate" in DAYLOOP_PREP
    assert "T.getNextSchoolTermStartDate()" not in DAYLOOP_PREP


def test_dayloop_prep_owns_school_swimwear_and_clears_stale_outfit_choice() -> None:
    """合成夹具要有真实泳装物品；旧的 outfit 索引不能带进换衣流程。"""
    assert 'ensureSchoolWardrobeItem("under_upper", "school swimsuit")' in DAYLOOP_PREP
    assert 'ensureSchoolWardrobeItem("under_lower", "school swimsuit bottom")' in DAYLOOP_PREP
    assert "ensureWardrobeItem(V.wardrobes?.schoolGirls" in DAYLOOP_PREP
    assert "ensureWardrobeItem(V.wardrobes?.schoolBoys" in DAYLOOP_PREP
    assert 'V.wear_outfit = "none"' in DAYLOOP_PREP
    assert "outfit.some((item) => item?.type?.includes?.(\"swim\")" in DAYLOOP_PREP


def test_dayloop_prep_seeds_safe_danger_on_every_passage_start() -> None:
    """Hallways 会在渲染末尾重置 eventskip；安全危险值必须挂在 passage start。"""
    assert '":passagestart"' in DAYLOOP_PREP
    assert "S.suppressDayloopDanger = true" in DAYLOOP_PREP
    assert "SC.State.temporary.danger = 1" in DAYLOOP_PREP


def test_dayloop_driver_never_pre_sets_debug_before_prep() -> None:
    """驱动器不得先写 ``$debug=1``：prep 会把它当作原值还原，导致整天 debug 常开。"""
    source = inspect.getsource(run_dayloop)
    assert "V.debug = 1" not in source
    assert "V.debug=1" not in source


def test_dayloop_plays_the_scripted_tutorial_combat_once_and_never_counts_it() -> None:
    page = _DayloopEncounterFakePage()

    report = run_dayloop(page, max_clicks_per_step=2, timeout_ms=50, settle_ms=0)

    phases = {(r.get("phase"), r["status"]) for r in report["records"]}
    assert ("combat", "progress") in phases
    assert ("tutorial", "progress") in phases
    # 逃跑优先：尖叫让教程以“获救”结束，而不是把攻击打满。
    assert page.radio_clicks == ["radio-scream"]
    # 遭遇回合与脚本续接都不是任何一步的完成。
    assert report["ok_clicks"] == 0
    assert report["verdict"] == "soft_fail"


def test_roundtrip_digest_diff_ignores_volatile_keys() -> None:
    before = {"money": "number:500", "passageCount": "number:10", "rng": "number:1"}
    after = {"money": "number:500", "passageCount": "number:11", "rng": "number:2"}

    diff = roundtrip_digest_diff(before, after)

    assert diff["core_equal"] is True
    assert diff["exact_equal"] is False
    assert diff["core_differences"] == []
    assert {item["path"] for item in diff["differences"]} == {"passageCount", "rng"}
    assert "passageCount" in ROUNDTRIP_VOLATILE_KEYS


def test_roundtrip_digest_diff_flags_real_state_change() -> None:
    before = {"money": "number:500", "pain": "number:0"}
    after = {"money": "number:499", "pain": "number:0"}

    diff = roundtrip_digest_diff(before, after)

    assert diff["core_equal"] is False
    assert diff["core_differences"] == ["money"]
    assert diff["differences"] == [
        {"path": "money", "before": "number:500", "after": "number:499"}
    ]


def test_roundtrip_digest_diff_sample_keys_scope_the_core_comparison() -> None:
    before = {"money": "number:500", "pain": "number:0", "BeastList": "array:14"}
    after = {"money": "number:500", "pain": "number:3", "BeastList": "array:15"}

    sampled = roundtrip_digest_diff(before, after, sample_keys=("money",))
    assert sampled["core_equal"] is True
    assert sampled["core_differences"] == []
    assert sampled["exact_equal"] is False

    caught = roundtrip_digest_diff(before, after, sample_keys=("money", "pain"))
    assert caught["core_equal"] is False
    assert caught["core_differences"] == ["pain"]


# --------------------------------------------------------------------------- #
# Row selection, CLI, reports
# --------------------------------------------------------------------------- #


def _manifest_rows() -> list[dict]:
    return [
        {"section": "Main", "index": 0, "kind": "link", "target": "Bedroom"},
        {"section": "Main", "index": 1, "kind": "separator", "target": None},
        {"section": "Main", "index": 2, "kind": "link", "target": "Test"},
        {"section": "Events", "index": 0, "kind": "link", "target": "Molestation"},
        {"section": "Events", "index": 1, "kind": "link", "target": "Struggle"},
        {"section": "Events", "index": 2, "kind": "link", "target": "The Pod"},
    ]


def test_select_rows_filters_sections_and_limit() -> None:
    rows = _manifest_rows()
    assert [r["target"] for r in select_rows(rows, sections=["Events"], limit=2)] == [
        "Molestation",
        "Struggle",
    ]
    assert [r["target"] for r in select_rows(rows, limit=3)] == ["Bedroom", "Test", "Molestation"]
    # 分隔行绝不能进入 sweep
    assert all(r["kind"] == "link" for r in select_rows(rows, limit=99))


def test_select_rows_sample_is_seed_stable() -> None:
    rows = _manifest_rows()
    first = select_rows(rows, sample=3, seed=7)
    second = select_rows(rows, sample=3, seed=7)
    other = select_rows(rows, sample=3, seed=8)

    assert [r["target"] for r in first] == [r["target"] for r in second]
    assert [r["target"] for r in other] != [r["target"] for r in first] or len(first) == len(rows)
    assert len(first) == 3


def test_default_out_dir_and_baseline_paths() -> None:
    assert default_out_dir("scenarios", "20261004") == Path(".local/sweep/scenarios-20261004")
    assert default_out_dir("all", "20261004") == Path(".local/sweep/all-20261004")
    assert baseline_path(Path(".local/fixtures/base-1004.json"), "scenarios") == Path(
        ".local/sweep/baselines/scenario-sweep-base-1004.json"
    )
    assert baseline_path(Path(".local/fixtures/base-1004.json"), "dayloop") == Path(
        ".local/sweep/baselines/dayloop-base-1004.json"
    )
    assert manifest_baseline_path(Path(".local/fixtures/base-1004.json")) == Path(
        ".local/sweep/baselines/scenario-manifest-base-1004.json"
    )


def test_parse_args_defaults() -> None:
    args = parse_args(["artifact.html"])

    assert args.target == Path("artifact.html")
    assert args.suite == "scenarios"
    assert args.out is None
    assert args.fixture == DEFAULT_FIXTURE
    assert args.manifest_out == DEFAULT_MANIFEST_OUT
    assert args.static_check is True
    assert args.seed == 20261004
    assert args.timeout_ms == 20000
    assert args.limit is None
    assert args.sample is None
    assert args.section is None
    assert args.baseline is None
    assert args.save_baseline is False
    assert args.headful is False


def test_parse_args_overrides() -> None:
    args = parse_args(
        [
            "artifact.html",
            "--suite",
            "all",
            "--out",
            "reports/x",
            "--section",
            "Events",
            "--section",
            "Character",
            "--limit",
            "40",
            "--timeout-ms",
            "5000",
            "--no-static-check",
            "--headful",
            "--baseline",
            "base.json",
            "--save-baseline",
            "--dayloop-max-clicks",
            "5",
        ]
    )

    assert args.suite == "all"
    assert args.out == Path("reports/x")
    assert args.section == ["Events", "Character"]
    assert args.limit == 40
    assert args.timeout_ms == 5000
    assert args.static_check is False
    assert args.headful is True
    assert args.baseline == Path("base.json")
    assert args.save_baseline is True
    assert args.dayloop_max_clicks == 5


def test_parse_args_rejects_unknown_suite() -> None:
    with pytest.raises(SystemExit):
        parse_args(["artifact.html", "--suite", "nonsense"])


def _sample_report() -> dict:
    return {
        "tool": "scenario_sweep",
        "target": "artifact.html",
        "html_path": "artifact.html",
        "suite": "scenarios",
        "fixture": {"path": ".local/fixtures/base-1004.json"},
        "started_at": "2026-10-04T10:00:00",
        "finished_at": "2026-10-04T10:05:00",
        "manifest": {
            "ok": True,
            "summary": {
                "rows": 363,
                "clickable": 331,
                "separators": 32,
                "by_section": dict(EXPECTED_MANIFEST["sections"]),
            },
            "cross_check": {"ok": True, "counts_match": True, "drift": []},
            "drift": {"ok": True, "differences": []},
        },
        "results": [
            {
                "section": "Events",
                "index": 45,
                "label": "被黑狼威胁",
                "target": "Forest Wolf Molestation",
                "resolved_target": "Forest Wolf Molestation",
                "verdict": "hard_fail",
                "detail": "landed on 'Forest' instead of 'Forest Wolf Molestation'",
                "spec": {"ok": False, "hard_failures": ["combat_on: false"]},
            },
            {
                "section": "Main",
                "index": 0,
                "label": "家",
                "target": "Bedroom",
                "resolved_target": "Bedroom",
                "verdict": "ok",
                "detail": "",
                "spec": None,
            },
        ],
        "verdict_counts": {"ok": 1, "soft_fail": 0, "hard_fail": 1, "fixture_insufficient": 0, "not_applicable": 0},
        "dayloop": None,
        "fatal_error": None,
    }


def test_write_report_writes_json_and_markdown(tmp_path: Path) -> None:
    report = _sample_report()
    diff = {
        "new_regressions": [
            {
                "key": "Events#45",
                "target": "Forest Wolf Molestation",
                "was": "ok",
                "now": "hard_fail",
            }
        ],
        "fixed": [],
        "changed": [],
        "new_scenarios": [{"key": "Events#99", "verdict": "ok"}],
        "manifest": {"rows": {"baseline": 363, "current": 364}, "changed": True},
    }

    md_path = write_report(report, tmp_path, diff)

    json_path = tmp_path / "scenario-sweep.json"
    assert json_path.exists()
    assert md_path.exists()
    assert md_path.name == "scenario-sweep.md"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    for key in ("tool", "manifest", "results", "verdict_counts"):
        assert key in payload
    assert payload["results"][0]["verdict"] == "hard_fail"

    markdown = md_path.read_text(encoding="utf-8")
    assert "# DOL-X scenario sweep report" in markdown
    assert "| hard_fail | 1 |" in markdown
    assert "## hard failures (1)" in markdown
    assert "Events#45" in markdown
    assert "## baseline diff" in markdown
    assert "new regressions: **1**" in markdown


def test_write_report_includes_dayloop_table(tmp_path: Path) -> None:
    report = _sample_report()
    report["dayloop"] = {
        "verdict": "soft_fail",
        "clicks": 2,
        "ok_clicks": 1,
        "fallback_clicks": 0,
        "stalled_clicks": 0,
        "not_applicable": 1,
        "time_advance_hours": 2.5,
        "time_method": "Time.date.getTime()",
        "location_switches": 1,
        "save_roundtrip": {"ok": False, "method": None},
        "records": [
            {
                "step": "起床",
                "passage_before": "Orphanage Intro",
                "passage_after": "Bedroom",
                "clicked_text": "(1) 继续",
                "status": "ok",
            },
            {
                "step": "洗漱",
                "passage_before": "Bedroom",
                "passage_after": "Bedroom",
                "clicked_text": None,
                "status": "not_applicable",
            },
        ],
        "assertions": [
            {"name": "time_advance>=16h", "ok": False, "detail": "2.50h"},
            {"name": "no_hard_errors", "ok": True, "detail": "0 hard errors"},
        ],
    }

    md_path = write_report(report, tmp_path, None)
    markdown = md_path.read_text(encoding="utf-8")

    assert "## dayloop - soft_fail" in markdown
    assert "| 起床 | Orphanage Intro | Bedroom | (1) 继续 | ok |" in markdown
    assert "fallback=0" in markdown
    assert "[FAIL] time_advance>=16h" in markdown
