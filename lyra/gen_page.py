"""
Markdown 下载页面生成模块

生成带有下载链接的 Markdown 表格。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
import logging

try:
    import pytablewriter

    HAS_TABLEWRITER = True
except ImportError:
    HAS_TABLEWRITER = False

from .combo import CombinationCalculator, ModCombination
from .config_loader import load_build_config
from .config import ModCode
from .version import VersionInfo, VersionRegistry

logger = logging.getLogger(__name__)


def load_version_info(path: Path) -> list[VersionInfo]:
    """加载版本信息（兼容旧接口）"""
    registry = VersionRegistry.load(path)
    return list(registry)


@dataclass
class DownloadPageConfig:
    """下载页面配置"""

    version: str
    github_owner: str = ""
    github_repo: str = ""
    include_zip: bool = True
    include_apk: bool = True
    output_path: Optional[Path] = None
    mirror_base: str = "https://ghfast.top/https://github.com"
    base_game_version: str = ""
    chs_version: str = ""
    date_suffix: str = ""
    versions_file: Optional[Path] = None  # 版本信息文件路径
    version_info: list[VersionInfo] = field(default_factory=list)  # 版本信息列表

    def __post_init__(self):
        """如果没有指定 GitHub 信息，从配置文件加载"""
        if not self.github_owner or not self.github_repo:
            try:
                build_config = load_build_config()
                if not self.github_owner:
                    self.github_owner = build_config.github_owner or "sakarie9"
                if not self.github_repo:
                    self.github_repo = build_config.github_repo or "DoL-Lyra"
            except Exception:
                if not self.github_owner:
                    self.github_owner = "sakarie9"
                if not self.github_repo:
                    self.github_repo = "DoL-Lyra"

        # 解析版本号，例如 v0.5.7.9-5.0.2a-0112
        if not self.base_game_version or not self.chs_version or not self.date_suffix:
            if self.version:
                parts = self.version.lstrip("v").split("-")
                if len(parts) >= 3:
                    if not self.base_game_version:
                        self.base_game_version = parts[0]
                    if not self.chs_version:
                        self.chs_version = parts[1]
                    if not self.date_suffix:
                        self.date_suffix = parts[2]

        # 如果指定了版本文件，加载版本信息
        if self.versions_file and not self.version_info:
            self.version_info = load_version_info(self.versions_file)

    @property
    def release_base_url(self) -> str:
        return f"https://github.com/{self.github_owner}/{self.github_repo}/releases/download"

    def get_download_url(self, filename: str) -> str:
        """获取下载链接"""
        tag = self.version
        return f"{self.release_base_url}/{tag}/{filename}"

    def get_mirror_url(self, filename: str) -> str:
        """获取镜像下载链接"""
        tag = self.version
        return f"{self.mirror_base}/{self.github_owner}/{self.github_repo}/releases/download/{tag}/{filename}"

    def get_filename(self, mod_code: int, ext: str, is_polyfill: bool = False) -> str:
        """
        生成文件名

        使用 ModCode.get_suffix() 确保与构建时的文件名完全一致。

        Args:
            mod_code: MOD组合代码
            ext: 文件扩展名 (zip/apk)
            is_polyfill: 是否为 polyfill 版本

        Returns:
            生成的文件名
        """
        # 构建前缀
        prefix = f"DoL-{self.base_game_version}-Lyra-{self.chs_version}"
        if is_polyfill:
            prefix += "-polyfill"

        # 使用 ModCode.get_suffix() 生成 MOD 后缀，确保与构建时一致
        mod_suffix = ModCode(mod_code).get_suffix()
        if mod_suffix:
            prefix += f"-{mod_suffix}"

        return f"{prefix}-{self.date_suffix}.{ext}"


class DownloadPageGenerator:
    """下载页面生成器"""

    def __init__(
        self,
        config: DownloadPageConfig,
        config_dir: Optional[Path] = None,
    ):
        self.config = config
        self.calculator = CombinationCalculator(config_dir)
        self.config.calculator = self.calculator

    def _format_link(self, url: str, text: str) -> str:
        """格式化Markdown链接"""
        return f"[{text}]({url})"

    def _generate_row(
        self,
        combination: ModCombination,
    ) -> list[str]:
        """生成表格行"""
        # 显示名称
        display_name = combination.display_name

        # polyfill 版本的特殊处理
        if combination.is_polyfill:
            # 移除原有的 (兼容版) 后缀（如果有）
            display_name = display_name.replace("(兼容版)", "").strip()
            display_name = f"{display_name}+CSD(兼容版)"
        elif combination.is_recommended:
            display_name = f"***{display_name}(推荐)***"

        row = [display_name]

        if self.config.include_zip:
            filename = self.config.get_filename(
                combination.code, "zip", combination.is_polyfill
            )
            github_url = self.config.get_download_url(filename)
            mirror_url = self.config.get_mirror_url(filename)
            link = f"[Github下载]({github_url}) / [备链]({mirror_url})"
            row.append(link)

        if self.config.include_apk:
            filename = self.config.get_filename(
                combination.code, "apk", combination.is_polyfill
            )
            github_url = self.config.get_download_url(filename)
            mirror_url = self.config.get_mirror_url(filename)
            link = f"[Github下载]({github_url}) / [备链]({mirror_url})"
            row.append(link)

        return row

    def generate_table_pytablewriter(self, combinations: list[ModCombination]) -> str:
        """使用 pytablewriter 生成表格"""
        if not HAS_TABLEWRITER:
            raise ImportError("pytablewriter is required for this function")

        headers = ["版本选择"]
        if self.config.include_zip:
            headers.append("ZIP")
        if self.config.include_apk:
            headers.append("APK")

        matrix = [self._generate_row(c) for c in combinations]

        writer = pytablewriter.MarkdownTableWriter(
            headers=headers,
            value_matrix=matrix,
            margin=0,
        )

        return writer.dumps()

    def generate_table_simple(self, combinations: list[ModCombination]) -> str:
        """简单表格生成（无需外部依赖）"""
        headers = ["版本选择"]
        if self.config.include_zip:
            headers.append("ZIP")
        if self.config.include_apk:
            headers.append("APK")

        lines = []

        # 表头
        lines.append("|" + "|".join(headers) + "|")
        lines.append("|" + "|".join(["-" * (len(h) + 20) for h in headers]) + "|")

        # 数据行
        for comb in combinations:
            row = self._generate_row(comb)
            lines.append("|" + "|".join(row) + "|")

        return "\n".join(lines)

    def generate(self) -> str:
        """
        生成完整的 Markdown 下载页面

        Returns:
            Markdown 内容
        """
        combinations = self.calculator.calculate(include_polyfill=True)

        # 按照示例顺序：polyfill BESC 在最前面，然后是推荐版本，基础，最后是其他版本
        polyfill_besc = [
            c for c in combinations if c.is_polyfill and "BESC" in c.display_name
        ]
        recommended = [
            c for c in combinations if c.is_recommended and not c.is_polyfill
        ]
        base = [
            c for c in combinations if c.display_name == "基础" and not c.is_polyfill
        ]
        others = [
            c
            for c in combinations
            if not c.is_recommended
            and c.display_name != "基础"
            and not c.is_polyfill
            and not (c.is_polyfill and "BESC" in c.display_name)
        ]

        # 合并所有组合
        all_combinations = polyfill_besc + recommended + base + others
        # 用于组合对照的组合（不包含 polyfill）
        non_polyfill_combinations = [c for c in combinations if not c.is_polyfill]

        # 生成当前时间的 ISO 8601 格式字符串
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        # 生成 frontmatter
        lines = [
            "+++",
            f"title = '{self.config.version}'",
            f"date = {current_time}",
            f"slug = 'downloads/{self.config.version}'",
            "showTableOfContents = false",
            "+++",
            "",
            "{{< alert >}}",
            "⚠永远记得在升级之前备份你的存档⚠",
            "{{< /alert >}}",
            "<br>",
            "{{< alert >}}",
            '下载之前请阅读 [版本说明]({{< ref "docs" >}}) 以选择所需版本',
            "{{< /alert >}}",
            "<br>",
            "{{< alert >}}",
            '如出现问题请参考 [⚠疑难解答⚠]({{< ref "troubleshoot" >}})',
            "{{< /alert >}}",
            "<br>",
            "{{< alert >}}",
            "使用本整合出现问题时请先使用 [汉化仓库](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization) 发布的版本，或是汉化仓库提供的 [汉化在线版](https://eltirosto.github.io/Degrees-of-Lewdity-Chinese-Localization/)，测试是否同样出现问题，参考 [发布下载版](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/README.md#%E5%8F%91%E5%B8%83%E4%B8%8B%E8%BD%BD%E7%89%88)。",
            "<br>",
            "如问题同样能够复现请前往汉化仓库反馈；如问题只在本整合内出现请向 [本仓库](https://github.com/DoL-Lyra/Lyra/issues) 反馈",
            "{{< /alert >}}",
            "<br>",
            "{{< alert >}}",
            "本仓库分发的为完整游戏本体+mod的 **`整合包`**，并非单独的 mod，请勿使用 modloader 加载。",
            "<br>",
            "请 **`不要`** 手动再添加汉化 `ModI18N.mod.zip` 和图片包 `GameOriginalImagePack.mod.zip`",
            "{{< /alert >}}",
            "",
            "## 下载",
            "",
            "> 内置的 `汉化/作弊/CSD` mod 已可以在 ModLoader 处自行选择禁用或者启用，不需要特定 mod 的需自行禁用",
            "> 基础即为只包含 `作弊+CSD` 的版本，其他版本均在基础上添加了对应功能",
            "",
            "",
        ]

        # 生成统一表格
        if HAS_TABLEWRITER:
            lines.append(self.generate_table_pytablewriter(all_combinations))
        else:
            lines.append(self.generate_table_simple(all_combinations))

        # 添加版本信息表格
        if self.config.version_info:
            lines.extend(self._generate_version_table())

        # 添加组合对照
        lines.extend(
            [
                "",
                "",
                "<details>",
                "",
                "<summary>组合对照</summary>",
                "",
                "```",
            ]
        )

        # 使用 CombinationCalculator 的 to_string 方法生成组合对照
        lines.append(self.calculator.to_string(include_polyfill=False))

        lines.extend(
            [
                "```",
                "",
                "</details>",
            ]
        )

        return "\n".join(lines)

    def _generate_version_table(self) -> list[str]:
        """生成版本信息表格"""
        lines = [
            "",
            "",
            "<details>",
            "",
            "<summary>资源版本信息</summary>",
            "",
            "| 资源 | 版本 | 来源 |",
            "|------|------|------|",
        ]

        for v in self.config.version_info:
            source = v.source or "-"
            # 如果来源是 GitHub/GitGud，生成链接
            if "github.com" in source or "/" in source:
                if "gitgud.io" in source:
                    source_link = f"[{source}](https://{source})"
                elif "/" in source and "http" not in source:
                    source_link = f"[{source}](https://github.com/{source})"
                else:
                    source_link = source
            else:
                source_link = source

            lines.append(f"| {v.name} | `{v.version}` | {source_link} |")

        lines.extend(
            [
                "",
                "</details>",
            ]
        )

        return lines

    def save(self, path: Optional[Path] = None):
        """
        保存到文件

        Args:
            path: 输出路径，默认使用 config 中的 output_path
        """
        output_path = path or self.config.output_path
        if output_path is None:
            raise ValueError("Output path not specified")

        content = self.generate()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Download page saved to: {output_path}")


def generate_download_page(
    version: str,
    output_path: Optional[Path] = None,
    github_owner: str = "sakarie9",
    github_repo: str = "DoL-Lyra",
    versions_file: Optional[Path] = None,
) -> str:
    """
    便捷函数：生成下载页面

    Args:
        version: 版本号
        output_path: 输出路径（可选）
        github_owner: GitHub 用户名
        github_repo: GitHub 仓库名
        versions_file: 版本信息文件路径（可选）

    Returns:
        Markdown 内容
    """
    config = DownloadPageConfig(
        version=version,
        github_owner=github_owner,
        github_repo=github_repo,
        output_path=output_path,
        versions_file=versions_file,
    )

    generator = DownloadPageGenerator(config)
    content = generator.generate()

    if output_path:
        generator.save(output_path)

    return content
