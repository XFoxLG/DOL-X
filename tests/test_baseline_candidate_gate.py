"""Baseline candidate gate helper tests."""

import base64
import io
import json
import zipfile

import pytest

import tools.baseline_candidate_gate as baseline_candidate_gate
from lyra.build import BuildResult
from tools.artifact_inspection import APK_HTML_MEMBER, load_html_artifact
from tools.baseline_candidate_gate import (
    APK_AUDIT_REPORT,
    APK_BUILD_REPORT,
    APK_DEBUG_REPORT,
    APK_EQUIVALENCE_REPORT,
    CANDIDATE_CODES,
    DEFAULT_STABLE_CODE_ORDER,
    FULL_GATE_COMPONENT_LEVEL,
    PHASE1A_CONFIG_REPORT,
    PHASE1A_SUMMARY,
    PARTIAL_GATE_LEVEL,
    WEBVIEW_DEBUG_INVOKE,
    ZIP_AUDIT_REPORT,
    ZIP_BROWSER_SUMMARY,
    ZIP_BUILD_REPORT,
    audit_apk_equivalence_target,
    audit_apk_target,
    check_phase2_promotion,
    derive_debug_apk_target,
    summarize_browser_reports,
    summarize_phase1a_gate,
    validate_candidate_build_result,
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
    assert payload["reports"]["zip_build"]["exists"] is False
    assert "zip_build" in payload["missing_reports"]
    assert f"missing required report: {ZIP_BUILD_REPORT}" in payload["errors"]


@pytest.mark.config
def test_phase1a_summary_requires_b1_component_reports(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
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
    assert payload["reports"]["apk_debug_derivation"]["filename"] == APK_DEBUG_REPORT
    assert payload["reports"]["apk_equivalence"]["filename"] == APK_EQUIVALENCE_REPORT
    assert f"missing required report: {APK_DEBUG_REPORT}" in payload["errors"]
    assert f"missing required report: {APK_EQUIVALENCE_REPORT}" in payload["errors"]


@pytest.mark.config
def test_phase1a_summary_accepts_complete_green_reports(tmp_path):
    gate_dir = tmp_path / "baseline-candidate-gate"
    gate_dir.mkdir(parents=True)
    output = gate_dir / PHASE1A_SUMMARY

    _write_simple_success_report(gate_dir, PHASE1A_CONFIG_REPORT)
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
    assert payload["reports"]["apk_debug_derivation"]["filename"] == APK_DEBUG_REPORT
    assert payload["reports"]["apk_equivalence"]["filename"] == APK_EQUIVALENCE_REPORT
    assert all(report["success"] for report in payload["reports"].values())


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
