"""Verify the two-tier public build code configuration in the CI workflow."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "build.yaml"


def read_build_workflow() -> str:
    return BUILD_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_branch_tier_contains_base_and_au_f():
    workflow = read_build_workflow()

    assert 'BRANCH_BUILD_CODES: "15704320 15705344"' in workflow


def test_branch_tier_excludes_au_m_and_au_a():
    workflow = read_build_workflow()

    assert "15706368" not in workflow.split("BRANCH_BUILD_CODES")[1].split("\n")[0]
    assert "15708416" not in workflow.split("BRANCH_BUILD_CODES")[1].split("\n")[0]


def test_release_tier_contains_all_four_codes():
    workflow = read_build_workflow()

    release_line = [
        line for line in workflow.splitlines()
        if "RELEASE_BUILD_CODES" in line and ":" in line
    ][0]
    assert "15704320" in release_line
    assert "15705344" in release_line
    assert "15706368" in release_line
    assert "15708416" in release_line


def test_warmup_and_build_use_same_codes_source():
    """Warmup and build must reference the same resolved codes output."""
    workflow = read_build_workflow()

    warmup_section = workflow[workflow.index("Warmup beautify resources"):]
    warmup_codes_line = warmup_section.split("--codes")[1].split("\n")[0]

    build_section = workflow[workflow.index("Build combinations"):]
    build_codes_line = build_section.split("--codes")[1].split("\n")[0]

    assert "steps.codes.outputs.value" in warmup_codes_line
    assert "steps.codes.outputs.value" in build_codes_line


def test_workflow_selects_tier_by_ref_type():
    """The codes selection step branches on github.ref_type."""
    workflow = read_build_workflow()

    assert "Select build codes" in workflow
    codes_section = workflow[workflow.index("Select build codes"):]
    selection_block = codes_section[:codes_section.index("Warmup")]
    assert "RELEASE_BUILD_CODES" in selection_block
    assert "BRANCH_BUILD_CODES" in selection_block
    assert 'github.ref_type' in selection_block
