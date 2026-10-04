"""tools/save_safety_guard.py（fail-closed 存档守卫）的单元测试。

覆盖：
- LZString 解码器（用真机取回的已知向量，非人为构造）
- 五条规则各自的取证测试（故意放入假载荷时必须失败）
- 仓库本身必须干净（每次 pytest 都会跑，等于常驻门禁）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.save_safety_guard import (
    check_path,
    check_text,
    guard,
    lzstring_decompress_from_base64,
)

# 2026-10-04 真机从产物内 LZString.compressToBase64 取回的向量。
# 明文：{"id":"test","state":{"variables":{"passage":"Start"}}}
LZ_VECTOR = "N4IglgJiBcIC4FMDOcQBoQoIaJqAblgE5hYBGANsniAA5ZJJYDmCMIAynMagL79A"
LZ_VECTOR_PLAINTEXT = '{"id":"test","state":{"variables":{"passage":"Start"}}}'

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SAVE = REPO_ROOT / ".local" / "fixtures" / "selftest-roundtrip.save"

# 真实 .save 是 LZString 流 + 元数据尾巴；解码器在结束标记处停止，因此给向量
# 追加任意尾巴（这里用 A 填充）与磁盘格式同构，可用于验证"规模阈值 + 规则联动"
# 这条链路，同时不引入任何真实存档数据。
PADDED_VECTOR = LZ_VECTOR + "A" * 400


def _rules(findings: list[dict[str, str]]) -> set[str]:
    return {item["rule"] for item in findings}


# --------------------------------------------------------------------------- #
# LZString
# --------------------------------------------------------------------------- #


def test_lzstring_decodes_known_vector() -> None:
    assert lzstring_decompress_from_base64(LZ_VECTOR) == LZ_VECTOR_PLAINTEXT


def test_lzstring_tolerates_garbage() -> None:
    assert lzstring_decompress_from_base64("") is None
    # 忠实移植的 JS 语义：无法识别的字符按 0 位处理，结果可能是空串
    assert lzstring_decompress_from_base64("!!!!") in (None, "")
    assert lzstring_decompress_from_base64("AAAA") in (None, "")
    assert check_text("!!!!", "notes.txt") == []


def test_lzstring_handles_whitespace_and_newlines() -> None:
    wrapped = LZ_VECTOR[:20] + "\n" + LZ_VECTOR[20:] + "\n"
    assert lzstring_decompress_from_base64(wrapped) == LZ_VECTOR_PLAINTEXT


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


def test_save_filename_rule() -> None:
    assert _rules(check_path("saves/My Character.save")) == {"save-filename"}
    assert _rules(check_path("backup/game.sav")) == {"save-filename"}
    assert _rules(check_path("notes/save-2026.json")) == {"save-filename"}
    assert _rules(check_path("docs/TESTING_GUIDE.md")) == set()


def test_lzstring_save_rule_fires_on_real_payload_shape() -> None:
    findings = check_text(PADDED_VECTOR, "docs/innocent-looking.txt")
    assert "lzstring-save" in _rules(findings)


def test_lzstring_decoder_ignores_trailing_metadata_tail() -> None:
    """磁盘格式的尾巴不能被当成载荷内容。"""
    assert lzstring_decompress_from_base64(PADDED_VECTOR) == LZ_VECTOR_PLAINTEXT


@pytest.mark.skipif(not LOCAL_SAVE.exists(), reason="本地真机存档不在（CI 为正常情况）")
def test_lzstring_save_rule_fires_on_real_local_save() -> None:
    text = LOCAL_SAVE.read_text(encoding="utf-8", errors="replace")
    findings = check_text(text, "docs/leaked.txt")
    assert "lzstring-save" in _rules(findings)


def test_uncompressed_save_object_rule() -> None:
    payload = json.dumps({"id": "degrees-of-lewdity", "state": {"variables": {"a": 1}}})
    findings = check_text(payload, "x.json")
    assert "save-json-shape" in _rules(findings)


def test_fixture_payload_rule_fires_on_fixture_document() -> None:
    fixture = {
        "meta": {"schema": 1, "sha256": "0" * 64},
        "variables": {f"v{index}": index for index in range(60)},
        "stats": {"top_level_keys": 60},
    }
    findings = check_text(json.dumps(fixture), "docs/fixture.json")
    assert "fixture-payload" in _rules(findings)


def test_fixture_marker_alone_is_not_a_finding() -> None:
    """工具源码里出现标记字面量是正常现象，不能误报。"""
    source = 'const marker = "__dolx_type__";\n' * 3
    assert check_text(source, "tools/example.py") == []


def test_personal_path_rule_covers_windows_and_posix() -> None:
    windows = "root = " + "C:" + "\\Users\\" + "L\\" + "AppData"
    posix = "path = /home/" + "alice" + "/games"
    project = "dir = " + "E:" + "\\projects\\" + "DOL-X\\workspace"
    assert "personal-path" in _rules(check_text(windows, "a.md"))
    assert "personal-path" in _rules(check_text(posix, "a.md"))
    assert "personal-path" in _rules(check_text(project, "a.md"))


def test_personal_path_rule_ignores_placeholders() -> None:
    for placeholder in ("runner", "user", "you", "example"):
        text = "workdir: /home/" + placeholder + "/build"
        assert check_text(text, "ci.yml") == [], placeholder
    assert check_text("C:" + "\\Users\\" + "<user>\\file", "a.md") == []


# --------------------------------------------------------------------------- #
# Guard over a real tree
# --------------------------------------------------------------------------- #


def test_guard_fails_closed_on_injected_leak(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "leak.save").write_text(LZ_VECTOR, encoding="utf-8")
    (tmp_path / "docs" / "notes.md").write_text(
        "compressed: " + PADDED_VECTOR, encoding="utf-8"
    )
    fixture = {
        "meta": {"schema": 1},
        "variables": {f"v{index}": index for index in range(60)},
        "stats": {},
    }
    (tmp_path / "docs" / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    (tmp_path / "docs" / "paths.md").write_text(
        "root: " + "E:" + "\\projects\\" + "DOL-X\\workspace", encoding="utf-8"
    )

    report = guard(tmp_path, use_git=False)
    assert report["ok"] is False
    rules = _rules(report["findings"])
    assert {
        "save-filename",
        "lzstring-save",
        "fixture-payload",
        "personal-path",
    } <= rules


def test_guard_skips_local_and_workspace_in_tree_mode(tmp_path: Path) -> None:
    (tmp_path / ".local" / "fixtures").mkdir(parents=True)
    (tmp_path / ".local" / "fixtures" / "x.save").write_text(LZ_VECTOR, encoding="utf-8")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "y.save").write_text(LZ_VECTOR, encoding="utf-8")
    (tmp_path / "keep.txt").write_text("clean\n", encoding="utf-8")
    report = guard(tmp_path, use_git=False)
    assert report["ok"] is True
    assert report["scanned"] == 1


def test_repository_is_clean() -> None:
    """常驻门禁：仓库里不得出现存档、夹具载荷或本机绝对路径。"""
    report = guard(REPO_ROOT)
    details = "\n".join(
        f"{item['rule']}: {item['path']} :: {item['detail']}" for item in report["findings"]
    )
    assert report["ok"], f"save-safety guard failed:\n{details}"
    assert report["scanned"] >= 100


def test_report_formatting_round_trip(tmp_path: Path) -> None:
    from tools.save_safety_guard import format_report

    (tmp_path / "a.save").write_text(LZ_VECTOR, encoding="utf-8")
    report = guard(tmp_path, use_git=False)
    text = format_report(report)
    assert "save-safety guard" in text
    assert "FAILED" in text
    assert "a.save" in text
