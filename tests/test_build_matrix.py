"""
Phase 1: 构建矩阵配置测试

验证：
- build_codes 只包含 4 个自用组合
- polyfill 已关闭
- 基础版 (57602) 不注入 AU 扩展
- AU 三版本 (58626/59650/61698) 注入 AU 扩展
- 所有版本都包含 more_love、custom_spellbook 与 cheatExtended/maplebirch
- 没有在线版相关配置
"""
import pytest
from pathlib import Path

from lyra.combo import CombinationCalculator
from lyra.config_loader import get_config_loader


@pytest.mark.config
class TestBuildMatrix:
    """构建矩阵配置测试"""

    def test_build_codes_count(self):
        """验证只构建 4 个自用组合"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        assert len(combinations_config.build_codes) == 4, (
            f"期望 4 个构建组合，实际 {len(combinations_config.build_codes)}"
        )

    def test_build_codes_values(self):
        """验证构建组合代码正确"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        expected_codes = {"57602", "58626", "59650", "61698"}
        actual_codes = set(combinations_config.build_codes)

        assert actual_codes == expected_codes, (
            f"构建组合不匹配\n"
            f"期望: {expected_codes}\n"
            f"实际: {actual_codes}"
        )

    def test_polyfill_disabled(self):
        """验证 polyfill 已关闭"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        assert not combinations_config.polyfill_enabled, (
            "polyfill 应该关闭，当前为启用状态"
        )

    def test_base_code_is_57602(self):
        """验证实验基础版代码为 57602"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        assert combinations_config.base_code == 57602, (
            f"基础版代码应为 57602，实际为 {combinations_config.base_code}"
        )

    def test_no_online_version(self):
        """验证没有在线版相关配置"""
        # 在线版通常代码为 0 或 1
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        build_codes_int = [int(code) for code in combinations_config.build_codes]
        
        assert 0 not in build_codes_int, "不应包含在线版 (code=0)"
        assert 1 not in build_codes_int, "不应包含在线版 (code=1)"

    def test_au_features_exist(self):
        """验证 AU 相关 feature 存在"""
        config_loader = get_config_loader()
        
        au_features = ["au-f", "au-m", "au-a"]
        for feature_id in au_features:
            feature = config_loader.get_feature_by_id(feature_id)
            assert feature is not None, f"AU feature {feature_id} 不存在"
            assert not feature.skip, f"AU feature {feature_id} 不应被跳过"

    def test_base_version_no_au(self):
        """验证基础版 (57602) 不包含 AU"""
        config_loader = get_config_loader()
        
        base_code = 57602
        au_features = ["au-f", "au-m", "au-a"]
        
        for feature_id in au_features:
            feature = config_loader.get_feature_by_id(feature_id)
            assert feature is not None
            
            # 基础版不应包含任何 AU feature
            assert not (base_code & feature.bit), (
                f"基础版 {base_code} 不应包含 AU feature {feature_id} (bit={feature.bit})"
            )

    def test_au_versions_have_au(self):
        """验证 AU 三版本包含对应 AU feature"""
        config_loader = get_config_loader()
        
        au_variants = [
            (58626, "au-f"),
            (59650, "au-m"),
            (61698, "au-a"),
        ]
        
        for code, feature_id in au_variants:
            feature = config_loader.get_feature_by_id(feature_id)
            assert feature is not None
            
            # AU 版本应包含对应 feature
            assert (code & feature.bit), (
                f"AU 版本 {code} 应包含 feature {feature_id} (bit={feature.bit})"
            )

    def test_all_versions_have_ucb(self):
        """验证所有版本都包含 UCB"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations
        
        ucb_feature = config_loader.get_feature_by_id("ucb")
        assert ucb_feature is not None, "UCB feature 不存在"
        
        for code_str in combinations_config.build_codes:
            code = int(code_str)
            assert (code & ucb_feature.bit), (
                f"版本 {code} 应包含 UCB (bit={ucb_feature.bit})"
            )

    def test_all_versions_have_cheat_or_csd(self):
        """验证所有版本都包含作弊或 CSD"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations
        
        cheat_feature = config_loader.get_feature_by_id("cheat_csd")
        assert cheat_feature is not None, "cheat_csd feature 不存在"
        
        for code_str in combinations_config.build_codes:
            code = int(code_str)
            assert (code & cheat_feature.bit), (
                f"版本 {code} 应包含 cheat_csd (bit={cheat_feature.bit})"
            )

    def test_all_versions_have_more_love_custom_spellbook_and_cheat_extended(self):
        """验证所有版本都包含主线 mod 与本实验候选 mod"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        required_features = [
            "more_love",
            "custom_spellbook",
            "cheat_extended_maplebirch",
        ]
        for feature_id in required_features:
            feature = config_loader.get_feature_by_id(feature_id)
            assert feature is not None, f"feature {feature_id} 不存在"

            for code_str in combinations_config.build_codes:
                code = int(code_str)
                assert (code & feature.bit), (
                    f"版本 {code} 应包含 {feature_id} (bit={feature.bit})"
                )

    def test_combination_calculator_consistency(self):
        """验证 CombinationCalculator 与配置一致"""
        calculator = CombinationCalculator()
        combinations = calculator.calculate(include_polyfill=False)
        
        # 应该只生成 4 个组合
        assert len(combinations) == 4, (
            f"CombinationCalculator 应生成 4 个组合，实际 {len(combinations)}"
        )
        
        # 验证生成的代码与配置一致
        config_loader = get_config_loader()
        expected_codes = set(int(code) for code in config_loader.combinations.build_codes)
        actual_codes = set(combo.code for combo in combinations)
        
        assert actual_codes == expected_codes, (
            f"CombinationCalculator 生成的代码与配置不一致\n"
            f"期望: {expected_codes}\n"
            f"实际: {actual_codes}"
        )
