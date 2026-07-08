"""
本地自研 mod 打包模块

把仓库内 `mods/<name>/` 源码目录打包成 ModLoader 可加载的 `.mod.zip`。
与 lyra_mod.py（纯信息 mod）不同，这里打包的是带 boot.json + 脚本的功能 mod，
源码在版本控制内、可复用、可追溯。

设计目标：
- 不依赖远程下载（区别于 warmup 的 modloader_mods），源码就在仓库里。
- boot.json 已由作者手写并纳入版本控制，这里原样打包，只校验声明的文件都存在。
- 打包结果供 build 阶段通过 ModInjector 注入 HTML。
"""

import json
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 仓库内本地 mod 源码根目录
LOCAL_MODS_DIR = Path(__file__).parent.parent / "mods"

# boot.json 中所有可能引用源文件的字段
_FILE_LIST_FIELDS = (
    "scriptFileList_inject_early",
    "scriptFileList_earlyload",
    "scriptFileList_preload",
    "scriptFileList",
    "styleFileList",
    "tweeFileList",
    "imgFileList",
    "additionFile",
    "additionBinaryFile",
)


def _collect_declared_files(boot: dict) -> list[str]:
    """收集 boot.json 中声明的所有源文件相对路径。"""
    files: list[str] = []
    for field in _FILE_LIST_FIELDS:
        for entry in boot.get(field, []):
            if isinstance(entry, str):
                files.append(entry)
    return files


def build_local_mod(mod_name: str, output_path: Path) -> Path:
    """
    把 `mods/<mod_name>/` 源码打包成 `.mod.zip`。

    Args:
        mod_name: mod 目录名（= boot.json 的 name，约定一致）
        output_path: 输出的 .mod.zip 路径

    Returns:
        生成的 .mod.zip 路径

    Raises:
        FileNotFoundError: 源码目录或 boot.json 缺失
        ValueError: boot.json 声明的文件在源码目录中不存在
    """
    src_dir = LOCAL_MODS_DIR / mod_name
    boot_path = src_dir / "boot.json"

    if not src_dir.is_dir():
        raise FileNotFoundError(f"本地 mod 源码目录不存在: {src_dir}")
    if not boot_path.is_file():
        raise FileNotFoundError(f"boot.json 不存在: {boot_path}")

    boot = json.loads(boot_path.read_text(encoding="utf-8"))

    # 校验 boot.json 声明的每个文件都真实存在，避免打出加载即报错的坏包。
    declared = _collect_declared_files(boot)
    missing = [rel for rel in declared if not (src_dir / rel).is_file()]
    if missing:
        raise ValueError(
            f"本地 mod '{mod_name}' 的 boot.json 声明了不存在的文件: {', '.join(missing)}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # boot.json 必须在 zip 根目录；其余按声明路径原样打包。
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("boot.json", json.dumps(boot, indent=2, ensure_ascii=False))
        for rel in declared:
            zf.write(src_dir / rel, rel)

    logger.info(f"本地 mod 已打包: {mod_name} -> {output_path}")
    return output_path
