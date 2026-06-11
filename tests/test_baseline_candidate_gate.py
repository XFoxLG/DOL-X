"""Baseline candidate gate helper tests."""

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest

import tools.baseline_candidate_gate as baseline_candidate_gate
from lyra.build import BuildResult
from tools.artifact_inspection import APK_HTML_MEMBER, load_html_artifact
from tools.baseline_candidate_gate import (
    APK_AUDIT_REPORT,
    APK_BUILD_REPORT,
    APK_CDP_BLOCKING_SLUGS,
    APK_CDP_DIAGNOSTIC_SLUGS,
    APK_CDP_SMOKE_REPORT,
    APK_DEBUG_REPORT,
    APK_EQUIVALENCE_REPORT,
    CANDIDATE_CODES,
    DEFAULT_STABLE_CODE_ORDER,
    FRAMEWORK_CANDIDATE_PURPOSE,
    FULL_GATE_LEVEL,
    FULL_GATE_COMPONENT_LEVEL,
    MAPLEBIRCH_PROVIDER,
    PHASE1A_CONFIG_REPORT,
    PHASE1A_SUMMARY,
    PARTIAL_GATE_LEVEL,
    REPLACEMENT_CANDIDATE_CODES,
    REPLACEMENT_CANDIDATE_PURPOSE,
    STABLE_REPLACEMENT_READINESS_REPORT,
    WEBVIEW_DEBUG_INVOKE,
    ZIP_AUDIT_REPORT,
    ZIP_BROWSER_SUMMARY,
    ZIP_BUILD_REPORT,
    audit_apk_equivalence_target,
    audit_apk_target,
    build_stable_replacement_readiness,
    check_phase2_promotion,
    derive_debug_apk_target,
    build_manifest,
    parse_args,
    run_apk_cdp_smokes,
    summarize_apk_cdp_smoke_reports,
    summarize_browser_reports,
    summarize_phase1a_gate,
    validate_candidate_build_result,
    validate_replacement_candidate_code,
)


REQUIRED_PAYLOAD_NAMES = (
    "ModLoaderGui",
    "ModI18N",
    "maplebirch",
    "cheatExtended",
    "More Love Interests Mod",
    "Custom-Spellbook",
    "Lyra",
)


def _embedded_candidate_mod_zip() -> str:
    buffer = io.BytesIO()
    boot_json = {
        "name": "Phase 1A baseline candidate bundle",
        "mods": list(REQUIRED_PAYLOAD_NAMES),
    }
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", json.dumps(boot_json, ensure_ascii=False))
        zf.writestr("main.js", "console.log('phase1a candidate');")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _candidate_html() -> str:
    return (
        "<html><script>window.modDataValueZipList = "
        + json.dumps([_embedded_candidate_mod_zip()])
        + ";</script></html>"
    )


def _candidate_artifact_name(slug: str, suffix: str) -> str:
    code = CANDIDATE_CODES[slug]
    slug_prefix = "" if slug == "base" else f"{slug}-"
    return f"DoL-{slug_prefix}ucb-more-love-custom-spellbook-cheat-extended-maplebirch-{code}.{suffix}"


def _write_candidate_apk(root, slug: str):
    apk_path = root / _candidate_artifact_name(slug, "apk")
    with zipfile.ZipFile(apk_path, "w") as zf:
        zf.writestr(APK_HTML_MEMBER, _candidate_html())
        zf.writestr("AndroidManifest.xml", "<manifest><application /></manifest>")
        zf.writestr(
            "smali/org/example/MainActivity.smali",
            "\n".join(
                [
                    ".class public Lorg/example/MainActivity;",
                    ".super Landroid/app/Activity;",
                    ".method protected onCreate(Landroid/os/Bundle;)V",
                    "    .locals 1",
                    "    return-void",
                    ".end method",
                    "",
                ]
            ),
        )
    return apk_path


def _write_binary_manifest_candidate_apk(root, slug: str):
    apk_path = root / _candidate_artifact_name(slug, "apk")
    with zipfile.ZipFile(apk_path, "w") as zf:
        zf.writestr(APK_HTML_MEMBER, _candidate_html())
        zf.writestr("AndroidManifest.xml", b"binary-manifest-placeholder")
        zf.writestr("classes.dex", b"release-dex-placeholder")
    return apk_path


def _read_zip_member(path, member: str) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        return zf.read(member).decode("utf-8", errors="replace")


@pytest.mark.config
def test_candidate_build_validation_rejects_missing_candidate_payload_markers():
    result = BuildResult(
        success=True,
        output_name=(
            "DoL-0.5.8.10-XFox-3.1.3a-"
            "ucb-more-love-custom-spellbook-cheat-extended-maplebirch-0604.zip"
        ),
        applied_mods=["UCB", "More Love Interests Mod", "Custom-Spellbook"],
    )

    errors = validate_candidate_build_result("base", result)

    assert "missing applied candidate mod: maplebirch" in errors
    assert "missing applied candidate mod: cheatExtended" in errors


@pytest.mark.config
def test_candidate_build_validation_accepts_required_candidate_mod_markers():
    result = BuildResult(
        success=True,
        output_name=(
            "DoL-0.5.8.10-XFox-3.1.3a-au-f-"
            "ucb-more-love-custom-spellbook-cheat-extended-maplebirch-0604.zip"
        ),
        applied_mods=["UCB", "maplebirch", "cheatExtended", "More Love Interests Mod", "Custom-Spellbook"],
    )

    assert validate_candidate_build_result("au-f", result) == []


@pytest.mark.config
def test_baseline_candidate_manifest_records_maplebirch_provider_and_replacement_boundary():
    manifest = build_manifest()

    assert manifest["provider"] == MAPLEBIRCH_PROVIDER
    assert manifest["purpose"] == FRAMEWORK_CANDIDATE_PURPOSE
    assert manifest["legacy_cheat_stack_included"] is True
    assert manifest["candidate_codes"] == CANDIDATE_CODES
    assert manifest["replacement_candidate"] == {
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": REPLACEMENT_CANDIDATE_PURPOSE,
        "candidate_codes": REPLACEMENT_CANDIDATE_CODES,
        "legacy_cheat_stack_included": False,
        "default_matrix_mutated": False,
        "legacy_entries_retained_for_rollback": True,
        "notes": [
            "Prepared replacement candidate codes exclude the legacy cheat_csd bit 2.",
            "Phase 1A/B2 still keeps default build_codes and legacy mod entries unchanged.",
        ],
    }
    assert [target["provider"] for target in manifest["targets"]] == [MAPLEBIRCH_PROVIDER] * 4
    assert [target["purpose"] for target in manifest["targets"]] == [FRAMEWORK_CANDIDATE_PURPOSE] * 4
    assert [target["replacement_candidate_code"] for target in manifest["targets"]] == [
        REPLACEMENT_CANDIDATE_CODES[slug] for slug in DEFAULT_STABLE_CODE_ORDER
    ]
    assert all(target["legacy_cheat_stack_included"] is True for target in manifest["targets"])


@pytest.mark.config
def test_replacement_candidate_codes_exclude_legacy_cheat_stack_without_changing_defaults():
    assert REPLACEMENT_CANDIDATE_CODES == {
        "base": 57600,
        "au-f": 58624,
        "au-m": 59648,
        "au-a": 61696,
    }
    assert set(REPLACEMENT_CANDIDATE_CODES) == set(CANDIDATE_CODES)
    for slug, code in REPLACEMENT_CANDIDATE_CODES.items():
        assert validate_replacement_candidate_code(slug, code) == []
        assert code == CANDIDATE_CODES[slug] - 2

    assert "legacy cheat_csd bit 2" in "; ".join(
        validate_replacement_candidate_code("base", CANDIDATE_CODES["base"])
    )


@pytest.mark.config
def test_stable_replacement_readiness_reports_soft_replacement_boundary():
    payload = build_stable_replacement_readiness()

    assert payload["success"] is True
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["default_migration_allowed"] is False
    assert payload["provider"] == MAPLEBIRCH_PROVIDER
    assert payload["purpose"] == REPLACEMENT_CANDIDATE_PURPOSE
    assert payload["legacy_cheat_stack_included"] is False
    assert payload["legacy_entries_retained_for_rollback"] is True
    assert payload["candidate_codes"] == REPLACEMENT_CANDIDATE_CODES
    assert payload["framework_candidate_codes"] == CANDIDATE_CODES
    assert payload["legacy_stable_codes"] == {
        "base": 24834,
        "au-f": 25858,
        "au-m": 26882,
        "au-a": 28930,
    }
    assert payload["checks"] == {
        "default_matrix_unchanged": True,
        "legacy_feature_present": True,
        "replacement_feature_present": True,
        "replacement_codes_valid": True,
        "replacement_codes_exclude_legacy_bits": True,
        "legacy_modloader_entries_retained_disabled": True,
        "legacy_base_mods_absent": True,
        "replacement_mods_present_enabled": True,
        "maplebirch_before_cheat_extended": True,
    }
    assert payload["legacy_base_mod_keys"] == []
    assert {entry["key"] for entry in payload["legacy_modloader_rollback_entries"]} == {
        "bjx_word_unlock",
        "bjx_portable_word",
        "bccm",
    }
    assert all(entry["enabled"] is False for entry in payload["legacy_modloader_rollback_entries"])
    assert all(entry["feature_id"] == "cheat_csd" for entry in payload["legacy_modloader_rollback_entries"])
    assert [entry["key"] for entry in payload["replacement_modloader_entries"]] == [
        "maplebirch",
        "cheat_extended",
    ]
    assert all(entry["enabled"] is True for entry in payload["replacement_modloader_entries"])
    assert all(
        entry["feature_id"] == "cheat_extended_maplebirch" for entry in payload["replacement_modloader_entries"]
    )
    assert payload["errors"] == []


@pytest.mark.config
def test_stable_replacement_readiness_cli_is_exposed():
    args = parse_args(["stable-replacement-readiness"])

    assert args.command == "stable-replacement-readiness"
    assert args.output.name == STABLE_REPLACEMENT_READINESS_REPORT


@pytest.mark.config
def test_run_apk_cdp_cli_is_exposed():
    args = parse_args(
        [
            "run-apk-cdp",
            "apk-debug-artifacts",
            "--reports-dir",
            "apk-cdp-smoke",
            "--profile",
            "custom-profile",
        ]
    )

    assert args.command == "run-apk-cdp"
    assert args.target.name == "apk-debug-artifacts"
    assert args.reports_dir.name == "apk-cdp-smoke"
    assert args.profile == "custom-profile"
    assert args.slugs is None
    assert args.targeted_slugs == ""
    assert args.require_selected_success is False


@pytest.mark.config
def test_run_apk_cdp_cli_accepts_targeted_slug_subset():
    args = parse_args(
        [
            "run-apk-cdp",
            "apk-debug-artifacts",
            "--slugs",
            "au-f",
            "au-a",
            "--require-selected-success",
        ]
    )

    assert args.command == "run-apk-cdp"
    assert args.slugs == ["au-f", "au-a"]
    assert args.require_selected_success is True


@pytest.mark.config
def test_run_apk_cdp_cli_accepts_workflow_targeted_slug_string():
    args = parse_args(
        [
            "run-apk-cdp",
            "apk-debug-artifacts",
            "--targeted-slugs",
            "au-f au-a",
        ]
    )

    assert args.command == "run-apk-cdp"
    assert args.slugs is None
    assert args.targeted_slugs == "au-f au-a"
    assert args.require_selected_success is False


@pytest.mark.config
def test_run_apk_cdp_cli_dispatches_runner(tmp_path, monkeypatch):
    calls = []

    def fake_runner(target, reports_dir, profile, slugs, require_selected_success):
        calls.append((target, reports_dir, profile, slugs, require_selected_success))
        return 7

    monkeypatch.setattr(baseline_candidate_gate, "run_apk_cdp_smokes", fake_runner)
    target = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"

    assert (
        baseline_candidate_gate.main(
            [
                "run-apk-cdp",
                str(target),
                "--reports-dir",
                str(reports_dir),
                "--profile",
                "profile-x",
                "--slugs",
                "au-f",
                "au-a",
                "--require-selected-success",
            ]
        )
        == 7
    )
    assert calls == [(target, reports_dir, "profile-x", ("au-f", "au-a"), True)]


@pytest.mark.config
def test_run_apk_cdp_cli_dispatches_workflow_targeted_slug_string(tmp_path, monkeypatch):
    calls = []

    def fake_runner(target, reports_dir, profile, slugs, require_selected_success):
        calls.append((target, reports_dir, profile, slugs, require_selected_success))
        return 3

    monkeypatch.setattr(baseline_candidate_gate, "run_apk_cdp_smokes", fake_runner)
    target = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"

    assert (
        baseline_candidate_gate.main(
            [
                "run-apk-cdp",
                str(target),
                "--reports-dir",
                str(reports_dir),
                "--targeted-slugs",
                "au-f au-a",
            ]
        )
        == 3
    )
    assert calls == [(target, reports_dir, baseline_candidate_gate.PROFILE, ("au-f", "au-a"), True)]


@pytest.mark.config
def test_run_apk_cdp_smokes_invokes_helper_for_all_candidate_debug_apks(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(apk_dir, slug)
    calls = []

    class Result:
        returncode = 0

    def fake_run(cmd, check):
        calls.append(cmd)
        assert check is False
        return Result()

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", fake_run)

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 0
    assert len(calls) == len(DEFAULT_STABLE_CODE_ORDER)
    assert [cmd[cmd.index("--slug") + 1] for cmd in calls] == list(DEFAULT_STABLE_CODE_ORDER)
    assert [cmd[cmd.index("--output-dir") + 1] for cmd in calls] == [
        str(reports_dir / slug) for slug in DEFAULT_STABLE_CODE_ORDER
    ]
    assert all(cmd[0] == baseline_candidate_gate.sys.executable for cmd in calls)
    assert all(cmd[1] == "tools/apk_emulator_smoke_test.py" for cmd in calls)


@pytest.mark.config
def test_run_apk_cdp_smokes_invokes_helper_for_targeted_slug_subset(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    targeted_slugs = ("au-f", "au-a")
    for slug in targeted_slugs:
        _write_candidate_apk(apk_dir, slug)
    calls = []

    class Result:
        returncode = 0

    def fake_run(cmd, check):
        calls.append(cmd)
        assert check is False
        return Result()

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", fake_run)

    assert run_apk_cdp_smokes(apk_dir, reports_dir, slugs=targeted_slugs) == 0
    assert [cmd[cmd.index("--slug") + 1] for cmd in calls] == list(targeted_slugs)
    assert [cmd[cmd.index("--output-dir") + 1] for cmd in calls] == [
        str(reports_dir / slug) for slug in targeted_slugs
    ]
    assert not (reports_dir / "base" / "apk-emulator-smoke.json").exists()


@pytest.mark.config
def test_run_apk_cdp_smokes_writes_failure_report_for_missing_candidate(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER[:-1]:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        returncode = 0

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", lambda cmd, check: Result())

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 0
    missing_slug = DEFAULT_STABLE_CODE_ORDER[-1]
    payload = json.loads((reports_dir / missing_slug / "apk-emulator-smoke.json").read_text(encoding="utf-8"))

    assert payload["success"] is False
    assert payload["gate_level"] == FULL_GATE_COMPONENT_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["slug"] == missing_slug
    assert any("missing smoke-debug candidate APK" in error for error in payload["errors"])


@pytest.mark.config
def test_run_apk_cdp_smokes_blocks_on_missing_base_candidate(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER[1:]:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        returncode = 0

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", lambda cmd, check: Result())

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 1
    payload = json.loads((reports_dir / "base" / "apk-emulator-smoke.json").read_text(encoding="utf-8"))

    assert payload["success"] is False
    assert payload["slug"] == "base"
    assert any("missing smoke-debug candidate APK" in error for error in payload["errors"])


@pytest.mark.config
def test_run_apk_cdp_smokes_writes_fallback_report_when_helper_fails_without_report(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        returncode = 3

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", lambda cmd, check: Result())

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 1
    payload = json.loads((reports_dir / "base" / "apk-emulator-smoke.json").read_text(encoding="utf-8"))

    assert payload["success"] is False
    assert payload["gate_level"] == FULL_GATE_COMPONENT_LEVEL
    assert any("APK CDP smoke helper exited with 3" in error for error in payload["errors"])


@pytest.mark.config
def test_run_apk_cdp_smokes_preserves_helper_report_when_helper_fails(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        returncode = 4

    def fake_run(cmd, check):
        assert check is False
        slug = cmd[cmd.index("--slug") + 1]
        output_dir = reports_dir / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        marker = {"success": False, "slug": slug, "errors": ["helper-written"]}
        (output_dir / "apk-emulator-smoke.json").write_text(json.dumps(marker), encoding="utf-8")
        return Result()

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", fake_run)

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 1
    payload = json.loads((reports_dir / "base" / "apk-emulator-smoke.json").read_text(encoding="utf-8"))

    assert payload["errors"] == ["helper-written"]


@pytest.mark.config
def test_run_apk_cdp_smokes_does_not_block_on_diagnostic_au_helper_failures(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, check):
        assert check is False
        slug = cmd[cmd.index("--slug") + 1]
        output_dir = reports_dir / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        marker = {"success": slug == "base", "slug": slug, "errors": [] if slug == "base" else ["au runtime"]}
        (output_dir / "apk-emulator-smoke.json").write_text(json.dumps(marker), encoding="utf-8")
        return Result(0 if slug == "base" else 4)

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", fake_run)

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 0


@pytest.mark.config
def test_run_apk_cdp_smokes_can_require_selected_diagnostic_success(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    targeted_slugs = ("au-f", "au-a")
    for slug in targeted_slugs:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, check):
        assert check is False
        slug = cmd[cmd.index("--slug") + 1]
        output_dir = reports_dir / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        marker = {"success": slug == "au-f", "slug": slug, "errors": [] if slug == "au-f" else ["au runtime"]}
        (output_dir / "apk-emulator-smoke.json").write_text(json.dumps(marker), encoding="utf-8")
        return Result(0 if slug == "au-f" else 4)

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", fake_run)

    assert run_apk_cdp_smokes(
        apk_dir,
        reports_dir,
        slugs=targeted_slugs,
        require_selected_success=True,
    ) == 1


@pytest.mark.config
def test_run_apk_cdp_smokes_blocks_on_base_helper_failure(tmp_path, monkeypatch):
    apk_dir = tmp_path / "apk-debug-artifacts"
    reports_dir = tmp_path / "apk-cdp-smoke"
    apk_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(apk_dir, slug)

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, check):
        assert check is False
        slug = cmd[cmd.index("--slug") + 1]
        return Result(5 if slug == "base" else 0)

    monkeypatch.setattr(baseline_candidate_gate.subprocess, "run", fake_run)

    assert run_apk_cdp_smokes(apk_dir, reports_dir) == 1


@pytest.mark.config
def test_baseline_candidate_apk_audit_is_static_and_requires_all_four_candidates(tmp_path):
    apk_paths = [_write_candidate_apk(tmp_path, slug) for slug in DEFAULT_STABLE_CODE_ORDER]
    html_member, html_content = load_html_artifact(apk_paths[0])

    assert html_member == APK_HTML_MEMBER
    assert html_content is not None
    assert "modDataValueZipList" in html_content

    output = tmp_path / "baseline-candidate-apk-audit.json"
    assert audit_apk_target(tmp_path, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["strict_candidate_presence"]["missing_slugs"] == []
    assert set(payload["strict_candidate_presence"]["seen_slugs"]) == set(DEFAULT_STABLE_CODE_ORDER)
    assert len(payload["results"]) == 4
    for result in payload["results"]:
        assert result["success"] is True
        assert result["html_member"] == APK_HTML_MEMBER
        assert result["manifest_debuggable"] is None
        assert result["release_debuggable_ok"] is None
        assert all(result["required_payloads"].values())
        assert not result["errors"]
        assert any("Phase 1A APK audit is static" in warning for warning in result["warnings"])


@pytest.mark.config
def test_baseline_candidate_apk_debug_derivation_reports_full_gate_component_identity(tmp_path):
    release_dir = tmp_path / "apk-artifacts"
    debug_dir = tmp_path / "apk-debug-artifacts"
    release_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(release_dir, slug)

    output = tmp_path / APK_DEBUG_REPORT
    assert derive_debug_apk_target(release_dir, debug_dir, output, workspace=tmp_path) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == FULL_GATE_COMPONENT_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["signing_mode"] == "debug-only"
    assert payload["strict_candidate_presence"]["missing_slugs"] == []
    assert payload["strict_candidate_presence"]["duplicate_slugs"] == []
    assert len(payload["results"]) == 4
    for result in payload["results"]:
        assert result["success"] is True
        assert result["release_debuggable"] is False
        assert result["debug_manifest_debuggable"] is True
        assert result["webview_debug_hook_applied"] is True
        assert result["html_sha256_match"] is True
        assert result["payload_sha256_match"] is True
        assert result["errors"] == []
        debug_apk = result["debug_apk"]
        assert debug_apk is not None
        assert 'android:debuggable="true"' in _read_zip_member(debug_apk, "AndroidManifest.xml")
        assert WEBVIEW_DEBUG_INVOKE in _read_zip_member(debug_apk, "smali/org/example/MainActivity.smali")


@pytest.mark.config
def test_baseline_candidate_apk_debug_derivation_uses_static_overlay_without_java_toolchain(tmp_path, monkeypatch):
    release_dir = tmp_path / "apk-artifacts"
    debug_dir = tmp_path / "apk-debug-artifacts"
    release_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_binary_manifest_candidate_apk(release_dir, slug)
    monkeypatch.setattr(baseline_candidate_gate.shutil, "which", lambda name: None)

    output = tmp_path / APK_DEBUG_REPORT
    assert derive_debug_apk_target(release_dir, debug_dir, output, workspace=tmp_path) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert len(payload["results"]) == 4
    for result in payload["results"]:
        assert result["success"] is True
        assert result["debug_manifest_debuggable"] is True
        assert result["webview_debug_hook_applied"] is True
        assert result["html_sha256_match"] is True
        assert result["payload_sha256_match"] is True
        assert result["commands"][0]["command"][0] == "static-debug-overlay"
        assert "APK Java toolchain unavailable" in result["commands"][0]["reason"]
        debug_apk = result["debug_apk"]
        assert debug_apk is not None
        assert 'android:debuggable="true"' in _read_zip_member(debug_apk, "AndroidManifest.xml")
        assert WEBVIEW_DEBUG_INVOKE in _read_zip_member(debug_apk, "smali/dolx/smokedebug/WebViewDebugHook.smali")


@pytest.mark.config
def test_baseline_candidate_apk_debug_derivation_allows_signer_zipalign(tmp_path, monkeypatch):
    release_apk = _write_binary_manifest_candidate_apk(tmp_path, "base")
    debug_dir = tmp_path / "apk-debug-artifacts"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "apktool.jar").write_text("", encoding="utf-8")
    (workspace / "uber-apk-signer.jar").write_text("", encoding="utf-8")
    signer_commands = []

    def fake_runner(cmd, **kwargs):
        if cmd[:3] == ["java", "-jar", str(workspace / "apktool.jar")] and cmd[3] == "d":
            work_dir = Path(cmd[cmd.index("-o") + 1])
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "AndroidManifest.xml").write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
                "<application /></manifest>",
                encoding="utf-8",
            )
            smali_path = work_dir / "smali" / "org" / "example" / "MainActivity.smali"
            smali_path.parent.mkdir(parents=True, exist_ok=True)
            smali_path.write_text(
                "\n".join(
                    [
                        ".class public Lorg/example/MainActivity;",
                        ".super Landroid/app/Activity;",
                        ".method protected onCreate(Landroid/os/Bundle;)V",
                        "    .locals 1",
                        "    return-void",
                        ".end method",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        elif cmd[:3] == ["java", "-jar", str(workspace / "apktool.jar")] and cmd[3] == "b":
            work_dir = Path(cmd[4])
            patch_apk = Path(cmd[cmd.index("-o") + 1])
            patch_apk.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(patch_apk, "w") as zf:
                zf.writestr("AndroidManifest.xml", (work_dir / "AndroidManifest.xml").read_text(encoding="utf-8"))
                zf.writestr("classes.dex", b"debug-dex")
        elif cmd[:3] == ["java", "-jar", str(workspace / "uber-apk-signer.jar")]:
            signer_commands.append(cmd)
            unsigned_apk = Path(cmd[cmd.index("-a") + 1])
            signed_dir = Path(cmd[cmd.index("-o") + 1])
            signed_dir.mkdir(parents=True, exist_ok=True)
            (signed_dir / "signed.apk").write_bytes(unsigned_apk.read_bytes())
        return baseline_candidate_gate.subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(baseline_candidate_gate.shutil, "which", lambda name: "java" if name == "java" else None)

    record = baseline_candidate_gate.derive_debug_apk(
        release_apk,
        debug_dir,
        workspace=workspace,
        command_runner=fake_runner,
    )

    assert record.success is True
    assert signer_commands
    assert all("--skipZipAlign" not in command for command in signer_commands)


@pytest.mark.config
def test_baseline_candidate_apk_equivalence_accepts_release_derived_debug_apks(tmp_path):
    release_dir = tmp_path / "apk-artifacts"
    debug_dir = tmp_path / "apk-debug-artifacts"
    release_dir.mkdir()
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_candidate_apk(release_dir, slug)

    assert derive_debug_apk_target(release_dir, debug_dir, tmp_path / APK_DEBUG_REPORT, workspace=tmp_path) == 0

    output = tmp_path / APK_EQUIVALENCE_REPORT
    assert audit_apk_equivalence_target(release_dir, debug_dir, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == FULL_GATE_COMPONENT_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["release_candidate_presence"]["success"] is True
    assert payload["debug_candidate_presence"]["success"] is True
    assert len(payload["results"]) == 4
    for result in payload["results"]:
        assert result["success"] is True
        assert result["release_debuggable"] is False
        assert result["debug_manifest_debuggable"] is True
        assert result["webview_debug_hook_applied"] is True
        assert result["html_sha256_match"] is True
        assert result["payload_sha256_match"] is True
        assert result["payload_names_match"] is True
        assert result["required_payloads_match"] is True
        assert all(result["release_identity"]["required_payloads"].values())
        assert all(result["debug_identity"]["required_payloads"].values())
        assert result["errors"] == []


def _write_browser_smoke_evidence(reports_dir, slug: str) -> None:
    slug_dir = reports_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "success": True,
        "issue_counts": {"high": 0},
        "browser_diagnostics": {"pageerror_count": 0},
        "game_ready": {"ready": True, "passage": "Orphanage Intro"},
        "enter_game": {"success": True},
        "startup_interactions": {"success": True},
        "package_identity": {"profile_slug_match": True},
    }
    report = {"issues": []}
    (slug_dir / "browser-smoke-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False),
        encoding="utf-8",
    )
    (slug_dir / "browser-smoke-report.json").write_text(
        json.dumps(report, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_apk_cdp_smoke_evidence(reports_dir, slug: str, *, success: bool = True) -> None:
    slug_dir = reports_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "success": success,
        "gate_level": FULL_GATE_COMPONENT_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "runtime_scope": {
            "platform": "Android emulator",
            "webview_cdp": True,
            "manual_phone_testing": False,
            "harmonyos_covered": False,
        },
        "target": f"artifact-{slug}-smoke-debug.apk",
        "slug": slug,
        "package": "com.example.dolx",
        "profile": "ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        "cdp_url": "http://127.0.0.1:9222",
        "cdp_socket": "webview_devtools_remote_123",
        "cdp_targets": [{"id": f"target-{slug}", "type": "page"}],
        "browser_summary": {
            "success": success,
            "issue_counts": {"high": 0 if success else 1},
            "browser_diagnostics": {"pageerror_count": 0},
            "game_ready": {"ready": True, "passage": "Orphanage Intro"},
            "enter_game": {"success": True},
            "startup_interactions": {"success": True},
            "package_identity": {"profile_slug_match": True},
        },
        "browser_summary_path": str(slug_dir / "browser-smoke-summary.json"),
        "browser_report_path": str(slug_dir / "browser-smoke-report.json"),
        "markdown_report_path": str(slug_dir / "browser-smoke-report.md"),
        "logcat_path": str(slug_dir / "logcat.txt"),
        "screenshot_path": str(slug_dir / "browser-smoke-final.png"),
        "errors": [] if success else ["runtime failure"],
    }
    (slug_dir / "apk-emulator-smoke.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.mark.config
def test_baseline_candidate_browser_summary_requires_four_strict_zip_smokes(tmp_path):
    reports_dir = tmp_path / "browser-smoke"
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_browser_smoke_evidence(reports_dir, slug)

    output = tmp_path / "baseline-candidate-zip-browser-summary.json"
    assert summarize_browser_reports(reports_dir, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert [result["slug"] for result in payload["results"]] == list(DEFAULT_STABLE_CODE_ORDER)
    assert all(result["success"] for result in payload["results"])
    assert all(result["checks"]["passage_orphanage_intro"] for result in payload["results"])


@pytest.mark.config
def test_baseline_candidate_apk_cdp_summary_requires_four_android_webview_smokes(tmp_path):
    reports_dir = tmp_path / "apk-cdp-smoke"
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_apk_cdp_smoke_evidence(reports_dir, slug)

    output = tmp_path / APK_CDP_SMOKE_REPORT
    assert summarize_apk_cdp_smoke_reports(reports_dir, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == FULL_GATE_COMPONENT_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["runtime_scope"] == {
        "platform": "Android emulator",
        "webview_cdp": True,
        "manual_phone_testing": False,
        "harmonyos_covered": False,
    }
    assert [result["slug"] for result in payload["results"]] == list(DEFAULT_STABLE_CODE_ORDER)
    assert all(result["success"] for result in payload["results"])
    assert payload["blocking_success"] is True
    assert payload["diagnostic_success"] is True
    assert payload["full_candidate_gate_ready"] is True
    assert payload["gate_policy"]["blocking_slugs"] == list(APK_CDP_BLOCKING_SLUGS)
    assert payload["gate_policy"]["diagnostic_slugs"] == list(APK_CDP_DIAGNOSTIC_SLUGS)
    assert payload["signal_layers"]["base_apk_readiness"]["blocking"] is True
    assert payload["signal_layers"]["au_apk_runtime_readiness"]["blocking"] is False
    assert all(result["checks"]["cdp_target_present"] for result in payload["results"])
    assert all(result["checks"]["no_manual_phone_scope"] for result in payload["results"])
    assert all(result["checks"]["no_harmonyos_scope"] for result in payload["results"])


@pytest.mark.config
def test_baseline_candidate_apk_cdp_summary_keeps_au_failures_diagnostic(tmp_path):
    reports_dir = tmp_path / "apk-cdp-smoke"
    _write_apk_cdp_smoke_evidence(reports_dir, "base", success=True)
    for slug in APK_CDP_DIAGNOSTIC_SLUGS:
        _write_apk_cdp_smoke_evidence(reports_dir, slug, success=False)

    output = tmp_path / APK_CDP_SMOKE_REPORT
    assert summarize_apk_cdp_smoke_reports(reports_dir, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["blocking_success"] is True
    assert payload["diagnostic_success"] is False
    assert payload["full_candidate_gate_ready"] is False
    assert payload["blocking_errors"] == []
    assert payload["diagnostic_errors"]
    by_slug = {result["slug"]: result for result in payload["results"]}
    assert by_slug["base"]["blocking"] is True
    assert by_slug["base"]["success"] is True
    assert by_slug["au-f"]["diagnostic"] is True
    assert "au_runtime_startup" in by_slug["au-f"]["failure_layers"]


@pytest.mark.config
def test_baseline_candidate_apk_cdp_summary_still_blocks_base_failure(tmp_path):
    reports_dir = tmp_path / "apk-cdp-smoke"
    _write_apk_cdp_smoke_evidence(reports_dir, "base", success=False)
    for slug in APK_CDP_DIAGNOSTIC_SLUGS:
        _write_apk_cdp_smoke_evidence(reports_dir, slug, success=True)

    output = tmp_path / APK_CDP_SMOKE_REPORT
    assert summarize_apk_cdp_smoke_reports(reports_dir, output) == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["blocking_success"] is False
    assert payload["diagnostic_success"] is True
    assert payload["full_candidate_gate_ready"] is False
    assert payload["blocking_errors"]


def _write_candidate_build_report(gate_dir, filename: str, pack_type: str) -> None:
    (gate_dir / filename).write_text(
        json.dumps(
            {
                "pack_type": pack_type,
                "results": [
                    {
                        "slug": slug,
                        "code": CANDIDATE_CODES[slug],
                        "success": True,
                        "output_path": f"artifact-{slug}.{pack_type}",
                        "validation_errors": [],
                    }
                    for slug in DEFAULT_STABLE_CODE_ORDER
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_simple_success_report(gate_dir, filename: str) -> None:
    (gate_dir / filename).write_text(
        json.dumps(
            {
                "success": True,
                "gate_level": PARTIAL_GATE_LEVEL,
                "counts_for_phase2_promotion": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_b1_component_success_report(gate_dir, filename: str) -> None:
    (gate_dir / filename).write_text(
        json.dumps(
            {
                "success": True,
                "gate_level": FULL_GATE_COMPONENT_LEVEL,
                "counts_for_phase2_promotion": False,
                "default_matrix_mutated": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.config
def test_phase1a_summary_records_missing_required_reports(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    output = gate_dir / PHASE1A_SUMMARY

    assert summarize_phase1a_gate(gate_dir, output, head_sha="abc123", run_id="42") == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["head_sha"] == "abc123"
    assert payload["run_id"] == "42"
    assert payload["reports"]["stable_replacement_readiness"]["exists"] is False
    assert "stable_replacement_readiness" in payload["missing_reports"]
    assert payload["reports"]["zip_build"]["exists"] is False
    assert "zip_build" in payload["missing_reports"]
    assert f"missing required report: {STABLE_REPLACEMENT_READINESS_REPORT}" in payload["errors"]
    assert f"missing required report: {ZIP_BUILD_REPORT}" in payload["errors"]


@pytest.mark.config
def test_phase1a_summary_requires_b1_component_reports(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
    _write_simple_success_report(gate_dir, STABLE_REPLACEMENT_READINESS_REPORT)
    _write_candidate_build_report(gate_dir, ZIP_BUILD_REPORT, "zip")
    _write_candidate_build_report(gate_dir, APK_BUILD_REPORT, "apk")
    _write_simple_success_report(gate_dir, ZIP_AUDIT_REPORT)
    _write_simple_success_report(gate_dir, APK_AUDIT_REPORT)
    _write_simple_success_report(gate_dir, ZIP_BROWSER_SUMMARY)

    assert summarize_phase1a_gate(gate_dir, output, head_sha="abc123", run_id="42") == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["missing_reports"] == ["apk_debug_derivation", "apk_equivalence"]
    assert payload["failed_reports"] == []
    assert payload["reports"]["stable_replacement_readiness"]["filename"] == STABLE_REPLACEMENT_READINESS_REPORT
    assert payload["reports"]["apk_debug_derivation"]["filename"] == APK_DEBUG_REPORT
    assert payload["reports"]["apk_equivalence"]["filename"] == APK_EQUIVALENCE_REPORT
    assert f"missing required report: {APK_DEBUG_REPORT}" in payload["errors"]
    assert f"missing required report: {APK_EQUIVALENCE_REPORT}" in payload["errors"]


@pytest.mark.config
def test_candidate_summary_accepts_b1_green_as_partial_when_b2_missing(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
    _write_simple_success_report(gate_dir, STABLE_REPLACEMENT_READINESS_REPORT)
    _write_candidate_build_report(gate_dir, ZIP_BUILD_REPORT, "zip")
    _write_candidate_build_report(gate_dir, APK_BUILD_REPORT, "apk")
    _write_simple_success_report(gate_dir, ZIP_AUDIT_REPORT)
    _write_simple_success_report(gate_dir, APK_AUDIT_REPORT)
    _write_b1_component_success_report(gate_dir, APK_DEBUG_REPORT)
    _write_b1_component_success_report(gate_dir, APK_EQUIVALENCE_REPORT)
    _write_simple_success_report(gate_dir, ZIP_BROWSER_SUMMARY)

    assert summarize_phase1a_gate(gate_dir, output, head_sha="abc123", run_id="42") == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["default_matrix_mutated"] is False
    assert payload["missing_reports"] == []
    assert payload["failed_reports"] == []
    assert payload["reports"]["stable_replacement_readiness"]["present"] is True
    assert payload["reports"]["stable_replacement_readiness"]["success"] is True
    assert payload["reports"]["apk_debug_derivation"]["filename"] == APK_DEBUG_REPORT
    assert payload["reports"]["apk_equivalence"]["filename"] == APK_EQUIVALENCE_REPORT
    assert payload["reports"]["apk_cdp_smoke"]["filename"] == APK_CDP_SMOKE_REPORT
    assert payload["reports"]["apk_cdp_smoke"]["present"] is False
    assert payload["reports"]["apk_cdp_smoke"]["success"] is False
    assert payload["b2_runtime"] == {
        "required_for_candidate_gate": True,
        "required_for_full_candidate_gate": True,
        "present": False,
        "success": False,
        "full_candidate_gate_ready": False,
        "report": "apk_cdp_smoke",
        "blocking_slugs": list(APK_CDP_BLOCKING_SLUGS),
        "diagnostic_slugs": list(APK_CDP_DIAGNOSTIC_SLUGS),
        "diagnostic_success": False,
        "au_failures_block_candidate": False,
        "au_failures_block_full_promotion": True,
        "scope": {
            "platform": "Android emulator",
            "webview_cdp": True,
            "manual_phone_testing": False,
            "harmonyos_covered": False,
        },
    }
    assert all(report["success"] for name, report in payload["reports"].items() if name != "apk_cdp_smoke")


@pytest.mark.config
def test_candidate_summary_promotes_to_full_gate_only_with_b2_runtime(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
    _write_simple_success_report(gate_dir, STABLE_REPLACEMENT_READINESS_REPORT)
    _write_candidate_build_report(gate_dir, ZIP_BUILD_REPORT, "zip")
    _write_candidate_build_report(gate_dir, APK_BUILD_REPORT, "apk")
    _write_simple_success_report(gate_dir, ZIP_AUDIT_REPORT)
    _write_simple_success_report(gate_dir, APK_AUDIT_REPORT)
    _write_b1_component_success_report(gate_dir, APK_DEBUG_REPORT)
    _write_b1_component_success_report(gate_dir, APK_EQUIVALENCE_REPORT)
    _write_simple_success_report(gate_dir, ZIP_BROWSER_SUMMARY)
    apk_cdp_reports = gate_dir / "apk-cdp-smoke"
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_apk_cdp_smoke_evidence(apk_cdp_reports, slug)
    assert summarize_apk_cdp_smoke_reports(apk_cdp_reports, gate_dir / APK_CDP_SMOKE_REPORT) == 0

    assert summarize_phase1a_gate(gate_dir, output, head_sha="abc123", run_id="42") == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == FULL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is True
    assert payload["default_matrix_mutated"] is False
    assert payload["missing_reports"] == []
    assert payload["failed_reports"] == []
    assert payload["reports"]["stable_replacement_readiness"]["present"] is True
    assert payload["reports"]["stable_replacement_readiness"]["success"] is True
    assert payload["reports"]["apk_cdp_smoke"]["present"] is True
    assert payload["reports"]["apk_cdp_smoke"]["success"] is True
    assert payload["b2_runtime"]["present"] is True
    assert payload["b2_runtime"]["success"] is True
    assert payload["b2_runtime"]["full_candidate_gate_ready"] is True


@pytest.mark.config
def test_candidate_summary_allows_au_diagnostic_failures_without_full_promotion(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
    _write_simple_success_report(gate_dir, STABLE_REPLACEMENT_READINESS_REPORT)
    _write_candidate_build_report(gate_dir, ZIP_BUILD_REPORT, "zip")
    _write_candidate_build_report(gate_dir, APK_BUILD_REPORT, "apk")
    _write_simple_success_report(gate_dir, ZIP_AUDIT_REPORT)
    _write_simple_success_report(gate_dir, APK_AUDIT_REPORT)
    _write_b1_component_success_report(gate_dir, APK_DEBUG_REPORT)
    _write_b1_component_success_report(gate_dir, APK_EQUIVALENCE_REPORT)
    _write_simple_success_report(gate_dir, ZIP_BROWSER_SUMMARY)
    apk_cdp_reports = gate_dir / "apk-cdp-smoke"
    _write_apk_cdp_smoke_evidence(apk_cdp_reports, "base", success=True)
    for slug in APK_CDP_DIAGNOSTIC_SLUGS:
        _write_apk_cdp_smoke_evidence(apk_cdp_reports, slug, success=False)
    assert summarize_apk_cdp_smoke_reports(apk_cdp_reports, gate_dir / APK_CDP_SMOKE_REPORT) == 0

    assert summarize_phase1a_gate(gate_dir, output, head_sha="abc123", run_id="42") == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["missing_reports"] == []
    assert payload["failed_reports"] == []
    assert payload["errors"] == []
    assert payload["reports"]["apk_cdp_smoke"]["present"] is True
    assert payload["reports"]["apk_cdp_smoke"]["success"] is True
    assert payload["reports"]["apk_cdp_smoke"]["diagnostic_success"] is False
    assert payload["reports"]["apk_cdp_smoke"]["full_candidate_gate_ready"] is False
    assert payload["reports"]["apk_cdp_smoke"]["diagnostic_errors"]
    assert payload["b2_runtime"]["present"] is True
    assert payload["b2_runtime"]["success"] is True
    assert payload["b2_runtime"]["diagnostic_success"] is False
    assert payload["b2_runtime"]["full_candidate_gate_ready"] is False
    assert payload["b2_runtime"]["au_failures_block_candidate"] is False
    assert payload["b2_runtime"]["au_failures_block_full_promotion"] is True


@pytest.mark.config
def test_candidate_summary_rejects_failing_b2_runtime_without_phase2_promotion(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
    _write_simple_success_report(gate_dir, STABLE_REPLACEMENT_READINESS_REPORT)
    _write_candidate_build_report(gate_dir, ZIP_BUILD_REPORT, "zip")
    _write_candidate_build_report(gate_dir, APK_BUILD_REPORT, "apk")
    _write_simple_success_report(gate_dir, ZIP_AUDIT_REPORT)
    _write_simple_success_report(gate_dir, APK_AUDIT_REPORT)
    _write_b1_component_success_report(gate_dir, APK_DEBUG_REPORT)
    _write_b1_component_success_report(gate_dir, APK_EQUIVALENCE_REPORT)
    _write_simple_success_report(gate_dir, ZIP_BROWSER_SUMMARY)
    (gate_dir / APK_CDP_SMOKE_REPORT).write_text(
        json.dumps(
            {
                "success": False,
                "gate_level": FULL_GATE_COMPONENT_LEVEL,
                "counts_for_phase2_promotion": False,
                "default_matrix_mutated": False,
                "errors": ["base: runtime failure"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert summarize_phase1a_gate(gate_dir, output, head_sha="abc123", run_id="42") == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["missing_reports"] == []
    assert payload["failed_reports"] == ["apk_cdp_smoke"]
    assert payload["reports"]["stable_replacement_readiness"]["present"] is True
    assert payload["reports"]["stable_replacement_readiness"]["success"] is True
    assert payload["reports"]["apk_cdp_smoke"]["present"] is True
    assert payload["reports"]["apk_cdp_smoke"]["success"] is False
    assert payload["b2_runtime"]["present"] is True
    assert payload["b2_runtime"]["success"] is False
    assert "base: runtime failure" in payload["errors"]


@pytest.mark.config
def test_phase2_promotion_rejects_phase1a_partial_candidate_evidence(tmp_path):
    evidence_paths = []
    for index in range(2):
        evidence_path = tmp_path / f"partial-green-{index}.json"
        evidence_path.write_text(
            json.dumps(
                {
                    "success": True,
                    "gate_level": PARTIAL_GATE_LEVEL,
                    "counts_for_phase2_promotion": False,
                    "head_sha": "abc123",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        evidence_paths.append(evidence_path)

    output = tmp_path / "phase2-promotion-check.json"
    assert check_phase2_promotion(evidence_paths, "abc123", output) == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["default_migration_allowed"] is False
    assert payload["eligible_green_runs"] == []
    assert len(payload["rejected_runs"]) == 2
    assert all(not item["checks"]["gate_level_full"] for item in payload["rejected_runs"])
    assert all(not item["checks"]["counts_for_phase2"] for item in payload["rejected_runs"])
