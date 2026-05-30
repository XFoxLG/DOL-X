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
def test_build_canary_browser_smoke_runs_in_dispatchable_workflow():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yaml").read_text(encoding="utf-8")

    assert "Run cheatExtended/maplebirch canary browser smoke" in workflow
    assert "--profile ucb-cheat-extended-maplebirch" in workflow
    assert "--output-dir \"${{ github.workspace }}/output/cheat-canary-browser-smoke\"" in workflow
    assert "name: cheat-canary-browser-smoke-report" in workflow
    assert "path: ${{ github.workspace }}/output/cheat-canary-browser-smoke/" in workflow
