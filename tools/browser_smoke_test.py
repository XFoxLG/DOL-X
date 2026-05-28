#!/usr/bin/env python3
"""Phase 4: browser smoke test for built DoL packages.

This tool intentionally stays outside the Lyra build pipeline.  It opens a
built ZIP/HTML package through a local HTTP server, captures browser runtime
evidence, and writes report-only artifacts that can later be promoted to a
strict CI gate.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import functools
import http.server
import io
import json
import re
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


MOD_LIST_PATTERN = re.compile(
    r"window\.modDataValueZipList\s*=\s*(\[.*?\]);",
    re.DOTALL,
)


@dataclass(frozen=True)
class SmokeProfile:
    """Mod-specific browser checks layered on top of generic smoke checks."""

    name: str
    required_mod_names: tuple[str, ...] = ()
    required_globals: tuple[str, ...] = ()
    click_selectors: tuple[str, ...] = ()


PROFILES: dict[str, SmokeProfile] = {
    "ucb-more-love-custom-spellbook": SmokeProfile(
        name="ucb-more-love-custom-spellbook",
        required_mod_names=(
            "ModLoaderGui",
            "ModI18N",
            "Cheat-Lyra",
            "CombatStatusDisplay-Lyra",
            "言灵解放",
            "随身言灵",
            "BetterCheatCommandManagement",
            "More Love Interests Mod",
            "Custom-Spellbook",
            "Lyra",
        ),
        required_globals=("spellBookMobileClicked",),
        click_selectors=('[onclick*="spellBookMobileClicked"]',),
    ),
    "ucb-more-love-custom-spellbook-cheat-extended-maplebirch": SmokeProfile(
        name="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        required_mod_names=(
            "ModLoaderGui",
            "ModI18N",
            "maplebirch",
            "cheatExtended",
            "More Love Interests Mod",
            "Custom-Spellbook",
            "Lyra",
        ),
        required_globals=("spellBookMobileClicked",),
        click_selectors=('[onclick*="spellBookMobileClicked"]',),
    ),
    "none": SmokeProfile(name="none"),
}


@dataclass
class Issue:
    """One classified browser smoke finding."""

    severity: str
    kind: str
    source: str
    message: str
    url: str | None = None
    location: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrowserSmokeReport:
    """Serializable browser smoke report."""

    target: str
    profile: str
    report_only: bool
    success: bool = False
    html_path: str | None = None
    served_url: str | None = None
    elapsed_seconds: float = 0.0
    issues: list[Issue] = field(default_factory=list)
    console_messages: list[dict[str, Any]] = field(default_factory=list)
    network_failures: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddedModInfo:
    """Minimal metadata extracted from an embedded ModLoader ZIP payload."""

    index: int
    names: list[str] = field(default_factory=list)
    boot_json_found: bool = False
    error: str | None = None
    search_text: str = ""


ALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "usettings_inactive_normal",
        re.compile(r"usettings\.js not active, this is normal", re.IGNORECASE),
    ),
)

WARNING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "optional_remote_mod_list",
        re.compile(r"modList\.json", re.IGNORECASE),
    ),
    (
        "more_love_optional_dependency",
        re.compile(r"Remy Love Mod|NPC Avatars Mod", re.IGNORECASE),
    ),
    (
        "spellbook_external_asset",
        re.compile(r"style\.css|img/misc/banner\.png|banner\.png", re.IGNORECASE),
    ),
    (
        "usettings_optional_asset",
        re.compile(r"usettings\.js", re.IGNORECASE),
    ),
)

HIGH_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "spellbook_missing_click_handler",
        re.compile(r"spellBookMobileClicked.*not defined", re.IGNORECASE),
    ),
    (
        "prevent_default_type_error",
        re.compile(r"ev\.preventDefault is not a function", re.IGNORECASE),
    ),
    (
        "maplebirch_framework_missing",
        re.compile(r"maplebirchFrameworks.*not defined", re.IGNORECASE),
    ),
    (
        "tw_user_script_error",
        re.compile(r"Error \[tw-user-script-[^\]]*\]", re.IGNORECASE),
    ),
    ("reference_error", re.compile(r"\bReferenceError\b", re.IGNORECASE)),
    ("type_error", re.compile(r"\bTypeError\b", re.IGNORECASE)),
    ("uncaught_error", re.compile(r"\bUncaught\b", re.IGNORECASE)),
)


def _decode_base64_zip(encoded: str) -> bytes:
    payload = encoded.strip()
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)
    return base64.b64decode(payload, validate=True)


def _collect_string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _collect_string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _collect_string_values(item)


def extract_embedded_mods_from_html(content: str) -> list[EmbeddedModInfo]:
    """Extract best-effort embedded mod metadata from a built HTML file."""
    match = MOD_LIST_PATTERN.search(content)
    if not match:
        return []

    try:
        mod_entries = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    if not isinstance(mod_entries, list):
        return []

    embedded_mods: list[EmbeddedModInfo] = []
    for index, entry in enumerate(mod_entries):
        info = EmbeddedModInfo(index=index)
        embedded_mods.append(info)

        if not isinstance(entry, str):
            info.error = "modDataValueZipList entry is not a string"
            continue

        try:
            payload = _decode_base64_zip(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
                boot_names = [name for name in zf.namelist() if name.lower().endswith("boot.json")]
                if not boot_names:
                    info.error = "boot.json not found"
                    continue

                info.boot_json_found = True
                boot_text = zf.read(boot_names[0]).decode("utf-8", errors="replace")
                info.search_text = boot_text
                try:
                    boot_json = json.loads(boot_text)
                    strings = list(_collect_string_values(boot_json))
                    preferred_keys = ("name", "modName", "id", "nickName")
                    if isinstance(boot_json, dict):
                        for key in preferred_keys:
                            value = boot_json.get(key)
                            if isinstance(value, str):
                                info.names.append(value)
                    for value in strings:
                        if value not in info.names:
                            info.names.append(value)
                except json.JSONDecodeError:
                    info.names.append(boot_text[:120])
        except Exception as exc:  # noqa: BLE001 - report malformed embedded entries.
            info.error = str(exc)

    return embedded_mods


def classify_message(source: str, message: str) -> Issue:
    """Classify a browser message into allowed, warning, or high-risk."""
    for kind, pattern in ALLOWED_PATTERNS:
        if pattern.search(message):
            return Issue("allowed", kind, source, message)

    for kind, pattern in HIGH_RISK_PATTERNS:
        if pattern.search(message):
            return Issue("high", kind, source, message)

    for kind, pattern in WARNING_PATTERNS:
        if pattern.search(message):
            return Issue("warning", kind, source, message)

    if source in {"console.error", "pageerror"}:
        return Issue("high", "unexpected_browser_error", source, message)

    if source in {"requestfailed", "http_error"}:
        return Issue("warning", "network_failure", source, message)

    return Issue("warning", "browser_warning", source, message)


def _find_preferred_html(root: Path) -> Path | None:
    candidates = sorted(root.rglob("*.html"), key=lambda item: str(item).lower())
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: ("degrees of lewdity" not in item.name.lower(), str(item).lower()),
    )[0]


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = (destination / member.filename).resolve()
            try:
                member_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"unsafe ZIP member path: {member.filename}") from exc
        zf.extractall(destination)


def _resolve_target(target: Path, temp_root: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if not target.exists():
        raise FileNotFoundError(f"target does not exist: {target}")

    if target.is_file() and target.suffix.lower() == ".html":
        return target.parent, target

    if target.is_file() and target.suffix.lower() == ".zip":
        extract_dir = temp_root / target.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(target, extract_dir)
        html_path = _find_preferred_html(extract_dir)
        if html_path is None:
            raise FileNotFoundError(f"ZIP target has no HTML file: {target}")
        return extract_dir, html_path

    if target.is_dir():
        html_path = _find_preferred_html(target)
        if html_path is not None:
            return target, html_path

        zip_candidates = sorted(target.rglob("*.zip"), key=lambda item: str(item).lower())
        if zip_candidates:
            return _resolve_target(zip_candidates[0], temp_root)

    raise FileNotFoundError(f"target is not an HTML, ZIP, or artifact directory: {target}")


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that keeps CI logs focused on smoke findings."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - inherited name.
        return


@contextlib.contextmanager
def _serve_directory(directory: Path):
    handler = functools.partial(QuietHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _relative_url(server: http.server.ThreadingHTTPServer, serve_dir: Path, html_path: Path) -> str:
    relative = html_path.relative_to(serve_dir).as_posix()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/{quote(relative)}"


def _add_issue(report: BrowserSmokeReport, issue: Issue, **updates: Any) -> None:
    for key, value in updates.items():
        setattr(issue, key, value)
    report.issues.append(issue)


def _check_required_mods(
    report: BrowserSmokeReport,
    profile: SmokeProfile,
    embedded_mods: list[EmbeddedModInfo],
) -> None:
    search_text = "\n".join(
        [json.dumps(asdict(info), ensure_ascii=False) for info in embedded_mods]
        + [message.get("text", "") for message in report.console_messages]
    ).lower()
    required_results: dict[str, bool] = {}

    for mod_name in profile.required_mod_names:
        found = mod_name.lower() in search_text
        required_results[mod_name] = found
        if not found:
            _add_issue(
                report,
                Issue(
                    severity="high",
                    kind="required_mod_not_observed",
                    source="profile",
                    message=f"required mod was not observed: {mod_name}",
                ),
            )

    report.observations["required_mods"] = required_results


def _page_state_script(required_globals: tuple[str, ...]) -> str:
    return """
    (requiredGlobals) => {
      const globals = {};
      for (const name of requiredGlobals) {
        globals[name] = typeof window[name];
      }
      return {
        title: document.title,
        readyState: document.readyState,
        bodyTextSample: (document.body && document.body.innerText || '').slice(0, 500),
        hasJQuery: typeof window.jQuery !== 'undefined',
        hasSugarCube: typeof window.SugarCube !== 'undefined',
        hasModDataValueZipList: Array.isArray(window.modDataValueZipList),
        modDataValueZipListLength: Array.isArray(window.modDataValueZipList)
          ? window.modDataValueZipList.length
          : null,
        globals,
      };
    }
    """


def _run_playwright(
    report: BrowserSmokeReport,
    profile: SmokeProfile,
    url: str,
    timeout_ms: int,
    settle_ms: int,
) -> None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        _add_issue(
            report,
            Issue(
                severity="high",
                kind="playwright_missing",
                source="runner",
                message=f"Playwright is not installed: {exc}",
            ),
        )
        return

    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = context.new_page()

        def on_console(message: Any) -> None:
            entry = {
                "type": message.type,
                "text": message.text,
                "location": message.location,
            }
            report.console_messages.append(entry)
            if message.type in {"error", "warning"}:
                source = "console.error" if message.type == "error" else "console.warning"
                issue = classify_message(source, message.text)
                _add_issue(report, issue, location=message.location)

        def on_page_error(error: Any) -> None:
            text = str(error)
            page_errors.append(text)
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
            issue = classify_message("requestfailed", f"{request.url} {failure}")
            _add_issue(report, issue, url=request.url)

        def on_response(response: Any) -> None:
            if response.status < 400:
                return
            entry = {
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text,
            }
            report.network_failures.append(entry)
            issue = classify_message("http_error", f"{response.url} HTTP {response.status}")
            _add_issue(report, issue, url=response.url)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            with contextlib.suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15_000))
            page.wait_for_timeout(settle_ms)
        except PlaywrightTimeoutError as exc:
            _add_issue(
                report,
                Issue("high", "navigation_timeout", "runner", f"navigation timed out: {exc}"),
            )
        except PlaywrightError as exc:
            _add_issue(report, Issue("high", "browser_navigation_error", "runner", str(exc)))

        try:
            page_state = page.evaluate(_page_state_script(profile.required_globals), list(profile.required_globals))
            report.observations["page_state"] = page_state
            for global_name, global_type in page_state.get("globals", {}).items():
                if global_type != "function":
                    _add_issue(
                        report,
                        Issue(
                            "high",
                            "required_global_missing",
                            "profile",
                            f"window.{global_name} expected function, got {global_type}",
                        ),
                    )
        except PlaywrightError as exc:
            _add_issue(report, Issue("high", "page_state_error", "runner", str(exc)))

        click_results: dict[str, dict[str, Any]] = {}
        for selector in profile.click_selectors:
            result: dict[str, Any] = {"selector": selector, "found": 0, "clicked": False, "errors_after_click": []}
            click_results[selector] = result
            try:
                locator = page.locator(selector)
                count = locator.count()
                result["found"] = count
                if count == 0:
                    _add_issue(
                        report,
                        Issue(
                            "warning",
                            "click_selector_not_found",
                            "profile",
                            f"selector not found; may require navigation: {selector}",
                        ),
                    )
                    continue

                before_errors = len(page_errors)
                locator.first.click(timeout=3_000)
                page.wait_for_timeout(1_000)
                result["clicked"] = True
                result["errors_after_click"] = page_errors[before_errors:]
            except PlaywrightError as exc:
                _add_issue(
                    report,
                    Issue("high", "profile_click_failed", "profile", f"{selector}: {exc}"),
                )
        report.observations["click_results"] = click_results

        context.close()
        browser.close()


def _write_console_log(report: BrowserSmokeReport, output_dir: Path) -> None:
    lines = []
    for message in report.console_messages:
        location = message.get("location") or {}
        suffix = ""
        if location.get("url"):
            suffix = f" ({location.get('url')}:{location.get('lineNumber', '')})"
        lines.append(f"[{message.get('type')}] {message.get('text')}{suffix}")
    (output_dir / "console.log").write_text("\n".join(lines), encoding="utf-8")


def summarize_report(report: BrowserSmokeReport, top_limit: int = 5) -> dict[str, Any]:
    """Return a compact summary for CI step summaries and quick artifact checks."""
    high = [issue for issue in report.issues if issue.severity == "high"]
    warnings = [issue for issue in report.issues if issue.severity == "warning"]
    allowed = [issue for issue in report.issues if issue.severity == "allowed"]
    status = "pass" if report.success else "report_only_with_findings" if report.report_only else "fail"

    return {
        "status": status,
        "success": report.success,
        "report_only": report.report_only,
        "target": report.target,
        "profile": report.profile,
        "html_path": report.html_path,
        "served_url": report.served_url,
        "elapsed_seconds": round(report.elapsed_seconds, 2),
        "issue_counts": {
            "high": len(high),
            "warning": len(warnings),
            "allowed": len(allowed),
            "total": len(report.issues),
        },
        "top_high_risk": [asdict(issue) for issue in high[:top_limit]],
    }


def _write_markdown_report(report: BrowserSmokeReport, output_dir: Path) -> None:
    summary = summarize_report(report)
    high = [issue for issue in report.issues if issue.severity == "high"]
    warnings = [issue for issue in report.issues if issue.severity == "warning"]
    allowed = [issue for issue in report.issues if issue.severity == "allowed"]
    status = "PASS" if report.success else "REPORT ONLY - HIGH RISK FOUND" if report.report_only else "FAIL"
    counts = summary["issue_counts"]

    lines = [
        "# DoL-X Phase 4 Browser Smoke Report",
        "",
        f"- Status: `{status}`",
        f"- Success: `{report.success}`",
        f"- Report-only mode: `{report.report_only}`",
        f"- Target: `{report.target}`",
        f"- Profile: `{report.profile}`",
        f"- HTML: `{report.html_path}`",
        f"- URL: `{report.served_url}`",
        f"- Elapsed seconds: `{report.elapsed_seconds:.2f}`",
        f"- High risk issues: `{counts['high']}`",
        f"- Warnings: `{counts['warning']}`",
        f"- Allowed findings: `{counts['allowed']}`",
        f"- Total findings: `{counts['total']}`",
        "",
    ]

    if report.report_only and high:
        lines.extend(
            [
                "> This job is currently report-only: high-risk runtime findings are recorded but do not fail CI.",
                "",
            ]
        )

    if high:
        lines.extend(["## Top high-risk findings", ""])
        for issue in high[:5]:
            lines.append(f"- `{issue.kind}` from `{issue.source}`: {issue.message}")
        lines.append("")

    def add_issue_section(title: str, issues: list[Issue]) -> None:
        lines.extend([f"## {title}", ""])
        if not issues:
            lines.extend(["None.", ""])
            return
        for issue in issues:
            lines.append(f"- `{issue.kind}` from `{issue.source}`: {issue.message}")
            if issue.url:
                lines.append(f"  - URL: `{issue.url}`")
        lines.append("")

    add_issue_section("High risk issues", high)
    add_issue_section("Warnings", warnings)
    add_issue_section("Allowed findings", allowed)

    lines.extend(["## Observations", "", "```json"])
    lines.append(json.dumps(report.observations, ensure_ascii=False, indent=2))
    lines.extend(["```", ""])

    (output_dir / "browser-smoke-report.md").write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: BrowserSmokeReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report.success = not any(issue.severity == "high" for issue in report.issues)
    summary = summarize_report(report)
    (output_dir / "browser-smoke-report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "browser-smoke-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "network-failures.json").write_text(
        json.dumps(report.network_failures, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_console_log(report, output_dir)
    _write_markdown_report(report, output_dir)


def run_browser_smoke(args: argparse.Namespace) -> BrowserSmokeReport:
    start = time.monotonic()
    profile = PROFILES[args.profile]
    report = BrowserSmokeReport(
        target=str(args.target),
        profile=profile.name,
        report_only=args.report_only,
    )

    try:
        with tempfile.TemporaryDirectory(prefix="dolx-browser-smoke-") as temp_dir_name:
            serve_dir, html_path = _resolve_target(Path(args.target), Path(temp_dir_name))
            report.html_path = str(html_path)

            html_content = html_path.read_text(encoding="utf-8", errors="replace")
            embedded_mods = extract_embedded_mods_from_html(html_content)
            report.observations["embedded_mods"] = [asdict(info) for info in embedded_mods]

            with _serve_directory(serve_dir) as server:
                url = _relative_url(server, serve_dir, html_path)
                report.served_url = url
                _run_playwright(report, profile, url, args.timeout_ms, args.settle_ms)

            _check_required_mods(report, profile, embedded_mods)
    except Exception as exc:  # noqa: BLE001 - CI report must capture setup failures.
        _add_issue(report, Issue("high", "browser_smoke_setup_error", "runner", str(exc)))
    finally:
        report.elapsed_seconds = time.monotonic() - start

    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DoL-X Phase 4 browser smoke test")
    parser.add_argument("target", type=Path, help="Built ZIP, extracted package directory, or HTML file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/browser-smoke"),
        help="Directory for browser smoke reports",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        help="Mod-specific smoke profile",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Write high-risk findings but exit 0 so CI remains non-blocking",
    )
    parser.add_argument("--timeout-ms", type=int, default=60_000, help="Browser navigation timeout")
    parser.add_argument("--settle-ms", type=int, default=5_000, help="Wait after initial page load")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = run_browser_smoke(args)
    write_outputs(report, args.output_dir)

    high_count = sum(1 for issue in report.issues if issue.severity == "high")
    warning_count = sum(1 for issue in report.issues if issue.severity == "warning")
    print(
        f"Phase 4 browser smoke: success={report.success} "
        f"high={high_count} warnings={warning_count} report_only={report.report_only}"
    )
    print(f"Report: {args.output_dir / 'browser-smoke-report.md'}")

    if args.report_only:
        return 0
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
