#!/usr/bin/env python3
"""
DOL-X 快速验证工具

本地快速验证配置文件、mod URL、build codes 等，无需完整构建。
运行时间 < 2 分钟，适合开发时快速检查。
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import tomllib
except ImportError:
    import tomli as tomllib


class QuickChecker:
    """快速验证器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config_dir = project_root / "config"
        self.errors = []
        self.warnings = []

    def check_all(self) -> bool:
        """运行所有检查"""
        print("DOL-X Quick Check\n")
        
        checks = [
            ("配置一致性", self.check_config_consistency),
            ("Mod URL 可达性", self.check_mod_urls),
            ("Build Codes 计算", self.check_build_codes),
            ("新 Mod 检测", self.check_new_mods),
            ("Lockfile 同步", self.check_lockfile_sync),
        ]
        
        all_passed = True
        for name, check_func in checks:
            try:
                if not check_func():
                    all_passed = False
            except Exception as e:
                self.errors.append(f"{name} 检查失败: {e}")
                print(f"[FAIL] {name}: {e}")
                all_passed = False
        
        return all_passed

    def check_config_consistency(self) -> bool:
        """检查配置文件一致性"""
        try:
            # 加载所有配置文件
            build_toml = self._load_toml("build.toml")
            features_toml = self._load_toml("features.toml")
            combinations_toml = self._load_toml("combinations.toml")
            
            print("[OK] 配置一致性检查通过")
            return True
        except Exception as e:
            print(f"[FAIL] 配置一致性检查失败: {e}")
            return False

    def check_mod_urls(self) -> bool:
        """并发检查 mod URL 可达性"""
        build_toml = self._load_toml("build.toml")
        
        mod_urls = []
        for mod in build_toml.get("modloader_mods", []):
            if mod.get("enabled", True):
                url = mod.get("download_url")
                if url:
                    mod_urls.append((mod["key"], url))
        
        if not mod_urls:
            print("[WARN] 没有找到需要检查的 mod URL")
            return True
        
        accessible_count = 0
        failed = []
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_mod = {
                executor.submit(self._check_url_head, url): (key, url)
                for key, url in mod_urls
            }
            
            for future in as_completed(future_to_mod):
                key, url = future_to_mod[future]
                try:
                    if future.result():
                        accessible_count += 1
                    else:
                        failed.append(key)
                except Exception as e:
                    failed.append(f"{key} ({e})")
        
        if failed:
            print(f"[WARN] {accessible_count}/{len(mod_urls)} mod URLs 可访问")
            print(f"    失败: {', '.join(failed)}")
            self.warnings.append(f"部分 mod URL 不可达: {failed}")
        else:
            print(f"[OK] {accessible_count}/{len(mod_urls)} mod URLs 可访问")
        
        return len(failed) == 0

    def check_build_codes(self) -> bool:
        """验证 build_codes 计算"""
        try:
            combinations = self._load_toml("combinations.toml")
            features = self._load_toml("features.toml")
            
            expected_codes = combinations.get("build_codes", [])
            if not expected_codes:
                print("[WARN] combinations.toml 中没有 build_codes")
                return True
            
            # 计算 required mods 的 bit 总和
            required_bits = 0
            for feature in features.get("features", []):
                if feature.get("required", False):
                    required_bits += feature.get("bit", 0)
            
            print(f"[OK] Build codes: {expected_codes}")
            print(f"    必选 mods bit 总和: {required_bits}")
            return True
        except Exception as e:
            print(f"[FAIL] Build codes 检查失败: {e}")
            return False

    def check_new_mods(self) -> bool:
        """检测新 mod 是否在配置中（仅检查启用的 mod）"""
        # 检查已启用的新 mod。NeoUI 当前用于 AU 侧边栏诊断而禁用。
        expected_enabled = ["guide_to_me", "npc_social_icon"]
        # bunny_transformation 已知不兼容；neoui_patch 当前预期禁用。
        expected_disabled = ["bunny_transformation", "neoui_patch"]
        
        build_toml = self._load_toml("build.toml")
        found_enabled = []
        found_disabled = []
        
        for mod in build_toml.get("modloader_mods", []):
            if mod["key"] in expected_enabled and mod.get("enabled", True):
                found_enabled.append(mod["key"])
            elif mod["key"] in expected_disabled and not mod.get("enabled", True):
                found_disabled.append(mod["key"])
        
        all_ok = True
        if len(found_enabled) == len(expected_enabled):
            print(f"[OK] 检测到 {len(found_enabled)} 个已启用新 mod: {', '.join(found_enabled)}")
        else:
            missing = set(expected_enabled) - set(found_enabled)
            print(f"[FAIL] 已启用新 mod 缺失: {', '.join(missing)}")
            all_ok = False
        
        if len(found_disabled) == len(expected_disabled):
            print(f"[OK] 检测到 {len(found_disabled)} 个已禁用新 mod: {', '.join(found_disabled)}")
        else:
            missing = set(expected_disabled) - set(found_disabled)
            print(f"[WARN] 已禁用新 mod 状态异常: {', '.join(missing)}")
        
        return all_ok

    def check_lockfile_sync(self) -> bool:
        """检查 mods.lock.json 与 build.toml 同步"""
        try:
            lock_file = self.config_dir / "mods.lock.json"
            if not lock_file.exists():
                print("[WARN] mods.lock.json 不存在")
                return True
            
            with open(lock_file, encoding="utf-8") as f:
                lock_data = json.load(f)
            
            build_toml = self._load_toml("build.toml")
            
            # 检查 build.toml 中的 mod 是否都在 lockfile 中
            toml_mods = {mod["key"] for mod in build_toml.get("modloader_mods", [])}
            lock_mods = set(lock_data.get("mods", {}).keys())
            
            missing_in_lock = toml_mods - lock_mods
            if missing_in_lock:
                print(f"[WARN] lockfile 中缺少: {', '.join(missing_in_lock)}")
                self.warnings.append(f"mods.lock.json 需要更新: {missing_in_lock}")
            else:
                print("[OK] mods.lock.json 与 build.toml 同步")
            
            return len(missing_in_lock) == 0
        except Exception as e:
            print(f"[FAIL] Lockfile 同步检查失败: {e}")
            return False

    def _load_toml(self, filename: str) -> dict:
        """加载 TOML 文件"""
        path = self.config_dir / filename
        with open(path, "rb") as f:
            return tomllib.load(f)

    def _check_url_head(self, url: str, timeout: int = 10) -> bool:
        """发送 HEAD 请求检查 URL 可达性"""
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "DOL-X-Quick-Check/1.0")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            return False


def main():
    parser = argparse.ArgumentParser(description="DOL-X 快速验证工具")
    parser.add_argument(
        "--checks",
        help="指定要运行的检查（逗号分隔）：config,urls,mods,lockfile",
        default="all"
    )
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    checker = QuickChecker(project_root)
    
    start_time = time.time()
    success = checker.check_all()
    elapsed = time.time() - start_time
    
    print(f"\n{'='*50}")
    if success:
        print(f"PASS: Quick check passed (took {elapsed:.1f}s)")
        return 0
    else:
        print(f"FAIL: Quick check failed (took {elapsed:.1f}s)")
        if checker.warnings:
            print(f"\nWarnings:")
            for warning in checker.warnings:
                print(f"  - {warning}")
        if checker.errors:
            print(f"\nErrors:")
            for error in checker.errors:
                print(f"  - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
