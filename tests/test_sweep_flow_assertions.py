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


class _RemountPage:
    """Fake Playwright page driving ``flow_au_face_remount`` without a browser."""

    def __init__(
        self,
        *,
        candidates: list[dict[str, Any]],
        passage: str = "Start2",
        opaque_after_nav: int = 1200,
        container_connected: bool = True,
    ) -> None:
        self.passage = passage
        self.canvas_opaque = 1000
        self.candidates = list(candidates)
        self.opaque_after_nav = opaque_after_nav
        self.container_connected = container_connected
        self.clicked_selectors: list[str] = []
        self.navigated = False

    def evaluate(self, script: str, *_args: Any) -> Any:  # noqa: ANN401
        if script is sfa.AU_SE_PROBE:
            return _full_probe()
        if script is sfa.AU_PET_ENABLE:
            return {
                "enabled": True,
                "sync": True,
                "wiki": True,
                "container": True,
                "notes": [],
            }
        if script is sfa.AU_PET_PROBE:
            return {
                "passage": self.passage,
                "petEnabled": True,
                "liveContainer": {"children": 2, "connected": self.container_connected},
                "canvas": {"w": 128, "h": 128, "opaque": self.canvas_opaque},
            }
        if script is sfa.AU_REMOUNT_MARK_LINKS:
            return {
                "before": self.passage,
                "candidates": [] if self.navigated else list(self.candidates),
                "total": len(self.candidates),
            }
        raise AssertionError(f"unexpected evaluate: {script[:60]!r}")

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def wait_for_function(self, _selector: str, timeout: int | None = None) -> bool:
        return True

    def click(self, selector: str) -> None:
        self.clicked_selectors.append(selector)
        index = int(selector.split("'")[1])
        self.passage = str(self.candidates[index]["target"])
        self.navigated = True
        self.canvas_opaque = self.opaque_after_nav


def _remount_candidates() -> list[dict[str, Any]]:
    return [{"index": 0, "target": "Bedroom", "text": "Go to your room"}]


def test_remount_flow_not_applicable_for_non_au_variant() -> None:
    result = sfa.flow_au_face_remount(_ExplodingPage(), {"artifact_variant": "base"})
    assert result["status"] == sfa.NOT_APPLICABLE
    assert "not an AU artifact" in result["detail"]


def test_remount_flow_passes_when_canvas_survives_real_navigation() -> None:
    page = _RemountPage(candidates=_remount_candidates())
    result = sfa.flow_au_face_remount(page, {"artifact_variant": "au-f"})

    assert result["status"] == sfa.PASS
    assert page.clicked_selectors == ["[data-dolx-remount-target='0']"]
    assert result["evidence"]["post_nav_opaque"] == [1200]
    assert result["evidence"]["post_nav_container_connected"] == [True]
    assert "Start2 -> Bedroom" in result["detail"]


def test_remount_flow_fails_when_canvas_vanishes_after_navigation() -> None:
    page = _RemountPage(candidates=_remount_candidates(), opaque_after_nav=0)
    result = sfa.flow_au_face_remount(page, {"artifact_variant": "au-f"})

    assert result["status"] == sfa.FAIL
    assert "did not remount" in result["detail"]
    assert result["evidence"]["post_nav_opaque"] == [0]


def test_remount_flow_fails_when_container_disconnects_after_navigation() -> None:
    page = _RemountPage(
        candidates=_remount_candidates(), container_connected=False
    )
    result = sfa.flow_au_face_remount(page, {"artifact_variant": "au-f"})

    assert result["status"] == sfa.FAIL
    assert result["evidence"]["post_nav_container_connected"] == [False]


def test_remount_flow_not_implemented_without_navigation_links() -> None:
    page = _RemountPage(candidates=[])
    result = sfa.flow_au_face_remount(page, {"artifact_variant": "au-f"})

    assert result["status"] == sfa.NOT_IMPLEMENTED
    assert page.clicked_selectors == []
    assert "could not be exercised" in result["detail"]


def test_remount_flow_reports_missing_au_markers() -> None:
    class _BarePage:
        def evaluate(self, script: str, *_args: Any) -> Any:  # noqa: ANN401
            assert script is sfa.AU_SE_PROBE
            return {"errors": [], "seWidgetsPassage": True}

    result = sfa.flow_au_face_remount(_BarePage(), {"artifact_variant": "au-f"})
    assert result["status"] == sfa.FAIL
    assert "AU_facial_expansion widget" in result["detail"]
