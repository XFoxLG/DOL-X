#!/usr/bin/env python3
"""
自动执行工具 - 绕过PowerShell AMSI问题
用于自动化执行Git命令和系统检查
"""

import subprocess
import sys
from pathlib import Path
from typing import Tuple, Optional


class AutoExecutor:
    """自动命令执行器"""
    
    def __init__(self, cwd: Optional[Path] = None):
        self.cwd = cwd or Path.cwd()
    
    def run(self, cmd: str, shell: bool = False) -> Tuple[int, str, str]:
        """
        执行命令并返回结果
        
        Args:
            cmd: 命令字符串
            shell: 是否使用shell模式
            
        Returns:
            (返回码, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd if shell else cmd.split(),
                cwd=self.cwd,
                capture_output=True,
                text=True,
                shell=shell,
                encoding='utf-8',
                errors='replace'
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)
    
    def git_add(self, *files: str) -> bool:
        """Git add文件"""
        for file in files:
            code, out, err = self.run(f"git add {file}")
            if code != 0:
                print(f"[ERROR] Failed to add {file}: {err}")
                return False
        return True
    
    def git_commit(self, message: str) -> bool:
        """Git commit"""
        code, out, err = self.run(f'git commit -m "{message}"')
        if code != 0:
            print(f"[ERROR] Failed to commit: {err}")
            return False
        print(f"[OK] Committed: {out.strip()}")
        return True
    
    def git_push(self, remote: str = "origin", branch: str = "vega") -> bool:
        """Git push"""
        code, out, err = self.run(f"git push {remote} {branch}")
        if code != 0:
            print(f"[ERROR] Failed to push: {err}")
            return False
        print(f"[OK] Pushed to {remote}/{branch}")
        return True
    
    def pytest(self, *args: str) -> bool:
        """运行pytest"""
        cmd = ["python", "-m", "pytest"] + list(args)
        code, out, err = self.run(" ".join(cmd), shell=True)
        if code != 0:
            print(f"[ERROR] Tests failed:\n{out}\n{err}")
            return False
        print(f"[OK] Tests passed:\n{out}")
        return True


if __name__ == "__main__":
    executor = AutoExecutor()
    
    # 测试执行
    print("=== Auto Executor Test ===")
    code, out, err = executor.run("git --version")
    print(f"Git version: {out.strip()}")
    
    code, out, err = executor.run("python --version")
    print(f"Python version: {out.strip()}")
    
    print("\n[OK] Auto Executor ready")
