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
    CHEAT_EXTENDED_RUNTIME_MOD_PROBES,
    ENTER_GAME_LABELS,
    Issue,
    PROFILES,
    EmbeddedModInfo,
    _find_preferred_html,
    _check_required_mods,
    _looks_playable,
    _record_package_identity,
    _record_static_asset_audit,
    _page_state_script,
    _startup_instability_triggers,
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
            "browser_dialog",
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
        (
            "console.error",
            "http://127.0.0.1/style.css Failed to load resource: the server responded with a status of 404 (File not found)",
            "spellbook_external_asset",
        ),
        (
            "console.error",
            "ModOrderContainer getByNameOne() cannot find name. [Simple Frameworks, ModOrderContainer]",
            "simple_frameworks_optional_lookup",
        ),
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
    assert "ModLoaderGui" in profile.required_mod_names
    assert "ModI18N" in profile.required_mod_names
    assert "More Love Interests Mod" in profile.required_mod_names
    assert "Custom-Spellbook" in profile.required_mod_names
    assert "Lyra" in profile.required_mod_names
    assert "Cheat-Lyra" not in profile.required_mod_names
    assert "CombatStatusDisplay-Lyra" not in profile.required_mod_names
    assert "BetterCheatCommandManagement" not in profile.required_mod_names
    assert "cheatExtended" not in profile.required_mod_names
    assert "maplebirch" not in profile.required_mod_names
    assert profile.dialog_password == "DOL-Custom-Spellbook-Mod"
    assert "spellBookMobileClicked" in profile.warning_globals
    assert "spellBookMobileClicked" not in profile.required_globals


@pytest.mark.config
def test_browser_smoke_mainline_required_mods_match_current_stable_metadata():
    report = BrowserSmokeReport(
        target="stable.zip",
        profile="ucb-more-love-custom-spellbook",
        report_only=True,
    )
    embedded_mods = [
        EmbeddedModInfo(index=0, names=["ModLoaderGui"]),
        EmbeddedModInfo(index=1, names=["ModI18N"]),
        EmbeddedModInfo(index=2, names=["More Love Interests Mod"]),
        EmbeddedModInfo(index=3, names=["Custom-Spellbook"]),
        EmbeddedModInfo(index=4, names=["Lyra"]),
    ]

    _check_required_mods(report, PROFILES[report.profile], embedded_mods)

    assert report.observations["required_mods"] == {
        "ModLoaderGui": True,
        "ModI18N": True,
        "More Love Interests Mod": True,
        "Custom-Spellbook": True,
        "Lyra": True,
    }
    assert not report.issues


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
    assert profile.diagnostic_globals == (
        "maplebirchFrameworks",
        "CE_options",
        "SCMLSimpleFramework",
    )
    assert profile.diagnostic_mod_names == CHEAT_EXTENDED_RUNTIME_MOD_PROBES


@pytest.mark.config
def test_browser_smoke_can_select_stable_replacement_cheat_profile():
    args = parse_args(["dummy.zip", "--profile", "ucb-cheat-extended-maplebirch"])
    profile = PROFILES[args.profile]

    assert args.profile == "ucb-cheat-extended-maplebirch"
    assert "ModLoaderGui" in profile.required_mod_names
    assert "ModI18N" in profile.required_mod_names
    assert "cheatExtended" in profile.required_mod_names
    assert "maplebirch" in profile.required_mod_names
    assert "Lyra" in profile.required_mod_names
    assert "More Love Interests Mod" not in profile.required_mod_names
    assert "Custom-Spellbook" not in profile.required_mod_names
    assert "BetterCheatCommandManagement" not in profile.required_mod_names
    assert profile.dialog_password is None
    assert "spellBookMobileClicked" not in profile.required_globals
    assert "spellBookMobileClicked" not in profile.warning_globals
    assert profile.diagnostic_globals == (
        "maplebirchFrameworks",
        "CE_options",
        "SCMLSimpleFramework",
    )
    assert profile.diagnostic_mod_names == CHEAT_EXTENDED_RUNTIME_MOD_PROBES


@pytest.mark.config
def test_browser_smoke_page_state_script_includes_canary_getmod_probes():
    script = _page_state_script(("maplebirchFrameworks",))

    assert "modProbes" in script
    assert "window.modUtils.getMod" in script
    assert "modNames" in script
    assert CHEAT_EXTENDED_RUNTIME_MOD_PROBES == ("maplebirch", "Simple Frameworks")


@pytest.mark.config
@pytest.mark.parametrize("branch", ["experiment/cheat-extended-maplebirch", "vega"])
def test_browser_smoke_canary_artifact_accepts_stable_replacement_profile(branch, tmp_path):
    report = BrowserSmokeReport(
        target="canary-artifacts",
        profile="ucb-cheat-extended-maplebirch",
        report_only=True,
        ci_context={
            "workflow_head_branch": branch,
            "artifact_name": "dol-builds-cheat-canary-zip",
        },
    )
    target = tmp_path / "canary-artifacts"
    html_path = (
        target
        / "DoL-0.5.8.10-XFox-3.1.3a-ucb-cheat-extended-maplebirch-0531"
        / "Degrees of Lewdity.html"
    )

    identity = _record_package_identity(report, PROFILES[report.profile], target, html_path)

    assert identity["expected_profile_for_artifact"] == "ucb-cheat-extended-maplebirch"
    assert identity["expected_profile_source"] == "artifact"
    assert identity["branch_profile_match"] is True
    assert identity["profile_slug_match"] is True
    assert not [issue for issue in report.issues if issue.kind == "branch_profile_mismatch"]


@pytest.mark.config
def test_browser_smoke_non_canary_artifact_keeps_branch_profile_guard(tmp_path):
    report = BrowserSmokeReport(
        target="build-artifacts",
        profile="ucb-cheat-extended-maplebirch",
        report_only=True,
        ci_context={
            "workflow_head_branch": "experiment/cheat-extended-maplebirch",
            "artifact_name": "dol-builds-zip-sample",
        },
    )
    target = tmp_path / "build-artifacts"
    html_path = (
        target
        / "DoL-0.5.8.10-XFox-3.1.3a-ucb-cheat-extended-maplebirch-0531"
        / "Degrees of Lewdity.html"
    )

    identity = _record_package_identity(report, PROFILES[report.profile], target, html_path)

    assert identity["expected_profile_for_branch"] == "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"
    assert identity["expected_profile_for_artifact"] is None
    assert identity["expected_profile_source"] == "branch"
    assert identity["branch_profile_match"] is False
    assert identity["profile_slug_match"] is True
    assert [issue.kind for issue in report.issues] == ["branch_profile_mismatch"]


@pytest.mark.config
def test_browser_smoke_explicit_canary_gate_can_allow_branch_profile_mismatch(tmp_path):
    report = BrowserSmokeReport(
        target="maplebirch-version-gate-reports",
        profile="ucb-cheat-extended-maplebirch",
        report_only=True,
        ci_context={
            "workflow_head_branch": "vega",
            "artifact_name": "maplebirch-version-gate-reports",
        },
    )
    target = tmp_path / "maplebirch-version-gate-reports"
    html_path = (
        target
        / "DoL-0.5.8.10-XFox-3.1.3a-ucb-cheat-extended-maplebirch-33024"
        / "Degrees of Lewdity.html"
    )

    identity = _record_package_identity(
        report,
        PROFILES[report.profile],
        target,
        html_path,
        allow_branch_profile_mismatch=True,
    )

    assert identity["expected_profile_for_branch"] == "ucb-more-love-custom-spellbook"
    assert identity["expected_profile_for_artifact"] is None
    assert identity["expected_profile_source"] == "branch"
    assert identity["branch_profile_mismatch_allowed"] is True
    assert identity["branch_profile_match"] is True
    assert identity["profile_slug_match"] is True
    assert not [issue for issue in report.issues if issue.kind == "branch_profile_mismatch"]


@pytest.mark.config
def test_browser_smoke_canary_gate_profile_override_is_explicit():
    args = parse_args(["dummy.zip", "--allow-branch-profile-mismatch"])

    assert args.allow_branch_profile_mismatch is True
    assert parse_args(["dummy.zip"]).allow_branch_profile_mismatch is False


@pytest.mark.config
@pytest.mark.parametrize("branch", ["vega", "experiment/cheat-extended-maplebirch"])
def test_browser_smoke_baseline_candidate_artifact_uses_candidate_profile_override(branch, tmp_path):
    report = BrowserSmokeReport(
        target="baseline-candidate-zip-artifacts",
        profile="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        report_only=True,
        ci_context={
            "workflow_head_branch": branch,
            "artifact_name": "baseline-candidate-zip-artifacts",
        },
    )
    target = tmp_path / "baseline-candidate-zip-artifacts"
    html_path = (
        target
        / "DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-custom-spellbook-cheat-extended-maplebirch-57602"
        / "Degrees of Lewdity.html"
    )

    identity = _record_package_identity(report, PROFILES[report.profile], target, html_path)

    assert identity["expected_profile_for_artifact"] == "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"
    assert identity["expected_profile_source"] == "artifact"
    assert identity["branch_profile_match"] is True
    assert identity["profile_slug_match"] is True
    assert not [issue for issue in report.issues if issue.kind == "branch_profile_mismatch"]


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
def test_browser_smoke_does_not_treat_start_passage_as_playable_scene():
    start_state = {
        "ready": True,
        "loadingLike": False,
        "passage": "Start",
        "interactiveElementCount": 4,
        "bodyTextLength": 5000,
    }
    start2_state = {
        "ready": True,
        "loadingLike": False,
        "passage": "Start2",
        "interactiveElementCount": 6,
        "bodyTextLength": 5000,
    }
    bedroom_state = {
        "ready": True,
        "loadingLike": False,
        "passage": "Bedroom",
        "interactiveElementCount": 1,
        "bodyTextLength": 500,
    }

    assert _looks_playable(start_state) is False
    assert _looks_playable(start2_state) is False
    assert _looks_playable(bedroom_state) is True
    assert "(1) 开始游戏！" in ENTER_GAME_LABELS
    assert "进入游戏" in ENTER_GAME_LABELS
    assert "开始游戏" in ENTER_GAME_LABELS


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
    report.observations["navigation_events"] = [
        {
            "type": "framenavigated",
            "url": "http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
            "name": "",
            "main_frame": True,
        },
        {
            "type": "document_request_failed",
            "url": "http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
            "method": "GET",
            "failure": "net::ERR_ABORTED",
            "is_navigation_request": True,
        },
    ]
    report.observations["pageerror_context"] = [
        {
            "message": "TypeError: boom",
            "stack": "TypeError: boom\n    at startup.js:1:1",
            "url": "http://127.0.0.1:12345/Degrees%20of%20Lewdity.html",
            "ready_state": "interactive",
            "recent_navigation_events": report.observations["navigation_events"],
        }
    ]
    report.observations["startup_instability"] = {
        "context_destroyed": True,
        "document_abort": True,
        "extra_navigation": False,
        "main_frame_navigation_count": 1,
        "should_retry": True,
    }
    report.observations["game_ready_stability_retry"] = {
        "attempted": True,
        "trigger": report.observations["startup_instability"],
        "initial_ready": False,
        "initial_has_sugarcube": False,
        "page_state_after_wait": {
            "readyState": "complete",
            "hasSugarCube": True,
        },
        "game_ready_after_wait": {
            "ready": True,
            "hasSugarCube": True,
        },
    }
    report.observations["final_page_state"] = {
        "readyState": "complete",
        "hasSugarCube": True,
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
    assert summary["browser_diagnostics"]["navigation_event_count"] == 2
    assert summary["browser_diagnostics"]["document_abort_count"] == 1
    assert summary["browser_diagnostics"]["main_frame_navigation_count"] == 1
    assert summary["browser_diagnostics"]["pageerror_count"] == 1
    assert summary["browser_diagnostics"]["pageerror_samples"][0]["stack"].startswith("TypeError: boom")
    assert summary["browser_diagnostics"]["startup_instability"]["should_retry"] is True
    assert summary["browser_diagnostics"]["stability_retry_attempted"] is True
    assert summary["browser_diagnostics"]["stability_retry_ready_after_wait"] is True
    assert summary["browser_diagnostics"]["stability_retry_has_sugarcube_after_wait"] is True
    assert summary["browser_diagnostics"]["final_ready_state"] == "complete"
    assert summary["browser_diagnostics"]["final_has_sugarcube"] is True
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
    assert "Browser startup diagnostics" in markdown
    assert "Browser navigation events" in markdown
    assert "Startup stability retry attempted" in markdown
    assert "Final page readyState" in markdown
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
def test_browser_smoke_summary_captures_blocker_diagnostics(tmp_path):
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
        "dialog_count": 0,
        "popup_count": 1,
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
    report.observations["startup_interactions"] = {
        "attempted": True,
        "success": True,
        "reason": "playable_state_observed",
        "step_count": 3,
        "clicked_count": 3,
        "password_supplied": True,
        "consent_accepted_count": 2,
        "final_passage": "Bedroom",
        "last_action": "accept_consent_gate",
        "startup_gate_after": {"has_gate": False, "reason": "no_startup_gate"},
        "steps": [
            {
                "step": 1,
                "passage_before": None,
                "passage_after": "Start",
                "playable_after": False,
                "gate_before": {"has_gate": True, "reason": "custom_spellbook_sweetalert"},
                "gate_after": {"has_gate": False, "reason": "no_startup_gate"},
                "action": {
                    "action": "fill_custom_spellbook_password",
                    "clicked": True,
                    "button_text": "OK",
                    "password_supplied": True,
                },
            },
            {
                "step": 2,
                "passage_before": "Start",
                "passage_after": "Start",
                "playable_after": False,
                "gate_before": {
                    "has_gate": True,
                    "reason": "consent_label_visible",
                    "consent_label": "我确定我已年满十八岁",
                },
                "gate_after": {
                    "has_gate": True,
                    "reason": "consent_label_visible",
                    "consent_label": "我已阅读并理解上述说明",
                },
                "action": {
                    "action": "accept_consent_gate",
                    "clicked": True,
                    "button_text": "进入游戏",
                    "consent_label": "我确定我已年满十八岁",
                },
            },
            {
                "step": 3,
                "passage_before": "Start",
                "passage_after": "Bedroom",
                "playable_after": True,
                "gate_before": {
                    "has_gate": True,
                    "reason": "consent_label_visible",
                    "consent_label": "我已阅读并理解上述说明",
                },
                "gate_after": {"has_gate": False, "reason": "no_startup_gate"},
                "action": {
                    "action": "accept_consent_gate",
                    "clicked": True,
                    "button_text": "我已知晓",
                    "consent_label": "我已阅读并理解上述说明",
                },
            },
        ],
    }
    report.observations["modal_blockers"] = {
        "stage": "after_game_ready",
        "count": 1,
        "items": [
            {
                "selector": ".swal2-container",
                "simpleSelector": "div.swal2-container",
                "textSample": "Mod setup needs confirmation",
                "buttonTexts": ["OK"],
            }
        ],
    }
    report.observations["blocker_dismissal"] = {
        "initial_count": 1,
        "final_count": 0,
        "clicked_count": 1,
        "clicked": True,
        "attempts": [
            {
                "attempt": 1,
                "click": {
                    "clicked": True,
                    "text": "OK",
                    "rootSelector": ".swal2-container",
                    "blockerCount": 1,
                },
            }
        ],
    }
    report.observations["browser_popups"] = [
        {
            "source": "page.popup",
            "url": "http://127.0.0.1:12345/popup.html",
            "title": "Mod setup",
            "body_text_sample": "Click OK to continue",
            "closed": False,
        }
    ]
    report.observations["dialogs"] = [
        {
            "type": "alert",
            "message": "TypeError: ev.preventDefault is not a function",
            "accepted": True,
            "password_supplied": False,
        }
    ]
    report.observations["runtime_globals"] = {
        "maplebirchFrameworks": "undefined",
        "CE_options": "undefined",
        "SCMLSimpleFramework": "object",
    }

    write_outputs(report, tmp_path)

    summary = json.loads((tmp_path / "browser-smoke-summary.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "browser-smoke-report.md").read_text(encoding="utf-8")

    assert summary["blockers"]["modal_count"] == 1
    assert summary["blockers"]["modal_samples"][0] == {
        "selector": ".swal2-container",
        "simple_selector": "div.swal2-container",
        "text_sample": "Mod setup needs confirmation",
        "button_texts": ["OK"],
    }
    assert summary["blockers"]["popup_count"] == 1
    assert summary["blockers"]["popup_samples"][0]["source"] == "page.popup"
    assert summary["blockers"]["dismissal_attempts"] == 1
    assert summary["blockers"]["dismissal_clicked"] is True
    assert summary["blockers"]["dismissal_clicked_count"] == 1
    assert summary["blockers"]["dismissal_initial_count"] == 1
    assert summary["blockers"]["dismissal_final_count"] == 0
    assert summary["startup_interactions"]["attempted"] is True
    assert summary["startup_interactions"]["success"] is True
    assert summary["startup_interactions"]["step_count"] == 3
    assert summary["startup_interactions"]["clicked_count"] == 3
    assert summary["startup_interactions"]["password_supplied"] is True
    assert summary["startup_interactions"]["consent_accepted_count"] == 2
    assert summary["startup_interactions"]["final_passage"] == "Bedroom"
    assert summary["startup_interactions"]["startup_gate_after"] == {"has_gate": False, "reason": "no_startup_gate"}
    assert summary["startup_interactions"]["browser_dialogs"][0]["type"] == "alert"
    assert "ev.preventDefault" in summary["startup_interactions"]["browser_dialogs"][0]["message"]
    assert summary["startup_interactions"]["steps"][0]["action"] == "fill_custom_spellbook_password"
    assert summary["startup_interactions"]["steps"][0]["gate_before_reason"] == "custom_spellbook_sweetalert"
    assert summary["startup_interactions"]["steps"][1]["consent_label"] == "我确定我已年满十八岁"
    assert summary["startup_interactions"]["steps"][1]["gate_before_consent_label"] == "我确定我已年满十八岁"
    assert summary["runtime_globals"] == {
        "maplebirchFrameworks": "undefined",
        "CE_options": "undefined",
        "SCMLSimpleFramework": "object",
    }
    assert "Browser popups observed" in markdown
    assert "Runtime globals observed" in markdown
    assert "Modal blockers observed" in markdown
    assert "Blocker dismissal clicked" in markdown
    assert "Startup interaction steps" in markdown
    assert "Startup password supplied" in markdown
    assert "Startup gate after" in markdown
    assert "Startup browser dialogs" in markdown
    assert "## Startup interactions" in markdown


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
    report.observations["startup_interactions"] = {
        "attempted": True,
        "success": False,
        "reason": "max_steps_reached",
        "step_count": 15,
        "clicked_count": 0,
        "password_supplied": False,
        "consent_accepted_count": 0,
        "final_passage": None,
        "last_action": "no_action",
        "last_visible_text_sample": "ModLoader is still preparing the game.",
        "last_visible_text_length": 38,
        "recent_modloader_logs": ["[log] ModLoader still initializing"],
        "steps": [
            {
                "step": 15,
                "passage_before": None,
                "passage_after": None,
                "playable_after": False,
                "action": {"action": "no_action", "clicked": False},
            }
        ],
    }
    report.issues.append(Issue("warning", "game_ready_incomplete", "game_ready", "game runtime was observed but not fully ready"))

    write_outputs(report, tmp_path)

    summary = json.loads((tmp_path / "browser-smoke-summary.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "browser-smoke-report.md").read_text(encoding="utf-8")
    assert report.success is False
    assert summary["status"] == "report_only_with_findings"
    assert summary["issue_counts"] == {"high": 0, "warning": 1, "allowed": 0, "total": 1}
    assert summary["startup_interactions"]["reason"] == "max_steps_reached"
    assert summary["startup_interactions"]["last_visible_text_sample"] == "ModLoader is still preparing the game."
    assert summary["startup_interactions"]["recent_modloader_logs"] == ["[log] ModLoader still initializing"]
    assert "Startup final visible text sample" in markdown
    assert "Startup recent ModLoader logs" in markdown


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
