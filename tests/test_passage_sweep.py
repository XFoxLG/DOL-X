"""tools/passage_sweep.py（引擎 A：本地全 passage 扫描）的单元测试。

这些测试刻意不依赖浏览器与网络，只覆盖纯逻辑部分：
- extract_passages(): 从构建产物 HTML 解析 <tw-passagedata>
- classify(): ok / soft_fail / hard_fail / fixture_insufficient 四档判定
- diff_against_baseline(): 基线对比（新增回归、修复、新 passage）
- write_report(): passage-sweep.json / passage-sweep.md 输出
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.passage_sweep import (
    Passage,
    classify,
    diff_against_baseline,
    extract_passages,
    write_report,
)


class _FakeStartupPage:
    """Minimal Playwright stand-in for ``_reach_gameplay`` unit tests."""

    def __init__(self, passage: str = "Start", clicked: bool = True) -> None:
        from tools import browser_smoke_test as bst
        from tools import passage_sweep as ps

        self._ready_script = bst._game_ready_script()
        self._interaction_script = bst._startup_interaction_script()
        self.passage = passage
        self.clicked = clicked
        self.actions = 0
        self.waits = 0
        self.evaluations = 0

    def evaluate(self, script: str, *_args):
        assert script in (self._ready_script, self._interaction_script)
        self.evaluations += 1
        if script == self._ready_script:
            return {"passage": self.passage, "ready": True}
        self.actions += 1
        return {"action": "dismiss_modal", "clicked": self.clicked, "text": None}

    def wait_for_timeout(self, _ms: int) -> None:
        self.waits += 1


def test_reach_gameplay_returns_as_soon_as_passage_leaves_startup() -> None:
    from tools import passage_sweep as ps

    page = _FakeStartupPage(passage="Bedroom")
    info = ps._reach_gameplay(page, steps=50)

    assert info["passage"] == "Bedroom"
    assert info["steps"] == 0
    assert info["actions"] == []


def test_reach_gameplay_stops_after_no_progress_limit() -> None:
    from tools import passage_sweep as ps

    page = _FakeStartupPage(passage="Start", clicked=False)
    info = ps._reach_gameplay(page, steps=500, no_progress_limit=3)

    assert info["no_progress_steps"] == 3
    assert info["steps"] == 2
    assert info["deadline_hit"] is False
    assert page.waits == 2


def test_reach_gameplay_repeated_modal_clicks_do_not_end_early() -> None:
    """CI 2026-10-07: 240 步的 modal 点击被判成"有进度"，预算耗尽而不是早停。"""
    from tools import passage_sweep as ps

    page = _FakeStartupPage(passage="Start", clicked=True)
    info = ps._reach_gameplay(page, steps=5, no_progress_limit=2)

    assert info["no_progress_steps"] == 0
    assert info["steps"] == 5
    assert len(info["actions"]) == 5


def test_reach_gameplay_respects_wall_clock_deadline(monkeypatch) -> None:
    import itertools

    from tools import passage_sweep as ps

    ticks = itertools.count()
    monkeypatch.setattr(ps.time, "monotonic", lambda: float(next(ticks)))
    page = _FakeStartupPage(passage="Start", clicked=True)
    info = ps._reach_gameplay(page, steps=100000, no_progress_limit=40, deadline_s=1e-6)

    assert info["deadline_hit"] is True
    assert info["deadline_s"] == 1e-6
    # 第一轮就跨过 deadline：不再等预算，也不点第二次
    assert info["steps"] == 0
    assert page.waits == 0


class _RepeatingDismissPage(_FakeStartupPage):
    """A start gate whose modal root keeps returning the same dismissal."""

    def __init__(self, sample: str = "confirm overlay") -> None:
        super().__init__(passage="Start", clicked=True)
        self.sample = sample
        self.skip_keys_log: list[list[str]] = []

    def evaluate(self, script: str, *args):
        assert script in (self._ready_script, self._interaction_script)
        self.evaluations += 1
        if script == self._ready_script:
            return {"passage": self.passage, "ready": True}
        options = args[0] if args else None
        self.skip_keys_log.append(list((options or {}).get("skipKeys") or []))
        self.actions += 1
        return {
            "action": "dismiss_modal",
            "clicked": True,
            "button_text": "确定",
            "root_selector": "div.overlay",
            "text_sample": self.sample,
        }


def test_startup_budgets_cover_slow_ci_cold_boot() -> None:
    """run 37536425118：12 分钟 deadline 在 37 mod 冷启动上贴边，必须放宽。"""
    from tools import passage_sweep as ps

    assert ps.STARTUP_STEPS >= 1500
    assert ps.STARTUP_DEADLINE_S >= 1140


def test_startup_repeat_key_only_for_dismiss_actions() -> None:
    from tools import passage_sweep as ps

    assert ps._startup_repeat_key({"action": "no_action"}) is None
    # Page-level confirms key on the button label, not the unstable page text.
    assert ps._startup_repeat_key({"action": "click_startup_control", "text_sample": "x"}) is None
    assert (
        ps._startup_repeat_key(
            {
                "action": "click_startup_control",
                "clicked": True,
                "button_text": "  I Understand  ",
                "text_sample": "whole page text",
            }
        )
        == "I Understand"
    )
    assert (
        ps._startup_repeat_key(
            {
                "action": "accept_framework_notice",
                "clicked": True,
                "button_text": "我已知晓",
            }
        )
        == "我已知晓"
    )
    assert ps._startup_repeat_key({"action": "dismiss_modal", "text_sample": "   "}) is None
    key = ps._startup_repeat_key(
        {"action": "dismiss_sweetalert", "text_sample": "  confirm overlay  " + "x" * 400}
    )
    assert key is not None
    assert key.startswith("confirm overlay")
    assert len(key) <= ps.STARTUP_SKIP_SAMPLE_CHARS


def test_startup_interaction_script_supports_skip_keys() -> None:
    from tools import browser_smoke_test as bst

    script = bst._startup_interaction_script()
    assert "skipKeys" in script
    assert "skipHit" in script
    assert "slice(0, 120)" in script


def test_startup_interaction_script_handles_checkbox_gated_confirm() -> None:
    """CI 37544629870：Maplebirch 欢迎框必须先勾选再点 I Understand。"""
    from tools import browser_smoke_test as bst

    script = bst._startup_interaction_script()
    assert "skipTextHit" in script
    assert "ensureGateCheckboxes" in script
    assert "all_candidates_skipped" in script
    # <<checkbox '_maplebirchNoticeVerify'>> 渲染出的真实 input id
    assert "checkbox--maplebirchnoticeverify" in script
    assert "accept_framework_notice" in script


def test_startup_consent_labels_cover_maplebirch_notice() -> None:
    from tools import browser_smoke_test as bst

    labels = bst.STARTUP_CONSENT_LABELS
    assert "I have read and understood the notice above" in labels
    assert "我已阅读并已经了解上述说明" in labels


class _RepeatingPageConfirmPage(_FakeStartupPage):
    """页面级 confirm 永远点不消失（CI 37544629870 的 I Understand 死循环）。"""

    def __init__(self, button: str = "I Understand") -> None:
        super().__init__(passage="Start", clicked=True)
        self.button = button
        self.clicked_calls = 0
        self.first_skip_call: int | None = None

    def evaluate(self, script: str, *args):
        assert script in (self._ready_script, self._interaction_script)
        self.evaluations += 1
        if script == self._ready_script:
            return {"passage": self.passage, "ready": True}
        options = args[0] if args else None
        skipped = self.button in list((options or {}).get("skipKeys") or [])
        self.actions += 1
        if skipped:
            if self.first_skip_call is None:
                self.first_skip_call = self.actions - 1
            return {
                "action": "no_action",
                "clicked": False,
                "reason": "all_candidates_skipped",
            }
        self.clicked_calls += 1
        return {
            "action": "click_startup_control",
            "clicked": True,
            "button_text": self.button,
            "text_sample": "page text that keeps changing",
        }


def test_reach_gameplay_skips_repeated_page_confirm_button() -> None:
    """同一按钮连点 25 次无效后进入 skipKeys，并由 no-progress 早停。"""
    from tools import passage_sweep as ps

    page = _RepeatingPageConfirmPage()
    info = ps._reach_gameplay(page, steps=400, no_progress_limit=40, deadline_s=0)

    assert info["skip_keys"] == ["I Understand"]
    # 25 次点击（step 0..24）+ 40 次 no-action（step 25..64）→ 第 65 次前 break
    assert info["steps"] == 25 + 40 - 1
    assert info["no_progress_steps"] == 40
    assert info["deadline_hit"] is False
    assert page.actions == 65
    assert page.clicked_calls == 25
    # 第 26 次交互（索引 25）开始带 skipKeys
    assert page.first_skip_call == 25
    assert info["actions"][-1]["clicked"] is False


def test_reach_gameplay_skips_repeated_dismissal_root() -> None:
    """同一个 root 连点 25 次无效后，把它加入 skipKeys 并继续尝试其它控件。"""
    from tools import passage_sweep as ps

    page = _RepeatingDismissPage()
    info = ps._reach_gameplay(page, steps=30, no_progress_limit=1000, deadline_s=0)

    assert info["steps"] == 30
    assert info["skip_keys"] == ["confirm overlay"]
    # 第 25 次点击触发 skip；第 26 次调用才带 skipKeys
    assert page.skip_keys_log[23] == []
    assert page.skip_keys_log[24] == []
    assert page.skip_keys_log[25] == ["confirm overlay"]
    # actions 保留 root / 按钮文本 / repeat 计数供事后归因
    assert info["actions"][0]["root"] == "div.overlay"
    assert info["actions"][0]["text"] == "确定"
    repeats = [entry.get("repeat") for entry in info["actions"]]
    assert 25 in repeats


SAMPLE_HTML = (
    "<!DOCTYPE html>\n"
    "<html><body>\n"
    '<tw-storydata name="Sample" startnode="1">\n'
    '<tw-passagedata pid="1" name="Start" tags="tag1">Hello &amp; welcome\n'
    "&lt;b&gt;bold&lt;/b&gt;</tw-passagedata>\n"
    '<tw-passagedata pid="2" name="Second &amp; Third" tags="">Line one\n'
    "Line two</tw-passagedata>\n"
    '<tw-passagedata pid="3" name="Start" tags="">duplicate body</tw-passagedata>\n'
    "</tw-storydata>\n"
    "</body></html>\n"
)


def _write_html(tmp_path: Path, text: str = SAMPLE_HTML) -> Path:
    path = tmp_path / "sample.html"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# extract_passages
# --------------------------------------------------------------------------- #


def test_extract_passages_unescapes_names_and_bodies(tmp_path: Path) -> None:
    passages, target = extract_passages(_write_html(tmp_path))
    by_name = {p.name: p for p in passages}

    # name 与 body 都由 SugarCube 存储时的 HTML 实体形式反转义回来
    assert "Second & Third" in by_name
    assert by_name["Second & Third"].body == "Line one\nLine two"
    assert by_name["Start"].body == "Hello & welcome\n<b>bold</b>"

    # 返回值是 (passage 列表, 原始目标路径) 元组
    assert isinstance(passages, list)
    assert target == tmp_path / "sample.html"


def test_extract_passages_dedupes_duplicate_names_with_first_win(tmp_path: Path) -> None:
    passages, _ = extract_passages(_write_html(tmp_path))
    starts = [p for p in passages if p.name == "Start"]

    assert len(starts) == 1
    assert starts[0].body == "Hello & welcome\n<b>bold</b>"
    assert "duplicate body" not in starts[0].body


def test_extract_passages_preserves_document_order_and_types(tmp_path: Path) -> None:
    passages, _ = extract_passages(_write_html(tmp_path))

    assert [p.name for p in passages] == ["Start", "Second & Third"]
    assert all(isinstance(p, Passage) for p in passages)


# --------------------------------------------------------------------------- #
# classify
# --------------------------------------------------------------------------- #


def _probe(**overrides: object) -> dict:
    probe: dict = {
        "passage": "Somewhere",
        "done": True,
        "errors": [],
        "textLen": 42,
        "linkCount": 3,
        "childCount": 2,
        "hasPassageNode": True,
    }
    probe.update(overrides)
    return probe


def test_classify_ok_when_render_is_clean() -> None:
    verdict, detail = classify(_probe(), landed_ok=True)

    assert verdict == "ok"
    assert detail == ""


def test_classify_ignores_non_hard_error_kinds() -> None:
    # console.error 等只记录、不参与判定，只有 HARD_ERROR_KINDS 才升级
    probe = _probe(errors=[{"kind": "console.error", "message": "noise"}])

    verdict, _ = classify(probe, landed_ok=True)

    assert verdict == "ok"


def test_classify_fixture_insufficient_for_undefined_variable() -> None:
    probe = _probe(
        errors=[
            {
                "kind": "engine.play.throw",
                "message": "'someVar' is not defined",
                "source": "Engine.play",
            }
        ]
    )

    verdict, detail = classify(probe, landed_ok=True)

    assert verdict == "fixture_insufficient"
    assert "is not defined" in detail


def test_classify_fixture_insufficient_for_cannot_read_properties() -> None:
    probe = _probe(
        errors=[
            {
                "kind": "error",
                "message": "Cannot read properties of undefined (reading 'foo')",
            }
        ]
    )

    verdict, _ = classify(probe, landed_ok=True)

    assert verdict == "fixture_insufficient"


def test_classify_fixture_insufficient_for_cannot_set_properties() -> None:
    probe = _probe(
        errors=[
            {
                "kind": "error",
                "message": (
                    "Cannot set properties of undefined (setting 'type')"
                ),
            }
        ]
    )

    verdict, _ = classify(probe, landed_ok=True)

    assert verdict == "fixture_insufficient"


def test_classify_hard_fail_for_real_exception() -> None:
    probe = _probe(
        errors=[{"kind": "engine.play.throw", "message": "unexpected internal explosion"}]
    )

    verdict, detail = classify(probe, landed_ok=True)

    assert verdict == "hard_fail"
    assert "unexpected internal explosion" in detail


def test_classify_hard_fail_when_passage_node_missing() -> None:
    verdict, detail = classify(_probe(hasPassageNode=False), landed_ok=False)

    assert verdict == "hard_fail"
    assert "no #passage node" in detail


def test_classify_fixture_error_takes_priority_over_missing_node() -> None:
    # 判定顺序：先看 hard error 是否带 fixture 标记，再看 #passage 节点
    probe = _probe(
        hasPassageNode=False,
        errors=[{"kind": "engine.play.throw", "message": "'x' is not defined"}],
    )

    verdict, _ = classify(probe, landed_ok=False)

    assert verdict == "fixture_insufficient"


def test_classify_soft_fail_on_timeout_without_done() -> None:
    probe = _probe(done=False)

    verdict, detail = classify(probe, landed_ok=True, timed_out=True)

    assert verdict == "soft_fail"
    assert "timeout" in detail


def test_classify_soft_fail_when_hook_never_fires() -> None:
    probe = _probe(done=False)

    verdict, detail = classify(probe, landed_ok=True, timed_out=False)

    assert verdict == "soft_fail"
    assert ":passagedisplay" in detail


def test_classify_soft_fail_when_rendered_empty() -> None:
    probe = _probe(textLen=0, childCount=0)

    verdict, detail = classify(probe, landed_ok=True)

    assert verdict == "soft_fail"
    assert "empty" in detail


# --------------------------------------------------------------------------- #
# diff_against_baseline
# --------------------------------------------------------------------------- #


def test_diff_reports_regressions_fixed_and_unseen() -> None:
    baseline = {
        "results": [
            {"name": "A", "verdict": "ok"},
            {"name": "B", "verdict": "hard_fail"},
            {"name": "C", "verdict": "ok"},
        ]
    }
    report = {
        "results": [
            {"name": "A", "verdict": "hard_fail"},
            {"name": "B", "verdict": "ok"},
            {"name": "C", "verdict": "ok"},
            {"name": "D", "verdict": "soft_fail"},
        ]
    }

    diff = diff_against_baseline(report, baseline)

    assert diff["regressions"] == [{"name": "A", "was": "ok", "now": "hard_fail"}]
    assert diff["fixed"] == [{"name": "B", "was": "hard_fail", "now": "ok"}]
    assert diff["unseen_in_baseline"] == [{"name": "D", "verdict": "soft_fail"}]
    # C 状态未变，不应出现在任何一档
    seen = diff["regressions"] + diff["fixed"] + diff["unseen_in_baseline"]
    assert all(entry["name"] != "C" for entry in seen)


def test_diff_treats_empty_baseline_as_all_unseen() -> None:
    report = {"results": [{"name": "A", "verdict": "ok"}]}

    diff = diff_against_baseline(report, {})

    assert diff["regressions"] == []
    assert diff["fixed"] == []
    assert diff["unseen_in_baseline"] == [{"name": "A", "verdict": "ok"}]


def test_diff_reports_severity_upgrade_between_non_ok_verdicts() -> None:
    # fixture_insufficient -> hard_fail 表示"进不去"恶化为"真渲染失败"，必须报回归
    baseline = {"results": [{"name": "A", "verdict": "fixture_insufficient"}]}
    report = {"results": [{"name": "A", "verdict": "hard_fail"}]}

    diff = diff_against_baseline(report, baseline)

    assert diff["regressions"] == [
        {"name": "A", "was": "fixture_insufficient", "now": "hard_fail"}
    ]
    assert diff["changed"] == []


def test_diff_reports_severity_downgrade_as_changed() -> None:
    baseline = {"results": [{"name": "A", "verdict": "hard_fail"}]}
    report = {"results": [{"name": "A", "verdict": "soft_fail"}]}

    diff = diff_against_baseline(report, baseline)

    assert diff["regressions"] == []
    assert diff["changed"] == [{"name": "A", "was": "hard_fail", "now": "soft_fail"}]


# --------------------------------------------------------------------------- #
# write_report
# --------------------------------------------------------------------------- #


def _report_fixture() -> dict:
    return {
        "target": "Degrees of Lewdity.html",
        "total_passages": 3,
        "swept": 3,
        "bootstrap": {"passage": "Start"},
        "fixture_bytes": 1234,
        "verdict_counts": {
            "ok": 1,
            "soft_fail": 1,
            "hard_fail": 1,
            "fixture_insufficient": 0,
        },
        "results": [
            {"name": "Good", "verdict": "ok", "detail": ""},
            {"name": "SoftOne", "verdict": "soft_fail", "detail": "never finished"},
            {"name": "HardOne", "verdict": "hard_fail", "detail": "boom"},
        ],
    }


def test_write_report_creates_json_and_markdown(tmp_path: Path) -> None:
    diff = {
        "regressions": [{"name": "A", "was": "ok", "now": "hard_fail"}],
        "fixed": [],
        "unseen_in_baseline": [{"name": "D", "verdict": "ok"}],
    }

    md_path = write_report(_report_fixture(), tmp_path, diff)

    assert md_path == tmp_path / "passage-sweep.md"
    json_path = tmp_path / "passage-sweep.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["verdict_counts"]["ok"] == 1
    assert data["target"] == "Degrees of Lewdity.html"

    md = md_path.read_text(encoding="utf-8")
    # verdict 计数表格四档齐全
    assert "| ok | 1 |" in md
    assert "| soft_fail | 1 |" in md
    assert "| hard_fail | 1 |" in md
    assert "| fixture_insufficient | 0 |" in md
    # hard_fail 明细段落
    assert "## hard_fail (1)" in md
    assert "- `HardOne` — boom" in md
    # baseline diff 段落
    assert "## baseline diff" in md
    assert "regressions (verdict got worse): **1**" in md
    assert "`A`: ok -> hard_fail" in md


def test_write_report_without_diff_omits_diff_section(tmp_path: Path) -> None:
    md_path = write_report(_report_fixture(), tmp_path, None)

    md = md_path.read_text(encoding="utf-8")
    assert "## baseline diff" not in md


# --------------------------------------------------------------------------- #
# fixture ladder helpers (--fixture / --fixture-patch / --only-file / --context)
# --------------------------------------------------------------------------- #


def test_parse_only_file_skips_blanks_comments_and_dedupes(tmp_path: Path) -> None:
    from tools.passage_sweep import parse_only_file

    path = tmp_path / "only.txt"
    path.write_text(
        "\ufeff# sealed fix-set\n\nBedroom\n  Kitchen  \nBedroom\n# trailing\n",
        encoding="utf-8",
    )

    assert parse_only_file(path) == ["Bedroom", "Kitchen"]


def test_filter_passages_reports_missing_names() -> None:
    from tools.passage_sweep import filter_passages

    passages = [Passage(name="A", body=""), Passage(name="B", body=""), Passage(name="C", body="")]

    kept, missing = filter_passages(passages, ["C", "A", "Nope"])

    # 保留文档顺序，而不是请求顺序
    assert [p.name for p in kept] == ["A", "C"]
    assert missing == ["Nope"]


def test_load_fixture_file_accepts_capture_format(tmp_path: Path) -> None:
    from tools.passage_sweep import load_fixture_file

    path = tmp_path / "capture.json"
    path.write_text(
        json.dumps({"meta": {"source": "real"}, "variables": {"a": 1}, "stats": {}}),
        encoding="utf-8",
    )

    variables, meta = load_fixture_file(path)

    assert variables == {"a": 1}
    assert meta["format"] == "capture"
    assert meta["keys"] == 1
    assert len(meta["sha256"]) == 64


def test_load_fixture_file_accepts_flat_dict(tmp_path: Path) -> None:
    from tools.passage_sweep import load_fixture_file

    path = tmp_path / "flat.json"
    path.write_text(json.dumps({"timeStamp": 12}), encoding="utf-8")

    variables, meta = load_fixture_file(path)

    assert variables == {"timeStamp": 12}
    assert meta["format"] == "flat"


def test_load_fixture_file_rejects_empty_or_non_object(tmp_path: Path) -> None:
    import pytest

    from tools.passage_sweep import load_fixture_file

    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_fixture_file(empty)

    scalar = tmp_path / "scalar.json"
    scalar.write_text("42", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_fixture_file(scalar)


def test_apply_fixture_patch_creates_nested_paths_and_list_indexes() -> None:
    from tools.passage_sweep import apply_fixture_patch

    variables = {"worn": {"upper": [{"name": "shirt"}]}}

    patched, applied = apply_fixture_patch(
        variables,
        {
            "timeDistortion": 5,
            "avery_tower": {"progress": 100, "effects": [], "stage": 3, "intro": 1},
            "worn.upper.0.name": "coat",
            "worn.upper.1": {"name": "vest"},
        },
    )

    assert patched["timeDistortion"] == 5
    assert patched["avery_tower"]["progress"] == 100
    assert patched["worn"]["upper"][0]["name"] == "coat"
    assert patched["worn"]["upper"][1] == {"name": "vest"}
    assert len(applied) == 4
    # 输入不被原地修改（deep copy）
    assert variables["worn"]["upper"][0]["name"] == "shirt"
    assert "timeDistortion" not in variables


def test_apply_fixture_patch_is_fail_closed_on_scalar_descent() -> None:
    import pytest

    from tools.passage_sweep import apply_fixture_patch

    with pytest.raises(SystemExit):
        apply_fixture_patch({"a": 1}, {"a.b": 2})
    with pytest.raises(SystemExit):
        apply_fixture_patch({"a": [1, 2]}, {"a.notdigit": 3})
    with pytest.raises(SystemExit):
        apply_fixture_patch({}, {"": 1})


def test_write_report_records_context_and_fixture_summary(tmp_path: Path) -> None:
    report = _report_fixture()
    report["context"] = "spring-morning"
    report["fixture"] = {
        "source": "fixtures/base-1004.json",
        "sha256": "a" * 64,
        "keys": 780,
        "patch": {"source": "fix8.json", "applied": ["timeDistortion"]},
    }

    md = write_report(report, tmp_path, None).read_text(encoding="utf-8")

    assert "context: `spring-morning`" in md
    assert "fixtures/base-1004.json" in md
    assert "sha256=aaaaaaaaaaaa" in md
    assert "patch=fix8.json (1 paths)" in md
