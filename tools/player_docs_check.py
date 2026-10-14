"""玩家向文档禁词检查（Player-facing document check）.

`docs/release-notes/` 里的每个文件都会整份成为 GitHub Release 正文，玩家会原样看到；
根目录的 `玩家更新日志.md` 同理。本工具按 `docs/DOCUMENTATION_GUIDE.md` 的规则扫描这些文件，
命中内部术语、代码符号、仓库路径、哈希、CI 编号等即失败。

规则表是「从实际泄漏里长出来的」：每一条都对应过去真实出现过、被玩家看到的写法。
新增规则时请同时在 `tests/test_player_docs_check.py` 里加正例与反例。

用法::

    python tools/player_docs_check.py                     # 检查默认目标
    python tools/player_docs_check.py path/to/note.md     # 检查指定文件
    python tools/player_docs_check.py --json out.json     # 顺带写机器可读报告
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "dolx.player_docs.v1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEASE_NOTES_DIR = PROJECT_ROOT / "docs" / "release-notes"
PLAYER_CHANGELOG = PROJECT_ROOT / "玩家更新日志.md"

# 规则: (规则 id, 正则, 给人看的说明, 建议改写)
RULES: tuple[tuple[str, str, str, str], ...] = (
    (
        "hash",
        r"sha-?256|\b[a-f0-9]{32,}\b|\b\d{2,3},\d{3},\d{3}\b",
        "哈希值或精确字节数",
        "删掉，或把校验信息放进技术档案",
    ),
    (
        "ci_run",
        r"\brun\s*#?\d{5,}\b|\bGitHub Actions\b|\bworkflow\b",
        "CI 运行编号或流水线术语",
        "改成“自动构建”，编号放技术档案",
    ),
    (
        "commit",
        r"\bcommit\b|\b[a-f0-9]{7,40}\b",
        "提交哈希",
        "删掉，版本用 tag 或日期指代",
    ),
    (
        "internal_term",
        r"\bpayloads?\b|\bmanifest\b|fail[-\s]?closed|\bneedle\b|\bshim\b|\bschema\b|\bboot\.json\b",
        "内部术语",
        "改成玩家能懂的说法，细节放技术档案",
    ),
    (
        "repo_path",
        r"\btools/|\blyra/|\bconfig/|\bdocs/[A-Za-z]|\.py\b|\.toml\b|\.json\b|\.ya?ml\b",
        "仓库路径或代码文件",
        "删掉路径；要给线索就指向技术档案或 CHANGELOG 链接",
    ),
    (
        "code_symbol",
        r"\b[A-Za-z_][A-Za-z0-9_]{2,}\(\)|\$[A-Za-z_][A-Za-z0-9_]*",
        "函数名或游戏变量名",
        "改成玩家看到的界面说法",
    ),
    (
        "asset_file",
        r"\b[a-z0-9][a-z0-9_-]*\.(png|jpe?g|webp|gif|js|twee|css)\b",
        "素材或脚本文件名",
        "改成“某张立绘/图标”这类说法",
    ),
    (
        "internal_status",
        r"\baccepted_upstream\b|\bvisual_incomplete\b|\bno_visual_change\b|\bab_verdict\b"
        r"|\binfrastructure_fail\b|\bfixture_insufficient\b|\bsource_gap\b|\bhard_fail\b|\bsoft_fail\b"
        r"|\bA/B\b(?![^\n]{0,10}(截图|对比图))",
        "内部判定状态或内部验收术语",
        "改成“已确认属于上游机制”“未修复”这类玩家说法",
    ),
    (
        "internal_tool",
        r"\b(?:combat_sweep|passage_sweep|scenario_sweep|env_matrix|exploration_gate|sprite_layout_probe"
        r"|sweep_flow_assertions|framework_contract_check|au_artifact_check|target_package_check"
        r"|mod_passage_inventory|traversal_statistics|query_regression|story_graph_audit"
        r"|static_reachability_solver|checkpoint_store|exploration_oracle|player_docs_check)\b",
        "内部工具名",
        "写成“自动测试”即可，工具名放技术档案",
    ),
    (
        "code_ident",
        r"\bfaceStyleSrcFn\b|\bwhenSC2PassageEnd\b|\bUIBar\b|\bresolveFaceImagePath\b|\bbasehead\b"
        r"|\bdependenceInfo\b|\baddonPlugin\b|\bTweeReplacer\b|\bReplacePatcher\b|\bmodList\b"
        r"|\bvariant:\s*true\b",
        "源码标识符",
        "删掉；这是技术档案的内容",
    ),
    (
        "debug_jargon",
        r"\bpageerror\b|\blogcat\b|\bANR\b|\bFATAL\b|\bAndroidRuntime\b|\bCDP\b|\blocalStorage\b"
        r"|\bIndexedDB\b|\bconsole\.log\b",
        "调试术语",
        "改成“错误日志”“崩溃”这类玩家说法",
    ),
)

def default_targets() -> list[Path]:
    """Every file whose whole content becomes a GitHub Release body, plus the player changelog."""
    return sorted(RELEASE_NOTES_DIR.glob("*.md")) + [PLAYER_CHANGELOG]


@dataclass
class Violation:
    rule: str
    description: str
    suggestion: str
    line: int
    text: str
    match: str


@dataclass
class FileReport:
    path: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


COMPILED: tuple[tuple[str, re.Pattern[str], str, str], ...] = tuple(
    (rule, re.compile(pattern), description, suggestion) for rule, pattern, description, suggestion in RULES
)


URL_PATTERN = re.compile(r"https?://\S+")


def _mask_urls(line: str) -> str:
    """Links are allowed (players need them); only bare repo paths in prose are not."""
    return URL_PATTERN.sub("<link>", line)


def check_text(text: str) -> list[Violation]:
    """Return every rule violation in ``text`` (one entry per offending line/rule)."""
    found: list[Violation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = _mask_urls(line)
        for rule, pattern, description, suggestion in COMPILED:
            match = pattern.search(line)
            if match:
                found.append(
                    Violation(
                        rule=rule,
                        description=description,
                        suggestion=suggestion,
                        line=lineno,
                        text=line.strip()[:160],
                        match=match.group(0),
                    )
                )
    return found


def check_file(path: Path) -> FileReport:
    text = path.read_text(encoding="utf-8")
    return FileReport(path=str(path), violations=check_text(text))


def build_report(paths: list[Path]) -> dict[str, object]:
    files: list[FileReport] = []
    missing: list[str] = []
    for path in paths:
        if not path.exists():
            missing.append(str(path))
            continue
        files.append(check_file(path))
    return {
        "schema": SCHEMA,
        "ok": (not missing) and all(report.ok for report in files),
        "checked": [report.path for report in files],
        "missing": missing,
        "files": [
            {
                "path": report.path,
                "ok": report.ok,
                "violations": [
                    {
                        "rule": v.rule,
                        "description": v.description,
                        "suggestion": v.suggestion,
                        "line": v.line,
                        "match": v.match,
                        "text": v.text,
                    }
                    for v in report.violations
                ],
            }
            for report in files
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check player-facing documents for internal jargon.")
    parser.add_argument("paths", nargs="*", type=Path, help="files to check (default: all release notes + player changelog)")
    parser.add_argument("--json", dest="json_out", type=Path, default=None, help="write the machine readable report here")
    parser.add_argument("--quiet", action="store_true", help="only print violations")
    args = parser.parse_args(argv)

    targets = list(args.paths) if args.paths else default_targets()
    report = build_report([Path(t) for t in targets])

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    total = 0
    for entry in report["files"]:
        violations = entry["violations"]
        total += len(violations)
        if not violations:
            if not args.quiet:
                print(f"OK   {entry['path']}")
            continue
        print(f"FAIL {entry['path']}")
        for v in violations:
            print(f"  line {v['line']}: [{v['rule']}] {v['description']} -> {v['match']!r}")
            print(f"      {v['text']}")
            print(f"      fix: {v['suggestion']}")
    for path in report["missing"]:
        print(f"MISSING {path}")

    if report["ok"]:
        if not args.quiet:
            print(f"\nplayer-docs check: {len(report['checked'])} file(s) clean")
        return 0
    print(f"\nplayer-docs check: {total} violation(s), {len(report['missing'])} missing file(s)")
    return 2 if report["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())
