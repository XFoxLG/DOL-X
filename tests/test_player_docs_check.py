"""Tests for the player-facing document checker (tools/player_docs_check.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import player_docs_check as pd


MUST_FAIL: list[tuple[str, str]] = [
    ("hash", "验收对象 sha256 `280077aa` 一致。"),
    ("hash", "ZIP 115,012,853 字节。"),
    ("ci_run", "来自全四码干跑（run 38536372032）。"),
    ("repo_path", "见 tools/sweep_flow_assertions.py。"),
    ("internal_term", "包内 39 个 payload，target manifest 无缺失。"),
    ("internal_term", "发版前对 release note 做 fail-closed 校验。"),
    ("code_ident", "调用 faceStyleSrcFn(name, { variant: true })。"),
    ("code_symbol", "切换脸型后 $facestyle 被置成 default。"),
    ("asset_file", "缺少 img/face/碱性糖改脸/Q萌一号/eyes.png。"),
    ("internal_status", "状态记录为 accepted_upstream + visual_incomplete。"),
    ("internal_tool", "combat_sweep 的 hard_fail 已重新归因。"),
    ("debug_jargon", "logcat 无 FATAL / ANR / AndroidRuntime。"),
]

MUST_PASS: list[str] = [
    "**框架 4.1.13 → 4.1.14** —— 上游 4.2.9 有三个会直接影响 AU 版的问题。",
    "作弊拓展更新到 v1.20；更长遭遇战 1.0.1；言灵作弊集 1.0.1。",
    "游戏本体：DoL 0.5.11.9 · 汉化：1.0.0a。",
    "安卓端应用名 `DoL XFox`，包名 `com.vrelnir.dol.xfox`。",
    "后缀 `.apk` 为安卓版，`.zip` 为浏览器版。",
    "「选项 → 模组设置 → 秋枫白桦框架 → 桌宠遮罩分割线」拖到 0px。",
    "拿到 8 个脸型的截图对比，眼睛颜色恢复正常。",
    "用真实点击连走三段（床上 → 睡觉 → 卧室 → 床上）。",
    "D.O.L.I（AI 增强，需玩家自填 API key）。",
    "完整技术细节见 [技术档案](https://github.com/XFoxLG/DOL-X/blob/vega/docs/technical/v0.5.11.9-1.0.0a-1014.md)。",
]


@pytest.mark.parametrize(("rule", "text"), MUST_FAIL)
def test_forbidden_samples_are_caught(rule: str, text: str) -> None:
    found = pd.check_text(text)
    assert found, f"expected a violation for {text!r}"
    assert rule in {v.rule for v in found}, {v.rule for v in found}


@pytest.mark.parametrize("text", MUST_PASS)
def test_player_language_passes(text: str) -> None:
    found = pd.check_text(text)
    assert not found, [(v.rule, v.match) for v in found]


def test_build_report_flags_missing_file(tmp_path: Path) -> None:
    report = pd.build_report([tmp_path / "nope.md"])
    assert report["ok"] is False
    assert report["missing"]


def test_build_report_ok_for_clean_file(tmp_path: Path) -> None:
    note = tmp_path / "clean.md"
    note.write_text("## 本次更新\n\n框架升到 4.1.14，换脸不再报错。\n", encoding="utf-8")
    report = pd.build_report([note])
    assert report["ok"] is True


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("这一版修好了桌宠消失的问题。\n", encoding="utf-8")
    dirty = tmp_path / "dirty.md"
    dirty.write_text("run 123456789 的产物 sha256 一致。\n", encoding="utf-8")
    out = tmp_path / "report.json"

    assert pd.main([str(clean)]) == 0
    assert pd.main([str(dirty)]) == 1
    assert pd.main([str(dirty), "--json", str(out)]) == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == pd.SCHEMA
    assert payload["ok"] is False
    assert pd.main([str(tmp_path / "missing.md")]) == 2
    capsys.readouterr()


def test_default_targets_cover_release_notes_and_player_changelog() -> None:
    targets = {str(p).replace("\\", "/") for p in pd.default_targets()}
    assert any(t.endswith("docs/release-notes/v0.5.11.9-1.0.0a-1014.md") for t in targets)
    assert any(t.endswith("玩家更新日志.md") for t in targets)
