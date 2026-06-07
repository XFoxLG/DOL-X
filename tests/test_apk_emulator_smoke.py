"""Android WebView/CDP smoke helper tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tools import apk_emulator_smoke_test


@pytest.mark.config
def test_apk_cdp_selects_localhost_page_target_and_resolves_websocket_url():
    targets: list[dict[str, Any]] = [
        {
            "type": "page",
            "title": "background",
            "url": "chrome://inspect",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/background",
        },
        {
            "id": "game",
            "type": "page",
            "title": "Degrees of Lewdity",
            "url": "https://localhost/index.html",
            "webSocketDebuggerUrl": "/devtools/page/game",
        },
    ]

    target = apk_emulator_smoke_test._select_cdp_page_target(targets)

    assert target is targets[1]
    assert (
        apk_emulator_smoke_test._target_websocket_url("http://127.0.0.1:9222", target)
        == "ws://127.0.0.1:9222/devtools/page/game"
    )


@pytest.mark.config
def test_apk_webview_smoke_uses_page_target_cdp_adapter(tmp_path, monkeypatch):
    calls: dict[str, Any] = {}

    class FakePage:
        setup_errors: list[dict[str, str]] = []

        def __init__(self, websocket_url: str, timeout_ms: int, target: dict[str, Any]) -> None:
            calls["websocket_url"] = websocket_url
            calls["timeout_ms"] = timeout_ms
            calls["target"] = target
            self.url = str(target["url"])
            self.handlers: dict[str, Any] = {}

        def __enter__(self) -> "FakePage":
            calls["entered"] = True
            return self

        def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
            calls["exited"] = True

        def on(self, event_name: str, handler: Any) -> None:
            self.handlers[event_name] = handler

        def wait_for_timeout(self, timeout_ms: int) -> None:
            calls["settle_ms"] = timeout_ms

        def evaluate(self, script: str, arg: Any = None) -> dict[str, Any]:
            calls.setdefault("evaluate_args", []).append(arg)
            assert "probeConfig" in script
            return {
                "readyState": "complete",
                "hasJQuery": True,
                "hasSugarCube": True,
                "hasModDataValueZipList": True,
                "modDataValueZipListLength": 7,
                "globals": {
                    "maplebirchFrameworks": "object",
                    "CE_options": "object",
                    "SCMLSimpleFramework": "object",
                },
            }

        def screenshot(self, *, path: str, full_page: bool = False) -> None:
            calls["screenshot"] = {"path": path, "full_page": full_page}
            Path(path).write_bytes(b"fake-png")

    def fake_record_game_ready(report, page, *, add_issues=True):
        del page, add_issues
        state = {"ready": True, "loadingLike": False, "passage": "Orphanage Intro"}
        report.observations["game_ready"] = state
        return state

    def fake_startup_interactions(report, page, profile):
        del page, profile
        report.observations["startup_interactions"] = {"success": True}

    def fake_attempt_enter_game(report, page):
        del page
        report.observations["enter_game"] = {"success": True}

    def fake_check_required_mods(report, profile, embedded_mods):
        del profile, embedded_mods
        report.observations["required_mods"] = {}

    monkeypatch.setattr(apk_emulator_smoke_test, "_AndroidWebViewCdpPage", FakePage)
    monkeypatch.setattr(apk_emulator_smoke_test, "_extract_static_embedded_mods", lambda _apk_path: [])
    monkeypatch.setattr(apk_emulator_smoke_test, "_record_game_ready", fake_record_game_ready)
    monkeypatch.setattr(apk_emulator_smoke_test, "_run_startup_interactions", fake_startup_interactions)
    monkeypatch.setattr(apk_emulator_smoke_test, "_attempt_enter_game", fake_attempt_enter_game)
    monkeypatch.setattr(apk_emulator_smoke_test, "_check_required_mods", fake_check_required_mods)

    apk_path = tmp_path / "dol-ucb-more-love-custom-spellbook-cheat-extended-maplebirch-smoke-debug.apk"
    cdp_diagnostics = {
        "success": True,
        "targets": [
            {
                "id": "game",
                "type": "page",
                "title": "Degrees of Lewdity",
                "url": "https://localhost/index.html",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/game",
            }
        ],
    }

    report = apk_emulator_smoke_test._run_webview_browser_smoke(
        apk_path,
        tmp_path,
        "ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        "http://127.0.0.1:9222",
        "Orphanage Intro",
        60_000,
        5_000,
        cdp_diagnostics,
    )

    assert calls["entered"] is True
    assert calls["exited"] is True
    assert calls["websocket_url"] == "ws://127.0.0.1:9222/devtools/page/game"
    assert calls["settle_ms"] == 5_000
    assert report.served_url == "https://localhost/index.html"
    assert report.observations["apk_cdp_page_target"]["webSocketDebuggerUrl"] == calls["websocket_url"]
    assert report.observations["browser_boot"]["has_sugarcube"] is True
    assert report.observations["runtime_globals"]["maplebirchFrameworks"] == "object"
    assert report.observations["screenshot"]["full_page"] is True
    assert not [issue for issue in report.issues if issue.severity == "high"]


@pytest.mark.config
def test_apk_webview_smoke_reports_missing_page_target(tmp_path):
    report = apk_emulator_smoke_test._run_webview_browser_smoke(
        tmp_path / "dol-ucb-more-love-custom-spellbook-cheat-extended-maplebirch-smoke-debug.apk",
        tmp_path,
        "ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        "http://127.0.0.1:9222",
        "Orphanage Intro",
        60_000,
        5_000,
        {"success": True, "targets": [{"type": "page", "url": "https://localhost/index.html"}]},
    )

    assert [issue.kind for issue in report.issues if issue.severity == "high"] == ["apk_cdp_page_target_missing"]


@pytest.mark.config
def test_apk_cdp_console_array_preview_keeps_simple_frameworks_lookup_warning():
    text = apk_emulator_smoke_test._remote_object_text(
        {
            "type": "object",
            "subtype": "array",
            "description": "Array(2)",
            "preview": {
                "type": "object",
                "subtype": "array",
                "overflow": False,
                "properties": [
                    {"name": "0", "type": "string", "value": "Simple Frameworks"},
                    {"name": "1", "type": "string", "value": "ModOrderContainer"},
                ],
            },
        }
    )

    issue = apk_emulator_smoke_test._classify_apk_cdp_message(
        "console.error",
        f"ModOrderContainer getByNameOne() cannot find name. {text}",
    )

    assert text == "[Simple Frameworks, ModOrderContainer]"
    assert issue.severity == "warning"
    assert issue.kind == "simple_frameworks_optional_lookup"


@pytest.mark.config
def test_apk_cdp_remote_loader_failed_fetch_is_optional_remote_mod_list():
    issue = apk_emulator_smoke_test._classify_apk_cdp_message(
        "console.error",
        "TypeError: Failed to fetch\n    at RemoteLoader.load (webpack://SC2-mod-loader-framework/./src/BeforeSC2/ModZipReader.ts?:1127:31)",
    )

    assert issue.severity == "warning"
    assert issue.kind == "optional_remote_mod_list"


@pytest.mark.config
def test_apk_cdp_transport_close_is_adapter_warning_and_reconnects_once():
    report = apk_emulator_smoke_test.BrowserSmokeReport(
        target="apk",
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=False,
    )
    calls = {"operation": 0, "reconnect": 0}

    class FakePage:
        def reconnect(self) -> None:
            calls["reconnect"] += 1

    def operation() -> str:
        calls["operation"] += 1
        if calls["operation"] == 1:
            raise RuntimeError("CDP WebSocket closed while reading frame")
        return "ok"

    issue = apk_emulator_smoke_test._classify_apk_cdp_smoke_exception(
        RuntimeError("CDP WebSocket closed while reading frame")
    )
    result = apk_emulator_smoke_test._with_cdp_reconnect(report, FakePage(), "page_state", operation)

    assert issue.severity == "warning"
    assert issue.kind == "apk_cdp_adapter_closed"
    assert result == "ok"
    assert calls == {"operation": 2, "reconnect": 1}
    assert report.observations["apk_cdp_reconnects"] == [
        {"phase": "page_state", "error": "CDP WebSocket closed while reading frame"}
    ]


@pytest.mark.config
def test_apk_cdp_downgrades_cordova_pageerror_only_after_ready_passage():
    ready_report = apk_emulator_smoke_test.BrowserSmokeReport(
        target="apk",
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=False,
    )
    message = "Error: Java exception was raised during method invocation\n    at androidExec (https://localhost/cordova.js:992:40)"
    ready_report.observations["pageerror_context"] = [{"message": message, "url": "https://localhost/index.html"}]
    apk_emulator_smoke_test._add_issue(
        ready_report,
        apk_emulator_smoke_test.Issue("high", "unexpected_browser_error", "pageerror", message),
    )

    apk_emulator_smoke_test._downgrade_ready_cordova_pageerrors(
        ready_report,
        {"ready": True, "passage": "Orphanage Intro"},
        "Orphanage Intro",
    )

    assert ready_report.observations["pageerror_context"] == []
    assert ready_report.observations["apk_cdp_benign_pageerrors"] == [
        {"message": message, "url": "https://localhost/index.html"}
    ]
    assert [(issue.severity, issue.kind) for issue in ready_report.issues] == [
        ("warning", "cordova_android_exec_after_ready")
    ]

    not_ready_report = apk_emulator_smoke_test.BrowserSmokeReport(
        target="apk",
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=False,
    )
    not_ready_report.observations["pageerror_context"] = [{"message": message}]
    apk_emulator_smoke_test._add_issue(
        not_ready_report,
        apk_emulator_smoke_test.Issue("high", "unexpected_browser_error", "pageerror", message),
    )

    apk_emulator_smoke_test._downgrade_ready_cordova_pageerrors(
        not_ready_report,
        {"ready": False, "passage": None},
        "Orphanage Intro",
    )

    assert not_ready_report.observations["pageerror_context"] == [{"message": message}]
    assert [(issue.severity, issue.kind) for issue in not_ready_report.issues] == [
        ("high", "unexpected_browser_error")
    ]
