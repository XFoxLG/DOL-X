"""
预处理模块

处理APK反编译、mod注入等预处理任务。
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .paths import BuildPaths
from .version import VersionRegistry
from .config_loader import load_build_config
from .utils import (
    run_command,
    extract_zip,
    create_zip,
    copy_directory,
    safe_remove,
)

logger = logging.getLogger(__name__)


class ApkProcessor:
    """
    APK 处理器

    负责 APK 的反编译、配置修改等操作。
    """

    def __init__(self, paths: BuildPaths):
        """
        初始化 APK 处理器

        Args:
            paths: 路径管理器
        """
        self.paths = paths
        self.config = load_build_config()

    def decompile(self, apk_path: Path, dest_dir: Path) -> Path:
        """
        反编译 APK

        Args:
            apk_path: APK 文件路径
            dest_dir: 目标目录

        Returns:
            解压后的目录路径
        """
        logger.info(f"反编译 APK: {apk_path}")

        if dest_dir.exists():
            safe_remove(dest_dir)

        apktool_path = self.paths.apktool_path
        run_command(
            [
                "java",
                "-jar",
                str(apktool_path),
                "d",
                str(apk_path),
                "-o",
                str(dest_dir),
            ]
        )

        return dest_dir

    def apply_replacements(self, apk_dir: Path):
        """
        应用配置中的替换规则

        Args:
            apk_dir: 已解包的 APK 目录
        """
        logger.info("应用 APK 配置替换...")

        # 按文件分组替换规则
        file_replacements: dict[str, list] = {}
        for replacement in self.config.apk_replacements:
            if replacement.file not in file_replacements:
                file_replacements[replacement.file] = []
            file_replacements[replacement.file].append(replacement)

        # 应用替换规则
        for file_path, replacements in file_replacements.items():
            full_path = apk_dir / file_path
            if not full_path.exists():
                logger.warning(f"  文件不存在: {file_path}")
                continue

            content = full_path.read_text(encoding="utf-8")
            modified = False

            for r in replacements:
                if r.pattern in content:
                    content = content.replace(r.pattern, r.replacement)
                    modified = True
                    logger.debug(f"  替换: {r.pattern} -> {r.replacement}")

            if modified:
                full_path.write_text(content, encoding="utf-8")
                logger.info(f"  已修改: {file_path}")


class ModInjector:
    """
    Mod 注入器

    向 HTML 文件注入 mod。
    """

    def __init__(self, paths: BuildPaths):
        """
        初始化 Mod 注入器

        Args:
            paths: 路径管理器
        """
        self.paths = paths

    def add_mods(self, html_path: Path, mod_paths: list[Path]):
        """
        向 HTML 文件添加 mod

        Args:
            html_path: HTML 文件路径
            mod_paths: mod 文件路径列表（按加载顺序）
        """
        import base64

        # 过滤存在的 mod 文件
        existing_mods = [p for p in mod_paths if p and p.exists()]

        if not existing_mods:
            logger.warning("没有可添加的 mod 文件")
            return

        logger.info(f"向 {html_path.name} 添加 {len(existing_mods)} 个 mod...")

        # 读取 HTML 内容
        content = html_path.read_text(encoding="utf-8")

        # 提取现有的 modDataValueZipList
        pattern = r"window\.modDataValueZipList\s*=\s*(\[.*?\]);"
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            logger.error("HTML 文件中未找到 modDataValueZipList")
            return

        existing_list = json.loads(match.group(1))

        # 加载新的 mod 文件
        for mod_path in existing_mods:
            with open(mod_path, "rb") as f:
                base64_data = base64.b64encode(f.read()).decode("utf-8")
                existing_list.append(base64_data)
                logger.debug(f"  添加: {mod_path.name}")

        # 替换 modDataValueZipList
        new_content = re.sub(
            pattern,
            f"window.modDataValueZipList = {json.dumps(existing_list)};",
            content,
            flags=re.DOTALL,
        )

        html_path.write_text(new_content, encoding="utf-8")
        logger.info(f"  完成: 共 {len(existing_list)} 个 mod")

    def replace_mod(self, html_path: Path, mod_id: int, mod_path: Path):
        """
        替换 HTML 文件中指定 ID 的 mod

        Args:
            html_path: HTML 文件路径
            mod_id: 要替换的 mod ID（从 0 开始）
            mod_path: 新 mod 文件路径
        """
        import base64

        if not mod_path.exists():
            logger.warning(f"mod 文件不存在: {mod_path}")
            return

        logger.info(f"替换 {html_path.name} 的 mod ID {mod_id}")

        # 读取 HTML 内容
        content = html_path.read_text(encoding="utf-8")

        # 提取现有的 modDataValueZipList
        pattern = r"window\.modDataValueZipList\s*=\s*(\[.*?\]);"
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            logger.error("HTML 文件中未找到 modDataValueZipList")
            return

        existing_list = json.loads(match.group(1))

        if mod_id < 0 or mod_id >= len(existing_list):
            logger.error(f"无效的 mod ID: {mod_id}，有效范围: 0-{len(existing_list)-1}")
            return

        # 加载新的 mod 文件
        with open(mod_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")
            existing_list[mod_id] = base64_data

        # 替换 modDataValueZipList
        new_content = re.sub(
            pattern,
            f"window.modDataValueZipList = {json.dumps(existing_list)};",
            content,
            flags=re.DOTALL,
        )

        html_path.write_text(new_content, encoding="utf-8")

    def patch_modloader_code(self, html_path: Path):
        """
        修改 HTML 文件中 ModLoader 的 JavaScript 代码

        Args:
            html_path: HTML 文件路径
        """
        if not html_path.exists():
            logger.warning(f"HTML 文件不存在: {html_path}")
            return

        try:
            content = html_path.read_text(encoding="utf-8")

            # 查找并修改 ModLoader 代码
            # 将 modReadCache.clone() 后添加过滤逻辑
            old_pattern = "const remodloader = modReadCache.clone();"
            new_pattern = """const remodloader = modReadCache.clone();
            remodloader.filterItems((mod) => mod.bootJson && mod.bootJson.name !== 'ModLoader');"""

            if old_pattern in content:
                content = content.replace(old_pattern, new_pattern)
                html_path.write_text(content, encoding="utf-8")
                logger.info(f"  已修补 ModLoader 代码: {html_path.name}")
            else:
                logger.debug(f"  未找到需要修补的代码: {html_path.name}")

        except Exception as e:
            logger.error(f"修补 ModLoader 代码失败: {e}")


class GamePreparer:
    """
    游戏资源预处理器

    完成从下载到生成基包的完整流程。
    """

    def __init__(self, paths: BuildPaths):
        """
        初始化预处理器

        Args:
            paths: 路径管理器
        """
        self.paths = paths
        self.apk_processor = ApkProcessor(paths)
        self.mod_injector = ModInjector(paths)
        self.registry = VersionRegistry()

    def prepare_all(
        self,
        downloaded_files: dict[str, Path],
        extra_mods: dict[str, Path],
    ) -> VersionRegistry:
        """
        完整的预处理流程

        Args:
            downloaded_files: 下载的游戏文件
            extra_mods: 额外的 mod 文件

        Returns:
            版本信息注册表
        """
        logger.info("========== 开始游戏预处理 ==========")

        # 准备 ZIP 基包
        self._prepare_zip_base(downloaded_files, extra_mods)

        # 准备 APK
        self._prepare_apk(downloaded_files, extra_mods)

        logger.info("========== 游戏预处理完成 ==========")
        return self.registry

    def _prepare_zip_base(
        self,
        downloaded_files: dict[str, Path],
        extra_mods: dict[str, Path],
    ):
        """准备 ZIP 基包"""
        # 处理普通版
        if "zip" in downloaded_files:
            self._process_zip_version(
                downloaded_files["zip"],
                downloaded_files.get("image_pack"),
                extra_mods,
                polyfill=False,
            )

        # 处理 polyfill 版
        if "polyfill_zip" in downloaded_files:
            self._process_zip_version(
                downloaded_files["polyfill_zip"],
                downloaded_files.get("image_pack"),
                extra_mods,
                polyfill=True,
            )

    def _process_zip_version(
        self,
        zip_path: Path,
        image_pack_path: Optional[Path],
        extra_mods: dict[str, Path],
        polyfill: bool,
    ):
        """处理单个 ZIP 版本"""
        suffix = "-polyfill" if polyfill else ""
        logger.info(f"处理 ZIP{suffix}...")

        # 解压到临时目录
        extract_dir = self.paths.prepare_dir / f"zip{suffix}"
        extract_zip(zip_path, extract_dir)

        # 合并图片包
        if image_pack_path:
            self._merge_image_pack(image_pack_path, extract_dir)

        # 注入 mod
        html_files = list(extract_dir.glob("*.html"))
        if html_files:
            html_path = html_files[0]

            # 替换 ModLoader 为 ModLoaderGui
            if "modloader_gui" in extra_mods:
                self.mod_injector.replace_mod(html_path, 0, extra_mods["modloader_gui"])

            # 添加其他 mod
            mods_to_add = []
            for key in ["i18n", "cheat", "csd"]:
                if key in extra_mods:
                    mods_to_add.append(extra_mods[key])
                elif key == "i18n" and "i18n" in extra_mods:
                    mods_to_add.append(extra_mods["i18n"])

            # 添加 i18n (从下载的文件)
            if "i18n" in extra_mods:
                # 已在上面处理
                pass

            if mods_to_add:
                self.mod_injector.add_mods(html_path, mods_to_add)

            # 修补 ModLoader 代码
            self.mod_injector.patch_modloader_code(html_path)

        # 创建基包
        base_zip = self.paths.get_base_zip(polyfill)
        create_zip(extract_dir, base_zip)
        logger.info(f"  基包已创建: {base_zip}")

    def _prepare_apk(
        self,
        downloaded_files: dict[str, Path],
        extra_mods: dict[str, Path],
    ):
        """准备 APK"""
        if "apk" not in downloaded_files:
            logger.warning("未找到 APK 文件")
            return

        apk_path = downloaded_files["apk"]

        # 处理普通版和 polyfill 版 APK
        for polyfill in [False, True]:
            self._process_apk_version(
                apk_path,
                downloaded_files.get("image_pack"),
                extra_mods,
                polyfill=polyfill,
            )

    def _process_apk_version(
        self,
        apk_path: Path,
        image_pack_path: Optional[Path],
        extra_mods: dict[str, Path],
        polyfill: bool,
    ):
        """处理单个 APK 版本"""
        suffix = "-polyfill" if polyfill else ""
        logger.info(f"处理 APK{suffix}...")

        # 反编译
        apk_dir = self.paths.get_apk_dir(polyfill)
        self.apk_processor.decompile(apk_path, apk_dir)

        # 应用替换规则
        self.apk_processor.apply_replacements(apk_dir)

        # 合并图片包
        if image_pack_path:
            img_dest = apk_dir / "assets" / "www" / "img"
            self._merge_image_pack(image_pack_path, img_dest.parent)

        # 注入 mod
        html_path = apk_dir / "assets" / "www" / "index.html"
        if html_path.exists():
            # 替换 ModLoader 为 ModLoaderGui
            if "modloader_gui" in extra_mods:
                self.mod_injector.replace_mod(html_path, 0, extra_mods["modloader_gui"])

            # 添加其他 mod
            mods_to_add = []
            for key in ["i18n", "cheat", "csd"]:
                if key in extra_mods:
                    mods_to_add.append(extra_mods[key])

            if mods_to_add:
                self.mod_injector.add_mods(html_path, mods_to_add)

            # 修补 ModLoader 代码
            self.mod_injector.patch_modloader_code(html_path)

        logger.info(f"  APK 目录已准备: {apk_dir}")

    def _merge_image_pack(self, image_pack_path: Path, target_dir: Path):
        """合并图片包"""
        # 解压图片包
        temp_dir = self.paths.temp_dir / "image_pack_temp"
        extract_zip(image_pack_path, temp_dir)

        # 查找 img 目录
        img_src = None
        if (temp_dir / "img").exists():
            img_src = temp_dir / "img"
        else:
            for subdir in temp_dir.iterdir():
                if subdir.is_dir() and (subdir / "img").exists():
                    img_src = subdir / "img"
                    break

        if img_src:
            img_dest = target_dir / "img"
            copy_directory(img_src, img_dest)
            logger.debug(f"  合并图片包: {img_src} -> {img_dest}")

        # 清理
        safe_remove(temp_dir)
