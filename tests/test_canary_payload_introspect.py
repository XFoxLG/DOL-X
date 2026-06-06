"""Offline tests for cheatExtended/maplebirch canary payload introspection."""

import json
import zipfile
from dataclasses import asdict

import pytest

from tools.canary_payload_introspect import build_report, inspect_payload, summarize_smoke_evidence


def _write_mod_zip(path, boot_json, files):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("boot.json", json.dumps(boot_json, ensure_ascii=False))
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.mark.config
def test_inspect_payload_records_zip_metadata_and_keyword_files(tmp_path):
    payload = tmp_path / "cheat_extended.mod.zip"
    _write_mod_zip(
        payload,
        {"name": "cheat extended", "version": "1.18(Dev260325)"},
        {
            "game/cheat.js": "maplebirchFrameworks.register('cheatExtended'); window.CE_options = {};",
        },
    )

    result = inspect_payload(payload)

    assert result.exists is True
    assert result.kind == "zip"
    assert result.boot_jsons[0].name == "cheat extended"
    assert result.references_maplebirch_frameworks is True
    assert result.references_ce_options is True
    assert "game/cheat.js" in result.keyword_files["maplebirchFrameworks"]
    assert "game/cheat.js" in result.keyword_files["CE_options"]


@pytest.mark.config
def test_build_report_classifies_loaded_maplebirch_global_incompatibility(tmp_path):
    maplebirch_payload = tmp_path / "maplebirch.mod.zip"
    maplebirch_payload.write_text("maplebirch package mentions maplebirchFrameworks", encoding="utf-8")

    cheat_payload = tmp_path / "cheat_extended.mod.zip"
    _write_mod_zip(
        cheat_payload,
        {"name": "cheat extended", "version": "1.18(Dev260325)"},
        {
            "game/cheat.js": "maplebirchFrameworks.boot(); CE_options.enabled = true;",
        },
    )

    html_report = tmp_path / "html-smoke.json"
    html_report.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "mod_count": 27,
                        "valid_zip_count": 26,
                        "payloads": [{"index": 24, "kind": "non_zip"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    browser_report = tmp_path / "browser-smoke-report.json"
    browser_report.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "severity": "high",
                        "kind": "maplebirch_framework_missing",
                        "message": "maplebirchFrameworks is not defined",
                    }
                ],
                "console_messages": [
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: maplebirch, version: 3.2.5}",
                    },
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: cheat extended, version: 1.18(Dev260325)}",
                    },
                ],
                "observations": {
                    "runtime_globals": {
                        "maplebirchFrameworks": "undefined",
                        "CE_options": "undefined",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_report([maplebirch_payload, cheat_payload], html_report, browser_report)
    evidence = report.smoke_evidence

    assert evidence is not None
    assert evidence.html_mod_count == 27
    assert evidence.html_valid_zip_count == 26
    assert evidence.html_non_zip_indices == [24]
    assert evidence.load_order_ok is True
    assert evidence.maplebirch_framework_missing_issue_count == 1
    assert evidence.ce_options_observed is False
    assert evidence.maplebirch_framework_global_observed is False
    assert report.root_cause_classification == "framework_api_or_global_incompatibility"
    assert "browser logs show maplebirch loads before cheatExtended." in report.notes
    assert "static scan did not find a maplebirchFrameworks global definition in the maplebirch payload." in report.notes

    serialized = asdict(report)
    assert serialized["payloads"][0]["kind"] == "non_zip"
    assert serialized["payloads"][1]["kind"] == "zip"


@pytest.mark.config
def test_summarize_smoke_evidence_reads_runtime_globals_from_page_state(tmp_path):
    browser_report = tmp_path / "browser-smoke-report.json"
    browser_report.write_text(
        json.dumps(
            {
                "issues": [],
                "observations": {
                    "page_state": {
                        "globals": {
                            "maplebirchFrameworks": "object",
                            "CE_options": "object",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    evidence = summarize_smoke_evidence(browser_smoke_report=browser_report)

    assert evidence is not None
    assert evidence.ce_options_observed is True
    assert evidence.maplebirch_framework_global_observed is True


@pytest.mark.config
def test_build_report_traces_simple_framework_alias_and_ce_options_widget_contract(tmp_path):
    maplebirch_payload = tmp_path / "maplebirch.mod.zip"
    _write_mod_zip(
        maplebirch_payload,
        {"name": "maplebirch", "version": "3.1.13", "alias": ["Simple Frameworks"]},
        {
            "boot.js": "window.maplebirchFrameworks = {};",
        },
    )

    cheat_payload = tmp_path / "cheat_extended.mod.zip"
    _write_mod_zip(
        cheat_payload,
        {"name": "cheat extended", "version": "1.18(Dev260325)", "dependenceInfo": [{"modName": "ModLoader"}]},
        {
            "options.twee": '<<widget "CE_options">>content<</widget>>',
            "lookup.js": (
                'const simpleFrameworks = window.modUtils.getMod("Simple Frameworks");\n'
                'maplebirchFrameworks.addto("Options", "CE_options");\n'
            ),
        },
    )

    browser_report = tmp_path / "browser-smoke-report.json"
    browser_report.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "severity": "high",
                        "kind": "tw_user_script_error",
                        "message": (
                            "ModOrderContainer getByNameOne() cannot find name. "
                            "[Simple Frameworks, ModOrderContainer]"
                        ),
                    }
                ],
                "console_messages": [
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: maplebirch, version: 3.1.13}",
                    },
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: cheat extended, version: 1.18(Dev260325)}",
                    },
                ],
                "observations": {
                    "runtime_globals": {
                        "maplebirchFrameworks": "object",
                        "CE_options": "undefined",
                    },
                    "runtime_mod_probes": {
                        "modUtilsAvailable": True,
                        "results": {
                            "maplebirch": {
                                "available": True,
                                "type": "object",
                                "name": "maplebirch",
                                "version": "3.1.13",
                                "error": None,
                            },
                            "Simple Frameworks": {
                                "available": False,
                                "type": "error",
                                "name": None,
                                "version": None,
                                "error": (
                                    "ModOrderContainer getByNameOne() cannot find name. "
                                    "[Simple Frameworks, ModOrderContainer]"
                                ),
                            },
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_report([maplebirch_payload, cheat_payload], browser_smoke_report=browser_report)
    evidence = report.smoke_evidence
    cheat = report.payloads[1]

    assert evidence is not None
    assert evidence.simple_framework_lookup_issue_count == 1
    assert evidence.runtime_globals["maplebirchFrameworks"] == "object"
    assert evidence.runtime_globals["CE_options"] == "undefined"
    assert evidence.runtime_mod_probes["maplebirch"]["available"] is True
    assert evidence.maplebirch_getmod_available is True
    assert evidence.simple_framework_getmod_available is False
    assert "ModOrderContainer" in evidence.simple_framework_getmod_error
    assert report.root_cause_classification == "simple_framework_alias_lookup"
    assert any("getMod('maplebirch')" in note for note in report.notes)
    assert any("getMod('Simple Frameworks')" in note for note in report.notes)
    assert cheat.ce_options_widget_definitions
    assert cheat.ce_options_slot_registrations
    assert not cheat.ce_options_definitions
    assert not cheat.ce_options_reads
    assert cheat.mod_order_lookups
    assert any("alias list" in conclusion for conclusion in report.framework_contract_conclusions)
    assert any("widget/slot" in conclusion for conclusion in report.framework_contract_conclusions)
    assert any("ModOrderContainer getByNameOne()" in conclusion for conclusion in report.framework_contract_conclusions)
    assert any("runtime mod probes" in conclusion for conclusion in report.framework_contract_conclusions)
    assert "Simple Frameworks" in report.recommended_canary_fix
    assert "do not add" in report.recommended_canary_fix
    assert "alias shim" in report.recommended_canary_fix
    assert "load order" in report.recommended_canary_fix
    assert "branch logic" in report.recommended_canary_fix
    assert "window.CE_options" in report.recommended_canary_fix
    assert not any(step.startswith("Apply one canary-only shim") for step in report.single_validation_plan)
    assert any("runtime getMod probes" in step for step in report.single_validation_plan)
    assert report.single_validation_plan[-1].startswith("Stop after that single validation pass")


@pytest.mark.config
def test_build_report_classifies_resolved_simple_framework_alias_as_warning(tmp_path):
    maplebirch_payload = tmp_path / "maplebirch.mod.zip"
    _write_mod_zip(
        maplebirch_payload,
        {"name": "maplebirch", "version": "3.1.13", "alias": ["Simple Frameworks"]},
        {
            "boot.js": "window.maplebirchFrameworks = {};",
        },
    )

    cheat_payload = tmp_path / "cheat_extended.mod.zip"
    _write_mod_zip(
        cheat_payload,
        {"name": "cheat extended", "version": "1.18(Dev260325)", "dependenceInfo": [{"modName": "ModLoader"}]},
        {
            "options.twee": '<<widget "CE_options">>content<</widget>>',
            "lookup.js": (
                'const simpleFrameworks = window.modUtils.getMod("Simple Frameworks");\n'
                'maplebirchFrameworks.addto("Options", "CE_options");\n'
            ),
        },
    )

    browser_report = tmp_path / "browser-smoke-report.json"
    browser_report.write_text(
        json.dumps(
            {
                "success": True,
                "issues": [
                    {
                        "severity": "warning",
                        "kind": "simple_frameworks_optional_lookup",
                        "message": (
                            "ModOrderContainer getByNameOne() cannot find name. "
                            "[Simple Frameworks, ModOrderContainer]"
                        ),
                    }
                ],
                "console_messages": [
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: maplebirch, version: 3.1.13}",
                    },
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: cheat extended, version: 1.18(Dev260325)}",
                    },
                ],
                "observations": {
                    "game_ready": {
                        "ready": True,
                        "passage": "Orphanage Intro",
                    },
                    "enter_game": {
                        "success": True,
                        "passage_after": "Orphanage Intro",
                    },
                    "runtime_globals": {
                        "maplebirchFrameworks": "object",
                        "CE_options": "undefined",
                    },
                    "runtime_mod_probes": {
                        "modUtilsAvailable": True,
                        "results": {
                            "maplebirch": {
                                "available": True,
                                "type": "object",
                                "name": "maplebirch",
                                "version": "3.1.13",
                                "error": None,
                            },
                            "Simple Frameworks": {
                                "available": True,
                                "type": "object",
                                "name": "maplebirch",
                                "version": "3.1.13",
                                "error": None,
                            },
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_report([maplebirch_payload, cheat_payload], browser_smoke_report=browser_report)
    evidence = report.smoke_evidence

    assert evidence is not None
    assert evidence.simple_framework_lookup_issue_count == 1
    assert evidence.browser_success is True
    assert evidence.game_ready is True
    assert evidence.enter_game_success is True
    assert evidence.playable_passage == "Orphanage Intro"
    assert evidence.maplebirch_framework_global_observed is True
    assert evidence.maplebirch_getmod_available is True
    assert evidence.simple_framework_getmod_available is True
    assert evidence.simple_framework_getmod_error is None
    assert evidence.runtime_mod_probes["Simple Frameworks"]["name"] == "maplebirch"
    assert not evidence.high_risk_messages
    assert report.root_cause_classification == "simple_framework_alias_resolved_warning"
    assert any("resolved to maplebirch" in note for note in report.notes)
    assert any("Orphanage Intro" in note for note in report.notes)


@pytest.mark.config
def test_build_report_ignores_identity_high_risk_for_resolved_alias_playability(tmp_path):
    maplebirch_payload = tmp_path / "maplebirch.mod.zip"
    _write_mod_zip(
        maplebirch_payload,
        {"name": "maplebirch", "version": "3.1.13", "alias": ["Simple Frameworks"]},
        {"boot.js": "window.maplebirchFrameworks = {};"},
    )

    cheat_payload = tmp_path / "cheat_extended.mod.zip"
    _write_mod_zip(
        cheat_payload,
        {"name": "cheat extended", "version": "1.18(Dev260325)"},
        {
            "lookup.js": (
                'window.modUtils.getMod("Simple Frameworks");\n'
                'maplebirchFrameworks.addto("Options", "CE_options");\n'
            )
        },
    )

    browser_report = tmp_path / "browser-smoke-report.json"
    browser_report.write_text(
        json.dumps(
            {
                "success": False,
                "issues": [
                    {
                        "severity": "high",
                        "kind": "branch_profile_mismatch",
                        "source": "identity",
                        "message": "branch 'vega' should use stable profile, got canary profile",
                    },
                    {
                        "severity": "warning",
                        "kind": "simple_frameworks_optional_lookup",
                        "message": (
                            "ModOrderContainer getByNameOne() cannot find name. "
                            "[Simple Frameworks, ModOrderContainer]"
                        ),
                    },
                ],
                "console_messages": [
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: maplebirch, version: 3.1.13}",
                    },
                    {
                        "type": "log",
                        "text": "ModZipReader init() modInfo {name: cheat extended, version: 1.18(Dev260325)}",
                    },
                ],
                "observations": {
                    "game_ready": {"ready": True, "passage": "Orphanage Intro"},
                    "enter_game": {"success": True, "passage_after": "Orphanage Intro"},
                    "runtime_globals": {"maplebirchFrameworks": "object", "CE_options": "undefined"},
                    "runtime_mod_probes": {
                        "results": {
                            "maplebirch": {"available": True, "name": "maplebirch", "error": None},
                            "Simple Frameworks": {"available": True, "name": "maplebirch", "error": None},
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_report([maplebirch_payload, cheat_payload], browser_smoke_report=browser_report)
    evidence = report.smoke_evidence

    assert evidence is not None
    assert evidence.high_risk_issue_kinds == ["branch_profile_mismatch"]
    assert evidence.high_risk_messages
    assert report.root_cause_classification == "simple_framework_alias_resolved_warning"
    assert any("non-runtime high-risk" in note for note in report.notes)
