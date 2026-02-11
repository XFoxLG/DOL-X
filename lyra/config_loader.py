"""
配置加载模块

从 TOML 配置文件加载构建配置、功能定义和组合规则。
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# 默认配置目录
DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass
class Feature:
    """功能定义"""

    id: str
    name: str
    bit: int
    required: bool = False
    skip: bool = False
    depends_on: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Feature":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            bit=data["bit"],
            required=data.get("required", False),
            skip=data.get("skip", False),
            depends_on=data.get("depends_on", []),
            conflicts_with=data.get("conflicts_with", []),
        )


@dataclass
class CombinationsConfig:
    """组合配置"""

    recommended: list[int] = field(default_factory=list)
    whitelist: list[int] = field(default_factory=list)
    blacklist: list[int] = field(default_factory=list)
    polyfill_enabled: bool = True
    polyfill_code: int = 3

    @classmethod
    def from_dict(cls, data: dict) -> "CombinationsConfig":
        polyfill = data.get("polyfill", {})
        return cls(
            recommended=data.get("recommended", []),
            whitelist=data.get("whitelist", []),
            blacklist=data.get("blacklist", []),
            polyfill_enabled=polyfill.get("enabled", True),
            polyfill_code=polyfill.get("code", 3),
        )


@dataclass
class Replacement:
    """替换规则"""

    file: str
    pattern: str
    replacement: str

    @classmethod
    def from_dict(cls, data: dict) -> "Replacement":
        return cls(
            file=data["file"],
            pattern=data["pattern"],
            replacement=data["replacement"],
        )


@dataclass
class ImagePackConfig:
    """图片包配置"""

    name: str
    urls: list[str] = field(default_factory=list)
    case_fixes: dict[str, str] = field(default_factory=dict)
    files_to_remove: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict, dolp_base: str = "") -> "ImagePackConfig":
        # 替换 URL 中的模板变量
        urls = []
        for url in data.get("urls", []):
            if "{dolp_base}" in url:
                url = url.replace("{dolp_base}", dolp_base)
            urls.append(url)

        return cls(
            name=name,
            urls=urls,
            case_fixes=data.get("case_fixes", {}),
            files_to_remove=data.get("files_to_remove", []),
        )


@dataclass
class ModloaderModConfig:
    """Modloader mod 配置"""

    feature_id: str
    github_repo: str
    asset_pattern: str
    release_tag: str = "latest"

    @classmethod
    def from_dict(cls, data: dict) -> "ModloaderModConfig":
        return cls(
            feature_id=data["feature_id"],
            github_repo=data["github_repo"],
            asset_pattern=data["asset_pattern"],
            release_tag=data.get("release_tag", "latest"),
        )


@dataclass
class BaseModConfig:
    """基础 mod 注入配置"""

    key: str  # mod 标识，对应 extra_mods 字典中的键
    feature_id: str = ""  # 关联的 feature ID（可选）
    github_repo: str = ""  # GitHub 仓库，自动下载最新 .mod.zip（可选）
    inject: str = "add"  # 注入方式: "add" 追加 / "replace" 替换指定 slot
    replace_slot: int = 0  # 替换的 slot 索引（仅 inject="replace" 时有效）

    @classmethod
    def from_dict(cls, data: dict) -> "BaseModConfig":
        return cls(
            key=data["key"],
            feature_id=data.get("feature_id", ""),
            github_repo=data.get("github_repo", ""),
            inject=data.get("inject", "add"),
            replace_slot=data.get("replace_slot", 0),
        )


@dataclass
class BuildConfiguration:
    """完整构建配置"""

    # URLs
    apktool_url: str
    uber_apk_signer_url: str
    dolp_base_url: str
    chs_repo_url: str

    # Paths
    workspace_dir: str
    output_dir: str
    extract_dir: str
    temp_dir: str
    signed_dir: str
    base_dir: str
    prepare_package_dir: str

    # GitHub
    github_owner: str
    github_repo: str

    # APK replacements
    apk_replacements: list[Replacement] = field(default_factory=list)

    # Image packs
    imagepacks: dict[str, ImagePackConfig] = field(default_factory=dict)

    # Modloader mods
    modloader_mods: list[ModloaderModConfig] = field(default_factory=list)

    # Base mods (injection order)
    base_mods: list[BaseModConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "BuildConfiguration":
        urls = data.get("urls", {})
        paths = data.get("paths", {})
        github = data["github"]
        apk = data.get("apk", {})

        # 解析 APK 替换规则
        replacements = [Replacement.from_dict(r) for r in apk.get("replacements", [])]

        # 解析图片包配置
        dolp_base = urls["dolp_base"]
        imagepacks = {}
        for name, pack_data in data.get("imagepacks", {}).items():
            imagepacks[name] = ImagePackConfig.from_dict(name, pack_data, dolp_base)

        # 解析 modloader mod 配置
        modloader_mods = [
            ModloaderModConfig.from_dict(m) for m in data.get("modloader_mods", [])
        ]

        # 解析基础 mod 配置
        base_mods = [BaseModConfig.from_dict(m) for m in data.get("base_mods", [])]

        dolp_base = urls["dolp_base"]
        chs_repo = urls.get(
            "chs_repo", "Eltirosto/Degrees-of-Lewdity-Chinese-Localization"
        )

        return cls(
            apktool_url=urls["apktool"],
            uber_apk_signer_url=urls["uber_apk_signer"],
            dolp_base_url=dolp_base,
            chs_repo_url=chs_repo,
            workspace_dir=paths["workspace"],
            output_dir=paths["output"],
            extract_dir=paths["extract"],
            temp_dir=paths["temp"],
            signed_dir=paths["signed"],
            base_dir=paths["base"],
            prepare_package_dir=paths["prepare_package"],
            github_owner=github["owner"],
            github_repo=github["repo"],
            apk_replacements=replacements,
            imagepacks=imagepacks,
            modloader_mods=modloader_mods,
            base_mods=base_mods,
        )


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self._features: Optional[list[Feature]] = None
        self._combinations: Optional[CombinationsConfig] = None
        self._build: Optional[BuildConfiguration] = None

    def _load_toml(self, filename: str) -> dict:
        """加载 TOML 文件"""
        filepath = self.config_dir / filename
        if not filepath.exists():
            logger.warning(f"配置文件不存在: {filepath}")
            return {}

        with open(filepath, "rb") as f:
            return tomllib.load(f)

    @property
    def features(self) -> list[Feature]:
        """加载功能定义"""
        if self._features is None:
            data = self._load_toml("features.toml")
            self._features = [Feature.from_dict(f) for f in data.get("features", [])]
        return self._features

    @property
    def combinations(self) -> CombinationsConfig:
        """加载组合配置"""
        if self._combinations is None:
            data = self._load_toml("combinations.toml")
            self._combinations = CombinationsConfig.from_dict(data)
        return self._combinations

    @property
    def build(self) -> BuildConfiguration:
        """加载构建配置"""
        if self._build is None:
            data = self._load_toml("build.toml")
            self._build = BuildConfiguration.from_dict(data)
        return self._build

    def get_feature_by_id(self, feature_id: str) -> Optional[Feature]:
        """通过ID获取功能"""
        for f in self.features:
            if f.id == feature_id:
                return f
        return None

    def get_feature_by_bit(self, bit: int) -> Optional[Feature]:
        """通过位值获取功能"""
        for f in self.features:
            if f.bit == bit:
                return f
        return None

    def reload(self):
        """重新加载所有配置"""
        self._features = None
        self._combinations = None
        self._build = None


# 全局配置加载器实例
_config_loader: Optional[ConfigLoader] = None


def get_config_loader(config_dir: Optional[Path] = None) -> ConfigLoader:
    """获取配置加载器实例"""
    global _config_loader
    if _config_loader is None or config_dir is not None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader


def load_features(config_dir: Optional[Path] = None) -> list[Feature]:
    """加载功能定义"""
    return get_config_loader(config_dir).features


def load_combinations_config(config_dir: Optional[Path] = None) -> CombinationsConfig:
    """加载组合配置"""
    return get_config_loader(config_dir).combinations


def load_build_config(config_dir: Optional[Path] = None) -> BuildConfiguration:
    """加载构建配置"""
    return get_config_loader(config_dir).build
