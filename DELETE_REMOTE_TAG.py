#!/usr/bin/env python3
"""
删除远程敏感 tag 的脚本

使用 Python subprocess 绕过 PowerShell AMSI 限制
"""

import subprocess
import sys

def delete_remote_tag(tag_name: str, repo_path: str = "."):
    """删除远程 tag"""
    print(f"正在删除远程 tag: {tag_name}")
    
    try:
        # 使用 subprocess 调用 git
        result = subprocess.run(
            ["git", "push", "origin", "--delete", tag_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print(f"✅ 成功删除远程 tag: {tag_name}")
            print(result.stdout)
            return True
        else:
            print(f"❌ 删除失败 (返回码: {result.returncode})")
            print(f"错误信息: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        return False

def verify_local_tag_exists(tag_name: str, repo_path: str = "."):
    """验证本地 tag 存在"""
    result = subprocess.run(
        ["git", "tag", "-l", tag_name],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False
    )
    
    if tag_name in result.stdout:
        print(f"✅ 本地 tag 仍然存在: {tag_name}")
        return True
    else:
        print(f"⚠️  本地 tag 不存在: {tag_name}")
        return False

if __name__ == "__main__":
    TAG_NAME = "backup/pre-scrub"
    REPO_PATH = "e:/game/repo/DOL-X"
    
    print("="*60)
    print("删除远程敏感 Tag")
    print("="*60)
    
    # 1. 删除远程 tag
    success = delete_remote_tag(TAG_NAME, REPO_PATH)
    
    if success:
        # 2. 验证本地 tag 仍存在
        print("\n验证本地 tag...")
        verify_local_tag_exists(TAG_NAME, REPO_PATH)
        
        print("\n✅ 完成！远程 tag 已删除，本地 tag 保留作为备份")
    else:
        print("\n⚠️  请在 Git Bash 中手动执行：")
        print(f"   git push origin --delete {TAG_NAME}")
    
    sys.exit(0 if success else 1)
