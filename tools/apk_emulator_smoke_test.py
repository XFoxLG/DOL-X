#!/usr/bin/env python3
"""Automated Android WebView/CDP smoke test for smoke-debug APKs.

This helper is intentionally scoped to the manual baseline candidate gate.  It
installs one release-derived smoke-debug APK on an already running Android
emulator, launches it, attaches to the WebView DevTools endpoint, and reuses the
same runtime checks/report shape as the ZIP browser smoke where practical.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.config_loader import load_build_config
from tools.artifact_inspection import load_html_artifact
from tools.browser_smoke_test import (
    BrowserSmokeReport,
    Issue,
    PROFILES,
    _add_issue,
    _attempt_enter_game,
    _check_required_mods,
    _is_successful_smoke,
    _page_state_script,
    _record_game_ready,
    _run_startup_interactions,
    classify_message,
    collect_ci_context,
    extract_embedded_mods_from_html,
    summarize_report,
    write_outputs,
)


DEFAULT_CDP_PORT = 9222
DEFAULT_PROFILE = "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"
DEFAULT_EXPECTED_PASSAGE = "Orphanage Intro"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _short_text(value: str | bytes | None, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-limit:]
    return value[-limit:]


def _run_command(
    cmd: list[str],
    commands: list[dict[str, Any]],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    entry: dict[str, Any] = {"command": cmd}
    commands.append(entry)
    try:
        result = subprocess.run(cmd, capture_output=True, check=check, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        entry.update(
            {
                "returncode": exc.returncode,
                "stdout": _short_text(exc.stdout),
                "stderr": _short_text(exc.stderr),
            }
        )
        raise
    except subprocess.TimeoutExpired as exc:
        entry.update(
            {
                "returncode": None,
                "timeout_seconds": timeout,
                "stdout": _short_text(exc.stdout),
                "stderr": _short_text(exc.stderr),
            }
        )
        raise

    entry.update(
        {
            "returncode": result.returncode,
            "stdout": _short_text(result.stdout),
            "stderr": _short_text(result.stderr),
        }
    )
    return result


def _apk_slug(apk_path: Path) -> str:
    normalized = apk_path.name.lower().replace("_", "-")
    for slug in ("au-f", "au-m", "au-a"):
        if f"-{slug}-" in normalized:
            return slug
    return "base"


def _default_package_name() -> str:
    return load_build_config().identity_package


def _parse_devtools_sockets(proc_net_unix: str) -> list[str]:
    sockets: list[str] = []
    seen: set[str] = set()
    for line in proc_net_unix.splitlines():
        if "devtools_remote" not in line:
            continue
        raw_name = line.rsplit(maxsplit=1)[-1].strip()
        name = raw_name.lstrip("@").strip("\x00")
        if not name or "devtools_remote" not in name or name in seen:
            continue
        seen.add(name)
        sockets.append(name)
    return sockets


def _select_devtools_socket(sockets: list[str], package_name: str) -> str | None:
    if not sockets:
        return None
    package_tokens = {package_name, package_name.replace(".", "_")}
    for socket in sockets:
        if any(token and token in socket for token in package_tokens):
            return socket
    for socket in sockets:
        if socket.startswith("webview_devtools_remote"):
            return socket
    return sockets[0]


def _fetch_json(url: str, *, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - localhost CDP endpoint.
        return json.loads(response.read().decode("utf-8"))


def _discover_cdp_endpoint(
    adb: str,
    package_name: str,
    commands: list[dict[str, Any]],
    *,
    cdp_port: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, Any]] = []
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            proc_net = _run_command([adb, "shell", "cat", "/proc/net/unix"], commands, timeout=10).stdout
            sockets = _parse_devtools_sockets(proc_net)
            socket = _select_devtools_socket(sockets, package_name)
            attempts.append({"sockets": sockets, "selected_socket": socket})
            if not socket:
                time.sleep(1)
                continue

            _run_command([adb, "forward", "--remove", f"tcp:{cdp_port}"], commands, check=False, timeout=10)
            _run_command([adb, "forward", f"tcp:{cdp_port}", f"localabstract:{socket}"], commands, timeout=10)
            cdp_url = f"http://127.0.0.1:{cdp_port}"
            targets = _fetch_json(f"{cdp_url}/json/list")
            if isinstance(targets, list) and targets:
                return {
                    "success": True,
                    "cdp_url": cdp_url,
                    "socket": socket,
                    "targets": targets,
                    "attempts": attempts,
                }
            last_error = "CDP endpoint returned no targets"
        except (subprocess.SubprocessError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            attempts.append({"error": str(exc)})
        time.sleep(1)

    return {
        "success": False,
        "cdp_url": f"http://127.0.0.1:{cdp_port}",
        "socket": None,
        "targets": [],
        "attempts": attempts,
        "error": last_error or "timed out waiting for Android WebView DevTools target",
    }


def _attach_page_events(report: BrowserSmokeReport, page: Any) -> None:
    def on_console(message: Any) -> None:
        text = str(message.text)
        entry = {"type": message.type, "text": text, "location": message.location}
        report.console_messages.append(entry)
        if message.type in {"error", "warning"}:
            source = "console.error" if message.type == "error" else "console.warning"
            _add_issue(report, classify_message(source, text), location=message.location)

    def on_page_error(error: Any) -> None:
        text = str(error)
        report.observations.setdefault("pageerror_context", []).append({"message": text, "url": page.url})
        _add_issue(report, classify_message("pageerror", text))

    def on_request_failed(request: Any) -> None:
        failure = request.failure or "request failed"
        entry = {
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "failure": failure,
        }
        report.network_failures.append(entry)
        _add_issue(report, classify_message("requestfailed", f"{request.url} {failure}"), url=request.url)

    def on_response(response: Any) -> None:
        if response.status < 400:
            return
        entry = {"url": response.url, "status": response.status, "status_text": response.status_text}
        report.network_failures.append(entry)
        _add_issue(report, classify_message("http_error", f"{response.url} HTTP {response.status}"), url=response.url)

    def on_dialog(dialog: Any) -> None:
        entry = {"type": dialog.type, "message": dialog.message, "accepted": True}
        report.observations.setdefault("dialogs", []).append(entry)
        dialog.accept()

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)
    page.on("dialog", on_dialog)


def _wait_for_cdp_page(browser: Any, timeout_ms: int) -> Any:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        pages = [page for context in browser.contexts for page in context.pages]
        if pages:
            return pages[0]
        time.sleep(0.25)
    raise RuntimeError("CDP connection did not expose a WebView page")


def _record_apk_identity(report: BrowserSmokeReport, apk_path: Path, profile_name: str) -> None:
    normalized_name = apk_path.name.lower().replace("_", "-")
    required_tokens = ("ucb", "more-love", "custom-spellbook", "cheat-extended", "maplebirch")
    missing_tokens = [token for token in required_tokens if token not in normalized_name]
    identity = {
        "package_slug": apk_path.stem,
        "profile": profile_name,
        "profile_slug_match": not missing_tokens,
        "required_slug_tokens": list(required_tokens),
        "missing_required_slug_tokens": missing_tokens,
        "artifact_kind": "apk-smoke-debug",
    }
    report.observations["package_identity"] = identity
    for token in missing_tokens:
        _add_issue(
            report,
            Issue(
                "warning",
                "package_required_slug_token_missing",
                "identity",
                f"APK slug {apk_path.stem!r} does not include expected token {token!r} for profile {profile_name!r}",
            ),
        )


def _extract_static_embedded_mods(apk_path: Path) -> list[Any]:
    try:
        _, html_content = load_html_artifact(apk_path)
    except Exception:  # noqa: BLE001 - runtime report will still capture CDP status.
        return []
    if html_content is None:
        return []
    return extract_embedded_mods_from_html(html_content)


def _run_webview_browser_smoke(
    apk_path: Path,
    output_dir: Path,
    profile_name: str,
    cdp_url: str,
    expected_passage: str,
    timeout_ms: int,
    settle_ms: int,
    cdp_diagnostics: dict[str, Any],
) -> BrowserSmokeReport:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised by CI environment.
        report = BrowserSmokeReport(
            target=str(apk_path),
            profile=profile_name,
            report_only=False,
            ci_context=collect_ci_context(),
        )
        _add_issue(report, Issue("high", "playwright_missing", "runner", str(exc)))
        return report

    profile = PROFILES[profile_name]
    report = BrowserSmokeReport(
        target=str(apk_path),
        profile=profile.name,
        report_only=False,
        ci_context=collect_ci_context(),
    )
    report.observations["apk_cdp"] = cdp_diagnostics
    _record_apk_identity(report, apk_path, profile_name)

    embedded_mods = _extract_static_embedded_mods(apk_path)
    report.observations["embedded_mods"] = [asdict(info) for info in embedded_mods]

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_ms)
            try:
                page = _wait_for_cdp_page(browser, timeout_ms)
                _attach_page_events(report, page)
                page.wait_for_timeout(settle_ms)
                report.served_url = page.url

                _run_startup_interactions(report, page, profile)
                global_names = tuple(
                    dict.fromkeys([*profile.required_globals, *profile.warning_globals, *profile.diagnostic_globals])
                )
                page_state = page.evaluate(_page_state_script(), global_names)
                report.observations["page_state"] = page_state
                report.observations["runtime_globals"] = {
                    global_name: (page_state.get("globals", {}) or {}).get(global_name)
                    for global_name in profile.diagnostic_globals
                }
                report.observations["browser_boot"] = {
                    "navigation_ok": True,
                    "served_url": page.url,
                    "ready_state": page_state.get("readyState"),
                    "has_jquery": page_state.get("hasJQuery"),
                    "has_sugarcube": page_state.get("hasSugarCube"),
                    "has_mod_data_value_zip_list": page_state.get("hasModDataValueZipList"),
                    "mod_data_value_zip_list_length": page_state.get("modDataValueZipListLength"),
                    "dialog_count": len(report.observations.get("dialogs", [])),
                    "popup_count": 0,
                    "console_message_count": len(report.console_messages),
                    "network_failure_count": len(report.network_failures),
                }
                _record_game_ready(report, page)
                _attempt_enter_game(report, page)
                final_game_ready = _record_game_ready(report, page, add_issues=False)
                _check_required_mods(report, profile, embedded_mods)

                observed_passage = final_game_ready.get("passage")
                if expected_passage and observed_passage != expected_passage:
                    _add_issue(
                        report,
                        Issue(
                            "high",
                            "expected_passage_not_reached",
                            "apk_cdp_smoke",
                            f"expected passage {expected_passage!r}, got {observed_passage!r}",
                        ),
                    )

                screenshot_path = output_dir / "browser-smoke-final.png"
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    report.observations["screenshot"] = {"path": str(screenshot_path), "full_page": True}
                except PlaywrightError as exc:
                    _add_issue(report, Issue("warning", "screenshot_failed", "runner", str(exc)))
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - preserve CDP failures as report artifacts.
        _add_issue(report, Issue("high", "apk_cdp_smoke_error", "runner", str(exc)))

    return report


def _write_logcat(adb: str, output_dir: Path, commands: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    logcat_path = output_dir / "logcat.txt"
    result = _run_command([adb, "logcat", "-d", "-v", "time"], commands, check=False, timeout=30)
    logcat_path.write_text(result.stdout or result.stderr or "", encoding="utf-8", errors="replace")
    return logcat_path


def run_apk_emulator_smoke(args: argparse.Namespace) -> int:
    start = time.monotonic()
    apk_path = Path(args.apk).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []
    errors: list[str] = []
    package_name = args.package or _default_package_name()
    slug = args.slug or _apk_slug(apk_path)
    cdp: dict[str, Any] = {
        "success": False,
        "cdp_url": f"http://127.0.0.1:{args.cdp_port}",
        "socket": None,
        "targets": [],
    }
    browser_report: BrowserSmokeReport | None = None
    setup_completed = False

    try:
        _run_command([args.adb, "devices"], commands, timeout=30)
        _run_command([args.adb, "logcat", "-c"], commands, check=False, timeout=30)
        _run_command([args.adb, "install", "-r", "-d", str(apk_path)], commands, timeout=args.install_timeout_seconds)
        _run_command([args.adb, "shell", "pm", "clear", package_name], commands, check=False, timeout=30)
        _run_command(
            [args.adb, "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
            commands,
            timeout=30,
        )
        time.sleep(args.launch_settle_seconds)
        setup_completed = True

        cdp = _discover_cdp_endpoint(
            args.adb,
            package_name,
            commands,
            cdp_port=args.cdp_port,
            timeout_seconds=args.cdp_timeout_seconds,
        )
        if not cdp.get("success"):
            errors.append(str(cdp.get("error") or "failed to discover Android WebView CDP endpoint"))

        if cdp.get("success"):
            browser_report = _run_webview_browser_smoke(
                apk_path,
                output_dir,
                args.profile,
                str(cdp["cdp_url"]),
                args.expected_passage,
                args.timeout_ms,
                args.settle_ms,
                cdp,
            )
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        errors.append(str(exc))
        cdp["error"] = str(exc)

    if browser_report is None:
        browser_report = BrowserSmokeReport(
            target=str(apk_path),
            profile=args.profile,
            report_only=False,
            ci_context=collect_ci_context(),
        )
        browser_report.observations["apk_cdp"] = cdp
        _record_apk_identity(browser_report, apk_path, args.profile)
        issue_kind = "apk_cdp_endpoint_missing" if setup_completed else "apk_emulator_setup_failed"
        _add_issue(browser_report, Issue("high", issue_kind, "adb", errors[-1] if errors else issue_kind))

    browser_report.elapsed_seconds = time.monotonic() - start
    browser_report.observations["runtime_scope"] = {
        "platform": "Android emulator",
        "webview_cdp": True,
        "manual_phone_testing": False,
        "harmonyos_covered": False,
    }
    browser_report.success = _is_successful_smoke(browser_report)
    write_outputs(browser_report, output_dir)
    browser_summary = summarize_report(browser_report)
    try:
        logcat_path = _write_logcat(args.adb, output_dir, commands)
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"logcat collection failed: {exc}")
        logcat_path = output_dir / "logcat.txt"
        logcat_path.write_text(str(exc), encoding="utf-8", errors="replace")
    try:
        _run_command([args.adb, "forward", "--remove", f"tcp:{args.cdp_port}"], commands, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"CDP forward cleanup failed: {exc}")

    success = browser_report.success and not errors
    payload = {
        "success": success,
        "gate_level": "full_candidate_gate_ready_component",
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "runtime_scope": browser_report.observations["runtime_scope"],
        "target": str(apk_path),
        "slug": slug,
        "package": package_name,
        "profile": args.profile,
        "expected_passage": args.expected_passage,
        "cdp_url": cdp.get("cdp_url"),
        "cdp_socket": cdp.get("socket"),
        "cdp_targets": cdp.get("targets", []),
        "browser_summary": browser_summary,
        "browser_summary_path": str(output_dir / "browser-smoke-summary.json"),
        "browser_report_path": str(output_dir / "browser-smoke-report.json"),
        "markdown_report_path": str(output_dir / "browser-smoke-report.md"),
        "logcat_path": str(logcat_path),
        "screenshot_path": str((browser_summary.get("screenshot") or {}).get("path") or ""),
        "commands": commands,
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - start, 2),
    }
    _write_json(output_dir / "apk-emulator-smoke.json", payload)
    print(json.dumps({"slug": slug, "success": success, "errors": errors}, ensure_ascii=False))
    return 0 if success else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Android emulator WebView/CDP smoke test for a smoke-debug APK")
    parser.add_argument("apk", type=Path, help="Release-derived smoke-debug APK to install and smoke")
    parser.add_argument("--output-dir", type=Path, default=Path("output/apk-emulator-smoke"))
    parser.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE)
    parser.add_argument("--package", help="Android package name; defaults to config/build.toml identity package")
    parser.add_argument("--slug", choices=("base", "au-f", "au-m", "au-a"))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    parser.add_argument("--expected-passage", default=DEFAULT_EXPECTED_PASSAGE)
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--settle-ms", type=int, default=5_000)
    parser.add_argument("--install-timeout-seconds", type=int, default=180)
    parser.add_argument("--launch-settle-seconds", type=int, default=5)
    parser.add_argument("--cdp-timeout-seconds", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_apk_emulator_smoke(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
