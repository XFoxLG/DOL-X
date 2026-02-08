"""
路径管理模块

集中管理所有构建路径，避免路径计算散落在各处。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config_loader import load_build_config, BuildConfiguration


@dataclass
class BuildPaths:
    """
    构建路径管理器

    集中管理所有构建相关的路径计算，确保路径一致性。
    """

    workspace: Path = field(default_factory=lambda: Path("."))
    _config: Optional[BuildConfiguration] = field(default=None, repr=False)

    def __post_init__(self):
        if self._config is None:
            self._config = load_build_config()
        self.workspace = Path(self.workspace)

    # ========== 主要目录 ==========

    @property
    def base_dir(self) -> Path:
        """基包存放目录 (workspace/base)"""
        return self.workspace / self._config.base_dir

    @property
    def output_dir(self) -> Path:
        """构建输出目录 (output)"""
        return Path(self._config.output_dir)

    @property
    def workspace_inner(self) -> Path:
        """内部工作目录 (workspace)"""
        return self.workspace / self._config.workspace_dir

    @property
    def prepare_dir(self) -> Path:
        """预处理目录 (workspace/prepare_package)"""
        return self.workspace_inner / self._config.prepare_package_dir

    @property
    def temp_dir(self) -> Path:
        """临时文件目录 (workspace/temp)"""
        return self.workspace_inner / self._config.temp_dir

    @property
    def extract_dir(self) -> Path:
        """解压目录 (workspace/extract)"""
        return self.workspace_inner / self._config.extract_dir

    @property
    def signed_dir(self) -> Path:
        """签名输出目录 (workspace/signed)"""
        return self.workspace_inner / self._config.signed_dir

    # ========== 基包路径 ==========

    def get_base_zip(self, polyfill: bool = False) -> Path:
        """获取ZIP基包路径"""
        suffix = "-polyfill" if polyfill else ""
        return self.base_dir / f"base{suffix}.zip"

    def get_apk_dir(self, polyfill: bool = False) -> Path:
        """获取已解包APK目录路径"""
        suffix = "-polyfill" if polyfill else ""
        return self.prepare_dir / f"apk{suffix}"

    # ========== 工具路径 ==========

    @property
    def apktool_path(self) -> Path:
        """apktool.jar 路径"""
        return self.workspace / "apktool.jar"

    @property
    def apksign_path(self) -> Path:
        """uber-apk-signer.jar 路径"""
        return self.workspace / "uber-apk-signer.jar"

    @property
    def keystore_path(self) -> Path:
        """签名密钥路径"""
        return Path("dol.jks")

    # ========== 版本信息 ==========

    @property
    def versions_file(self) -> Path:
        """版本信息文件路径"""
        return self.base_dir / "versions.json"

    # ========== 美化资源缓存目录 ==========

    def get_beautify_cache_dir(self, name: str) -> Path:
        """
        获取美化资源缓存目录

        Args:
            name: 资源名称 (besc, hikari, goose, ucb)

        Returns:
            缓存目录路径
        """
        dir_map = {
            "besc": "besc",
            "hikari": "sideview_hikari",
            "goose": "sideview_goose",
            "ucb": "ucb",
        }
        return self.temp_dir / dir_map.get(name, name)

    def get_mod_cache_path(self, name: str) -> Path:
        """
        获取 modloader mod 缓存文件路径

        Args:
            name: mod 名称 (如 au_f, au_m, au_a)

        Returns:
            mod zip 文件路径
        """
        return self.temp_dir / f"{name}.mod.zip"

    # ========== 构建工作目录 ==========

    def get_build_work_dir(
        self, pack_type: str, mod_code: int, polyfill: bool = False
    ) -> Path:
        """
        获取特定构建的工作目录

        Args:
            pack_type: 包类型 (zip/apk)
            mod_code: MOD代码
            polyfill: 是否为polyfill版本

        Returns:
            工作目录路径
        """
        suffix = "-polyfill" if polyfill else ""
        return self.extract_dir / pack_type / f"{mod_code}{suffix}"

    def get_temp_apk(self, mod_code: int, polyfill: bool = False) -> Path:
        """获取临时APK文件路径"""
        suffix = "-polyfill" if polyfill else ""
        return self.workspace_inner / f"tmp_{mod_code}{suffix}.apk"

    def get_signed_dir(self, mod_code: int, polyfill: bool = False) -> Path:
        """获取签名输出目录"""
        suffix = "-polyfill" if polyfill else ""
        return self.signed_dir / f"{mod_code}{suffix}"

    # ========== 目录创建 ==========

    def ensure_dirs(self):
        """确保所有必要目录存在"""
        dirs = [
            self.base_dir,
            self.output_dir,
            self.prepare_dir,
            self.temp_dir,
            self.extract_dir,
            self.signed_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ========== 工厂方法 ==========

    @classmethod
    def from_workspace(cls, workspace: Path = Path(".")) -> "BuildPaths":
        """从工作空间创建路径管理器"""
        return cls(workspace=workspace)
