"""GitHub Actions workflow configuration tests."""

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.config
def test_build_zip_sample_prefers_non_au_package_with_fallback():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build.yaml").read_text(encoding="utf-8")

    assert 'find "${{ github.workspace }}/output" -maxdepth 1 -type f -name "*.zip" ! -name "*-au-*"' in workflow
    assert 'if [[ -z "$ZIP_FILE" ]]; then' in workflow
    assert 'ZIP_FILE=$(find "${{ github.workspace }}/output" -maxdepth 1 -type f -name "*.zip" | sort | head -n 1)' in workflow
    assert 'echo "zip=$ZIP_FILE" >> "$GITHUB_OUTPUT"' in workflow
