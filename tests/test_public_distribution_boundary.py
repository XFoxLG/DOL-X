"""Public CI must not redistribute AU assets without author permission."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "build.yaml"


def read_build_workflow() -> str:
    return BUILD_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_public_workflow_builds_only_the_base_code():
    workflow = read_build_workflow()

    assert 'PUBLIC_BUILD_CODES: "15704320"' in workflow
    assert workflow.count('--codes "${PUBLIC_BUILD_CODES}"') == 3
    assert "15705344" not in workflow
    assert "15706368" not in workflow
    assert "15708416" not in workflow


def test_public_workflow_documents_the_au_redistribution_boundary():
    workflow = read_build_workflow()

    assert "AU 作者仓库明确禁止二传" in workflow
    assert "公开 CI 只构建 base" in workflow
