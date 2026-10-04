"""tools/env_matrix.py（引擎 A：环境矩阵扫描）的单元测试。

这些测试刻意不依赖浏览器与网络，只覆盖纯逻辑部分：
- contexts_for_tier(): daily = 8 个具名上下文，full = 4 个
- scan_env_sensitive(): 环境敏感 passage 的静态口径与命中统计
- expand_matrix()/plan_summary()/dry_plan_lines(): 矩阵展开、抽样与 dry-plan
- apply_context()/evaluate_checks(): 注入 + 读回校验的 fail-closed 判定
- classify_result(): 五档判定 + 落点断言 + 缺失变量提取
- write_report()/diff_against_baseline(): 报告与基线 diff 输出
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.env_matrix import (
    BLOOD_MOON_NIGHT,
    SPRING_CLEAR,
    VERDICTS,
    apply_context,
    baseline_path,
    classify_result,
    context_payload,
    contexts_for_tier,
    default_out_dir,
    diff_against_baseline,
    dry_plan_lines,
    evaluate_checks,
    expand_matrix,
    extract_missing_vars,
    plan_summary,
    read_context,
    scan_env_sensitive,
    write_report,
)
from tools.passage_sweep import Passage


def _passage(name: str, body: str) -> Passage:
    return Passage(name=name, body=body)


SAMPLE_PASSAGES = [
    _passage("SnowScene", "<<if Weather.isSnow>>It is snowing<</if>>"),
    _passage("SeasonScene", "<<if Time.season is 'winter'>>Winter<</if>>"),
    _passage("PlainScene", "Just a quiet room with a chair."),
]


def _readback(**overrides: object) -> dict:
    """A clean spring-morning read-back, with per-test overrides."""
    data: dict = {
        "ok": True,
        "errors": [],
        "time": {
            "year": 2026,
            "month": 4,
            "day": 15,
            "hour": 8,
            "minute": 0,
            "monthName": "April",
            "monthDay": 15,
            "lastDayOfMonth": 30,
            "isLastDayOfMonth": False,
            "dayState": "day",
            "season": "spring",
            "isBloodMoon": False,
            "schoolDay": False,
            "schoolTime": False,
            "timeStamp": 1,
        },
        "weather": {
            "name": "clear",
            "value": 0,
            "precipitation": "none",
            "isSnow": False,
            "isFreezing": False,
            "temperature": 10.0,
            "bloodMoon": False,
            "skyState": "day",
        },
        "vars": {"halloween": None, "christmas": None, "moonstate": None},
    }
    for key, value in overrides.items():
        if key in ("time", "weather", "vars"):
            data[key].update(value)
        else:
            data[key] = value
    return data


class FakePage:
    """Minimal Playwright page stand-in: records evaluate calls, replays responses."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, object]] = []

    def evaluate(self, js: str, arg: object = None) -> object:
        self.calls.append((js, arg))
        if not self.responses:
            raise AssertionError("FakePage ran out of canned responses")
        return self.responses.pop(0)


# --------------------------------------------------------------------------- #
# context matrix
# --------------------------------------------------------------------------- #


def test_contexts_for_tier_daily_is_eight_and_full_is_four() -> None:
    daily = contexts_for_tier("daily")
    full = contexts_for_tier("full")

    assert len(daily) == 8
    assert len(full) == 4
    assert len({ctx.key for ctx in daily}) == 8
    assert {ctx.key for ctx in full} == {
        "day-clear",
        "night-rain",
        "winter-snow",
        "bloodmoon-night",
    }
    assert {"halloween-night", "christmas-morning", "school-day"} <= {
        ctx.key for ctx in daily
    }


def test_contexts_for_tier_rejects_unknown_tier() -> None:
    with pytest.raises(SystemExit):
        contexts_for_tier("weekly")


def test_context_payload_projects_spec_fields() -> None:
    payload = context_payload(BLOOD_MOON_NIGHT)

    assert payload["last_day_of_month"] is True
    assert payload["month"] == 7
    assert payload["hour"] == 22
    assert payload["set_vars"] == {"moonstate": "evening"}
    # 未设置的字段必须是 None/False，不能被误当作"要改这些值"
    assert payload["weather"] is None
    assert payload["temperature"] is None


# --------------------------------------------------------------------------- #
# static scan
# --------------------------------------------------------------------------- #


def test_scan_env_sensitive_matches_code_tokens_not_prose_only() -> None:
    kept, stats = scan_env_sensitive(SAMPLE_PASSAGES)

    assert [p.name for p in kept] == ["SnowScene", "SeasonScene"]
    assert stats["scanned"] == 3
    assert stats["hit_count"] == 2
    assert "PlainScene" not in stats["matches"]


def test_scan_env_sensitive_reports_per_pattern_hits() -> None:
    _, stats = scan_env_sensitive(SAMPLE_PASSAGES)

    # SnowScene: Weather.isSnow -> weather + storm_snow_ice
    # SeasonScene: Time.season -> season + time_clock
    assert stats["per_pattern"] == {
        "weather": 1,
        "storm_snow_ice": 1,
        "season": 1,
        "time_clock": 1,
        "day_state": 0,
        "sun_cycle": 0,
        "time_distortion": 0,
        "holiday": 0,
    }


# --------------------------------------------------------------------------- #
# matrix expansion / dry plan
# --------------------------------------------------------------------------- #


def test_expand_matrix_daily_cross_product_and_ordering() -> None:
    executions = expand_matrix(SAMPLE_PASSAGES, contexts_for_tier("daily"))

    assert len(executions) == 3 * 8
    pairs = {(e.context, e.name) for e in executions}
    assert pairs == {
        (ctx.key, p.name) for ctx in contexts_for_tier("daily") for p in SAMPLE_PASSAGES
    }
    # context-major 排序：同一 context 的执行条都连续
    seen: list[str] = []
    for execution in executions:
        if not seen or seen[-1] != execution.context:
            seen.append(execution.context)
    assert len(seen) == len(set(seen)) == 8


def test_expand_matrix_limit_is_seeded_and_reproducible() -> None:
    contexts = contexts_for_tier("daily")
    first = expand_matrix(SAMPLE_PASSAGES, contexts, limit=5, seed=7)
    again = expand_matrix(SAMPLE_PASSAGES, contexts, limit=5, seed=7)
    other = expand_matrix(SAMPLE_PASSAGES, contexts, limit=5, seed=8)

    assert len(first) == 5
    assert [(e.context, e.name) for e in first] == [(e.context, e.name) for e in again]
    assert len({(e.context, e.name) for e in first}) == 5
    assert len(other) == 5
    # 抽样结果必须是全矩阵的子集
    full = {(e.context, e.name) for e in expand_matrix(SAMPLE_PASSAGES, contexts)}
    assert {(e.context, e.name) for e in first} <= full


def test_expand_matrix_limit_above_matrix_keeps_everything() -> None:
    contexts = contexts_for_tier("full")
    executions = expand_matrix(SAMPLE_PASSAGES, contexts, limit=999)

    assert len(executions) == 3 * 4


def test_plan_summary_and_dry_plan_lines_report_matrix_stats() -> None:
    contexts = contexts_for_tier("daily")
    executions = expand_matrix(SAMPLE_PASSAGES, contexts, limit=6, seed=1)
    summary = plan_summary(
        tier="daily", passages=SAMPLE_PASSAGES, contexts=contexts, executions=executions
    )
    _, stats = scan_env_sensitive(SAMPLE_PASSAGES)
    lines = dry_plan_lines(
        tier="daily",
        all_passages=SAMPLE_PASSAGES,
        env_passages=SAMPLE_PASSAGES[:2],
        env_stats=stats,
        contexts=contexts,
        executions=executions,
        limit=6,
        seed=1,
    )

    assert summary["matrix_size"] == 24
    assert summary["execution_count"] == 6
    text = "\n".join(lines)
    assert "dry-plan tier=daily" in text
    # daily 档的矩阵基数是环境敏感 passage（2 条），而不是全量 3 条
    assert "2 passages x 8 contexts = 16 executions" in text
    assert "env-sensitive=2" in text
    assert "limit=6 seed=1 -> 6 executions" in text


# --------------------------------------------------------------------------- #
# read-back / injection
# --------------------------------------------------------------------------- #


def test_evaluate_checks_ok_when_all_required_checks_pass() -> None:
    ok, unmet = evaluate_checks(_readback(), SPRING_CLEAR)

    assert ok is True
    assert unmet == []


def test_evaluate_checks_fail_closed_on_mismatch() -> None:
    readback = _readback(time={"hour": 9, "season": "winter"})

    ok, unmet = evaluate_checks(readback, SPRING_CLEAR)

    assert ok is False
    failed = {item["path"] for item in unmet}
    assert failed == {"time.hour", "time.season"}


def test_evaluate_checks_fail_closed_on_error_readback() -> None:
    ok, unmet = evaluate_checks({"ok": False, "errors": ["boom"]}, SPRING_CLEAR)

    assert ok is False
    assert unmet[0]["actual"] == ["boom"]


def test_read_context_uses_page_evaluate() -> None:
    canned = _readback()
    page = FakePage([canned])

    result = read_context(page)

    assert result == canned
    assert len(page.calls) == 1
    assert "window.Time" in page.calls[0][0]


def test_apply_context_payload_and_readback_roundtrip() -> None:
    page = FakePage([{"applied": ["timeTravel:2026-4-15T8:0"], "errors": []}, _readback()])

    ok, unmet, readback = apply_context(page, SPRING_CLEAR)

    assert ok is True
    assert unmet == []
    assert readback["weather"]["name"] == "clear"
    payload = page.calls[0][1]
    assert payload["month"] == 4 and payload["day"] == 15 and payload["hour"] == 8
    assert payload["weather"] == "clear"


def test_apply_context_fail_closed_when_setup_throws() -> None:
    page = FakePage([{"applied": [], "errors": ["Time.timeTravel exploded"]}])

    ok, unmet, _readback_data = apply_context(page, SPRING_CLEAR)

    assert ok is False
    assert unmet[0]["check"] == "setup"


def test_apply_context_fail_closed_when_readback_mismatches() -> None:
    page = FakePage([{"applied": [], "errors": []}, _readback(time={"hour": 23})])

    ok, unmet, _readback_data = apply_context(page, SPRING_CLEAR)

    assert ok is False
    assert unmet[0]["path"] == "time.hour"


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #


def _probe(**overrides: object) -> dict:
    probe: dict = {
        "passage": "Wanted",
        "done": True,
        "errors": [],
        "textLen": 42,
        "linkCount": 2,
        "childCount": 1,
        "hasPassageNode": True,
    }
    probe.update(overrides)
    return probe


def test_classify_result_ok_on_clean_landing() -> None:
    status, reason, missing, redirect = classify_result(
        "Wanted", "Wanted", _probe(), timed_out=False
    )

    assert status == "ok"
    assert reason == ""
    assert missing == []
    assert redirect is False


def test_classify_result_soft_fail_on_redirect() -> None:
    status, reason, _missing, redirect = classify_result(
        "Wanted", "Wanted", _probe(passage="Somewhere_Else"), timed_out=False
    )

    assert status == "soft_fail"
    assert "redirected" in reason
    assert redirect is True


def test_classify_result_fixture_insufficient_extracts_missing_vars() -> None:
    probe = _probe(
        errors=[
            {"kind": "engine.play.throw", "message": "'schoolstate' is not defined"},
            {"kind": "error", "message": "Cannot read properties of undefined (reading 'x')"},
        ]
    )

    status, _reason, missing, redirect = classify_result("Wanted", "Wanted", probe, timed_out=False)

    assert status == "fixture_insufficient"
    assert missing == ["schoolstate", "x"]
    assert redirect is False


def test_classify_result_hard_fail_on_real_engine_error() -> None:
    probe = _probe(errors=[{"kind": "engine.play.throw", "message": "totally broken"}])

    status, reason, _missing, _redirect = classify_result(
        "Wanted", "Wanted", probe, timed_out=False
    )

    assert status == "hard_fail"
    assert "totally broken" in reason


def test_classify_result_not_applicable_for_engine_passages() -> None:
    status, reason, _missing, _redirect = classify_result(
        "StoryInit", "StoryInit", _probe(passage=None), timed_out=False
    )

    assert status == "not_applicable"
    assert "not a playable scene" in reason


def test_extract_missing_vars_dedupes_in_order() -> None:
    errors = [
        {"message": "'foo' is not defined"},
        {"message": "'foo' is not defined"},
        {"message": "'bar' is not defined"},
        {"message": "no match here"},
    ]

    assert extract_missing_vars(errors) == ["foo", "bar"]


# --------------------------------------------------------------------------- #
# report / baseline
# --------------------------------------------------------------------------- #


def _report_fixture(tier: str = "daily") -> dict:
    return {
        "tool": "env_matrix",
        "tier": tier,
        "target": "Degrees of Lewdity.html",
        "started_at": "2026-10-05T10:00:00",
        "finished_at": "2026-10-05T10:05:00",
        "fixture": {"source": ".local/fixtures/base-1004.json", "keys": 780, "sha256": "a" * 64},
        "meta": {
            "sha256": "b" * 64,
            "env_sensitive_rule": {
                "hit_count": 700,
                "reference_hit_count": 886,
                "drift_note": "drift recorded",
            },
            "plan": {"passage_count": 700, "context_count": 8, "execution_count": 5600},
        },
        "contexts": [
            {"key": "spring-morning-clear", "label": "春晨晴", "verified": True,
             "reads_ok": 3, "reads_failed": 0},
            {"key": "bloodmoon-night", "label": "血月夜", "verified": True,
             "reads_ok": 3, "reads_failed": 0},
        ],
        "plan": {"passage_count": 700, "context_count": 8, "execution_count": 5600},
        "verdict_counts": {
            "ok": 1,
            "soft_fail": 1,
            "hard_fail": 1,
            "fixture_insufficient": 1,
            "not_applicable": 1,
        },
        "results": [
            {"name": "Good", "context": "spring-morning-clear", "status": "ok", "reason": ""},
            {"name": "SoftOne", "context": "spring-morning-clear", "status": "soft_fail",
             "reason": "redirected: SoftOne -> Elsewhere"},
            {"name": "HardOne", "context": "bloodmoon-night", "status": "hard_fail",
             "reason": "boom"},
            {"name": "FixtureOne", "context": "bloodmoon-night",
             "status": "fixture_insufficient", "reason": "'x' is not defined",
             "missing_vars": ["x"]},
            {"name": "StoryInit", "context": "bloodmoon-night", "status": "not_applicable",
             "reason": "engine/system passage is not a playable scene"},
        ],
    }


def test_write_report_creates_named_json_and_markdown(tmp_path: Path) -> None:
    diff = {
        "regressions": [{"key": "bloodmoon-night#Wanted", "was": "ok", "now": "hard_fail"}],
        "fixed": [],
        "changed": [],
        "unseen_in_baseline": [{"key": "spring-morning-clear#Good", "verdict": "ok"}],
    }

    md_path = write_report(_report_fixture(), tmp_path, diff)

    assert md_path == tmp_path / "env-daily-report.md"
    json_path = tmp_path / "env-daily-report.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["tier"] == "daily"
    assert data["verdict_counts"]["not_applicable"] == 1

    md = md_path.read_text(encoding="utf-8")
    for verdict in VERDICTS:
        assert f"| {verdict} |" in md
    assert "## contexts" in md
    assert "| bloodmoon-night | 血月夜 | True | 3 | 0 |" in md
    assert "## baseline diff" in md
    assert "new regressions: **1**" in md
    assert "`bloodmoon-night#Wanted`: ok -> hard_fail" in md
    assert "## soft failures (1)" in md
    assert "## fixture_insufficient (1)" in md
    assert "[missing: x]" in md


def test_write_report_omits_diff_section_without_baseline(tmp_path: Path) -> None:
    md = write_report(_report_fixture(), tmp_path, None).read_text(encoding="utf-8")

    assert "## baseline diff" not in md


def test_diff_reports_only_new_regressions_and_keys_by_context() -> None:
    baseline = {
        "results": [
            {"name": "A", "context": "spring-morning-clear", "status": "ok"},
            {"name": "A", "context": "bloodmoon-night", "status": "ok"},
            {"name": "B", "context": "spring-morning-clear", "status": "hard_fail"},
            {"name": "C", "context": "spring-morning-clear", "status": "fixture_insufficient"},
        ]
    }
    report = {
        "results": [
            {"name": "A", "context": "spring-morning-clear", "status": "ok"},
            {"name": "A", "context": "bloodmoon-night", "status": "hard_fail"},
            {"name": "B", "context": "spring-morning-clear", "status": "ok"},
            {"name": "C", "context": "spring-morning-clear", "status": "hard_fail"},
            {"name": "D", "context": "spring-morning-clear", "status": "soft_fail"},
        ]
    }

    diff = diff_against_baseline(report, baseline)

    # 同一个 passage 在不同 context 下互不干扰：A 只在 bloodmoon-night 下回归
    assert diff["regressions"] == [
        {"key": "bloodmoon-night#A", "was": "ok", "now": "hard_fail"},
        {"key": "spring-morning-clear#C", "was": "fixture_insufficient", "now": "hard_fail"},
    ]
    assert diff["fixed"] == [
        {"key": "spring-morning-clear#B", "was": "hard_fail", "now": "ok"}
    ]
    assert diff["unseen_in_baseline"] == [
        {"key": "spring-morning-clear#D", "verdict": "soft_fail"}
    ]
    assert diff["changed"] == []


def test_diff_treats_soft_fail_to_ok_as_fixed_and_ok_to_soft_as_regression() -> None:
    baseline = {"results": [{"name": "A", "context": "x", "status": "soft_fail"}]}
    report = {"results": [{"name": "A", "context": "x", "status": "ok"}]}

    assert diff_against_baseline(report, baseline)["fixed"] == [
        {"key": "x#A", "was": "soft_fail", "now": "ok"}
    ]

    reversed_diff = diff_against_baseline(baseline, report)
    assert reversed_diff["regressions"] == [
        {"key": "x#A", "was": "ok", "now": "soft_fail"}
    ]


def test_default_out_dir_and_baseline_paths() -> None:
    assert default_out_dir("daily", day="1005") == Path(".local/sweep/env-1005")
    assert baseline_path("full") == Path(".local/sweep/baselines/env-full.json")
