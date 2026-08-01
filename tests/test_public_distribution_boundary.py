"""Verify the two-tier public build code configuration in the CI workflow."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "build.yaml"


def read_build_workflow() -> str:
    return BUILD_WORKFLOW_PATH.read_text(encoding="utf-8")


def read_codes_tier(tier_name: str) -> str:
    """Return the quoted value assigned to a build-code tier variable."""
    workflow = read_build_workflow()
    tier_line = [
        line for line in workflow.splitlines()
        if line.strip().startswith(f"{tier_name}:")
    ][0]
    return tier_line.split(":", 1)[1].strip().strip('"')


def test_branch_tier_contains_base_and_au_f():
    branch_codes = read_codes_tier("BRANCH_BUILD_CODES").split(",")

    assert branch_codes == ["15704320", "15705344"]


def test_branch_tier_excludes_au_m_and_au_a():
    branch_codes = read_codes_tier("BRANCH_BUILD_CODES").split(",")

    assert "15706368" not in branch_codes
    assert "15708416" not in branch_codes


def test_build_code_tiers_are_comma_separated():
    """main.py splits --codes on commas only, so space separators silently fail."""
    for tier_name in ("BRANCH_BUILD_CODES", "RELEASE_BUILD_CODES"):
        tier_value = read_codes_tier(tier_name)

        assert " " not in tier_value, (
            f"{tier_name} must be comma-separated; spaces are parsed as one code"
        )
        for code in tier_value.split(","):
            assert code.isdigit(), f"{tier_name} contains a non-numeric code: {code}"


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


def test_manual_dispatch_can_request_the_release_tier():
    """A pre-release dry run needs to build all four codes without pushing a tag."""
    workflow = read_build_workflow()

    assert "build_tier" in workflow, (
        "workflow_dispatch must expose a build_tier input for release dry runs"
    )

    codes_section = workflow[workflow.index("Select build codes"):]
    selection_block = codes_section[:codes_section.index("Warmup")]
    assert 'inputs.build_tier' in selection_block, (
        "the codes selection step must honour the build_tier input"
    )


def test_release_job_only_runs_for_tags():
    """A manual release-tier dry run must never publish a Release."""
    workflow = read_build_workflow()

    release_job_section = workflow[workflow.index("  release:"):]
    guard_lines = [
        line.strip() for line in release_job_section.splitlines()
        if line.strip().startswith("if:")
    ]

    assert guard_lines, "the release job must keep an explicit ref_type guard"
    assert guard_lines[0] == "if: github.ref_type == 'tag'"
