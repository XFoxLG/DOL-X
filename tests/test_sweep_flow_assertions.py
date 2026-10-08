"""tools/sweep_flow_assertions.py 的单元测试（纯逻辑，不启动浏览器）。

覆盖 AU 面部扩展运行时标记判定：
- 七个必需标记（SE Widgets passage / AU_facial_expansion widget /
  Widgets Mirror 注入 / setup.SE / au_* 键 / V.SE / eyesCustomColor 步骤）
  任一缺失都必须被点名，不允许被像素测量掩盖。
- 探针源码只使用标识符级名字，绝不包含解密明文内容。
- 非 AU 产物必须如实返回 not_applicable，且不触碰页面。
"""

from __future__ import annotations

from typing import Any

from tools import sweep_flow_assertions as sfa


def _full_probe() -> dict[str, Any]:
    return {
        "errors": [],
        "seWidgetsPassage": True,
        "widgetRegistry": {"passage": True, "hasAuWidget": True, "total": 120},
        "macros": {
            "AU_facial_expansion": None,
            "SE_Canvas_add": True,
            "eyesSelector": True,
            "mouthSelector": True,
            "auSelector": True,
        },
        "mirrorHook": {"passage": True, "injectedPanel": True, "callCount": 2},
        "setupSE": {
            "present": True,
            "hasInit": True,
            "listKeys": ["au_default", "au_kiss"],
            "auKeys": ["au_default", "au_kiss"],
        },
        "seVariables": {
            "present": True,
            "keyCount": 16,
            "eyeColor": "#FF0000",
            "eyesColorEnabled": False,
            "mixFaceEnable": False,
            "hasEyesFacestyle": True,
            "hasVariantEyes": True,
            "hasMouthFacestyle": True,
            "hasVariantMouth": True,
        },
        "pipeline": {
            "isArray": True,
            "stepCount": 12,
            "hasEyesCustomColor": True,
            "hasBlendColor": True,
            "beforeBlendColor": True,
        },
    }


def test_au_se_module_gaps_empty_when_all_markers_present() -> None:
    assert sfa.au_se_module_gaps(_full_probe()) == []


def test_au_se_module_gaps_names_every_missing_marker() -> None:
    cases = (
        (("seWidgetsPassage",), None, "SE Widgets passage"),
        (("widgetRegistry", "hasAuWidget"), False, "AU_facial_expansion widget"),
        (("mirrorHook", "injectedPanel"), False, "Widgets Mirror panel hook"),
        (("setupSE", "present"), False, "setup.SE"),
        (("setupSE", "auKeys"), [], "setup.SE.faceVariantList au_* keys"),
        (("seVariables", "present"), False, "V.SE"),
        (("pipeline", "hasEyesCustomColor"), False, "Renderer eyesCustomColor step"),
    )
    for path, broken, expected in cases:
        probe = _full_probe()
        target = probe
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = broken
        gaps = sfa.au_se_module_gaps(probe)
        assert expected in gaps, (path, gaps)
        # 只应点名被破坏的那一个标记
        assert len(gaps) == 1, (path, gaps)


def test_au_se_module_gaps_tolerates_missing_probe_and_optional_fields() -> None:
    assert sfa.au_se_module_gaps(None) == ["au_se_probe_missing"]
    probe = _full_probe()
    # eyeColor / eyesColorEnabled / mixFaceEnable 是信息性字段，不参与判定
    probe["seVariables"]["eyeColor"] = None
    probe["seVariables"]["eyesColorEnabled"] = None
    probe["seVariables"]["mixFaceEnable"] = None
    probe["pipeline"]["hasBlendColor"] = False
    probe["pipeline"]["beforeBlendColor"] = None
    assert sfa.au_se_module_gaps(probe) == []


def test_au_se_probe_is_identifier_level_only() -> None:
    source = sfa.AU_SE_PROBE
    for marker in (
        "SE Widgets",
        "AU_facial_expansion",
        "Widgets Mirror",
        "faceVariantList",
        "eyesCustomColor",
        "eyeColor",
    ):
        assert marker in source
    # 探针不读取纯文本正文，也不写入任何文件/上传路径
    assert "readFile" not in source
    assert "fetch(" not in source


def test_au_se_probe_reads_the_se_widgets_registry() -> None:
    source = sfa.AU_SE_PROBE
    # ``<<widget "AU_facial_expansion">>`` is defined in the payload's own
    # ``SE Widgets`` passage, and SugarCube exposes a passage's widget registry
    # as a Map (``.has``), so the probe must not assume a plain object.
    assert "SE Widgets" in source
    assert 'typeof container.has === "function"' in source
    assert "checkedPassages" in source


class _ExplodingPage:
    def evaluate(self, *_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("non-AU artifacts must not be probed")


def test_flow_au_face_not_applicable_for_non_au_variant() -> None:
    result = sfa.flow_au_face(_ExplodingPage(), {"artifact_variant": "base"})
    assert result["status"] == sfa.NOT_APPLICABLE
    assert "not an AU artifact" in result["detail"]


def test_flow_au_face_fails_on_missing_markers_with_named_gaps() -> None:
    class _BarePage:
        def evaluate(self, script: str, *_args: Any) -> Any:  # noqa: ANN401
            assert script is sfa.AU_SE_PROBE
            return {"errors": [], "seWidgetsPassage": True}

    result = sfa.flow_au_face(_BarePage(), {"artifact_variant": "au-f"})
    assert result["status"] == sfa.FAIL
    for expected in (
        "AU_facial_expansion widget",
        "Widgets Mirror panel hook",
        "setup.SE",
        "V.SE",
        "Renderer eyesCustomColor step",
    ):
        assert expected in result["detail"]
    assert result["evidence"]["au_se"]["seWidgetsPassage"] is True
