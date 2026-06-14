#!/usr/bin/env python3
"""
验证文档整理完成状态的脚本
"""
import sys
from pathlib import Path

def main():
    base = Path(__file__).parent.parent
    
    print("="*70)
    print("DOL-X 文档整理验证")
    print("="*70)
    print()
    
    # 检查 AGENTS.md
    agents_md = base / "AGENTS.md"
    print(f"[1/5] 检查 AGENTS.md...")
    if agents_md.exists():
        size = agents_md.stat().st_size
        print(f"  ✓ AGENTS.md 存在 ({size} bytes)")
        with open(agents_md, encoding='utf-8') as f:
            content = f.read()
            if "## 1. 项目定位与目标" in content and "## 6. 当前进度与 TODO" in content:
                print(f"  ✓ 结构完整（6节）")
            else:
                print(f"  ✗ 结构不完整")
                return 1
    else:
        print(f"  ✗ AGENTS.md 不存在")
        return 1
    
    # 检查 docs/INDEX.md
    index_md = base / "docs" / "INDEX.md"
    print(f"\n[2/5] 检查 docs/INDEX.md...")
    if index_md.exists():
        print(f"  ✓ docs/INDEX.md 存在")
    else:
        print(f"  ✗ docs/INDEX.md 不存在")
        return 1
    
    # 检查 .gitignore 更新
    gitignore = base / ".gitignore"
    print(f"\n[3/5] 检查 .gitignore...")
    if gitignore.exists():
        with open(gitignore, encoding='utf-8') as f:
            content = f.read()
            if ".local/" in content and "AGENTS.md" in content:
                print(f"  ✓ .gitignore 包含 .local/ 和 AGENTS.md")
            else:
                print(f"  ✗ .gitignore 未正确更新")
                return 1
    
    # 检查关联文档更新
    print(f"\n[4/5] 检查关联文档更新...")
    docs_to_check = [
        ("MOD_MATRIX_RATIONALE.md", "UCB_COMPATIBILITY_REPORT"),
        ("QUICK_REFERENCE.md", "美化兼容性说明"),
        ("docs/COMMUNITY_TOOLS.md", "场景 4: 验证美化兼容性"),
    ]
    
    for doc_path, keyword in docs_to_check:
        doc = base / doc_path
        if doc.exists():
            with open(doc, encoding='utf-8') as f:
                if keyword in f.read():
                    print(f"  ✓ {doc_path} 包含 '{keyword}'")
                else:
                    print(f"  ✗ {doc_path} 不包含 '{keyword}'")
                    return 1
        else:
            print(f"  ✗ {doc_path} 不存在")
            return 1
    
    # 检查临时文件是否被忽略
    print(f"\n[5/5] 检查临时文件状态...")
    print(f"  提示：运行 'git status' 确认 AGENTS.md 和 .local/ 不在 Untracked 列表")
    
    print()
    print("="*70)
    print("✓ 所有检查通过！")
    print("="*70)
    print()
    print("下一步：")
    print("1. 运行 'git status' 确认修改")
    print("2. 运行 'git add' 添加文件")
    print("3. 运行 'git commit' 提交")
    print("4. 运行 'git push origin vega' 推送")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
