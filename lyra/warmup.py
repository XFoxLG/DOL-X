"""
资源预热模块

在并行构建前预先下载并解压所有美化资源，避免并发下载冲突。
"""

import logging
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlparse

from .code_validation import parse_build_code
from .combo import CombinationCalculator
from .paths import BuildPaths
from .version import VersionInfo, VersionRegistry
from .config_loader import load_build_config, get_config_loader, ModloaderModConfig
from .utils import (
    download_file,
    extract_tar_gz,
    safe_remove,
    safe_move,
    get_gitgud_commit_hash,
    get_github_release_asset,
)

logger = logging.getLogger(__name__)


class ResourceWarmer:
    """
    资源预热器

    在并行构建前串行下载并解压所有美化资源，
    避免多个进程同时下载同一资源导致的冲突。
    """

    # DoL+ 图片包列表
    DOLP_PACKS = {
        "besc": ["dolp", "b3s", "kaervek", "dolp_b3s"],
        "hikari": ["b3s_hikfem", "b3s_hikfemsubs"],
        "goose": ["dolp", "goosefem", "goosefemsubs"],
        "ucb": ["mysterious"],
    }

    BEAUTIFY_FEATURES = {
        "besc": "besc",
        "hikari": "hikari",
        "goose": "goose",
        "ucb": "ucb",
    }

    def __init__(
        self,
        paths: BuildPaths,
        codes: list[str] | None = None,
    ):
        """
        初始化预热器

        Args:
            paths: 路径管理器
            codes: 已通过 CLI 校验的显式构建代码；为空时使用配置默认矩阵
        """
        self.paths = paths
        self.config = load_build_config()
        self.registry = VersionRegistry()
        self.codes = list(codes) if codes is not None else None
        self.required_feature_ids = self._get_required_feature_ids()

    def _get_required_feature_ids(self) -> set[str]:
        """根据当前构建列表推导需要预热的 feature。"""
        feature_ids: set[str] = set()

        if self.codes is not None:
            config_loader = get_config_loader()
            for raw_code in self.codes:
                parsed_code = parse_build_code(raw_code)
                if parsed_code.error or parsed_code.code is None:
                    raise ValueError(
                        f"显式预热构建代码无效 ({raw_code}): {parsed_code.error}"
                    )
                for feature in config_loader.features:
                    if parsed_code.code & feature.bit:
                        feature_ids.add(feature.id)
            return feature_ids

        calculator = CombinationCalculator()
        for combination in calculator.calculate(include_polyfill=False):
            for feature in calculator.features:
                if combination.code & feature.bit:
                    feature_ids.add(feature.id)

        return feature_ids

    def warmup_all(self) -> VersionRegistry:
        """
        预热所有美化资源

        Returns:
            版本信息注册表
        """
        logger.info("========== 开始资源预热 ==========")

        # 确保临时目录存在
        self.paths.temp_dir.mkdir(parents=True, exist_ok=True)

        # 预热 DoL+ 图片包
        self._warmup_dolp_packs()

        # 预热 modloader mod
        self._warmup_modloader_mods()

        logger.info("========== 资源预热完成 ==========")
        self.registry.print_summary()

        return self.registry

    def _warmup_dolp_packs(self):
        """预热 DoL+ 图片包"""
        logger.info("--- 预热 DoL+ 图片包 ---")

        required_beautify = [
            name
            for name, feature_id in self.BEAUTIFY_FEATURES.items()
            if feature_id in self.required_feature_ids
        ]

        if not required_beautify:
            logger.info("  当前构建列表不需要 DoL+ 图片包")
            return

        # 收集当前构建列表需要的包
        all_packs = set()
        for name in required_beautify:
            packs = self.DOLP_PACKS[name]
            all_packs.update(packs)

        # 获取 DoL+ commit hash 作为版本
        commit_hash = get_gitgud_commit_hash(
            "Frostberg/degrees-of-lewdity-plus", "master"
        )
        if commit_hash:
            self.registry.add(
                VersionInfo(
                    name="DoL+",
                    version=commit_hash,
                    source="gitgud.io/Frostberg/degrees-of-lewdity-plus",
                )
            )

        # 下载并解压每个图片包
        for pack_name in sorted(all_packs):
            # 映射包名到配置名（例如 mysterious -> ucb）
            config_name = None
            for beautify_name, pack_list in self.DOLP_PACKS.items():
                if pack_name in pack_list:
                    config_name = beautify_name
                    break
            self._download_dolp_pack(pack_name, config_name)

        # 仅处理当前构建列表会用到的美化包。
        processors = {
            "besc": self._process_besc,
            "hikari": self._process_hikari,
            "goose": self._process_goose,
            "ucb": self._process_ucb,
        }
        for name in required_beautify:
            processors[name]()

    def _download_dolp_pack(self, pack_name: str, config_name: str = None):
        """
        下载单个 DoL+ 图片包
        支持多 URL fallback 机制

        Args:
            pack_name: 包名称（如 mysterious）
            config_name: 配置名称（如 ucb），用于查找多 URL 配置
        """
        tar_path = self.paths.temp_dir / f"dolp-{pack_name}.tar.gz"
        extract_dir = self.paths.temp_dir / f"dolp-{pack_name}"

        # 检查是否已存在
        if extract_dir.exists() and (extract_dir / "img").exists():
            logger.debug(f"  {pack_name}: 已缓存")
            return

        logger.info(f"  下载: {pack_name}")
        
        urls = self._get_dolp_pack_urls(pack_name, config_name)
        logger.info(
            "  找到 %s 个与组件 %s 匹配的 URL（配置: %s）",
            len(urls),
            pack_name,
            config_name or "default",
        )

        # 尝试每个 URL，直到成功
        last_error = None
        for idx, url in enumerate(urls, 1):
            try:
                logger.info(f"  [{idx}/{len(urls)}] 尝试: {url[:100]}...")
                download_file(url, tar_path, quiet=True)
                logger.info(f"  下载成功！")
                break  # 下载成功，退出循环
            except Exception as e:
                last_error = e
                logger.warning(f"  [{idx}/{len(urls)}] 失败: {str(e)[:150]}")
                continue
        else:
            # 所有 URL 都失败
            logger.error(f"  所有 {len(urls)} 个 URL 均失败")
            raise last_error or Exception(f"无法下载 {pack_name}")

        # 解压
        img_dir = extract_dir / "img"
        img_dir.mkdir(parents=True, exist_ok=True)
        extract_tar_gz(tar_path, img_dir, strip_components=3)

    def _get_dolp_pack_urls(
        self,
        pack_name: str,
        config_name: str | None,
    ) -> list[str]:
        """Return source and mirror URLs that belong to one DoL+ pack."""
        imagepack_config = (
            self.config.imagepacks.get(config_name) if config_name else None
        )
        configured_urls = imagepack_config.urls if imagepack_config else []
        matching_urls = [
            source_url
            for source_url in configured_urls
            if self._url_targets_dolp_pack(source_url, pack_name)
        ]
        if matching_urls:
            return matching_urls

        return [f"{self.config.dolp_base_url}/{pack_name}"]

    @staticmethod
    def _url_targets_dolp_pack(source_url: str, pack_name: str) -> bool:
        """Match query-path and mirror filename forms without substring collisions."""
        parsed_url = urlparse(source_url)
        query_values = parse_qs(parsed_url.query).get("path", [])
        for query_path in query_values:
            if PurePosixPath(unquote(query_path)).name == pack_name:
                return True

        source_filename = PurePosixPath(unquote(parsed_url.path)).name.casefold()
        expected_mirror_suffix = f"imagepacks-{pack_name}.tar.gz".casefold()
        return source_filename.endswith(expected_mirror_suffix)

    def _process_besc(self):
        """处理 BESC 美化包"""
        dest_dir = self.paths.get_beautify_cache_dir("besc") / "img"
        if dest_dir.exists() and (dest_dir / "body").exists():
            logger.debug("  BESC: 已处理")
            return

        dest_dir.mkdir(parents=True, exist_ok=True)

        # 合并所有 BESC 包
        for pack in self.DOLP_PACKS["besc"]:
            src_dir = self.paths.temp_dir / f"dolp-{pack}" / "img"
            if src_dir.exists():
                self._copy_directory(src_dir, dest_dir)

        # 处理大小写问题
        self._fix_besc_case_issues(dest_dir)
        logger.info("  BESC: 处理完成")

    def _process_hikari(self):
        """处理 Hikari 美化包"""
        dest_dir = self.paths.get_beautify_cache_dir("hikari") / "img"
        if dest_dir.exists() and (dest_dir / "body").exists():
            logger.debug("  Hikari: 已处理")
            return

        dest_dir.mkdir(parents=True, exist_ok=True)

        # 合并 Hikari 包
        for pack in self.DOLP_PACKS["hikari"]:
            src_dir = self.paths.temp_dir / f"dolp-{pack}" / "img"
            if src_dir.exists():
                self._copy_directory(src_dir, dest_dir)

        # 删除问题文件
        safe_remove(dest_dir / "hair" / "fringe" / "Messy curls")
        safe_remove(dest_dir / "clothes" / "face" / "foxmask" / "Full.png")
        logger.info("  Hikari: 处理完成")

    def _process_goose(self):
        """处理 Goose 美化包"""
        dest_dir = self.paths.get_beautify_cache_dir("goose") / "img"
        if dest_dir.exists() and (dest_dir / "body").exists():
            logger.debug("  Goose: 已处理")
            return

        dest_dir.mkdir(parents=True, exist_ok=True)

        # 合并 Goose 包
        for pack in self.DOLP_PACKS["goose"]:
            src_dir = self.paths.temp_dir / f"dolp-{pack}" / "img"
            if src_dir.exists():
                self._copy_directory(src_dir, dest_dir)

        logger.info("  Goose: 处理完成")

    def _process_ucb(self):
        """处理 UCB 美化包"""
        dest_dir = self.paths.get_beautify_cache_dir("ucb") / "img"
        if dest_dir.exists() and (dest_dir / "body").exists():
            logger.debug("  UCB: 已处理")
            return

        dest_dir.mkdir(parents=True, exist_ok=True)

        # 合并 UCB 包
        for pack in self.DOLP_PACKS["ucb"]:
            src_dir = self.paths.temp_dir / f"dolp-{pack}" / "img"
            if src_dir.exists():
                self._copy_directory(src_dir, dest_dir)

        # 删除问题文件
        safe_remove(
            dest_dir / "sex" / "missionary" / "active" / "virginkiller" / "chest.png"
        )
        safe_remove(
            dest_dir / "sex" / "missionary" / "active" / "virginkiller" / "waist.png"
        )
        logger.info("  UCB: 处理完成")

    def _fix_besc_case_issues(self, img_dir: Path):
        """修复 BESC 的大小写问题"""
        # kaervek 的大小写问题
        messy_curls_upper = img_dir / "hair" / "fringe" / "Messy curls"
        messy_curls_lower = img_dir / "hair" / "fringe" / "messy curls"
        if messy_curls_upper.exists():
            messy_curls_lower.mkdir(parents=True, exist_ok=True)
            for item in messy_curls_upper.iterdir():
                shutil.move(str(item), str(messy_curls_lower / item.name))
            safe_remove(messy_curls_upper)

        shoulder_upper = img_dir / "hair" / "sides" / "messy ponytail" / "Shoulder.png"
        shoulder_lower = img_dir / "hair" / "sides" / "messy ponytail" / "shoulder.png"
        safe_move(shoulder_upper, shoulder_lower)

    def _warmup_modloader_mods(self):
        """预热 modloader mod"""
        if not self.config.modloader_mods:
            return

        logger.info("--- 预热 modloader mod ---")
        config_loader = get_config_loader()

        for mod_config in self.config.modloader_mods:
            if not mod_config.enabled:
                continue

            if not any(
                feature_id in self.required_feature_ids
                for feature_id in mod_config.required_feature_ids
            ):
                continue
            self._download_modloader_mod(mod_config, config_loader)

    def _download_modloader_mod(self, mod_config: ModloaderModConfig, config_loader):
        """
        下载单个 modloader mod

        Args:
            mod_config: mod 配置
            config_loader: 配置加载器（用于查找 feature 信息）
        """
        features = [
            config_loader.get_feature_by_id(feature_id)
            for feature_id in mod_config.required_feature_ids
        ]
        valid_features = [feature for feature in features if feature]
        if mod_config.name:
            display_name = mod_config.name
        elif len(valid_features) == 1:
            display_name = valid_features[0].name
        else:
            display_name = mod_config.key or mod_config.asset_pattern

        dest_path = self.paths.get_mod_cache_path(mod_config.cache_name)

        # 检查是否已存在
        if dest_path.exists():
            logger.debug(f"  {display_name}: 已缓存")
            return

        if mod_config.download_url:
            filename = mod_config.asset_pattern or f"{mod_config.cache_name}.zip"
            self.registry.add(
                VersionInfo(
                    name=display_name,
                    version=mod_config.release_tag,
                    source=mod_config.github_repo or mod_config.download_url,
                    filename=filename,
                )
            )
            download_file(mod_config.download_url, dest_path, quiet=True)
            logger.info(f"  {display_name}: 下载完成 ({mod_config.release_tag})")
            return

        # 获取资源信息
        asset = get_github_release_asset(
            mod_config.github_repo,
            mod_config.asset_pattern,
            tag=mod_config.release_tag,
        )

        if not asset:
            logger.warning(f"  {display_name}: 无法获取下载信息")
            return

        # 记录版本信息
        self.registry.add(
            VersionInfo(
                name=display_name,
                version=asset.version,
                source=mod_config.github_repo,
                filename=asset.name,
            )
        )

        # 下载 mod 文件
        download_file(asset.url, dest_path, quiet=True)
        logger.info(f"  {display_name}: 下载完成 ({asset.version})")

    def _copy_directory(self, src: Path, dest: Path):
        """复制目录内容"""
        for item in src.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(src)
                dest_path = dest / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_path)
