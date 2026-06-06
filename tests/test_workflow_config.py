"""GitHub Actions workflow configuration tests."""

import tomllib
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.config
def test_build_zip_sample_prefers_non_au_package_with_fallback():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yaml").read_text(encoding="utf-8")

    assert (
        'ZIP_FILE=$(find "${{ github.workspace }}/output" -maxdepth 1 -type f -name "*.zip" '
        '! -name "*-au-*" ! -name "*cheat-extended-maplebirch*" | sort | head -n 1)'
        in workflow
    )
    assert 'if [[ -z "$ZIP_FILE" ]]; then' in workflow
    assert (
        'ZIP_FILE=$(find "${{ github.workspace }}/output" -maxdepth 1 -type f -name "*.zip" '
        '! -name "*cheat-extended-maplebirch*" | sort | head -n 1)'
        in workflow
    )
    assert 'echo "zip=$ZIP_FILE" >> "$GITHUB_OUTPUT"' in workflow


@pytest.mark.config
def test_canary_browser_smoke_runs_only_in_compatibility_workflow():
    build_workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yaml").read_text(encoding="utf-8")
    compatibility_workflow = (PROJECT_ROOT / ".github" / "workflows" / "compatibility.yaml").read_text(
        encoding="utf-8"
    )
    build_config = (PROJECT_ROOT / "config" / "build.toml").read_text(encoding="utf-8")

    assert "Build cheatExtended/maplebirch canary ZIP" in build_workflow
    assert "--maplebirch-release-tag maplebirch-release-v3.1.13" in build_workflow
    assert "--maplebirch-asset-pattern maplebirch-0.5.8.10-v3.1.13.mod.zip" in build_workflow
    assert "--maplebirch-cache-label maplebirch-release-v3.1.13" in build_workflow
    assert 'asset_pattern = "maplebirch-0.5.8.10-v3.1.13.mod.zip"' in build_config
    assert 'release_tag = "maplebirch-release-v3.1.13"' in build_config
    assert "maplebirch-0.5.8.10-v3.2.5.modpack" not in build_config
    assert "Run cheatExtended/maplebirch canary HTML smoke" in build_workflow
    assert "name: dol-builds-cheat-canary-zip" in build_workflow
    assert "name: cheat-canary-build-reports" in build_workflow
    assert "Run cheatExtended/maplebirch canary browser smoke" not in build_workflow
    assert "Install cheatExtended/maplebirch canary browser smoke dependencies" not in build_workflow
    assert "--output-dir \"${{ github.workspace }}/output/cheat-canary-browser-smoke\"" not in build_workflow
    assert "path: ${{ github.workspace }}/output/cheat-canary-browser-smoke/" not in build_workflow

    assert "build_run_id:" in compatibility_workflow
    assert "run_canary_browser_smoke:" in compatibility_workflow
    assert "build_run_id is required when run_canary_browser_smoke is true" in compatibility_workflow
    assert "github.event.workflow_run.id || github.event.inputs.build_run_id" in compatibility_workflow

    assert "name: dol-builds-zip-sample" in compatibility_workflow
    assert 'PROFILE="ucb-more-love-custom-spellbook"' in compatibility_workflow
    assert '--profile "${PROFILE}"' in compatibility_workflow
    assert "name: browser-smoke-report" in compatibility_workflow

    assert "cheat-canary-browser-smoke:" in compatibility_workflow
    assert "github.event.inputs.run_canary_browser_smoke == 'true'" in compatibility_workflow
    assert "Download cheatExtended/maplebirch canary ZIP artifact from Build workflow" in compatibility_workflow
    assert "name: dol-builds-cheat-canary-zip" in compatibility_workflow
    assert "DOLX_ARTIFACT_NAME: dol-builds-cheat-canary-zip" in compatibility_workflow
    assert "--output-dir output/cheat-canary-browser-smoke" in compatibility_workflow
    assert "--profile ucb-cheat-extended-maplebirch" in compatibility_workflow
    assert "name: cheat-canary-browser-smoke-report" in compatibility_workflow


@pytest.mark.config
def test_baseline_candidate_gate_workflow_is_manual_candidate_only_with_b2_runtime():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "baseline-candidate-gate.yml").read_text(
        encoding="utf-8"
    )
    build_workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yaml").read_text(encoding="utf-8")
    compatibility_workflow = (PROJECT_ROOT / ".github" / "workflows" / "compatibility.yaml").read_text(
        encoding="utf-8"
    )

    assert "name: Baseline Candidate Gate" in workflow
    assert "workflow_dispatch:" in workflow
    assert "phase1a-candidate-gate:" in workflow
    assert 'CANDIDATE_CODES: "57602,58626,59650,61698"' in workflow
    assert "Check stable replacement readiness" in workflow
    assert "stable-replacement-readiness" in workflow
    assert "baseline-candidate-stable-replacement-readiness.json" in workflow
    assert "Build candidate ZIP artifacts" in workflow
    assert "Build candidate APK artifacts" in workflow
    assert workflow.count("python tools/baseline_candidate_gate.py build") == 2
    assert workflow.count("--ensure-payloads") == 2
    assert '--codes "$CANDIDATE_CODES"' not in workflow
    assert '--output-dir "${{ github.workspace }}/${GATE_DIR}/zip-artifacts"' in workflow
    assert '--output-dir "${{ github.workspace }}/${GATE_DIR}/apk-artifacts"' in workflow
    assert "baseline-candidate-zip-build.json" in workflow
    assert "baseline-candidate-apk-build.json" in workflow
    assert "Audit candidate ZIP artifacts" in workflow
    assert "Audit candidate APK artifacts" in workflow
    assert '"${{ github.workspace }}/${GATE_DIR}/zip-artifacts"' in workflow
    assert '"${{ github.workspace }}/${GATE_DIR}/apk-artifacts"' in workflow
    assert "Derive smoke-debug APK artifacts" in workflow
    assert workflow.count("python tools/baseline_candidate_gate.py derive-debug-apk") == 1
    assert '"${{ github.workspace }}/${GATE_DIR}/apk-debug-artifacts"' in workflow
    assert "baseline-candidate-apk-debug-derivation.json" in workflow
    assert "Audit release/debug APK equivalence" in workflow
    assert workflow.count("python tools/baseline_candidate_gate.py audit-apk-equivalence") == 1
    assert '--release-target "${{ github.workspace }}/${GATE_DIR}/apk-artifacts"' in workflow
    assert '--debug-target "${{ github.workspace }}/${GATE_DIR}/apk-debug-artifacts"' in workflow
    assert "baseline-candidate-apk-equivalence.json" in workflow
    assert "python -m pip install playwright" in workflow
    assert "Run candidate ZIP browser smokes" in workflow
    assert "Summarize candidate browser smokes" in workflow
    assert "Enable KVM for Android emulator" in workflow
    assert "Run candidate APK CDP smokes" in workflow
    assert "reactivecircus/android-emulator-runner@v2" in workflow
    assert "api-level: 35" in workflow
    assert "arch: x86_64" in workflow
    assert "profile: pixel_6" in workflow
    assert "DOLX_ARTIFACT_NAME: baseline-candidate-apk-debug-artifacts" in workflow
    assert "for slug in base au-f au-m au-a" in workflow
    assert workflow.count("python tools/apk_emulator_smoke_test.py") == 1
    assert '--slug "$slug"' in workflow
    assert '--output-dir "${GATE_DIR}/apk-cdp-smoke/${slug}"' in workflow
    assert "Summarize candidate APK CDP smokes" in workflow
    assert "summarize-apk-cdp" in workflow
    assert "baseline-candidate-apk-cdp-smoke.json" in workflow
    assert "Summarize candidate gate" in workflow
    assert "summarize-phase1a" in workflow
    assert "baseline-candidate-phase1a-summary.json" in workflow
    assert "DOLX_ARTIFACT_NAME: baseline-candidate-zip-artifacts" in workflow
    assert "name: baseline-candidate-zip-artifacts" in workflow
    assert "path: ${{ github.workspace }}/output/baseline-candidate-gate/zip-artifacts/*.zip" in workflow
    assert "name: baseline-candidate-apk-artifacts" in workflow
    assert "path: ${{ github.workspace }}/output/baseline-candidate-gate/apk-artifacts/*.apk" in workflow
    assert "name: baseline-candidate-apk-debug-artifacts" in workflow
    assert "path: ${{ github.workspace }}/output/baseline-candidate-gate/apk-debug-artifacts/*.apk" in workflow
    assert "name: baseline-candidate-apk-cdp-smoke-reports" in workflow
    assert "path: ${{ github.workspace }}/output/baseline-candidate-gate/apk-cdp-smoke/**" in workflow
    assert "name: baseline-candidate-gate-reports" in workflow
    assert "path: ${{ github.workspace }}/output/baseline-candidate-gate/\n" not in workflow
    assert "${{ github.workspace }}/output/baseline-candidate-gate/*.json" in workflow
    assert "${{ github.workspace }}/output/baseline-candidate-gate/browser-smoke/**" in workflow
    assert "${{ github.workspace }}/output/baseline-candidate-gate/apk-cdp-smoke/**" in workflow
    assert "!${{ github.workspace }}/output/baseline-candidate-gate/zip-artifacts/**" in workflow
    assert "!${{ github.workspace }}/output/baseline-candidate-gate/apk-artifacts/**" in workflow
    assert "!${{ github.workspace }}/output/baseline-candidate-gate/apk-debug-artifacts/**" in workflow

    assert "Run candidate APK browser smokes" not in workflow
    assert workflow.index("Check stable replacement readiness") > workflow.index("Validate Phase 1A static config")
    assert workflow.index("Check stable replacement readiness") < workflow.index("Prepare game packages")
    assert workflow.index("Run candidate APK CDP smokes") > workflow.index("Audit release/debug APK equivalence")

    assert "Baseline Candidate Gate" not in build_workflow
    assert "baseline-candidate-gate" not in build_workflow
    assert "baseline-candidate-gate" not in compatibility_workflow
    assert "apk-cdp" not in build_workflow.lower()
    assert "apk-cdp" not in compatibility_workflow.lower()
    assert "apk_emulator_smoke_test.py" not in build_workflow
    assert "apk_emulator_smoke_test.py" not in compatibility_workflow
    assert "reactivecircus/android-emulator-runner" not in build_workflow
    assert "reactivecircus/android-emulator-runner" not in compatibility_workflow


@pytest.mark.config
def test_maplebirch_version_gate_is_manual_base_zip_canary_only():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "maplebirch-version-gate.yml").read_text(
        encoding="utf-8"
    )
    build_workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yaml").read_text(encoding="utf-8")
    build_config = (PROJECT_ROOT / "config" / "build.toml").read_text(encoding="utf-8")
    combinations_config = tomllib.loads(
        (PROJECT_ROOT / "config" / "combinations.toml").read_text(encoding="utf-8")
    )

    assert "name: Maplebirch Version Gate" in workflow
    assert "workflow_dispatch:" in workflow
    assert "max_smoke_candidates:" in workflow
    assert "candidate_tags:" in workflow
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in workflow
    assert "tools/maplebirch_version_matrix.py" in workflow
    assert "--scan" in workflow
    assert "--max-smoke-candidates" in workflow
    assert "maplebirch-version-matrix.json" in workflow
    assert "maplebirch-version-matrix.md" in workflow
    assert "selected_for_smoke" in workflow
    assert "tools/cheat_extended_canary.py" in workflow
    assert '"--flavor",' in workflow
    assert '"stable-replacement",' in workflow
    assert '"--variant",' in workflow
    assert '"base",' in workflow
    assert '"--maplebirch-release-tag",' in workflow
    assert '"--maplebirch-asset-pattern",' in workflow
    assert '"--maplebirch-cache-label",' in workflow
    assert "canary-build.json" in workflow
    assert "tools/html_smoke_test.py" in workflow
    assert "html-smoke.json" in workflow
    assert "tools/browser_smoke_test.py" in workflow
    assert '"--profile",' in workflow
    assert "PROFILE: ucb-cheat-extended-maplebirch" in workflow
    assert "--report-only" in workflow
    assert "--allow-branch-profile-mismatch" in workflow
    assert 'candidate_dir / canary_zip.name' in workflow
    assert 'candidate_dir / "canary.zip"' not in workflow
    assert "browser-smoke-report.json" in workflow
    assert "tools/canary_payload_introspect.py" in workflow
    assert "canary-introspection.json" in workflow
    assert "maplebirch-version-gate-summary.json" in workflow
    assert "maplebirch-version-gate-summary.md" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "maplebirch-version-gate-matrix" in workflow
    assert "maplebirch-version-gate-reports" in workflow
    assert "maplebirch-version-gate-zips" in workflow
    assert "candidates/**/*.zip" in workflow
    assert "Review artifacts before pinning; this gate does not mutate stable/default build config." in workflow

    assert "apk_emulator_smoke_test.py" not in workflow
    assert "reactivecircus/android-emulator-runner" not in workflow
    assert "Build candidate APK artifacts" not in workflow
    assert "for slug in base au-f au-m au-a" not in workflow

    assert "Maplebirch Version Gate" not in build_workflow
    assert "maplebirch-version-gate" not in build_workflow
    assert "--maplebirch-release-tag maplebirch-release-v3.1.13" in build_workflow
    assert "--maplebirch-asset-pattern maplebirch-0.5.8.10-v3.1.13.mod.zip" in build_workflow
    assert "--maplebirch-cache-label maplebirch-release-v3.1.13" in build_workflow
    assert combinations_config["build_codes"] == ["24834", "25858", "26882", "28930"]
    assert combinations_config["base_code"] == 24834
    assert combinations_config["recommended"] == [25858, 26882, 28930]
    assert 'asset_pattern = "maplebirch-0.5.8.10-v3.1.13.mod.zip"' in build_config
    assert 'release_tag = "maplebirch-release-v3.1.13"' in build_config
