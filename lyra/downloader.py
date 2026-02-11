"""
资源下载模块

从各种来源下载构建所需的资源文件。
"""

import logging
from pathlib import Path
from typing import Optional

import requests

from .paths import BuildPaths
from .version import LyraVersion, VersionInfo, VersionRegistry
from .config_loader import load_build_config
from .utils import download_file, extract_zip

logger = logging.getLogger(__name__)


class Downloader:
    """
    资源下载器

    负责下载构建所需的各种资源文件。
    """

    def __init__(self, paths: BuildPaths):
        """
        初始化下载器

        Args:
            paths: 路径管理器
        """
        self.paths = paths
        self.registry = VersionRegistry()

    def download_from_chs_repo(
        self, version: Optional[LyraVersion] = None
    ) -> dict[str, Path]:
        """
        从汉化仓库下载资源文件

        Args:
            version: 版本信息（可选，为None时使用latest release）

        Returns:
            下载文件的路径字典 {类型: 路径}
        """
        logger.info("========== 从汉化仓库下载资源 ==========")

        build_config = load_build_config()
        chs_repo = build_config.chs_repo_url

        # 确定要获取的release tag
        if version:
            tag = f"v{version.dol_ver}-chs-{version.chs_ver}"
            release_data = self._get_github_release(chs_repo, tag)
        else:
            release_data = self._get_github_release(chs_repo, "latest")

        if not release_data:
            raise RuntimeError("无法获取汉化仓库release信息")

        # 记录版本信息
        release_tag = release_data.get("tag_name", "unknown")
        self.registry.add(
            VersionInfo(
                name="汉化仓库",
                version=release_tag,
                source=chs_repo,
            )
        )
        logger.info(f"汉化仓库版本: {release_tag}")

        # 定义需要下载的文件模式
        required_patterns = [
            (
                "apk",
                lambda name: name.endswith(".APK") and "polyfill" not in name.lower(),
            ),
            (
                "zip",
                lambda name: name.endswith(".zip")
                and "ModLoader" in name
                and "polyfill" not in name.lower(),
            ),
            (
                "polyfill_zip",
                lambda name: name.endswith(".zip") and "polyfill" in name.lower(),
            ),
            (
                "image_pack",
                lambda name: "GameOriginalImagePack" in name and name.endswith(".zip"),
            ),
            ("i18n", lambda name: "ModI18N" in name and name.endswith(".zip")),
        ]

        # 从release assets中筛选需要的文件
        assets_to_download = {}
        for asset in release_data.get("assets", []):
            asset_name = asset.get("name", "")
            for key, matcher in required_patterns:
                if key not in assets_to_download and matcher(asset_name):
                    assets_to_download[key] = {
                        "name": asset_name,
                        "url": asset.get("browser_download_url"),
                    }
                    break

        # 检查是否找到所有必需文件
        missing = [key for key, _ in required_patterns if key not in assets_to_download]
        if missing:
            logger.warning(f"未找到以下资源: {missing}")

        # 下载文件
        downloaded_files = {}
        download_dir = self.paths.base_dir
        download_dir.mkdir(parents=True, exist_ok=True)

        for key, asset_info in assets_to_download.items():
            dest_path = download_dir / asset_info["name"]
            download_file(asset_info["url"], dest_path)
            downloaded_files[key] = dest_path
            logger.info(f"  下载完成: {asset_info['name']}")

        return downloaded_files

    def download_extra_mods(self) -> dict[str, Path]:
        """
        下载额外的mod文件

        从 build.toml 的 base_mods 配置中读取需要下载的 mod，
        下载配置了 github_repo 的 mod 的最新 .mod.zip 文件。

        Returns:
            下载的mod文件路径字典
        """
        logger.info("========== 下载额外mod ==========")

        build_config = load_build_config()
        downloaded_mods = {}
        download_dir = self.paths.base_dir / "mods"
        download_dir.mkdir(parents=True, exist_ok=True)

        for mod in build_config.base_mods:
            if not mod.github_repo:
                continue

            try:
                release_data = self._get_github_release(mod.github_repo, "latest")
                if not release_data:
                    logger.warning(f"无法获取 {mod.github_repo} 的release信息")
                    continue

                release_tag = release_data.get("tag_name", "unknown")

                # 查找mod.zip文件
                for asset in release_data.get("assets", []):
                    asset_name = asset.get("name", "")
                    if asset_name.endswith(".mod.zip"):
                        dest_path = download_dir / asset_name
                        download_file(asset.get("browser_download_url"), dest_path)
                        downloaded_mods[mod.key] = dest_path

                        # 记录版本信息
                        self.registry.add(
                            VersionInfo(
                                name=mod.key,
                                version=release_tag,
                                source=mod.github_repo,
                                filename=asset_name,
                            )
                        )
                        logger.info(f"  {mod.key}: {asset_name} ({release_tag})")
                        break

            except Exception as e:
                logger.error(f"下载 {mod.key} 失败: {e}")

        return downloaded_mods

    def download_apktool(self) -> Path:
        """下载apktool"""
        from .config_loader import load_build_config

        config = load_build_config()

        dest_path = self.paths.apktool_path
        if not dest_path.exists():
            download_file(config.apktool_url, dest_path)
            logger.info(f"apktool 下载完成: {dest_path}")
        return dest_path

    def download_apksign(self) -> Path:
        """下载uber-apk-signer"""
        from .config_loader import load_build_config

        config = load_build_config()

        dest_path = self.paths.apksign_path
        if not dest_path.exists():
            download_file(config.uber_apk_signer_url, dest_path)
            logger.info(f"uber-apk-signer 下载完成: {dest_path}")
        return dest_path

    def _get_github_release(self, repo: str, tag: str) -> Optional[dict]:
        """
        获取GitHub release信息

        Args:
            repo: 仓库名称，格式为 "owner/repo"
            tag: release tag，或 "latest" 获取最新版本

        Returns:
            release数据字典，失败返回None
        """
        try:
            if tag == "latest":
                api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            else:
                api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"

            logger.debug(f"获取 GitHub Release: {api_url}")
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"获取 GitHub release 失败 ({repo}): {e}")
            return None


class GamePreparer:
    """
    游戏资源预处理器

    解压和处理下载的游戏资源文件。
    """

    def __init__(self, paths: BuildPaths):
        """
        初始化预处理器

        Args:
            paths: 路径管理器
        """
        self.paths = paths

    def prepare_sources(
        self, downloaded_files: dict[str, Path]
    ) -> tuple[Optional[Path], Optional[Path]]:
        """
        准备游戏源文件：解压并合并资源

        Args:
            downloaded_files: 下载的文件路径字典

        Returns:
            (normal_zip_dir, polyfill_zip_dir) 解压后的目录路径
        """
        logger.info("========== 解压游戏源文件 ==========")

        normal_zip_dir = None
        polyfill_zip_dir = None
        image_pack_dir = None

        # 解压GameOriginalImagePack获取img目录
        if "image_pack" in downloaded_files:
            image_pack_path = downloaded_files["image_pack"]
            image_pack_dir = self.paths.temp_dir / "image_pack"
            extract_zip(image_pack_path, image_pack_dir)
            logger.info(f"  图片包解压完成: {image_pack_dir}")

        # 解压普通版zip
        if "zip" in downloaded_files:
            zip_path = downloaded_files["zip"]
            normal_zip_dir = self.paths.prepare_dir / "zip"
            extract_zip(zip_path, normal_zip_dir)
            logger.info(f"  普通版解压完成: {normal_zip_dir}")

            # 合并图片包
            if image_pack_dir:
                self._merge_image_pack(image_pack_dir, normal_zip_dir)

        # 解压polyfill版zip
        if "polyfill_zip" in downloaded_files:
            zip_path = downloaded_files["polyfill_zip"]
            polyfill_zip_dir = self.paths.prepare_dir / "zip-polyfill"
            extract_zip(zip_path, polyfill_zip_dir)
            logger.info(f"  polyfill版解压完成: {polyfill_zip_dir}")

            # 合并图片包
            if image_pack_dir:
                self._merge_image_pack(image_pack_dir, polyfill_zip_dir)

        return normal_zip_dir, polyfill_zip_dir

    def _merge_image_pack(self, image_pack_dir: Path, target_dir: Path):
        """
        将图片包的img目录合并到目标目录

        Args:
            image_pack_dir: 图片包解压目录
            target_dir: 目标目录
        """
        from .utils import copy_directory

        # 查找img目录（可能在子目录中）
        img_src = None
        if (image_pack_dir / "img").exists():
            img_src = image_pack_dir / "img"
        else:
            for subdir in image_pack_dir.iterdir():
                if subdir.is_dir() and (subdir / "img").exists():
                    img_src = subdir / "img"
                    break

        if img_src:
            img_dest = target_dir / "img"
            logger.debug(f"合并图片包: {img_src} -> {img_dest}")
            copy_directory(img_src, img_dest)
        else:
            logger.warning("未找到图片包中的img目录")
