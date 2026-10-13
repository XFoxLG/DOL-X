#!/usr/bin/env python3
"""
SugarCube 静态验证器

功能：
- 检测 passage 链接完整性（断链检测）
- 验证 macro 语法正确性
- 检查变量使用一致性
- 识别潜在的运行时错误

用法：
    python tools/sugarcube_validator.py output/*.html --output report.json
    python tools/sugarcube_validator.py game.html --fail-on-errors
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# 添加项目根目录到路径
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.source_index import HTML_PASSAGE_RE, _html_name


# SugarCube built-in macros commonly used by DoL (macro registration lint).
SUGARCUBE_BUILTIN_MACROS = frozenset(
    {
        "append", "array", "audio", "back", "button", "capture", "checkbox",
        "choice", "click", "cycle", "else", "elseif", "endcapture", "endfor",
        "endif", "endsilently", "endswitch", "endwidget", "for", "goto", "if",
        "include", "link", "listbox", "nobr", "numberbox", "once", "prepend",
        "print", "radiobutton", "random", "remove", "replace", "run", "script",
        "set", "silently", "stop", "switch", "textbox", "time", "unset",
        "unless", "widget", "redo", "repeat", "type", "settings", "timed",
        "done", "goto", "actions",
    }
)

# Macros removed or renamed after SugarCube 1.x; DoL collects this list in
# sanityCheck.sh for the upstream source tree.
DEPRECATED_MACROS = {
    "display": "use <<include>> instead",
    "click": "use <<link>> / <<button>> instead",
    "endclick": "use finalize / onclick semantics instead",
    "remember": "use <<set>> on story variables instead",
    "forget": "use <<unset>> instead",
}

TAG_PAIRS = ("div", "span", "table", "ul", "ol", "p")

MISASSIGNMENT_RE = re.compile(
    r"<<\s*(?:if|elseif|unless)\b[^>{}]*?(?<![=!<>])=(?!=)[^>]*?>>",
    re.IGNORECASE,
)
DOUBLE_EQUALS_SET_RE = re.compile(r"<<\s*set\b[^>]*?==[^>]*?>>", re.IGNORECASE)
PASS_TIME_LINK_RE = re.compile(
    r"\[\[[^\]]*?\((?P<hours>\d{1,2}):(?P<minutes>\d{2})\)[^\]]*?\|[^\]]+\]\]"
    r"[^<]{0,120}?<<\s*pass\s+(?P<amount>\d+)\s*>>",
    re.IGNORECASE,
)
VARIABLE_RE = re.compile(r"(?<![\w])\$[A-Za-z_][\w]*")
MACRO_CALL_RE = re.compile(r"<<\s*([A-Za-z_][\w.-]*)")
MACRO_JS_REGISTER_RE = re.compile(r"Macro\.add\(\s*[\"']([^\"']+)[\"']")
WIDGET_DEF_RE = re.compile(r"<<\s*widget\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))")
DEPRECATED_MACRO_RE = re.compile(
    r"<<\s*(?P<name>" + "|".join(sorted(DEPRECATED_MACROS)) + r")\b", re.IGNORECASE
)


@dataclass
class ValidationIssue:
    """验证问题"""

    severity: str  # error, warning, info
    kind: str
    message: str
    passage: str | None = None
    line: int | None = None
    context: str | None = None


@dataclass
class ValidationResult:
    """验证结果"""

    target: str
    success: bool = True
    passage_count: int = 0
    link_count: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


class SugarCubeValidator:
    """SugarCube HTML 文件验证器"""

    # SugarCube 链接模式
    LINK_PATTERNS = [
        r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]",  # [[text|passage]] or [[passage]]
        r"<<(?:link|button)\s+['\"]([^'\"]+)['\"](?:\s+['\"]([^'\"]+)['\"])?>",  # <<link "text" "passage">>
    ]

    # Macro 配对检测
    MACRO_PAIRS = {
        "if": "endif",
        "for": "endfor",
        "switch": "endswitch",
        "capture": "endcapture",
        "nobr": "endnobr",
        "silently": "endsilently",
        "widget": "endwidget",
    }

    def __init__(
        self,
        strict: bool = False,
        *,
        lints: bool = True,
        lint_limit: int = 200,
    ):
        """
        Args:
            strict: 严格模式，将 warning 也视为错误
            lints: 是否运行上游启发的静态 lint（变量/宏/标签/时间/赋值）
            lint_limit: 每类 lint 最多记录的条数
        """
        self.strict = strict
        self.lints = lints
        self.lint_limit = max(0, int(lint_limit))

    def validate_html(self, html_path: Path) -> ValidationResult:
        """验证单个 HTML 文件"""
        result = ValidationResult(target=str(html_path))

        try:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result.success = False
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    kind="file_read_error",
                    message=f"无法读取文件: {e}",
                )
            )
            return result

        # 1. 提取所有 passage
        passages = self._extract_passages(html_content)
        result.passage_count = len(passages)

        if not passages:
            result.success = False
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    kind="no_passages",
                    message="HTML 文件中未找到任何 passage",
                )
            )
            return result

        # 2. 检测断链
        broken_links = self._find_broken_links(passages)
        result.issues.extend(broken_links)
        result.link_count = sum(
            len(self._extract_links(content)) for content in passages.values()
        )

        # 3. 验证 macro 语法
        for passage_name, content in passages.items():
            macro_issues = self._validate_macros(content, passage_name)
            result.issues.extend(macro_issues)

        # 4. 上游启发的 lint（变量只出现一次、废弃宏、未注册宏、标签配平、
        #    <pass> 时间不匹配、误赋值、set 里的双等号）
        lint_counts: dict[str, int] = {}
        if self.lints:
            lint_issues, lint_counts = self._lint_passages(passages, html_content)
            result.issues.extend(lint_issues)

        # 5. 统计信息
        result.stats = {
            "total_passages": len(passages),
            "total_links": result.link_count,
            "broken_links": sum(1 for i in result.issues if i.kind == "broken_link"),
            "unclosed_macros": sum(
                1 for i in result.issues if i.kind == "unclosed_macro"
            ),
            "lint_counts": lint_counts,
        }

        # 判断成功状态
        result.success = result.error_count == 0
        if self.strict:
            result.success = result.success and result.warning_count == 0

        return result

    def _extract_passages(self, html_content: str) -> dict[str, str]:
        """从 HTML 提取所有 passage"""
        passages = {}
        # 与 source_index 相同的属性解析：带撇号的 passage 名
        # （如 name="Men's Toilets"）不能被截断。
        for match in HTML_PASSAGE_RE.finditer(html_content):
            name = _html_name(match.group("attrs"))
            if name is not None:
                passages[html.unescape(name)] = html.unescape(match.group("body"))
        return passages

    def _extract_links(self, passage_content: str) -> list[str]:
        """从 passage 内容提取所有链接目标"""
        links = []

        # Pattern 1: [[text|passage]] or [[passage]]
        simple_link_pattern = r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]"
        for match in re.finditer(simple_link_pattern, passage_content):
            # 如果有 |，取第二部分作为目标，否则取第一部分
            if match.group(2):
                target = match.group(2).strip()
            else:
                target = match.group(1).strip()
            links.append(target)

        # Pattern 2: <<link "text" "passage">>
        macro_link_pattern = (
            r"<<(?:link|button)\s+(?:\"([^\"]+)\"|'([^']+)')\s+"
            r"(?:\"([^\"]+)\"|'([^']+)')"
        )
        for match in re.finditer(macro_link_pattern, passage_content):
            target = (match.group(3) or match.group(4) or "").strip()
            if not target:
                continue
            links.append(target)

        return links

    def _find_broken_links(self, passages: dict[str, str]) -> list[ValidationIssue]:
        """查找断链"""
        issues = []
        passage_names = set(passages.keys())

        for passage_name, content in passages.items():
            links = self._extract_links(content)

            for link_target in links:
                if link_target not in passage_names:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            kind="broken_link",
                            message=f"链接指向不存在的 passage: '{link_target}'",
                            passage=passage_name,
                            context=link_target,
                        )
                    )

        return issues

    def _validate_macros(
        self, passage_content: str, passage_name: str
    ) -> list[ValidationIssue]:
        """验证 macro 语法（检测未闭合的 macro）"""
        issues = []
        macro_stack = []

        # 匹配所有 macro: <<macroname ...>> 或 <</macroname>>
        # 改进的正则：匹配 << 和 >> 之间的内容
        macro_pattern = r"<<(/?)(\w+)(?:[^>]*)>>"
        matches = re.finditer(macro_pattern, passage_content)

        for match in matches:
            is_closing = bool(match.group(1))  # <</ 表示闭合标签
            macro_name = match.group(2).lower()

            if is_closing:
                # 闭合 macro
                if not macro_stack:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            kind="unexpected_close_macro",
                            message=f"意外的闭合 macro: <</{macro_name}>>，没有对应的开始标签",
                            passage=passage_name,
                        )
                    )
                elif macro_stack[-1] != macro_name:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            kind="mismatched_macro",
                            message=f"Macro 不匹配: 期望 <</{macro_stack[-1]}>>, 实际是 <</{macro_name}>>",
                            passage=passage_name,
                        )
                    )
                    macro_stack.pop()
                else:
                    macro_stack.pop()
            elif macro_name in self.MACRO_PAIRS:
                # 需要闭合的 macro
                macro_stack.append(macro_name)

        # 检查未闭合的 macro
        for unclosed_macro in macro_stack:
            issues.append(
                ValidationIssue(
                    severity="error",
                    kind="unclosed_macro",
                    message=f"Macro 未闭合: <<{unclosed_macro}>>, 缺少 <</{self.MACRO_PAIRS[unclosed_macro]}>>",
                    passage=passage_name,
                )
            )

        return issues

    def _lint_passages(
        self, passages: dict[str, str], html_content: str
    ) -> tuple[list["ValidationIssue"], dict[str, int]]:
        """上游 sanityCheck/check.py 启发的静态 lint。

        返回 (issues, counts)。counts 是所有命中的全量计数（issues 只保留
        每类前 lint_limit 条，避免真实 15k passage 构建下报告爆炸）。
        """
        issues: list[ValidationIssue] = []
        counts: Counter[str] = Counter()
        limit = self.lint_limit

        registered = set(SUGARCUBE_BUILTIN_MACROS)
        registered |= {match.group(1) for match in MACRO_JS_REGISTER_RE.finditer(html_content)}
        for body in passages.values():
            for match in WIDGET_DEF_RE.finditer(body):
                name = match.group(1) or match.group(2) or match.group(3)
                if name:
                    registered.add(name)
        registered_lower = {name.lower() for name in registered}

        variable_counts: Counter[str] = Counter()
        variable_passage: dict[str, str] = {}

        def record(kind: str, severity: str, message: str, passage: str, context: str | None = None) -> None:
            counts[kind] += 1
            if counts[kind] <= limit:
                issues.append(
                    ValidationIssue(
                        severity=severity,
                        kind=kind,
                        message=message,
                        passage=passage,
                        context=context,
                    )
                )

        for passage_name, content in passages.items():
            for match in VARIABLE_RE.finditer(content):
                name = match.group(0)
                variable_counts[name] += 1
                variable_passage.setdefault(name, passage_name)

            for match in DEPRECATED_MACRO_RE.finditer(content):
                name = match.group("name").lower()
                record(
                    "deprecated_macro",
                    "warning",
                    f"废弃宏 <<{name}>>: {DEPRECATED_MACROS[name]}",
                    passage_name,
                    name,
                )

            for match in MACRO_CALL_RE.finditer(content):
                name = match.group(1)
                if name.lower() in registered_lower:
                    continue
                record(
                    "unregistered_macro",
                    "info",
                    f"宏 <<{name}>> 未在 SugarCube 内置、JS Macro.add 或 widget 定义中登记",
                    passage_name,
                    name,
                )

            for tag in TAG_PAIRS:
                opens = len(re.findall(rf"<{tag}\b", content, re.IGNORECASE))
                closes = len(re.findall(rf"</{tag}>", content, re.IGNORECASE))
                if opens != closes:
                    record(
                        "unbalanced_html_tag",
                        "warning",
                        f"<{tag}> 标签不配平: {opens} 个开始 / {closes} 个结束",
                        passage_name,
                        tag,
                    )

            for match in MISASSIGNMENT_RE.finditer(content):
                record(
                    "suspect_assignment_in_condition",
                    "warning",
                    "条件表达式中出现单个 '='（可能是把 == 写成了 =）",
                    passage_name,
                    match.group(0)[:80],
                )

            for match in DOUBLE_EQUALS_SET_RE.finditer(content):
                record(
                    "double_equals_in_set",
                    "warning",
                    "<<set>> 中出现 '=='（可能是把 = 写成了 ==）",
                    passage_name,
                    match.group(0)[:80],
                )

            for match in PASS_TIME_LINK_RE.finditer(content):
                expected = int(match.group("hours")) * 60 + int(match.group("minutes"))
                actual = int(match.group("amount"))
                if expected != actual:
                    record(
                        "pass_time_mismatch",
                        "warning",
                        f"链接时间标注 {(expected // 60):02d}:{expected % 60:02d} 与 <<pass {actual}>> 不一致",
                        passage_name,
                        match.group(0)[:80],
                    )

        for name, count in sorted(variable_counts.items()):
            if count == 1:
                record(
                    "single_use_variable",
                    "info",
                    f"变量 {name} 只出现一次（可能是拼写错误）",
                    variable_passage.get(name, ""),
                    name,
                )

        return issues, {kind: total for kind, total in sorted(counts.items())}

    def validate_zip(self, zip_path: Path) -> ValidationResult:
        """验证 ZIP 包中的 HTML 文件"""
        result = ValidationResult(target=str(zip_path))

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # 查找 HTML 文件
                html_files = [
                    name for name in zf.namelist() if name.lower().endswith(".html")
                ]

                if not html_files:
                    result.success = False
                    result.issues.append(
                        ValidationIssue(
                            severity="error",
                            kind="no_html_in_zip",
                            message="ZIP 文件中未找到 HTML 文件",
                        )
                    )
                    return result

                # 验证第一个 HTML 文件
                html_file = html_files[0]
                html_content = zf.read(html_file).decode("utf-8", errors="replace")

                # 使用临时文件验证
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".html", delete=False
                ) as tmp:
                    tmp.write(html_content)
                    tmp_path = Path(tmp.name)

                try:
                    result = self.validate_html(tmp_path)
                    result.target = f"{zip_path} ({html_file})"
                finally:
                    tmp_path.unlink()

        except Exception as e:
            result.success = False
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    kind="zip_read_error",
                    message=f"无法读取 ZIP 文件: {e}",
                )
            )

        return result


def write_report(results: list[ValidationResult], output_path: Path) -> None:
    """写入验证报告（JSON 格式）"""
    report = {
        "total_targets": len(results),
        "successful": sum(1 for r in results if r.success),
        "failed": sum(1 for r in results if not r.success),
        "results": [
            {
                "target": r.target,
                "success": r.success,
                "passage_count": r.passage_count,
                "link_count": r.link_count,
                "error_count": r.error_count,
                "warning_count": r.warning_count,
                "stats": r.stats,
                "issues": [asdict(issue) for issue in r.issues],
            }
            for r in results
        ],
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="SugarCube HTML 静态验证器")
    parser.add_argument("targets", nargs="+", help="要验证的 HTML 或 ZIP 文件路径")
    parser.add_argument(
        "--output", type=Path, help="输出验证报告（JSON 格式）"
    )
    parser.add_argument(
        "--fail-on-errors", action="store_true", help="发现错误时以非零状态码退出"
    )
    parser.add_argument(
        "--strict", action="store_true", help="严格模式：将 warning 也视为错误"
    )
    parser.add_argument(
        "--no-lints", action="store_true", help="跳过上游启发的静态 lint"
    )
    parser.add_argument(
        "--lint-limit", type=int, default=200, help="每类 lint 最多记录的条数"
    )

    args = parser.parse_args()

    validator = SugarCubeValidator(
        strict=args.strict, lints=not args.no_lints, lint_limit=args.lint_limit
    )
    results = []

    for target_str in args.targets:
        target = Path(target_str)

        if not target.exists():
            print(f"错误: 文件不存在: {target}", file=sys.stderr)
            continue

        if target.suffix.lower() == ".zip":
            result = validator.validate_zip(target)
        else:
            result = validator.validate_html(target)

        results.append(result)

        # 打印结果
        status = "✓ PASS" if result.success else "✗ FAIL"
        print(f"{status} {result.target}")
        print(f"  Passages: {result.passage_count}, Links: {result.link_count}")
        print(
            f"  Errors: {result.error_count}, Warnings: {result.warning_count}"
        )

        if result.issues:
            for issue in result.issues[:10]:  # 只显示前 10 个问题
                print(
                    f"  [{issue.severity.upper()}] {issue.kind}: {issue.message}"
                )
            if len(result.issues) > 10:
                print(f"  ... 还有 {len(result.issues) - 10} 个问题")

    # 写入报告
    if args.output:
        write_report(results, args.output)
        print(f"\n报告已写入: {args.output}")

    # 确定退出状态
    if args.fail_on_errors:
        failed_count = sum(1 for r in results if not r.success)
        if failed_count > 0:
            print(f"\n验证失败: {failed_count}/{len(results)} 个目标", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
