"""
简化构建模块

假设所有资源已通过 warmup 预热，只负责资源复制和打包。
专为CI流程设计，不包含资源下载逻辑。
"""

import logging
import re
import shutil
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .paths import BuildPaths
from .version import LyraVersion, VersionRegistry
from .config import ModCode
from .lyra_mod import build_lyra_mod
from .combo import CombinationCalculator
from .config_loader import load_build_config, get_config_loader
from .prepare import ModInjector
from .utils import (
    extract_zip,
    create_zip,
    run_command,
    copy_directory,
    safe_remove,
)

logger = logging.getLogger(__name__)

MORE_LOVE_CACHE_NAME = "more_love"
MORE_LOVE_DRAG_MEMBER = "game/More_Love_Interest_Mod_Drag.js"
MORE_LOVE_DRAG_PATCH_MARKER = "function preventDefaultMLIM(ev)"
MORE_LOVE_DRAG_HELPERS = """function preventDefaultMLIM(ev) {
\tvar preventDefault = ev && ev.preventDefault;
\tif (typeof preventDefault === \"function\") {
\t\tpreventDefault.call(ev);
\t}
}
function stopPropagationMLIM(ev) {
\tvar stopPropagation = ev && ev.stopPropagation;
\tif (typeof stopPropagation === \"function\") {
\t\tstopPropagation.call(ev);
\t}
}
function getDataTransferTextMLIM(ev) {
\tvar dataTransfer = ev && ev.dataTransfer;
\tif (dataTransfer && typeof dataTransfer.getData === \"function\") {
\t\treturn dataTransfer.getData(\"Text\");
\t}
\treturn \"\";
}
function setDataTransferTextMLIM(ev, value) {
\tvar dataTransfer = ev && ev.dataTransfer;
\tif (dataTransfer && typeof dataTransfer.setData === \"function\") {
\t\tdataTransfer.setData(\"Text\", value || \"\");
\t}
}
"""


def _patch_more_love_drag_script(script: str) -> tuple[str, bool]:
    """Guard More Love drag handlers against non-DOM event arguments."""
    if MORE_LOVE_DRAG_PATCH_MARKER in script:
        return script, False

    patched = re.sub(r"\bev\.preventDefault\(\);?", "preventDefaultMLIM(ev);", script)
    patched = re.sub(r"\bev\.stopPropagation\(\);?", "stopPropagationMLIM(ev);", patched)
    patched = re.sub(
        r"\bev\.dataTransfer\.getData\(([\"'])Text\1\)",
        "getDataTransferTextMLIM(ev)",
        patched,
    )
    patched = re.sub(
        r"\bev\.dataTransfer\.setData\(([\"'])Text\1,\s*ev\.target\.id\);?",
        "setDataTransferTextMLIM(ev, ev && ev.target ? ev.target.id : \"\");",
        patched,
    )

    if patched == script:
        return script, False

    if not patched.rstrip().endswith(";"):
        patched = f"{patched.rstrip()};\n"

    return f";\n{MORE_LOVE_DRAG_HELPERS}\n{patched}", True


def patch_more_love_drag_event_handlers(
    source_path: Path,
    target_path: Path,
) -> dict[str, object]:
    """Create a patched More Love payload with defensive drag event handlers."""
    result: dict[str, object] = {
        "applied": False,
        "member": MORE_LOVE_DRAG_MEMBER,
        "source": str(source_path),
        "target": str(target_path),
    }

    try:
        with zipfile.ZipFile(source_path, "r") as source_zip:
            if MORE_LOVE_DRAG_MEMBER not in source_zip.namelist():
                result["status"] = "missing_patch_member"
                return result

            original_script = source_zip.read(MORE_LOVE_DRAG_MEMBER).decode(
                "utf-8",
                errors="replace",
            )
            patched_script, applied = _patch_more_love_drag_script(original_script)
            if not applied:
                result["status"] = (
                    "already_patched"
                    if MORE_LOVE_DRAG_PATCH_MARKER in original_script
                    else "patch_needle_not_found"
                )
                return result

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_path, "w") as target_zip:
                for member in source_zip.infolist():
                    data = source_zip.read(member)
                    if member.filename == MORE_LOVE_DRAG_MEMBER:
                        data = patched_script.encode("utf-8")
                    target_zip.writestr(member, data)
    except zipfile.BadZipFile as exc:
        result["status"] = "not_zip"
        result["error"] = str(exc)
        return result

    result["applied"] = True
    result["status"] = "patched"
    return result


@dataclass
class BuildTask:
    """
    构建任务

    定义单个构建任务的所有参数。
    """

    pack_type: str  # zip 或 apk
    mod_code: int  # MOD代码
    is_polyfill: bool = False  # 是否为polyfill版本
    version: Optional[LyraVersion] = None  # 版本信息
    paths: Optional[BuildPaths] = None  # 路径管理器

    def __post_init__(self):
        if self.paths is None:
            self.paths = BuildPaths()

    @property
    def code_str(self) -> str:
        """获取构建代码字符串"""
        prefix = "polyfill-" if self.is_polyfill else ""
        return f"{prefix}{self.mod_code}"

    @classmethod
    def from_code_str(
        cls,
        code_str: str,
        pack_type: str,
        version: Optional[LyraVersion] = None,
        paths: Optional[BuildPaths] = None,
    ) -> "BuildTask":
        """
        从代码字符串创建任务

        Args:
            code_str: 代码字符串，如 "3" 或 "polyfill-3"
            pack_type: 包类型
            version: 版本信息
            paths: 路径管理器
        """
        is_polyfill = code_str.startswith("polyfill-")
        mod_code = int(code_str.replace("polyfill-", ""))
        return cls(
            pack_type=pack_type,
            mod_code=mod_code,
            is_polyfill=is_polyfill,
            version=version,
            paths=paths,
        )


@dataclass
class BuildResult:
    """构建结果"""

    success: bool
    output_path: Optional[Path] = None
    output_name: str = ""
    error: Optional[str] = None
    applied_mods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": str(self.output_path) if self.output_path else None,
            "output_name": self.output_name,
            "error": self.error,
            "applied_mods": self.applied_mods,
        }


class PackageBuilder(ABC):
    """
    打包构建器基类

    假设所有资源已通过 warmup 预热到 temp 目录。
    """

    def __init__(self, task: BuildTask):
        """
        初始化构建器

        Args:
            task: 构建任务
        """
        self.task = task
        self.paths = task.paths
        self.mod_code = ModCode(task.mod_code)

    @property
    @abstractmethod
    def pack_type(self) -> str:
        """包类型"""
        pass

    @property
    @abstractmethod
    def img_path(self) -> Path:
        """图片目录路径（相对于工作目录）"""
        pass

    @property
    @abstractmethod
    def html_path(self) -> Path:
        """HTML 文件路径（相对于工作目录）"""
        pass

    @property
    def work_dir(self) -> Path:
        """当前构建的工作目录"""
        return self.paths.get_build_work_dir(
            self.pack_type,
            self.task.mod_code,
            self.task.is_polyfill,
        )

    def _infer_output_version(self) -> Optional[tuple[str, str]]:
        """从预处理记录中推断非 tag 构建的游戏与汉化版本。"""
        registry = VersionRegistry.load(self.paths.versions_file)

        for info in registry:
            if info.name != "汉化仓库":
                continue

            release_tag = (info.version or "").strip()
            if release_tag.startswith("v"):
                release_tag = release_tag[1:]

            marker = "-chs-"
            if marker not in release_tag:
                continue

            dol_ver, chs_ver = release_tag.split(marker, 1)
            if dol_ver and chs_ver:
                return dol_ver, chs_ver

        return None

    def get_output_name(self) -> str:
        """生成输出文件名"""
        if self.task.version:
            dol_ver = self.task.version.dol_ver
            chs_ver = self.task.version.chs_ver
            date_str = self.task.version.date
        else:
            inferred_version = self._infer_output_version()
            if inferred_version:
                dol_ver, chs_ver = inferred_version
            else:
                dol_ver = "unknown"
                chs_ver = "unknown"
            tz = timezone(timedelta(hours=8))
            date_str = datetime.now(tz).strftime("%m%d")

        # 构建前缀
        build_config = load_build_config()
        identity = build_config.identity_name or "Lyra"
        prefix = f"DoL-{dol_ver}-{identity}-{chs_ver}"
        if self.task.is_polyfill:
            prefix += "-polyfill"

        # 添加MOD后缀
        mod_suffix = self.mod_code.get_suffix()
        if mod_suffix:
            prefix += f"-{mod_suffix}"

        return f"{prefix}-{date_str}.{self.pack_type}"

    def _apply_beautify(self) -> list[str]:
        """
        应用预热的美化资源

        直接从 temp 目录复制已处理好的资源。

        Returns:
            应用的MOD名称列表
        """
        applied = []

        # 美化资源映射
        beautify_map = {
            ModCode.BESC: ("besc", "BESC"),
            ModCode.SIDEVIEW_HIKARI: ("hikari", "Hikari"),
            ModCode.SIDEVIEW_GOOSE: ("goose", "Goose"),
            ModCode.UCB: ("ucb", "UCB"),
        }

        # 按顺序处理美化
        order = [
            ModCode.BESC,
            ModCode.SIDEVIEW_HIKARI,
            ModCode.SIDEVIEW_GOOSE,
            ModCode.UCB,  # UCB 最后处理
        ]

        for code in order:
            if self.mod_code & code:
                cache_name, display_name = beautify_map.get(code, (None, None))
                if cache_name:
                    cache_dir = self.paths.get_beautify_cache_dir(cache_name) / "img"
                    if cache_dir.exists():
                        logger.debug(f"应用美化: {display_name}")
                        copy_directory(cache_dir, self.img_path)
                        applied.append(display_name)
                    else:
                        logger.warning(f"美化资源不存在: {cache_dir}")

        return applied

    def _has_au_feature(self) -> bool:
        """当前构建是否包含任一 AU 体型资源。"""
        return bool(
            self.mod_code
            & (ModCode.AU_FEMALE | ModCode.AU_MALE | ModCode.AU_ANDROGYNOUS)
        )

    def _apply_au_face_compatibility_aliases(self) -> list[str]:
        """
        为运行时请求的嵌套 default face 路径补齐兼容别名。

        AU/BeautySelector 运行时会请求 img/face/default/default/blush*.png，
        但当前打包结果只包含 img/face/default/blush*.png。这里在构建阶段
        复制缺失目标，避免运行时 Failed to load image ... for layer blush。

        基础 canary 也会请求 img/face/default/default/mouth*.png，而资源包
        只提供 img/face/default/mouth*.png；这些 mouth aliases 与 AU 无关，
        所以对所有构建补齐。
        """
        source_dir = self.img_path / "face" / "default"
        target_dir = source_dir / "default"
        if not source_dir.exists():
            return []

        patterns = ["mouth*.png"]
        if self._has_au_feature():
            patterns.append("blush*.png")

        copied = []
        for pattern in patterns:
            for source in sorted(
                source_dir.glob(pattern), key=lambda item: item.name.lower()
            ):
                if not source.is_file():
                    continue

                target = target_dir / source.name
                if target.exists():
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(target.relative_to(self.img_path).as_posix())

        if copied:
            logger.info(
                "Face compatibility aliases created: %s", ", ".join(copied)
            )

        return copied

    def _modloader_mod_path_for_injection(self, mod_config, mod_path: Path) -> Path:
        """Return the payload path to inject, applying build-local hotfixes."""
        if mod_config.cache_name != MORE_LOVE_CACHE_NAME:
            return mod_path

        patched_path = (
            self.paths.temp_dir
            / f"{MORE_LOVE_CACHE_NAME}-{self.pack_type}-{self.task.code_str}.patched.mod.zip"
        )
        patch_result = patch_more_love_drag_event_handlers(mod_path, patched_path)
        status = str(patch_result.get("status") or "unknown")
        if status == "patched":
            logger.info("More Love drag event compatibility patch applied")
            return patched_path
        if status != "already_patched":
            logger.warning(
                "More Love drag event compatibility patch skipped: %s",
                status,
            )
        return mod_path

    def _inject_modloader_mods(self) -> list[str]:
        """
        注入 modloader mod 到 HTML

        根据配置，将匹配当前 mod_code 的 modloader mod 注入到
        HTML 的 modDataValueZipList 中。

        Returns:
            注入的MOD名称列表
        """
        build_config = load_build_config()
        if not build_config.modloader_mods:
            return []

        config_loader = get_config_loader()
        mod_paths = []
        applied = []

        for mod_config in build_config.modloader_mods:
            if not mod_config.enabled:
                continue

            matching_features = []
            for feature_id in mod_config.required_feature_ids:
                feature = config_loader.get_feature_by_id(feature_id)
                if not feature:
                    logger.warning(f"未找到 feature: {feature_id}")
                    continue
                if self.mod_code & feature.bit:
                    matching_features.append(feature)

            if matching_features:
                mod_path = self.paths.get_mod_cache_path(mod_config.cache_name)
                if mod_path.exists():
                    mod_paths.append(
                        self._modloader_mod_path_for_injection(mod_config, mod_path)
                    )
                    if mod_config.name:
                        applied.append(mod_config.name)
                    elif len(matching_features) == 1:
                        applied.append(matching_features[0].name)
                    else:
                        applied.append(mod_config.key or mod_config.asset_pattern)
                else:
                    logger.warning(f"mod 文件不存在: {mod_path}")

        if mod_paths:
            injector = ModInjector(self.paths)
            injector.add_mods(self.html_path, mod_paths)

        return applied

    def _inject_lyra_mod(self):
        """
        构建并注入 Lyra 信息 mod

        从 versions.json 加载完整版本信息（包含 prepare 和 warmup 阶段），
        构建 Lyra mod 并注入到 HTML 中。
        """
        # 加载完整版本信息
        registry = VersionRegistry.load(self.paths.versions_file)

        # 获取 MOD 组合后缀
        mod_suffix = self.mod_code.get_suffix()

        # 构建 Lyra mod（使用任务唯一路径避免并行竞态）
        lyra_mod_path = (
            self.paths.temp_dir / f"Lyra-{self.pack_type}-{self.task.code_str}.mod.zip"
        )
        build_lyra_mod(lyra_mod_path, self.task.version, list(registry), mod_suffix)

        # 注入到 HTML
        injector = ModInjector(self.paths)
        injector.add_mods(self.html_path, [lyra_mod_path])

    @abstractmethod
    def build(self) -> BuildResult:
        """执行构建"""
        pass


class ZipBuilder(PackageBuilder):
    """ZIP包构建器"""

    @property
    def pack_type(self) -> str:
        return "zip"

    @property
    def img_path(self) -> Path:
        return self.work_dir / "img"

    @property
    def html_path(self) -> Path:
        html_files = list(self.work_dir.glob("*.html"))
        if html_files:
            return html_files[0]
        return self.work_dir / "index.html"

    def build(self) -> BuildResult:
        """构建ZIP包"""
        try:
            calculator = CombinationCalculator()
            combo_name = calculator._get_display_name(self.task.mod_code)
            logger.info(f"构建 ZIP: {self.task.code_str} ({combo_name})")
        except Exception:
            logger.info(f"构建 ZIP: {self.task.code_str}")

        try:
            # 获取基包路径
            base_zip = self.paths.get_base_zip(self.task.is_polyfill)
            if not base_zip.exists():
                return BuildResult(success=False, error=f"基包不存在: {base_zip}")

            # 清理并创建工作目录
            if self.work_dir.exists():
                safe_remove(self.work_dir)
            self.work_dir.mkdir(parents=True)

            # 解压基包
            extract_zip(base_zip, self.work_dir)

            # 应用美化
            applied_mods = self._apply_beautify()

            if self._apply_au_face_compatibility_aliases():
                applied_mods.append("AU face compatibility aliases")

            # 注入 modloader mod
            applied_mods.extend(self._inject_modloader_mods())

            # 注入 Lyra 信息 mod
            self._inject_lyra_mod()

            # 生成输出文件名
            output_name = self.get_output_name()
            output_path = self.paths.output_dir / output_name

            # 创建ZIP
            create_zip(self.work_dir, output_path)

            # 清理工作目录
            safe_remove(self.work_dir)

            logger.info(f"  完成: {output_name}")

            return BuildResult(
                success=True,
                output_path=output_path,
                output_name=output_name,
                applied_mods=applied_mods,
            )

        except Exception as e:
            logger.error(f"ZIP构建失败: {e}")
            if self.work_dir.exists():
                safe_remove(self.work_dir)
            return BuildResult(success=False, error=str(e))


class ApkBuilder(PackageBuilder):
    """APK包构建器"""

    # 签名配置
    KEYSTORE_PATH = Path("dol.jks")
    KEYSTORE_ALIAS = "dol"
    KEYSTORE_PASSWORD = "dolchs"

    @property
    def pack_type(self) -> str:
        return "apk"

    @property
    def img_path(self) -> Path:
        return self.work_dir / "assets" / "www" / "img"

    @property
    def html_path(self) -> Path:
        return self.work_dir / "assets" / "www" / "index.html"

    def build(self) -> BuildResult:
        """构建APK包"""
        try:
            calculator = CombinationCalculator()
            combo_name = calculator._get_display_name(self.task.mod_code)
            logger.info(f"构建 APK: {self.task.code_str} ({combo_name})")
        except Exception:
            logger.info(f"构建 APK: {self.task.code_str}")

        try:
            # 获取已解包APK目录
            apk_dir = self.paths.get_apk_dir(self.task.is_polyfill)
            if not apk_dir.exists():
                return BuildResult(success=False, error=f"APK目录不存在: {apk_dir}")

            # 清理并创建工作目录
            if self.work_dir.exists():
                safe_remove(self.work_dir)
            self.work_dir.mkdir(parents=True)

            # 复制已解包APK目录
            copy_directory(apk_dir, self.work_dir)

            # 应用美化
            applied_mods = self._apply_beautify()

            if self._apply_au_face_compatibility_aliases():
                applied_mods.append("AU face compatibility aliases")

            # 注入 modloader mod
            applied_mods.extend(self._inject_modloader_mods())

            # 注入 Lyra 信息 mod
            self._inject_lyra_mod()

            # 重新编译
            tmp_apk = self._recompile()

            # 签名
            signed_apk = self._sign(tmp_apk)

            # 生成输出文件名
            output_name = self.get_output_name()
            output_path = self.paths.output_dir / output_name

            # 移动到输出目录
            shutil.move(str(signed_apk), str(output_path))

            # 清理
            safe_remove(tmp_apk)
            safe_remove(
                self.paths.get_signed_dir(self.task.mod_code, self.task.is_polyfill)
            )
            safe_remove(self.work_dir)

            logger.info(f"  完成: {output_name}")

            return BuildResult(
                success=True,
                output_path=output_path,
                output_name=output_name,
                applied_mods=applied_mods,
            )

        except Exception as e:
            logger.error(f"APK构建失败: {e}")
            if self.work_dir.exists():
                safe_remove(self.work_dir)
            return BuildResult(success=False, error=str(e))

    def _recompile(self) -> Path:
        """重新编译APK"""
        logger.debug("重新编译APK...")

        apktool_path = self.paths.apktool_path
        tmp_apk = self.paths.get_temp_apk(self.task.mod_code, self.task.is_polyfill)

        run_command(
            [
                "java",
                "-jar",
                str(apktool_path),
                "b",
                str(self.work_dir),
                "-o",
                str(tmp_apk),
            ]
        )

        return tmp_apk

    def _sign(self, apk_path: Path) -> Path:
        """签名APK"""
        logger.debug("签名APK...")

        apksign_path = self.paths.apksign_path
        signed_dir = self.paths.get_signed_dir(
            self.task.mod_code, self.task.is_polyfill
        )
        signed_dir.mkdir(parents=True, exist_ok=True)

        run_command(
            [
                "java",
                "-jar",
                str(apksign_path),
                "-a",
                str(apk_path),
                "--ks",
                str(self.KEYSTORE_PATH),
                "--ksAlias",
                self.KEYSTORE_ALIAS,
                "--ksKeyPass",
                self.KEYSTORE_PASSWORD,
                "--ksPass",
                self.KEYSTORE_PASSWORD,
                "-o",
                str(signed_dir),
            ]
        )

        # 查找签名后的APK
        for f in signed_dir.iterdir():
            if f.suffix == ".apk":
                return f

        raise FileNotFoundError("签名后的APK未找到")


def create_builder(task: BuildTask) -> PackageBuilder:
    """
    创建打包构建器

    Args:
        task: 构建任务

    Returns:
        对应类型的构建器
    """
    builders = {
        "zip": ZipBuilder,
        "apk": ApkBuilder,
    }

    builder_class = builders.get(task.pack_type.lower())
    if not builder_class:
        raise ValueError(f"不支持的包类型: {task.pack_type}")

    return builder_class(task)


def build_single(task: BuildTask) -> BuildResult:
    """
    执行单个构建

    Args:
        task: 构建任务

    Returns:
        构建结果
    """
    builder = create_builder(task)
    return builder.build()
