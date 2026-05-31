"""GitHub Actions workflow configuration tests."""

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

    assert "Build cheatExtended/maplebirch canary ZIP" in build_workflow
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
