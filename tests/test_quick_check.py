"""测试 quick_check.py 工具"""

import pytest
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.quick_check import QuickChecker


def test_quick_checker_init():
    """测试 QuickChecker 初始化"""
    project_root = Path(__file__).parent.parent
    checker = QuickChecker(project_root)
    
    assert checker.project_root == project_root
    assert checker.config_dir == project_root / "config"
    assert isinstance(checker.errors, list)
    assert isinstance(checker.warnings, list)


def test_config_consistency(tmp_path):
    """测试配置一致性检查"""
    project_root = Path(__file__).parent.parent
    checker = QuickChecker(project_root)
    
    # 应该能加载所有配置文件
    result = checker.check_config_consistency()
    assert result is True


def test_new_mods_detection(tmp_path):
    """测试新 mod 检测"""
    project_root = Path(__file__).parent.parent
    checker = QuickChecker(project_root)
    
    # 应该检测到 4 个新 mod
    result = checker.check_new_mods()
    assert result is True


def test_build_codes_check(tmp_path):
    """测试 build codes 验证"""
    project_root = Path(__file__).parent.parent
    checker = QuickChecker(project_root)
    
    # 应该能验证 build codes
    result = checker.check_build_codes()
    assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
