#!/usr/bin/env python3
"""
自动执行文档整理的 3 次提交
"""
import subprocess
import sys
from pathlib import Path

def run(cmd, description):
    """执行命令并显示结果"""
    print(f"\n{'='*70}")
    print(f"[执行] {description}")
    print(f"[命令] {cmd}")
    print(f"{'='*70}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    print(f"\n{'✅' if result.returncode == 0 else '❌'} {'成功' if result.returncode == 0 else '失败'} (返回码: {result.returncode})")
    
    return result.returncode == 0

def main():
    base = Path(__file__).parent.parent
    
    print("="*70)
    print("DOL-X 文档整理 - 自动提交")
    print("="*70)
    
    # 提交 1: 文档整理
    print("\n[提交 1/3] 文档整理")
    
    if not run("git add .gitignore", "添加 .gitignore"):
        return 1
    
    if not run("git add docs/INDEX.md", "添加 docs/INDEX.md"):
        return 1
    
    if not run("git add docs/UCB_COMPATIBILITY_REPORT.md", "添加 UCB 兼容性报告"):
        return 1
    
    if not run("git add tools/verify_docs_structure.py", "添加验证脚本"):
        return 1
    
    commit_msg_1 = """docs: reorganize documentation structure

- Add docs/INDEX.md for navigation
- Update .gitignore to ignore .local/ and AGENTS.md
- Add tools/verify_docs_structure.py for validation
- Establish 4-tier documentation structure:
  * User docs (root): README, QUICK_REFERENCE
  * Internal docs (docs/): technical decisions, sync guides
  * Local docs (.local/): temporary analysis, scripts (gitignored)
  * Memory (AGENTS.md): AI context source (gitignored)

Part of memory system establishment and documentation cleanup."""
    
    if not run(f'git commit -m "{commit_msg_1}"', "提交文档整理"):
        print("  (如果没有变更则跳过)")
    
    # 提交 2: 更新引用
    print("\n[提交 2/3] 更新引用")
    
    if not run("git add MOD_MATRIX_RATIONALE.md", "添加 MOD_MATRIX_RATIONALE.md"):
        return 1
    
    if not run("git add QUICK_REFERENCE.md", "添加 QUICK_REFERENCE.md"):
        return 1
    
    if not run("git add docs/COMMUNITY_TOOLS.md", "添加 COMMUNITY_TOOLS.md"):
        return 1
    
    commit_msg_2 = """docs: add UCB compatibility verification references

- Update MOD_MATRIX_RATIONALE: link to UCB_COMPATIBILITY_REPORT
- Update QUICK_REFERENCE: add beautification compatibility FAQ
- Update COMMUNITY_TOOLS: add compatibility verification guide

Key updates:
- Explain why UCB + AU combination is technically sound
- Clarify why BESC is not used (UCB覆盖战斗图片)
- Add imagepack overlap analysis guidance

References UCB compatibility report (docs/UCB_COMPATIBILITY_REPORT.md)."""
    
    if not run(f'git commit -m "{commit_msg_2}"', "提交引用更新"):
        print("  (如果没有变更则跳过)")
    
    # 提交 3: 提交辅助脚本
    print("\n[提交 3/3] 提交辅助脚本")
    
    if not run("git add tools/commit_docs_reorganization.py", "添加提交脚本"):
        return 1
    
    commit_msg_3 = """chore: add documentation reorganization commit script

- Add tools/commit_docs_reorganization.py for automated commits
- Script handles 3-stage commit process:
  1. Documentation structure
  2. Cross-reference updates
  3. Helper scripts

Part of unattended execution workflow."""
    
    if not run(f'git commit -m "{commit_msg_3}"', "提交辅助脚本"):
        print("  (如果没有变更则跳过)")
    
    # 推送
    print("\n[推送] 推送到 origin/vega")
    
    if not run("git push origin vega", "推送到远程"):
        return 1
    
    print("\n" + "="*70)
    print("✅ 完成！所有提交已推送到 origin/vega")
    print("="*70)
    print()
    print("验证：")
    print("1. 访问 https://github.com/XFoxLG/DOL-X/commits/vega")
    print("2. 确认看到 3 个新提交")
    print("3. 检查 AGENTS.md 不在 GitHub 上（被 .gitignore 忽略）")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
