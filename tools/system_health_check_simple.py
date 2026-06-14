#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOL-X System Health Check - Simplified ASCII version
检查: 开发环境、项目结构、配置完整性、构建系统、测试、CI/CD、文档
"""

import subprocess
import sys
from pathlib import Path

def run_cmd(cmd):
    """执行命令"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.returncode, result.stdout, result.stderr

def main():
    print("="*70)
    print("DOL-X System Health Check")
    print("="*70)
    
    passed = []
    warnings = []
    errors = []
    
    # 1. Python环境
    print("\n[1/8] Checking Python Environment...")
    version = sys.version_info
    if version >= (3, 12):
        passed.append(f"Python {version.major}.{version.minor}.{version.micro} OK")
    else:
        errors.append(f"Python version too low: {version.major}.{version.minor}.{version.micro}")
    
    for pkg in ["pytest", "tomli"]:
        code, _, _ = run_cmd(f'python -c "import {pkg}"')
        if code == 0:
            passed.append(f"Package {pkg} installed")
        else:
            errors.append(f"Missing package: {pkg}")
    
    # 2. Git配置
    print("\n[2/8] Checking Git Configuration...")
    code, out, _ = run_cmd("git --version")
    if code == 0:
        passed.append(f"Git: {out.strip()}")
    
    code, out, _ = run_cmd("git remote -v")
    if "origin" in out:
        passed.append("Git remote 'origin' configured")
    if "upstream" in out:
        passed.append("Git remote 'upstream' configured")
    else:
        warnings.append("Git remote 'upstream' not configured (optional)")
    
    # 3. 项目结构
    print("\n[3/8] Checking Project Structure...")
    for dir_name in ["lyra", "tools", "config", "tests", "docs", ".github/workflows"]:
        if Path(dir_name).exists():
            passed.append(f"Directory {dir_name}/ exists")
        else:
            errors.append(f"Missing directory: {dir_name}/")
    
    for file_name in ["main.py", "config/build.toml", "config/features.toml", "config/combinations.toml"]:
        if Path(file_name).exists():
            passed.append(f"File {file_name} exists")
        else:
            errors.append(f"Missing file: {file_name}")
    
    # 4. 配置检查
    print("\n[4/8] Checking Configuration...")
    try:
        import tomli
        
        # Check features.toml
        with open("config/features.toml", "rb") as f:
            features_data = tomli.load(f)
        passed.append("config/features.toml syntax valid")
        
        # Check BESC status
        features = features_data.get("features", [])
        besc = next((f for f in features if f.get("id") == "besc"), None)
        if besc and besc.get("skip") == True:
            passed.append("BESC skip=true (DOL-X policy)")
        
        if besc and "ucb" in besc.get("conflicts_with", []):
            passed.append("BESC conflicts_with contains ucb")
        
        # Check combinations.toml
        with open("config/combinations.toml", "rb") as f:
            comb_data = tomli.load(f)
        passed.append("config/combinations.toml syntax valid")
        
        build_codes = comb_data.get("build_codes", [])
        codes_with_besc = [int(c) for c in build_codes if int(c) & 1]
        if not codes_with_besc:
            passed.append("build_codes does not contain BESC (bit 1)")
        else:
            errors.append(f"build_codes contains BESC: {codes_with_besc}")
            
    except ImportError:
        warnings.append("tomli not installed, skipping config validation")
    except Exception as e:
        errors.append(f"Config validation failed: {e}")
    
    # 5. 测试
    print("\n[5/8] Running Tests...")
    code, out, _ = run_cmd("python -m pytest tests/test_build_matrix.py tests/test_mod_config.py -v --tb=short")
    if code == 0:
        count = out.count("PASSED")
        passed.append(f"Core tests passed ({count} tests)")
    else:
        errors.append("Core tests failed")
    
    # 6. 构建系统
    print("\n[6/8] Checking Build System...")
    for file in ["lyra/__init__.py", "lyra/build.py", "lyra/combo.py", "lyra/config_loader.py"]:
        if Path(file).exists():
            passed.append(f"Core file {file} exists")
    
    code, out, _ = run_cmd("python main.py matrix")
    if code == 0 and "57600" in out:
        passed.append("Build matrix generation works")
    
    # 7. CI/CD
    print("\n[7/8] Checking CI/CD...")
    if Path(".github/workflows/compatibility.yaml").exists():
        passed.append("Workflow compatibility.yaml exists")
    
    # 8. 文档
    print("\n[8/8] Checking Documentation...")
    for doc in ["README.md", "BUILD.md", "QUICK_REFERENCE.md", "MOD_MATRIX_RATIONALE.md"]:
        if Path(doc).exists():
            passed.append(f"Documentation {doc} exists")
            
            if doc in ["QUICK_REFERENCE.md", "MOD_MATRIX_RATIONALE.md"]:
                content = Path(doc).read_text(encoding='utf-8')
                if "skip=true" in content or "禁用" in content:
                    passed.append(f"{doc} correctly describes BESC status")
    
    # 总结
    print("\n" + "="*70)
    print("Health Check Summary")
    print("="*70)
    print(f"[PASS] {len(passed)} checks passed")
    print(f"[WARN] {len(warnings)} warnings")
    print(f"[FAIL] {len(errors)} errors")
    
    if warnings:
        print("\nWarnings:")
        for w in warnings[:5]:
            print(f"  - {w}")
    
    if errors:
        print("\nErrors:")
        for e in errors[:5]:
            print(f"  - {e}")
    
    print("="*70)
    
    return 0 if len(errors) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
