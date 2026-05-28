"""Phase 4 browser smoke helper tests."""

import base64
import io
import json
import zipfile

import pytest

from tools.browser_smoke_test import classify_message, extract_embedded_mods_from_html


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
