"""SugarCube 静态验证器测试"""

import tempfile
from pathlib import Path

import pytest

from tools.sugarcube_validator import (
    SugarCubeValidator,
    ValidationIssue,
    ValidationResult,
)


@pytest.fixture
def validator():
    """创建验证器实例"""
    return SugarCubeValidator()


@pytest.fixture
def strict_validator():
    """创建严格模式验证器"""
    return SugarCubeValidator(strict=True)


def _create_test_html(passages_content: str) -> Path:
    """创建临时测试 HTML 文件"""
    html = f"""<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<tw-storydata>
{passages_content}
</tw-storydata>
</body>
</html>"""

    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".html", delete=False
    )
    tmp.write(html)
    tmp.close()
    return Path(tmp.name)


@pytest.mark.sugarcube
def test_validator_detects_broken_links(validator):
    """验证器能检测断链"""
    passages = """
    <tw-passagedata name="Start">
        [[Go to NonExistent]]
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is False
        assert result.error_count == 1
        assert any(issue.kind == "broken_link" for issue in result.issues)
        assert any("NonExistent" in issue.message for issue in result.issues)
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_accepts_valid_passages(validator):
    """验证器接受正确的 passage"""
    passages = """
    <tw-passagedata name="Start">
        [[Next]]
    </tw-passagedata>
    <tw-passagedata name="Next">
        Content
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is True
        assert result.error_count == 0
        assert result.passage_count == 2
        assert result.link_count == 1
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_detects_unclosed_macros(validator):
    """验证器检测未闭合的 macro"""
    passages = """
    <tw-passagedata name="Start">
        <<if $condition>>
        Some content
        <!-- Missing <<endif>> -->
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is False
        assert result.error_count == 1
        assert any(issue.kind == "unclosed_macro" for issue in result.issues)
        assert any("<<if>>" in issue.message for issue in result.issues)
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_extracts_link_with_text(validator):
    """验证器提取带文本的链接"""
    passages = """
    <tw-passagedata name="Start">
        [[Click here|Target]]
    </tw-passagedata>
    <tw-passagedata name="Target">
        Destination
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is True
        assert result.link_count == 1
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_detects_multiple_broken_links(validator):
    """验证器检测多个断链"""
    passages = """
    <tw-passagedata name="Start">
        [[Link1|Missing1]]
        [[Link2|Missing2]]
        [[Link3|Missing3]]
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is False
        assert result.error_count == 3
        broken_link_issues = [i for i in result.issues if i.kind == "broken_link"]
        assert len(broken_link_issues) == 3
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_stats_are_correct(validator):
    """验证器统计信息正确"""
    passages = """
    <tw-passagedata name="Start">
        [[Valid1]]
        [[Valid2]]
        [[Invalid]]
    </tw-passagedata>
    <tw-passagedata name="Valid1">Content</tw-passagedata>
    <tw-passagedata name="Valid2">Content</tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.stats["total_passages"] == 3
        assert result.stats["total_links"] == 3
        assert result.stats["broken_links"] == 1
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_handles_empty_html(validator):
    """验证器处理空 HTML"""
    html_path = _create_test_html("")

    try:
        result = validator.validate_html(html_path)

        assert result.success is False
        assert any(issue.kind == "no_passages" for issue in result.issues)
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_handles_link_macro_syntax(validator):
    """验证器处理 <<link>> macro 语法"""
    passages = """
    <tw-passagedata name="Start">
        <<link "Go here" "Target">>
    </tw-passagedata>
    <tw-passagedata name="Target">
        Destination
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is True
        assert result.link_count == 1
    finally:
        html_path.unlink()


@pytest.mark.sugarcube
def test_validator_detects_broken_link_macro(validator):
    """验证器检测 <<link>> macro 中的断链"""
    passages = """
    <tw-passagedata name="Start">
        <<link "Click" "NonExistent">>
    </tw-passagedata>
    """
    html_path = _create_test_html(passages)

    try:
        result = validator.validate_html(html_path)

        assert result.success is False
        assert any(issue.kind == "broken_link" for issue in result.issues)
    finally:
        html_path.unlink()
