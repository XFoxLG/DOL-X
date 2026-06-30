"""
Phase 1: 构建矩阵配置测试

验证：
- build_codes 只包含 4 个稳定自用组合
- polyfill 已关闭
- 基础版 (5218560) 不注入 AU 扩展
- AU 三版本 (5219584/5220608/5222656) 注入 AU 扩展
- 所有版本都包含 more_love、cheatExtended+maplebirch、custom_hair、mae_picvary、maplebirch_expansion、guide_to_me、npc_social_icon
- BunnyTransformation 不进入当前诊断矩阵
- NeoUI Patch 只进入 AU-F 对比包 (7316736)
- 没有在线版相关配置
"""
import pytest

from lyra.combo import CombinationCalculator
from lyra.config import ModCode
from lyra.config_loader import get_config_loader


@pytest.mark.config
class TestBuildMatrix:
    """构建矩阵配置测试"""

    def test_build_codes_count(self):
        """验证当前诊断矩阵为 5 个组合（含 AU-F + NeoUI 对比包）"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        assert len(combinations_config.build_codes) == 5, (
            f"期望 5 个构建组合，实际 {len(combinations_config.build_codes)}"
        )

    def test_build_codes_values(self):
        """验证构建组合代码正确（含 NeoUI 对比包 7316736，禁用 BunnyTransformation）"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        expected_codes = {"5218560", "5219584", "7316736", "5220608", "5222656"}
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

    def test_base_code_is_5218560(self):
        """验证诊断基础版代码为 5218560（禁用 NeoUI Patch 与 BunnyTransformation）"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        assert combinations_config.base_code == 5218560, (
            f"基础版代码应为 5218560，实际为 {combinations_config.base_code}"
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
        """验证基础版 (5218560) 不包含 AU"""
        config_loader = get_config_loader()

        base_code = 5218560
        au_features = ["au-f", "au-m", "au-a"]
        
        for feature_id in au_features:
            feature = config_loader.get_feature_by_id(feature_id)
            assert feature is not None
            
            # 基础版不应包含任何 AU feature
            assert not (base_code & feature.bit), (
                f"基础版 {base_code} 不应包含 AU feature {feature_id} (bit={feature.bit})"
            )

    def test_base_version_no_besc(self):
        """验证基础版不应包含 BESC (bit=1)"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations
        
        base_code = combinations_config.base_code
        besc_feature = config_loader.get_feature_by_id("besc")
        assert besc_feature is not None
        
        assert not (base_code & besc_feature.bit), (
            f"基础版 {base_code} 不应包含 BESC (bit={besc_feature.bit})"
        )

    def test_au_versions_have_au(self):
        """验证 AU 三版本包含对应 AU feature"""
        config_loader = get_config_loader()
        
        au_variants = [
            (5219584, "au-f"),
            (5220608, "au-m"),
            (5222656, "au-a"),
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

    def test_ucb_no_longer_depends_on_besc(self):
        """验证 UCB 已按当前稳定矩阵改为独立美化资源。"""
        config_loader = get_config_loader()
        ucb_feature = config_loader.get_feature_by_id("ucb")

        assert ucb_feature is not None, "UCB feature 不存在"
        assert "besc" not in ucb_feature.depends_on, (
            "UCB 已按项目决策独立于 BESC；features.toml 不应继续声明 besc 依赖"
        )

    def test_explicit_build_codes_are_self_consistent(self):
        """验证当前显式稳定构建代码与 feature 图自洽。"""
        config_loader = get_config_loader()
        features = config_loader.features
        feature_by_id = {feature.id: feature for feature in features}
        known_bits = 0
        for feature in features:
            known_bits |= feature.bit

        findings = []
        for code_str in config_loader.combinations.build_codes:
            code = int(code_str)
            enabled_features = [feature for feature in features if code & feature.bit]
            enabled_ids = {feature.id for feature in enabled_features}

            unknown_bits = code & ~known_bits
            if unknown_bits:
                findings.append(
                    {
                        "code": code,
                        "kind": "unknown_bits",
                        "unknown_bits": unknown_bits,
                    }
                )

            for feature in features:
                if feature.required and feature.id not in enabled_ids:
                    findings.append(
                        {
                            "code": code,
                            "kind": "missing_required",
                            "feature": feature.id,
                        }
                    )

            for feature in enabled_features:
                for dep_id in feature.depends_on:
                    dep_feature = feature_by_id.get(dep_id)
                    if dep_feature is None:
                        findings.append(
                            {
                                "code": code,
                                "kind": "unknown_dependency",
                                "feature": feature.id,
                                "dependency": dep_id,
                            }
                        )
                    elif dep_feature.id not in enabled_ids:
                        findings.append(
                            {
                                "code": code,
                                "kind": "missing_dependency",
                                "feature": feature.id,
                                "dependency": dep_id,
                            }
                        )

                for conflict_id in feature.conflicts_with:
                    conflict_feature = feature_by_id.get(conflict_id)
                    if conflict_feature is None:
                        findings.append(
                            {
                                "code": code,
                                "kind": "unknown_conflict",
                                "feature": feature.id,
                                "conflict": conflict_id,
                            }
                        )
                    elif conflict_feature.id in enabled_ids:
                        findings.append(
                            {
                                "code": code,
                                "kind": "conflict_present",
                                "feature": feature.id,
                                "conflict": conflict_id,
                            }
                        )

        assert findings == []

    def test_all_versions_have_cheat_extended_maplebirch(self):
        """验证所有版本都包含 cheatExtended+maplebirch"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations
        
        cheat_extended_feature = config_loader.get_feature_by_id("cheat_extended_maplebirch")
        assert cheat_extended_feature is not None, "cheat_extended_maplebirch feature 不存在"
        
        for code_str in combinations_config.build_codes:
            code = int(code_str)
            assert (code & cheat_extended_feature.bit), (
                f"版本 {code} 应包含 cheat_extended_maplebirch (bit={cheat_extended_feature.bit})"
            )

    def test_all_versions_have_required_features(self):
        """验证所有默认版本都包含稳定主线 mod（移除 custom_spellbook）。"""
        config_loader = get_config_loader()
        combinations_config = config_loader.combinations

        required_features = [
            "more_love",
            "custom_hair",
            "mae_picvary",
            "maplebirch_expansion",
            "guide_to_me",
            "npc_social_icon",
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
        
        # 当前诊断矩阵为 5 个组合（含 AU-F + NeoUI 对比包）
        assert len(combinations) == 5, (
            f"CombinationCalculator 应生成 5 个组合，实际 {len(combinations)}"
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

    def test_build_codes_have_unique_output_suffixes(self):
        """验证每个 build code 都会生成唯一文件名后缀，避免产物互相覆盖。"""
        config_loader = get_config_loader()
        suffixes = {
            code_str: ModCode(int(code_str)).get_suffix()
            for code_str in config_loader.combinations.build_codes
        }

        assert len(set(suffixes.values())) == len(suffixes), (
            f"构建产物文件名后缀存在重复，可能导致 output 中互相覆盖: {suffixes}"
        )
        assert "neoui-patch" in suffixes["7316736"], (
            f"NeoUI 对比包 7316736 的文件名后缀应包含 neoui-patch，实际为 {suffixes['7316736']}"
        )
        assert "guide-to-me" in suffixes["5218560"], (
            f"当前主线包文件名后缀应包含 guide-to-me，实际为 {suffixes['5218560']}"
        )
        assert "npc-social-icon" in suffixes["5218560"], (
            f"当前主线包文件名后缀应包含 npc-social-icon，实际为 {suffixes['5218560']}"
        )
