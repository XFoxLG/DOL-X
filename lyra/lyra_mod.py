"""
Lyra 信息 mod 构建模块

生成一个仅用于显示版本信息的 mod，包含 boot.json 和 README.md。
"""

import json
import logging
import zipfile
from pathlib import Path
from typing import Optional

from .version import LyraVersion, VersionInfo

logger = logging.getLogger(__name__)


def build_lyra_mod(
    output_path: Path,
    version: Optional[LyraVersion] = None,
    version_info: Optional[list[VersionInfo]] = None,
) -> Path:
    """
    构建 Lyra 信息 mod

    生成一个仅用于显示版本信息的 mod.zip 文件。

    Args:
        output_path: 输出文件路径
        version: Lyra 版本信息
        version_info: 资源版本信息列表

    Returns:
        生成的 mod.zip 文件路径
    """
    version_str = str(version) if version else "unknown"

    # 构建 boot.json
    boot_json = {
        "name": "Lyra",
        "version": version_str,
        "scriptFileList_inject_early": [],
        "scriptFileList_earlyload": [],
        "scriptFileList_preload": [],
        "styleFileList": [],
        "scriptFileList": [],
        "tweeFileList": [],
        "imgFileList": [],
        "additionFile": ["README.md"],
    }

    # 构建 README.md
    readme = _generate_readme(version_str, version_info or [])

    # 创建 mod.zip
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("boot.json", json.dumps(boot_json, indent=2, ensure_ascii=False))
        zf.writestr("README.md", readme)

    logger.info(f"Lyra mod 已生成: {output_path}")
    return output_path


def _generate_readme(
    version_str: str,
    version_info: list[VersionInfo],
) -> str:
    """
    生成 README.md 内容

    Args:
        version_str: Lyra 版本字符串
        version_info: 资源版本信息列表

    Returns:
        README.md 内容
    """
    lines = [
        f"# Lyra {version_str}",
        "",
        "此 mod 为 Lyra 整合包的信息标识，不包含实质功能。",
        "",
    ]

    if version_info:
        lines.extend(
            [
                "## 资源版本信息",
                "",
                "| 资源 | 版本 | 来源 |",
                "|------|------|------|",
            ]
        )

        for v in version_info:
            source = v.source or "-"
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

    return "\n".join(lines)
