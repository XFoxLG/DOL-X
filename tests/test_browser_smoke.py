"""Phase 4 browser smoke helper tests."""

import base64
import io
import json
from argparse import Namespace
import zipfile

import pytest

from tools.browser_smoke_test import (
    BrowserSmokeReport,
    Issue,
    classify_message,
    extract_embedded_mods_from_html,
    main,
    write_outputs,
)


def _embedded_mod_zip(boot_json: dict) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", json.dumps(boot_json, ensure_ascii=False))
        zf.writestr("main.js", "console.log('ok');")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.config
def test_browser_smoke_extracts_embedded_mod_names():
    payload = _embedded_mod_zip(
        {
            "name": "Custom-Spellbook",
            "version": "1.0.0",
            "alias": ["自定义魔法书"],
        }
    )
    html = f"<script>window.modDataValueZipList = {json.dumps([payload])};</script>"

    mods = extract_embedded_mods_from_html(html)

    assert len(mods) == 1
    assert mods[0].boot_json_found is True
    assert "Custom-Spellbook" in mods[0].names
    assert "自定义魔法书" in mods[0].names


@pytest.mark.config
@pytest.mark.parametrize(
    ("source", "message", "expected_kind"),
    [
        (
            "pageerror",
            "ReferenceError: spellBookMobileClicked is not defined",
            "spellbook_missing_click_handler",
        ),
        (
            "console.error",
            "TypeError: ev.preventDefault is not a function",
            "prevent_default_type_error",
        ),
        (
            "console.error",
            "Error [tw-user-script-0]: maplebirchFrameworks is not defined.",
            "maplebirch_framework_missing",
        ),
    ],
)
def test_browser_smoke_classifies_high_risk_runtime_errors(source, message, expected_kind):
    issue = classify_message(source, message)

    assert issue.severity == "high"
    assert issue.kind == expected_kind


@pytest.mark.config
@pytest.mark.parametrize(
    ("source", "message", "expected_kind"),
    [
        ("requestfailed", "http://127.0.0.1/modList.json net::ERR_FAILED", "optional_remote_mod_list"),
        ("console.warning", "NPC Avatars Mod not found", "more_love_optional_dependency"),
        ("http_error", "http://127.0.0.1/style.css HTTP 404", "spellbook_external_asset"),
        ("console.error", "usettings.js not active, this is normal", "usettings_inactive_normal"),
    ],
)
def test_browser_smoke_classifies_allowed_and_warning_findings(source, message, expected_kind):
    issue = classify_message(source, message)

    assert issue.kind == expected_kind
    assert issue.severity in {"allowed", "warning"}


@pytest.mark.config
def test_browser_smoke_keeps_runtime_errors_high_risk_before_warning_matches():
    issue = classify_message(
        "console.error",
        "TypeError: modList.json loader crashed before startup",
    )

    assert issue.severity == "high"
    assert issue.kind == "type_error"


@pytest.mark.config
def test_browser_smoke_treats_actions_node_warning_as_warning():
    issue = classify_message(
        "console.warning",
        "Node.js 20 actions are deprecated; update actions/checkout when available.",
    )

    assert issue.severity == "warning"
    assert issue.kind == "browser_warning"


@pytest.mark.config
def test_browser_smoke_summary_and_outputs_capture_report_only_findings(tmp_path):
    report = BrowserSmokeReport(
        target="build-artifacts/sample.zip",
        profile="ucb-more-love-custom-spellbook",
        report_only=True,
        html_path="Degrees of Lewdity.html",
        served_url="http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
    )
    report.issues.append(Issue("high", "type_error", "pageerror", "TypeError: boom"))
    report.issues.append(Issue("warning", "network_failure", "requestfailed", "optional asset missing"))

    write_outputs(report, tmp_path)

    summary = json.loads((tmp_path / "browser-smoke-summary.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "browser-smoke-report.md").read_text(encoding="utf-8")

    assert report.success is False
    assert summary["status"] == "report_only_with_findings"
    assert summary["issue_counts"] == {"high": 1, "warning": 1, "allowed": 0, "total": 2}
    assert summary["top_high_risk"][0]["kind"] == "type_error"
    assert "REPORT ONLY - HIGH RISK FOUND" in markdown
    assert "report-only" in markdown


@pytest.mark.config
def test_browser_smoke_report_only_main_exits_zero_with_high_risk(monkeypatch, tmp_path):
    def fake_run_browser_smoke(args: Namespace) -> BrowserSmokeReport:
        report = BrowserSmokeReport(target=str(args.target), profile=args.profile, report_only=args.report_only)
        report.issues.append(Issue("high", "reference_error", "pageerror", "ReferenceError: boom"))
        return report

    monkeypatch.setattr("tools.browser_smoke_test.run_browser_smoke", fake_run_browser_smoke)

    exit_code = main(["dummy.zip", "--output-dir", str(tmp_path), "--report-only"])

    report_json = json.loads((tmp_path / "browser-smoke-report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report_json["success"] is False


@pytest.mark.config
def test_browser_smoke_strict_main_exits_nonzero_with_high_risk(monkeypatch, tmp_path):
    def fake_run_browser_smoke(args: Namespace) -> BrowserSmokeReport:
        report = BrowserSmokeReport(target=str(args.target), profile=args.profile, report_only=args.report_only)
        report.issues.append(Issue("high", "reference_error", "pageerror", "ReferenceError: boom"))
        return report

    monkeypatch.setattr("tools.browser_smoke_test.run_browser_smoke", fake_run_browser_smoke)

    exit_code = main(["dummy.zip", "--output-dir", str(tmp_path)])

    assert exit_code == 1
