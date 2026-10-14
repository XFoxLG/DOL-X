"""Pure tests for Android semantic replay planning and matching."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import android_replay
from tools.android_replay import (
    EXECUTION_SCHEMA,
    collect_android_runtime_candidates,
    collect_runtime_candidates,
    execute_replay,
    build_plan,
    match_actions,
    summarize_replay_result,
)


def _report() -> dict:
    return {
        "schema": "dolx.exploration.v1",
        "target_manifest": {
            "target": {
                "package_sha256": "a" * 64,
                "game_version": "0.5.11.9",
                "target_tag": "v0.5.11.9-1.0.0a-0915",
            }
        },
        "actions": [
            {
                "step": 1,
                "kind": "link",
                "semantic_id": "Start2:link:4c6ebd08",
                "role": "link",
                "text": "(1) 继续",
                "text_hash": "hash-continue",
                "id": None,
                "name": None,
                "href": None,
                "value": None,
                "passage_before": "Start2",
                "passage_after": "Orphanage Intro",
            }
        ],
    }


def test_plan_keeps_semantics_and_omits_desktop_locator() -> None:
    plan = build_plan(_report())
    assert plan["schema"] == "dolx.android-replay-plan.v1"
    step = plan["steps"][0]
    assert step["semantic_id"] == "Start2:link:4c6ebd08"
    assert step["text_hash"] == "hash-continue"
    assert step["expected_passage"] == "Start2"
    assert step["locator_policy"] == "semantic_only"
    assert "selector" not in step
    assert "css" not in step


def test_plan_rejects_desktop_selector_fields() -> None:
    report = _report()
    report["actions"][0]["selector"] = "#continue"
    with pytest.raises(ValueError, match="desktop locator fields"):
        build_plan(report)


def test_plan_prefixes_bootstrap_when_trace_starts_after_bootstrap() -> None:
    report = _report()
    report["bootstrap"] = {
        "actions": [
            {
                "semantic_id": "Start:button:f5f23e6c",
                "kind": "button",
                "role": "button",
                "text": "进入游戏",
                "text_hash": "hash-enter",
                "passage_after": "Start2",
            }
        ]
    }

    plan = build_plan(report)

    assert plan["source"] == "natural_semantic_trace_with_bootstrap"
    assert [step["semantic_id"] for step in plan["steps"]] == [
        "Start:button:f5f23e6c",
        "Start2:link:4c6ebd08",
    ]
    assert [step["step"] for step in plan["steps"]] == [1, 2]


def test_plan_prefixes_bootstrap_using_report_end_passage() -> None:
    report = _report()
    report["bootstrap"] = {
        "actions": [
            {
                "semantic_id": "Start:button:f5f23e6c",
                "kind": "button",
                "role": "button",
                "text": "进入游戏",
                "text_hash": "hash-enter",
            }
        ],
        "passage": "Start2",
    }

    plan = build_plan(report)

    assert plan["source"] == "natural_semantic_trace_with_bootstrap"
    assert len(plan["steps"]) == 2


def test_match_prefers_semantic_id_then_identity_then_text_hash() -> None:
    step = {
        "step": 7,
        "semantic_id": "Tutorial:select:000bda84",
        "role": "select",
        "text_hash": "hash-a",
        "identity": {"id": "listbox-undressrighttarget", "name": "listbox-undressrighttarget"},
    }
    candidates = [
        {
            "semantic_id": "different",
            "role": "select",
            "text": "wrong",
            "id": "listbox-undressrighttarget",
            "name": "listbox-undressrighttarget",
        },
        {
            "semantic_id": "Tutorial:select:000bda84",
            "role": "select",
            "text": "right",
            "id": "other-id",
        },
        {
            "role": "select",
            "text": "same-label",
        },
    ]
    result = match_actions([step], candidates)
    assert result[0]["status"] == "matched"
    assert result[0]["evidence"][0]["index"] == 1


def test_match_does_not_fall_back_across_expected_passage() -> None:
    step = {
        "step": 1,
        "semantic_id": "Start2:link:missing",
        "role": "link",
        "text_hash": "same-text",
        "expected_passage": "Start2",
    }
    candidates = [
        {
            "semantic_id": "Start:link:same-text",
            "role": "link",
            "text_hash": "same-text",
        }
    ]

    result = match_actions([step], candidates)

    assert result[0]["status"] == "unmapped"


def test_match_normalizes_android_shortcut_prefix() -> None:
    step = {
        "step": 1,
        "semantic_id": "Start:button:old-runtime-hash",
        "role": "button",
        "text": "开始游戏！",
        "expected_passage": "Start",
    }
    candidates = [
        {
            "semantic_id": "Start:button:android-shortcut-hash",
            "role": "button",
            "text": "(1) 开始游戏！",
        }
    ]

    result = match_actions([step], candidates)

    assert result[0]["status"] == "matched"


def test_match_reports_ambiguous_and_unmapped() -> None:
    steps = [
        {"step": 1, "semantic_id": "same", "role": "button", "text_hash": "h"},
        {"step": 2, "semantic_id": "missing", "role": "button", "text_hash": "nope"},
    ]
    candidates = [
        {"semantic_id": "same", "role": "button", "text_hash": "h"},
        {"semantic_id": "same", "role": "button", "text_hash": "h"},
    ]
    result = match_actions(steps, candidates)
    assert result[0]["status"] == "ambiguous"
    assert result[1]["status"] == "unmapped"


def test_match_refines_ambiguous_semantic_id_with_identity() -> None:
    step = {
        "step": 1,
        "semantic_id": "same",
        "role": "input",
        "text_hash": "h",
        "identity": {"id": "wanted-id", "name": "group"},
    }
    candidates = [
        {"semantic_id": "same", "role": "input", "text_hash": "h", "id": "other-id"},
        {
            "semantic_id": "same",
            "role": "input",
            "text_hash": "h",
            "id": "wanted-id",
            "name": "group",
        },
    ]
    result = match_actions([step], candidates)
    assert result[0]["status"] == "matched"
    assert result[0]["evidence"][0]["index"] == 1


def test_summary_counts_failures_and_redacts_paths() -> None:
    entries = [
        {"step": 1, "semantic_id": "a", "status": "matched"},
        {"step": 2, "semantic_id": "b", "status": "ambiguous"},
        {"step": 3, "semantic_id": "c", "status": "unmapped"},
    ]
    summary = summarize_replay_result(
        entries,
        apk_sha256="a" * 64,
        adb_serial="127.0.0.1:16384",
        cdp_connected=True,
        logcat_summary={"artifact": "E:\\private\\logcat.txt", "fatal": 0},
        profile_mode="clean_install",
    )
    assert summary["totals"] == {"planned": 3, "matched": 1, "ambiguous": 1, "unmapped": 1}
    assert summary["unmapped"] == [
        {"step": 2, "semantic_id": "b"},
        {"step": 3, "semantic_id": "c"},
    ]
    assert summary["logcat_summary"]["artifact"] == "<redacted-path>"
    assert summary["completion_claim"] == "none"
    assert summary["profile_mode"] == "clean_install"


def test_summary_records_profile_mode_as_none_when_unspecified() -> None:
    summary = summarize_replay_result([{"step": 1, "semantic_id": "a", "status": "matched"}])

    assert summary["profile_mode"] is None


class _FakePage:
    def __init__(self, actions: list[dict], *, fail_action: bool = False) -> None:
        self.actions = actions
        self.fail_action = fail_action
        self.errors: list[BaseException] = []
        self.executed: list[object] = []
        self.screenshots: list[Path] = []
        self.passage = "Start"
        self.passage_sequence: list[object] = []

    def on(self, event: str, handler) -> None:
        if event == "pageerror" and self.errors:
            for error in self.errors:
                handler(error)

    def evaluate(self, script: str, arg=None):
        if "semantic action is no longer present" in script:
            self.executed.append(arg)
            if self.fail_action:
                return json.dumps({"ok": False, "error": "action failed"})
            return json.dumps({"ok": True, "passage": "After"})
        if "SugarCube?.State?.passage" in script:
            if self.passage_sequence:
                value = self.passage_sequence.pop(0)
            elif self.executed:
                value = "After"
            else:
                value = self.passage
            return value
        if "scrollHeight" in script:
            return True
        return json.dumps({"ok": True, "actions": self.actions})

    def wait_for_timeout(self, timeout_ms: int) -> None:
        return None

    def screenshot(self, *, path: str, full_page: bool = False) -> None:
        screenshot_path = Path(path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(b"png")
        self.screenshots.append(screenshot_path)


def test_collect_runtime_candidates_uses_runtime_snapshot() -> None:
    actions = [{"semantic_id": "Start:link:abc", "index": 1, "role": "link", "text_hash": "h"}]
    page = _FakePage(actions)
    assert collect_runtime_candidates(page) == actions


def test_collect_android_runtime_candidates_requests_full_document_actions() -> None:
    actions = [{"semantic_id": "Orphanage Intro:input:abc", "index": 1, "visible": False}]

    class RecordingPage(_FakePage):
        def __init__(self) -> None:
            super().__init__(actions)
            self.evaluate_args: list[object] = []

        def evaluate(self, script: str, arg=None):
            if "SugarCube runtime is not ready" in script:
                self.evaluate_args.append(arg)
            return super().evaluate(script, arg)

    page = RecordingPage()
    assert collect_android_runtime_candidates(page) == actions
    assert page.evaluate_args == [True]


def test_execute_replay_matches_executes_and_writes_evidence(tmp_path: Path) -> None:
    step = {
        "step": 1,
        "semantic_id": "Start:link:abc",
        "role": "link",
        "text_hash": "h",
        "expected_passage": "Start",
    }
    candidate = {
        "semantic_id": "Start:link:abc",
        "kind": "link",
        "role": "link",
        "text": "继续",
        "text_hash": "h",
        "index": 3,
    }
    page = _FakePage([candidate])
    result = execute_replay({"steps": [step]}, page, tmp_path, adb_serial="emu")

    assert result["summary"]["verdict"] == "ok"
    assert result["summary"]["totals"] == {
        "planned": 1,
        "matched": 1,
        "ambiguous": 0,
        "unmapped": 0,
    }
    assert page.executed == [3]
    assert result["entries"][0]["after_passage"] == "After"
    execution = json.loads((tmp_path / "android-replay-execution.json").read_text(encoding="utf-8"))
    assert execution["schema"] == EXECUTION_SCHEMA
    assert (tmp_path / "screenshots" / "step-0001.png").exists()


def test_execute_replay_does_not_fire_pointer_blocked_action(tmp_path: Path) -> None:
    step = {"step": 1, "semantic_id": "Start:button:blocked", "role": "button", "text_hash": "h"}
    candidate = {
        "semantic_id": "Start:button:blocked",
        "kind": "button",
        "role": "button",
        "text_hash": "h",
        "index": 5,
        "pointer_blocked": True,
    }
    page = _FakePage([candidate])

    result = execute_replay({"steps": [step]}, page, tmp_path)

    assert result["summary"]["verdict"] == "ok"
    assert page.executed == []
    assert result["entries"][0]["executed"] is False
    assert result["entries"][0]["blocked_reason"] == "pointer_blocked"


def test_execute_replay_waits_for_runtime_actions_before_matching(tmp_path: Path) -> None:
    step = {"step": 1, "semantic_id": "Start:button:ready", "role": "button", "text_hash": "h"}
    candidate = {
        "semantic_id": "Start:button:ready",
        "kind": "button",
        "role": "button",
        "text_hash": "h",
        "index": 4,
    }

    class DelayedPage(_FakePage):
        def __init__(self) -> None:
            super().__init__([])
            self.runtime_calls = 0

        def evaluate(self, script: str, arg=None):
            if "SugarCube runtime is not ready" in script:
                self.runtime_calls += 1
                if self.runtime_calls == 1:
                    return json.dumps({"ok": True, "actions": []})
                return json.dumps({"ok": True, "actions": [candidate]})
            return super().evaluate(script, arg)

    page = DelayedPage()
    result = execute_replay({"steps": [step]}, page, tmp_path)

    assert result["summary"]["verdict"] == "ok"
    assert page.runtime_calls >= 2
    assert page.executed == [4]


def test_execute_replay_waits_for_planned_passage_during_modloader_boot(tmp_path: Path) -> None:
    """ModLoader exposes controls before SugarCube starts the story.

    A cold start therefore has to wait for the planned passage, otherwise the
    bootstrap steps race the boot sequence and are reported as unmapped.
    """
    step = {"step": 1, "semantic_id": "Start:input:5148d274", "role": "input", "text_hash": "h"}
    candidate = {
        "semantic_id": "Start:input:5148d274",
        "kind": "checkbox",
        "role": "input",
        "text_hash": "h",
        "index": 2,
    }
    page = _FakePage([candidate])
    page.passage_sequence = [None, None, "Start"]

    result = execute_replay({"steps": [step]}, page, tmp_path)

    assert result["summary"]["verdict"] == "ok"
    assert page.executed == [2]


def test_execute_replay_raises_when_planned_passage_never_arrives(tmp_path: Path) -> None:
    """A boot that never reaches the planned passage is an infrastructure failure.

    The CLI turns this into ``infrastructure_fail`` instead of reporting the
    unreached steps as product-level unmapped actions.
    """
    step = {"step": 1, "semantic_id": "Start:input:5148d274", "role": "input", "text_hash": "h"}
    page = _FakePage([{"semantic_id": "Other:input:x", "role": "input", "text_hash": "h", "index": 1}])
    page.passage = None

    with pytest.raises(RuntimeError, match="did not become replayable"):
        execute_replay({"steps": [step]}, page, tmp_path, runtime_ready_timeout_ms=0)
    assert page.executed == []


def test_execute_replay_reports_unmapped_without_executing(tmp_path: Path) -> None:
    step = {"step": 2, "semantic_id": "missing", "role": "button", "text_hash": "expected"}
    page = _FakePage([{"semantic_id": "other", "index": 1, "role": "button", "text_hash": "actual"}])
    result = execute_replay({"steps": [step]}, page, tmp_path)

    assert result["summary"]["verdict"] == "failed"
    assert result["summary"]["totals"]["unmapped"] == 1
    assert result["entries"][0]["status"] == "unmapped"
    assert page.executed == []


def test_execute_replay_marks_action_failure_and_page_error(tmp_path: Path) -> None:
    step = {"step": 1, "semantic_id": "same", "role": "button", "text_hash": "h"}
    candidate = {
        "semantic_id": "same",
        "kind": "button",
        "role": "button",
        "text_hash": "h",
        "index": 2,
    }
    page = _FakePage([candidate], fail_action=True)
    page.errors = [RuntimeError("boom")]
    result = execute_replay({"steps": [step]}, page, tmp_path)

    assert result["summary"]["verdict"] == "failed"
    assert result["summary"]["page_errors"] == [{"message": "boom"}]
    assert result["entries"][0]["status"] == "action_failed"


def test_execute_replay_is_partial_when_some_steps_match(tmp_path: Path) -> None:
    steps = [
        {"step": 1, "semantic_id": "same", "role": "button", "text_hash": "h"},
        {"step": 2, "semantic_id": "missing", "role": "button", "text_hash": "expected"},
    ]
    page = _FakePage([{"semantic_id": "same", "kind": "button", "role": "button", "text_hash": "h", "index": 1}])
    result = execute_replay({"steps": steps}, page, tmp_path)

    assert result["summary"]["verdict"] == "partial"
    assert result["summary"]["totals"] == {
        "planned": 2,
        "matched": 1,
        "ambiguous": 0,
        "unmapped": 1,
    }


def test_device_versions_reads_current_webview_from_webviewupdate(monkeypatch) -> None:
    def fake_run_command(cmd, commands, *, check=True, timeout=None):
        if cmd[-2:] == ["getprop", "ro.build.version.release"]:
            return subprocess.CompletedProcess(cmd, 0, "12\n", "")
        if cmd[-2:] == ["dumpsys", "webviewupdate"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                "Current WebView package (name, version): (com.android.webview, 110.0.5481.154.1)\n",
                "",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(android_replay, "_run_command", fake_run_command)
    assert android_replay._device_versions("adb", "serial-1", []) == (
        "12",
        "110.0.5481.154.1",
    )


def test_device_versions_falls_back_to_vendor_webview_package(monkeypatch) -> None:
    def fake_run_command(cmd, commands, *, check=True, timeout=None):
        if cmd[-2:] == ["getprop", "ro.build.version.release"]:
            return subprocess.CompletedProcess(cmd, 0, "12\n", "")
        if cmd[-2:] == ["dumpsys", "webviewupdate"]:
            return subprocess.CompletedProcess(cmd, 1, "", "unknown service")
        if cmd[-3:] == ["dumpsys", "package", "com.google.android.webview"]:
            return subprocess.CompletedProcess(cmd, 1, "", "package not found")
        if cmd[-3:] == ["dumpsys", "package", "com.android.webview"]:
            return subprocess.CompletedProcess(cmd, 0, "    versionName=110.0.5481.154.1\n", "")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(android_replay, "_run_command", fake_run_command)
    assert android_replay._device_versions("adb", None, []) == (
        "12",
        "110.0.5481.154.1",
    )
