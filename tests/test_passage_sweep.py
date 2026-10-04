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
