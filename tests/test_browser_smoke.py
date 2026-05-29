"""Phase 4 browser smoke helper tests."""

import base64
import io
import json
import urllib.request
from argparse import Namespace
import zipfile

import pytest

from tools.browser_smoke_test import (
    BrowserSmokeReport,
    Issue,
    PROFILES,
    _find_preferred_html,
    _record_package_identity,
    _record_static_asset_audit,
    _serve_directory,
    classify_message,
    extract_embedded_mods_from_html,
    main,
    parse_args,
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
        (
            "console.error",
            "Failed to load image img/face/default/default/blush1.png for layer blush",
            "image_layer_load_failed",
        ),
        (
            "http_error",
            "http://127.0.0.1/img/face/default/default/blush1.png HTTP 404",
            "face_image_asset_missing",
        ),
        (
            "pageerror",
            "ReferenceError: skinColourFullback is not defined",
            "skin_colour_fallback_missing",
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
def test_browser_smoke_default_profile_targets_mainline():
    args = parse_args(["dummy.zip"])
    profile = PROFILES[args.profile]

    assert args.profile == "ucb-more-love-custom-spellbook"
    assert "BetterCheatCommandManagement" in profile.required_mod_names
    assert "cheatExtended" not in profile.required_mod_names
    assert "maplebirch" not in profile.required_mod_names
    assert profile.dialog_password == "DOL-Custom-Spellbook-Mod"
    assert "spellBookMobileClicked" in profile.warning_globals
    assert "spellBookMobileClicked" not in profile.required_globals


@pytest.mark.config
def test_browser_smoke_can_select_cheat_experiment_profile():
    args = parse_args(["dummy.zip", "--profile", "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"])
    profile = PROFILES[args.profile]

    assert args.profile == "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"
    assert "cheatExtended" in profile.required_mod_names
    assert "maplebirch" in profile.required_mod_names
    assert "BetterCheatCommandManagement" not in profile.required_mod_names
    assert profile.dialog_password == "DOL-Custom-Spellbook-Mod"
    assert "spellBookMobileClicked" in profile.warning_globals
    assert "spellBookMobileClicked" not in profile.required_globals


@pytest.mark.config
def test_browser_smoke_custom_spellbook_profiles_use_password_and_warning_global():
    for profile_name in (
        "ucb-more-love-custom-spellbook",
        "ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
    ):
        profile = PROFILES[profile_name]

        assert profile.dialog_password == "DOL-Custom-Spellbook-Mod"
        assert "spellBookMobileClicked" in profile.warning_globals
        assert "spellBookMobileClicked" not in profile.required_globals


@pytest.mark.config
def test_browser_smoke_summary_and_outputs_capture_report_only_findings(tmp_path):
    report = BrowserSmokeReport(
        target="build-artifacts/sample.zip",
        profile="ucb-more-love-custom-spellbook",
        report_only=True,
        ci_context={
            "workflow_run_id": "12345",
            "workflow_head_branch": "experiment/cheat-extended-maplebirch",
            "workflow_head_sha": "abcdef0",
            "artifact_name": "dol-builds-zip-sample",
        },
        html_path="Degrees of Lewdity.html",
        served_url="http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
    )
    report.observations["dialogs"] = [
        {"type": "prompt", "accepted": True, "password_supplied": True}
    ]
    report.observations["browser_boot"] = {
        "navigation_ok": True,
        "has_sugarcube": True,
        "has_mod_data_value_zip_list": True,
        "dialog_count": 1,
    }
    report.observations["game_ready"] = {
        "ready": True,
        "hasJQuery": True,
        "hasSugarCube": True,
        "passage": "Start",
        "loadingLike": False,
        "interactiveElementCount": 4,
    }
    report.observations["enter_game"] = {
        "attempted": True,
        "success": True,
        "reason": "playable_state_observed",
        "passage_before": "Start",
        "passage_after": "Bedroom",
        "new_high_risk_errors": [],
    }
    report.observations["package_identity"] = {
        "package_slug": "DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-custom-spellbook-0528",
        "workflow_head_branch": "vega",
        "expected_profile_for_branch": "ucb-more-love-custom-spellbook",
        "branch_profile_match": True,
        "profile_slug_match": True,
        "forbidden_slug_tokens_present": [],
    }
    report.observations["screenshot"] = {
        "path": "output/browser-smoke/browser-smoke-final.png",
        "full_page": True,
    }
    report.observations["static_asset_audit"] = {
        "face_dir_exists": True,
        "face_png_count": 1,
        "blush_png_count": 1,
        "required_face_assets": [
            {"path": "img/face/default/default/blush1.png", "exists": True},
        ],
    }
    report.issues.append(Issue("high", "type_error", "pageerror", "TypeError: boom"))
    report.issues.append(Issue("warning", "network_failure", "requestfailed", "optional asset missing"))

    write_outputs(report, tmp_path)

    summary = json.loads((tmp_path / "browser-smoke-summary.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "browser-smoke-report.md").read_text(encoding="utf-8")

    assert report.success is False
    assert summary["status"] == "report_only_with_findings"
    assert summary["ci_context"]["workflow_head_branch"] == "experiment/cheat-extended-maplebirch"
    assert summary["dialog_observations"][0]["password_supplied"] is True
    assert summary["browser_boot"] == {
        "navigation_ok": True,
        "has_sugarcube": True,
        "has_mod_data_value_zip_list": True,
        "dialog_count": 1,
    }
    assert summary["game_ready"]["ready"] is True
    assert summary["game_ready"]["has_jquery"] is True
    assert summary["game_ready"]["has_sugarcube"] is True
    assert summary["game_ready"]["passage"] == "Start"
    assert summary["game_ready"]["interactive_element_count"] == 4
    assert summary["enter_game"]["attempted"] is True
    assert summary["enter_game"]["success"] is True
    assert summary["enter_game"]["reason"] == "playable_state_observed"
    assert summary["enter_game"]["passage_before"] == "Start"
    assert summary["enter_game"]["passage_after"] == "Bedroom"
    assert summary["enter_game"]["new_high_risk_count"] == 0
    assert summary["package_identity"]["package_slug"].endswith("ucb-more-love-custom-spellbook-0528")
    assert summary["package_identity"]["branch_profile_match"] is True
    assert summary["package_identity"]["profile_slug_match"] is True
    assert summary["screenshot"]["path"].endswith("browser-smoke-final.png")
    assert summary["static_asset_audit"]["face_dir_exists"] is True
    assert summary["static_asset_audit"]["required_face_assets"][0]["exists"] is True
    assert summary["issue_counts"] == {"high": 1, "warning": 1, "allowed": 0, "total": 2}
    assert summary["top_high_risk"][0]["kind"] == "type_error"
    assert "REPORT ONLY - HIGH RISK FOUND" in markdown
    assert "Browser navigation OK" in markdown
    assert "SugarCube ready" in markdown
    assert "Entered playable scene" in markdown
    assert "Package slug" in markdown
    assert "Branch/profile match" in markdown
    assert "Screenshot" in markdown
    assert "Face asset dir exists" in markdown
    assert "## CI context" in markdown
    assert "workflow_head_branch" in markdown
    assert "report-only" in markdown


@pytest.mark.config
def test_browser_smoke_outputs_pass_when_playable_without_high_risk(tmp_path):
    report = BrowserSmokeReport(
        target="build-artifacts/sample.zip",
        profile="ucb-more-love-custom-spellbook",
        report_only=True,
        html_path="Degrees of Lewdity.html",
        served_url="http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
    )
    report.observations["browser_boot"] = {
        "navigation_ok": True,
        "has_sugarcube": True,
        "has_mod_data_value_zip_list": True,
    }
    report.observations["game_ready"] = {
        "ready": True,
        "hasSugarCube": True,
        "loadingLike": False,
        "passage": "Bedroom",
        "interactiveElementCount": 1,
    }
    report.observations["enter_game"] = {
        "attempted": True,
        "success": True,
        "reason": "playable_state_observed",
        "new_high_risk_errors": [],
    }

    write_outputs(report, tmp_path)

    summary = json.loads((tmp_path / "browser-smoke-summary.json").read_text(encoding="utf-8"))
    assert report.success is True
    assert summary["status"] == "pass"


@pytest.mark.config
def test_browser_smoke_outputs_findings_when_game_never_ready(tmp_path):
    report = BrowserSmokeReport(
        target="build-artifacts/sample.zip",
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=True,
        html_path="Degrees of Lewdity.html",
        served_url="http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
    )
    report.observations["browser_boot"] = {
        "navigation_ok": True,
        "has_sugarcube": True,
        "has_mod_data_value_zip_list": True,
    }
    report.observations["game_ready"] = {
        "ready": False,
        "hasSugarCube": True,
        "loadingLike": False,
        "passage": None,
        "interactiveElementCount": 0,
    }
    report.observations["enter_game"] = {
        "attempted": False,
        "success": False,
        "reason": "game_not_ready",
        "new_high_risk_errors": [],
    }
    report.issues.append(Issue("warning", "game_ready_incomplete", "game_ready", "game runtime was observed but not fully ready"))

    write_outputs(report, tmp_path)

    summary = json.loads((tmp_path / "browser-smoke-summary.json").read_text(encoding="utf-8"))
    assert report.success is False
    assert summary["status"] == "report_only_with_findings"
    assert summary["issue_counts"] == {"high": 0, "warning": 1, "allowed": 0, "total": 1}


@pytest.mark.config
def test_browser_smoke_records_static_asset_audit(tmp_path):
    report = BrowserSmokeReport(
        target=str(tmp_path),
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=True,
    )
    package_root = tmp_path / "package"
    face_dir = package_root / "img" / "face" / "default" / "default"
    face_dir.mkdir(parents=True)
    (face_dir / "blush1.png").write_bytes(b"png")
    (package_root / "other-blush.png").write_bytes(b"png")

    audit = _record_static_asset_audit(report, package_root)

    assert audit["face_dir_exists"] is True
    assert audit["face_png_count"] == 1
    assert audit["blush_png_count"] == 2
    assert audit["required_face_assets"] == [
        {"path": "img/face/default/default/blush1.png", "exists": True},
    ]
    assert not report.issues


@pytest.mark.config
def test_browser_smoke_warns_when_expected_face_assets_are_missing(tmp_path):
    report = BrowserSmokeReport(
        target=str(tmp_path),
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=True,
    )
    package_root = tmp_path / "package"
    package_root.mkdir()

    audit = _record_static_asset_audit(report, package_root)

    assert audit["face_dir_exists"] is False
    assert audit["required_face_assets"][0]["exists"] is False
    assert [issue.kind for issue in report.issues] == [
        "face_asset_directory_missing",
        "face_blush_asset_not_packaged",
    ]


@pytest.mark.config
def test_browser_smoke_prefers_base_html_before_au_variant(tmp_path):
    base_dir = tmp_path / "DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-custom-spellbook-0528"
    au_dir = tmp_path / "DoL-0.5.8.10-XFox-3.1.3a-au-a-ucb-more-love-custom-spellbook-0528"
    base_dir.mkdir()
    au_dir.mkdir()
    base_html = base_dir / "Degrees of Lewdity.html"
    au_html = au_dir / "Degrees of Lewdity.html"
    au_html.write_text("<html>au</html>", encoding="utf-8")
    base_html.write_text("<html>base</html>", encoding="utf-8")

    assert _find_preferred_html(tmp_path) == base_html


@pytest.mark.config
def test_browser_smoke_server_stubs_missing_mod_list_json(tmp_path):
    with _serve_directory(tmp_path) as server:
        port = server.server_address[1]
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}/modList.json", timeout=5)
        body = response.read().decode("utf-8")

    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert body == "[]\n"


@pytest.mark.config
def test_browser_smoke_records_package_identity_for_mainline(tmp_path):
    report = BrowserSmokeReport(
        target=str(tmp_path / "DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-custom-spellbook-0528.zip"),
        profile="ucb-more-love-custom-spellbook",
        report_only=True,
        ci_context={"workflow_head_branch": "vega"},
    )
    html_dir = tmp_path / "DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-custom-spellbook-0528"
    html_dir.mkdir()
    html_path = html_dir / "Degrees of Lewdity.html"
    html_path.write_text("", encoding="utf-8")

    identity = _record_package_identity(report, PROFILES[report.profile], html_dir, html_path)

    assert identity["package_slug"] == html_dir.name
    assert identity["expected_profile_for_branch"] == "ucb-more-love-custom-spellbook"
    assert identity["branch_profile_match"] is True
    assert identity["profile_slug_match"] is True
    assert not report.issues


@pytest.mark.config
def test_browser_smoke_flags_experiment_slug_under_mainline_profile(tmp_path):
    report = BrowserSmokeReport(
        target=str(tmp_path / "DoL-0.5.8.10-XFox-3.1.3a-au-a-ucb-more-love-custom-spellbook-cheat-extended-maplebirch-0528"),
        profile="ucb-more-love-custom-spellbook",
        report_only=True,
        ci_context={"workflow_head_branch": "vega"},
    )
    html_dir = tmp_path / "DoL-0.5.8.10-XFox-3.1.3a-au-a-ucb-more-love-custom-spellbook-cheat-extended-maplebirch-0528"
    html_dir.mkdir()
    html_path = html_dir / "Degrees of Lewdity.html"
    html_path.write_text("", encoding="utf-8")

    identity = _record_package_identity(report, PROFILES[report.profile], html_dir, html_path)

    assert identity["profile_slug_match"] is False
    assert identity["forbidden_slug_tokens_present"] == ["cheat-extended", "maplebirch"]
    assert [issue.kind for issue in report.issues] == [
        "package_forbidden_slug_token_present",
        "package_forbidden_slug_token_present",
    ]


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
