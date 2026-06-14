#!/usr/bin/env python3
"""
DOL-X 系统全面健康检查工具
检查：开发环境、项目结构、配置完整性、构建系统、测试覆盖、CI/CD、文档一致性
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    import tomli
except ImportError:
    tomli = None


class HealthCheckResult:
    """健康检查结果"""
    
    def __init__(self):
        self.passed: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
    
    def add_pass(self, msg: str):
        self.passed.append(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def add_error(self, msg: str):
        self.errors.append(msg)
    
    def print_summary(self):
        """打印总结"""
        print("\n" + "="*70)
        print("系统健康检查总结")
        print("="*70)
        print(f"✓ 通过: {len(self.passed)}")
        print(f"⚠ 警告: {len(self.warnings)}")
        print(f"✗ 错误: {len(self.errors)}")
        
        if self.warnings:
            print("\n⚠ 警告详情:")
            for w in self.warnings:
                print(f"  - {w}")
        
        if self.errors:
            print("\n✗ 错误详情:")
            for e in self.errors:
                print(f"  - {e}")
        
        print("="*70)
        return len(self.errors) == 0


class SystemHealthChecker:
    """系统健康检查器"""
    
    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path.cwd()
        self.result = HealthCheckResult()
    
    def run_cmd(self, cmd: str) -> Tuple[int, str, str]:
        """执行命令"""
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        return result.returncode, result.stdout, result.stderr
    
    def check_python_env(self):
        """检查 Python 环境"""
        print("\n[1/8] 检查 Python 环境...")
        
        # Python 版本
        version = sys.version_info
        if version >= (3, 12):
            self.result.add_pass(f"Python 版本: {version.major}.{version.minor}.{version.micro} ✓")
        else:
            self.result.add_error(f"Python 版本过低: {version.major}.{version.minor}.{version.micro}，需要 3.12+")
        
        # 检查必需包
        required_packages = ["pytest", "playwright", "tomli", "tomli-w"]
        for pkg in required_packages:
            code, out, err = self.run_cmd(f"python -c \"import {pkg}\"")
            if code == 0:
                self.result.add_pass(f"包 {pkg} 已安装 ✓")
            else:
                self.result.add_error(f"缺少必需包: {pkg}")
    
    def check_git_config(self):
        """检查 Git 配置"""
        print("\n[2/8] 检查 Git 配置...")
        
        # Git 版本
        code, out, err = self.run_cmd("git --version")
        if code == 0:
            self.result.add_pass(f"Git: {out.strip()} ✓")
        else:
            self.result.add_error("Git 未安装或不可用")
            return
        
        # 检查 remote
        code, out, err = self.run_cmd("git remote -v")
        if "origin" in out:
            self.result.add_pass("Git remote 'origin' 已配置 ✓")
        else:
            self.result.add_error("Git remote 'origin' 未配置")
        
        if "upstream" in out:
            self.result.add_pass("Git remote 'upstream' 已配置 ✓")
        else:
            self.result.add_warning("Git remote 'upstream' 未配置（可选）")
        
        # 检查当前分支
        code, out, err = self.run_cmd("git branch --show-current")
        if code == 0:
            branch = out.strip()
            if branch == "vega":
                self.result.add_pass(f"当前分支: {branch} ✓")
            else:
                self.result.add_warning(f"当前分支: {branch}（不是 vega）")
    
    def check_project_structure(self):
        """检查项目结构"""
        print("\n[3/8] 检查项目结构...")
        
        required_dirs = [
            "lyra", "tools", "config", "tests", 
            "docs", ".github/workflows"
        ]
        
        for dir_name in required_dirs:
            dir_path = self.repo_path / dir_name
            if dir_path.exists():
                self.result.add_pass(f"目录 {dir_name}/ 存在 ✓")
            else:
                self.result.add_error(f"缺少必需目录: {dir_name}/")
        
        required_files = [
            "main.py", "pyproject.toml", "pytest.ini",
            "config/build.toml", "config/features.toml", 
            "config/combinations.toml"
        ]
        
        for file_name in required_files:
            file_path = self.repo_path / file_name
            if file_path.exists():
                self.result.add_pass(f"文件 {file_name} 存在 ✓")
            else:
                self.result.add_error(f"缺少必需文件: {file_name}")
    
    def check_config_validity(self):
        """检查配置文件有效性"""
        print("\n[4/8] 检查配置完整性...")
        
        # 检查 TOML 文件语法
        config_files = [
            "config/build.toml",
            "config/features.toml",
            "config/combinations.toml",
            "config/profiles.toml"
        ]
        
        for config_file in config_files:
            config_path = self.repo_path / config_file
            if not config_path.exists():
                continue
            
            try:
                if tomli:
                    with open(config_path, "rb") as f:
                        data = tomli.load(f)
                    self.result.add_pass(f"{config_file} 语法有效 ✓")
                else:
                    self.result.add_warning(f"{config_file} 跳过（tomli 未安装）")
                    continue
                
                # 特殊检查
                if config_file == "config/features.toml":
                    self._check_features_toml(data)
                elif config_file == "config/combinations.toml":
                    self._check_combinations_toml(data)
                
            except Exception as e:
                self.result.add_error(f"{config_file} 解析失败: {e}")
    
    def _check_features_toml(self, data: Dict):
        """检查 features.toml 特定规则"""
        features = data.get("features", [])
        
        # 检查 BESC 状态
        besc_feature = next((f for f in features if f.get("id") == "besc"), None)
        if besc_feature:
            if besc_feature.get("skip") == True:
                self.result.add_pass("BESC skip=true（符合 DOL-X 策略）✓")
            else:
                self.result.add_warning("BESC skip=false（与文档不一致）")
            
            if "ucb" in besc_feature.get("conflicts_with", []):
                self.result.add_pass("BESC conflicts_with 包含 ucb ✓")
            else:
                self.result.add_warning("BESC conflicts_with 缺少 ucb")
        
        # 检查 bit 唯一性
        bits = [f.get("bit") for f in features if f.get("bit")]
        if len(bits) == len(set(bits)):
            self.result.add_pass(f"所有 feature bits 唯一（共 {len(bits)} 个）✓")
        else:
            self.result.add_error("存在重复的 feature bit 值")
    
    def _check_combinations_toml(self, data: Dict):
        """检查 combinations.toml 特定规则"""
        build_codes = data.get("build_codes", [])
        base_code = data.get("base_code")
        
        if build_codes:
            self.result.add_pass(f"build_codes 已定义（共 {len(build_codes)} 个）✓")
            
            # 检查是否包含 BESC bit (1)
            codes_with_besc = [int(c) for c in build_codes if int(c) & 1]
            if not codes_with_besc:
                self.result.add_pass("build_codes 不包含 BESC（bit 1）✓")
            else:
                self.result.add_error(f"build_codes 包含 BESC: {codes_with_besc}")
        
        if base_code:
            if str(base_code) in build_codes:
                self.result.add_pass(f"base_code {base_code} 在 build_codes 中 ✓")
            else:
                self.result.add_error(f"base_code {base_code} 不在 build_codes 中")
    
    def check_tests(self):
        """检查测试"""
        print("\n[5/8] 运行测试套件...")
        
        test_files = [
            "tests/test_build_matrix.py",
            "tests/test_mod_config.py",
            "tests/test_compatibility_registry.py"
        ]
        
        for test_file in test_files:
            if not (self.repo_path / test_file).exists():
                self.result.add_warning(f"测试文件 {test_file} 不存在")
                continue
        
        # 运行核心测试
        print("  运行核心配置测试...")
        code, out, err = self.run_cmd(
            "python -m pytest tests/test_build_matrix.py tests/test_mod_config.py -v --tb=short"
        )
        
        if code == 0:
            # 解析测试结果
            if "passed" in out:
                passed_count = out.count("PASSED")
                self.result.add_pass(f"核心测试通过（{passed_count} 个）✓")
        else:
            self.result.add_error("核心测试失败")
            if "FAILED" in out:
                failed_tests = [line for line in out.split('\n') if 'FAILED' in line]
                for test in failed_tests[:3]:  # 只显示前3个
                    self.result.add_error(f"  {test.strip()}")
    
    def check_build_system(self):
        """检查构建系统"""
        print("\n[6/8] 检查构建系统...")
        
        # 检查 lyra/ 核心文件
        core_files = [
            "lyra/__init__.py",
            "lyra/build.py",
            "lyra/combo.py",
            "lyra/config_loader.py"
        ]
        
        for file in core_files:
            if (self.repo_path / file).exists():
                self.result.add_pass(f"核心文件 {file} 存在 ✓")
            else:
                self.result.add_error(f"缺少核心文件: {file}")
        
        # 测试矩阵生成
        print("  测试矩阵生成...")
        code, out, err = self.run_cmd("python main.py matrix")
        if code == 0 and "57600" in out:
            self.result.add_pass("构建矩阵生成正常 ✓")
        else:
            self.result.add_error("构建矩阵生成失败")
    
    def check_ci_config(self):
        """检查 CI/CD 配置"""
        print("\n[7/8] 检查 CI/CD 配置...")
        
        workflows = [
            ".github/workflows/compatibility.yaml",
        ]
        
        for workflow in workflows:
            workflow_path = self.repo_path / workflow
            if workflow_path.exists():
                self.result.add_pass(f"工作流 {workflow} 存在 ✓")
                
                # 检查 YAML 语法
                try:
                    import yaml
                    with open(workflow_path) as f:
                        yaml.safe_load(f)
                    self.result.add_pass(f"{workflow} YAML 语法有效 ✓")
                except ImportError:
                    self.result.add_warning("yaml 包未安装，跳过 YAML 语法检查")
                except Exception as e:
                    self.result.add_error(f"{workflow} YAML 语法错误: {e}")
            else:
                self.result.add_warning(f"工作流 {workflow} 不存在")
    
    def check_documentation(self):
        """检查文档一致性"""
        print("\n[8/8] 检查文档一致性...")
        
        required_docs = [
            "README.md",
            "BUILD.md",
            "TESTING.md",
            "QUICK_REFERENCE.md",
            "MOD_MATRIX_RATIONALE.md",
            "UPSTREAM_FRIENDLY_STRATEGY.md"
        ]
        
        for doc in required_docs:
            doc_path = self.repo_path / doc
            if doc_path.exists():
                self.result.add_pass(f"文档 {doc} 存在 ✓")
                
                # 检查 BESC 引用
                if doc in ["QUICK_REFERENCE.md", "MOD_MATRIX_RATIONALE.md"]:
                    content = doc_path.read_text(encoding='utf-8')
                    if "skip=true" in content or "已禁用" in content or "不使用" in content:
                        self.result.add_pass(f"{doc} 正确说明 BESC 状态 ✓")
                    else:
                        self.result.add_warning(f"{doc} 未明确说明 BESC 状态")
            else:
                self.result.add_warning(f"文档 {doc} 不存在")
    
    def run_all_checks(self):
        """运行所有检查"""
        print("="*70)
        print("DOL-X 系统全面健康检查")
        print("="*70)
        print(f"项目路径: {self.repo_path}")
        
        self.check_python_env()
        self.check_git_config()
        self.check_project_structure()
        self.check_config_validity()
        self.check_tests()
        self.check_build_system()
        self.check_ci_config()
        self.check_documentation()
        
        return self.result.print_summary()


def main():
    """主函数"""
    # 修复 Windows 控制台编码问题
    if sys.platform == "win32":
        import codecs
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except Exception:
                pass
    
    checker = SystemHealthChecker()
    success = checker.run_all_checks()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
