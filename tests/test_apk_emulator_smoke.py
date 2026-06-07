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
