#!/usr/bin/env python3
"""
环境检测脚本：自动检测并提示切换到 Git Bash

用法:
    python tools/check_environment.py
    
或在其他脚本中导入:
    from tools.check_environment import check_shell
    if not check_shell():
        sys.exit(1)
"""
import os
import sys
import platform


def check_shell():
    """
    检测当前 shell 环境
    
    返回:
        bool: True 如果环境合适，False 如果建议切换环境
    """
    if platform.system() == "Windows":
        # 检测是否在 PowerShell
        ps_module_path = os.environ.get("PSModulePath", "")
        if "POWERSHELL" in ps_module_path.upper() or "WINDOWSPOWERSHELL" in ps_module_path.upper():
            print("⚠️  检测到 PowerShell 环境")
            print("")
            print("由于 Windows PowerShell 的 AMSI（反恶意软件扫描接口）限制，")
            print("某些构建和 Git 操作可能会失败。")
            print("")
            print("建议：使用 Git Bash 运行 DOL-X 命令")
            print("")
            print("切换方法:")
            print("  1. 打开 Git Bash（开始菜单搜索 'Git Bash'）")
            print("  2. cd /e/game/repo/DOL-X")
            print("  3. 重新运行命令")
            print("")
            print("如果必须使用 PowerShell，可以尝试：")
            print("  - 以管理员身份运行 PowerShell")
            print("  - 临时禁用 AMSI（风险自负）")
            print("")
            return False
        
        # 检测是否在 Git Bash（MSYS/MinGW）
        msystem = os.environ.get("MSYSTEM", "")
        if msystem.startswith("MINGW") or msystem.startswith("MSYS"):
            print("✅ 检测到 Git Bash 环境（推荐）")
            return True
        
        # CMD 环境
        if os.environ.get("PROMPT"):
            print("⚠️  检测到 CMD 环境")
            print("建议使用 Git Bash 以获得更好的体验。")
            print("当前环境可以使用，但某些功能可能受限。")
            return True
    
    # Linux/macOS
    else:
        print("✅ 检测到 Unix-like 环境")
        return True
    
    # 未知环境
    print("⚠️  未能识别的环境")
    return True


def check_python_version():
    """检查 Python 版本是否满足要求"""
    required_version = (3, 12)
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        print(f"⚠️  Python 版本过低")
        print(f"   当前版本: {current_version[0]}.{current_version[1]}")
        print(f"   要求版本: {required_version[0]}.{required_version[1]}+")
        return False
    
    return True


def check_git_available():
    """检查 Git 是否可用"""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ Git 可用: {version}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    print("❌ Git 不可用")
    print("   请安装 Git: https://git-scm.com/downloads")
    return False


def main():
    """运行完整的环境检查"""
    print("="*60)
    print("DOL-X 环境检查")
    print("="*60)
    print()
    
    all_ok = True
    
    # 检查 shell 环境
    print("[1/3] 检查 Shell 环境...")
    if not check_shell():
        all_ok = False
    print()
    
    # 检查 Python 版本
    print("[2/3] 检查 Python 版本...")
    if not check_python_version():
        all_ok = False
    else:
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print()
    
    # 检查 Git
    print("[3/3] 检查 Git...")
    if not check_git_available():
        all_ok = False
    print()
    
    print("="*60)
    if all_ok:
        print("✅ 环境检查通过，可以继续")
        print("="*60)
        return 0
    else:
        print("⚠️  环境检查发现问题，请按照提示修复")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
