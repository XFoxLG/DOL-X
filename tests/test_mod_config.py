"""
Phase 1: Mod 配置测试

验证：
- modloader_mods 配置正确性
- feature_ids 有效性
- key/cache_name 唯一性
- AU 面部扩展只注入 AU 版本
- 依赖声明完整性
"""
import pytest
from collections import Counter

from lyra.config_loader import get_config_loader, load_build_config


@pytest.mark.config
class TestModConfig:
    """Mod 配置测试"""

    def test_modloader_mods_exist(self):
        """验证 modloader_mods 配置存在"""
        build_config = load_build_config()
        
        assert build_config.modloader_mods is not None, (
            "modloader_mods 配置不存在"
        )
        assert len(build_config.modloader_mods) > 0, (
            "modloader_mods 配置为空"
        )

    def test_au_face_mod_exists(self):
        """验证 AU 面部扩展配置存在"""
        build_config = load_build_config()
        
        au_face_mod = None
        for mod in build_config.modloader_mods:
            if mod.key == "au_face" or "facial" in mod.asset_pattern.lower():
                au_face_mod = mod
                break
        
        assert au_face_mod is not None, (
            "AU 面部扩展配置不存在"
        )
        assert au_face_mod.name == "AU面部扩展", (
            f"AU 面部扩展名称错误: {au_face_mod.name}"
        )

    def test_au_face_feature_ids(self):
        """验证 AU 面部扩展绑定正确的 feature_ids"""
        build_config = load_build_config()
        
        au_face_mod = None
        for mod in build_config.modloader_mods:
            if mod.key == "au_face":
                au_face_mod = mod
                break
        
        assert au_face_mod is not None
        
        expected_features = {"au-f", "au-m", "au-a"}
        actual_features = set(au_face_mod.required_feature_ids)
        
        assert actual_features == expected_features, (
            f"AU 面部扩展 feature_ids 不匹配\n"
            f"期望: {expected_features}\n"
            f"实际: {actual_features}"
        )

    def test_all_feature_ids_valid(self):
        """验证所有 mod 的 feature_ids 都有效"""
        build_config = load_build_config()
        config_loader = get_config_loader()
        
        for mod in build_config.modloader_mods:
            for feature_id in mod.required_feature_ids:
                feature = config_loader.get_feature_by_id(feature_id)
                assert feature is not None, (
                    f"Mod {mod.key or mod.asset_pattern} 引用了不存在的 feature: {feature_id}"
                )

    def test_cache_name_uniqueness(self):
        """验证 cache_name 唯一性"""
        build_config = load_build_config()
        
        cache_names = [mod.cache_name for mod in build_config.modloader_mods]
        duplicates = [name for name, count in Counter(cache_names).items() if count > 1]
        
        assert len(duplicates) == 0, (
            f"发现重复的 cache_name: {duplicates}\n"
            f"这会导致 mod 文件互相覆盖"
        )

    def test_key_uniqueness_when_present(self):
        """验证 key 唯一性（当存在时）"""
        build_config = load_build_config()
        
        keys = [mod.key for mod in build_config.modloader_mods if mod.key]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        
        assert len(duplicates) == 0, (
            f"发现重复的 key: {duplicates}"
        )

    def test_github_repo_format(self):
        """验证 github_repo 格式正确"""
        build_config = load_build_config()
        
        for mod in build_config.modloader_mods:
            assert "/" in mod.github_repo, (
                f"Mod {mod.key or mod.asset_pattern} 的 github_repo 格式错误: {mod.github_repo}\n"
                f"应为 'owner/repo' 格式"
            )
            
            parts = mod.github_repo.split("/")
            assert len(parts) == 2, (
                f"Mod {mod.key or mod.asset_pattern} 的 github_repo 格式错误: {mod.github_repo}"
            )

    def test_asset_pattern_not_empty(self):
        """验证 asset_pattern 不为空"""
        build_config = load_build_config()
        
        for mod in build_config.modloader_mods:
            assert mod.asset_pattern, (
                f"Mod {mod.key} 的 asset_pattern 为空"
            )

    def test_modloader_mods_have_download_source(self):
        """验证每个 modloader mod 至少有一种下载来源"""
        build_config = load_build_config()

        for mod in build_config.modloader_mods:
            assert mod.download_url or (mod.github_repo and mod.asset_pattern), (
                f"Mod {mod.key or mod.asset_pattern} 缺少下载来源"
            )

    def test_modloader_enabled_flags_are_boolean(self):
        """验证 modloader mod 的 enabled 开关是布尔值"""
        build_config = load_build_config()

        for mod in build_config.modloader_mods:
            assert isinstance(mod.enabled, bool), (
                f"Mod {mod.key or mod.asset_pattern} 的 enabled 必须是布尔值"
            )

    def test_cheat_extension_mods_exist(self):
        """验证作弊/CSD 扩展 mod 配置存在并绑定到 cheat_csd"""
        build_config = load_build_config()

        expected_mods = {
            "bjx_word_unlock": ("言灵解放", True),
            "bjx_portable_word": ("随身言灵", True),
            "bccm": ("随时施法", True),
        }
        mods_by_key = {mod.key: mod for mod in build_config.modloader_mods}

        for key, (name, enabled) in expected_mods.items():
            mod = mods_by_key.get(key)
            assert mod is not None, f"缺少作弊/CSD 扩展 mod: {key}"
            assert mod.name == name, f"{key} 名称错误: {mod.name}"
            assert mod.feature_id == "cheat_csd", (
                f"{key} 应绑定到 cheat_csd，当前: {mod.feature_id}"
            )
            assert mod.enabled is enabled, f"{key} 默认启用状态错误"
            assert mod.download_url, f"{key} 应使用已确认的直链下载地址"

    def test_au_main_mods_exist(self):
        """验证 AU 主模组配置存在"""
        build_config = load_build_config()
        
        au_main_features = {"au-f", "au-m", "au-a"}
        found_features = set()
        
        for mod in build_config.modloader_mods:
            if mod.feature_id in au_main_features:
                found_features.add(mod.feature_id)
        
        assert found_features == au_main_features, (
            f"AU 主模组配置不完整\n"
            f"期望: {au_main_features}\n"
            f"实际: {found_features}"
        )

    def test_base_mods_config_exists(self):
        """验证 base_mods 配置存在"""
        build_config = load_build_config()
        
        assert build_config.base_mods is not None, (
            "base_mods 配置不存在"
        )
        assert len(build_config.base_mods) > 0, (
            "base_mods 配置为空"
        )

    def test_base_mods_keys_unique(self):
        """验证 base_mods key 唯一性"""
        build_config = load_build_config()
        
        keys = [mod.key for mod in build_config.base_mods]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        
        assert len(duplicates) == 0, (
            f"base_mods 中发现重复的 key: {duplicates}"
        )

    def test_base_mods_inject_mode_valid(self):
        """验证 base_mods inject 模式有效"""
        build_config = load_build_config()
        
        valid_modes = {"add", "replace"}
        
        for mod in build_config.base_mods:
            assert mod.inject in valid_modes, (
                f"base_mod {mod.key} 的 inject 模式无效: {mod.inject}\n"
                f"有效值: {valid_modes}"
            )

    def test_modloader_gui_replaces_slot_0(self):
        """验证 modloader_gui 替换 slot 0"""
        build_config = load_build_config()
        
        modloader_gui = None
        for mod in build_config.base_mods:
            if mod.key == "modloader_gui":
                modloader_gui = mod
                break
        
        assert modloader_gui is not None, (
            "modloader_gui 配置不存在"
        )
        assert modloader_gui.inject == "replace", (
            f"modloader_gui 应使用 replace 模式，当前: {modloader_gui.inject}"
        )
        assert modloader_gui.replace_slot == 0, (
            f"modloader_gui 应替换 slot 0，当前: {modloader_gui.replace_slot}"
        )

    def test_no_conflicting_feature_assignments(self):
        """验证同 feature 多 mod 时都使用显式 key 避免缓存冲突"""
        build_config = load_build_config()
        
        # 多个扩展 mod 可以绑定同一个 feature_id，由 build.toml 的顺序决定加载顺序。
        # 但它们必须有显式 key，否则 cache_name 会落到同一个 feature_id 导致互相覆盖。
        feature_to_mods = {}
        
        for mod in build_config.modloader_mods:
            if mod.feature_id:  # 单独 feature_id
                if mod.feature_id not in feature_to_mods:
                    feature_to_mods[mod.feature_id] = []
                feature_to_mods[mod.feature_id].append(mod)
        
        conflicts = {
            feature: [mod.key or mod.asset_pattern for mod in mods]
            for feature, mods in feature_to_mods.items()
            if len(mods) > 1 and any(not mod.key for mod in mods)
        }
        
        assert len(conflicts) == 0, (
            f"发现缺少显式 key 的共享 feature_id mod:\n" +
            "\n".join(f"  {feature}: {mods}" for feature, mods in conflicts.items())
        )
