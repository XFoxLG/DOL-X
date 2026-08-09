"""
简化构建模块

假设所有资源已通过 warmup 预热，只负责资源复制和打包。
专为CI流程设计，不包含资源下载逻辑。
"""

import html
import json
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
from .compatibility import (
    AU_FACE_VARIANT_SELECTION_KEY,
    MORE_LOVE_DRAG_PATCH_KEY,
    DOLI_FLOAT_ICON_PATCH_KEY,
    MAPLEBIRCH_BASEHEAD_FALLBACK_PATCH_KEY,
    MAPLEBIRCH_PET_PASSAGE_REMOUNT_PATCH_KEY,
    compatibility_source_errors,
    compatibility_surface_by_key,
    is_patch_success_status,
)
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


DOLI_CACHE_NAME = "doli"
DOLI_FLOAT_ICON_MEMBER = "dist/DOLI.js"
# DOLI v0.2.3 硬编码悬浮按钮图标为旧版 DoL 的 img/ui/sym_awareness.png（下划线）。
# 游戏 0.5.9.8+ 把全部 sym_*.png 重命名为 sym-*.png（连字符），旧路径不再存在，
# 于是悬浮窗图标 404 图裂。这里在构建期把该引用改成当前命名，恢复图标。
# 只改这一个字符串，不动其它 UI 图标（options.png 等命名未变，仍有效）。
DOLI_FLOAT_ICON_OLD = "img/ui/sym_awareness.png"
DOLI_FLOAT_ICON_NEW = "img/ui/sym-awareness.png"


def patch_doli_float_icon_path(
    source_path: Path,
    target_path: Path,
) -> dict[str, object]:
    """Rewrite DOLI's hardcoded float-button icon to the current DoL asset name."""
    result: dict[str, object] = {
        "applied": False,
        "member": DOLI_FLOAT_ICON_MEMBER,
        "source": str(source_path),
        "target": str(target_path),
    }

    try:
        with zipfile.ZipFile(source_path, "r") as source_zip:
            if DOLI_FLOAT_ICON_MEMBER not in source_zip.namelist():
                result["status"] = "missing_patch_member"
                return result

            original_script = source_zip.read(DOLI_FLOAT_ICON_MEMBER).decode(
                "utf-8",
                errors="replace",
            )
            if DOLI_FLOAT_ICON_OLD not in original_script:
                result["status"] = (
                    "already_patched"
                    if DOLI_FLOAT_ICON_NEW in original_script
                    else "patch_needle_not_found"
                )
                return result

            patched_script = original_script.replace(
                DOLI_FLOAT_ICON_OLD, DOLI_FLOAT_ICON_NEW
            )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_path, "w") as target_zip:
                for member in source_zip.infolist():
                    data = source_zip.read(member)
                    if member.filename == DOLI_FLOAT_ICON_MEMBER:
                        data = patched_script.encode("utf-8")
                    target_zip.writestr(member, data)
    except zipfile.BadZipFile as exc:
        result["status"] = "not_zip"
        result["error"] = str(exc)
        return result

    result["applied"] = True
    result["status"] = "patched"
    return result


MAPLEBIRCH_CACHE_NAME = "maplebirch"
MAPLEBIRCH_BASEHEAD_MEMBER = "dist/inject_early.js"
MAPLEBIRCH_BASEHEAD_OLD = (
    'basehead:{srcfn:e=>e.mannequin?"img/body/mannequin/base-head.png":'
    'aO([`img/face/${e.facestyle}/base-head.png`,"img/body/base-head.png"])}'
)

# The replacement has to call .has() on the Set that Maplebirch's own aO() helper
# consults.  That Set's minified name is NOT stable across upstream builds: it was
# aP in v4.1.13 and aI in v4.1.14, where aP became an unrelated transformation
# table.  Hardcoding the name shipped a patch whose every call threw
# "TypeError: aP.has is not a function", so resolve the real identifier out of the
# asset instead and fail closed when it cannot be proven.
MAPLEBIRCH_FACE_INDEX_PATTERN = re.compile(
    r"let\s+(?P<identifier>[A-Za-z_$][\w$]*)\s*=\s*new Set;\s*"
    r"function\s+aO\s*\(\s*e\s*\)\s*\{\s*let\s+t\s*=\s*e\.find\(\s*e\s*=>\s*(?P=identifier)\.has\(\s*e\s*\)\s*\)"
)


def _maplebirch_basehead_replacement(face_index_identifier: str) -> str:
    """Build the basehead replacement bound to the resolved face-index Set."""
    candidate = "`img/face/${e.facestyle}/base-head.png`"
    return (
        'basehead:{srcfn:e=>e.mannequin?"img/body/mannequin/base-head.png":'
        f"{face_index_identifier}.has({candidate})?"
        f'{candidate}:"img/body/base-head.png"}}'
    )


def resolve_maplebirch_face_index_identifier(script: str) -> str | None:
    """Return the minified name of the Set that Maplebirch's aO() helper reads.

    Returns None when the surrounding helper does not match, which the caller must
    treat as a fail-closed condition rather than guessing an identifier.
    """
    match = MAPLEBIRCH_FACE_INDEX_PATTERN.search(script)
    return match.group("identifier") if match else None


# SugarCube rebuilds StoryFooter on every passage render, so the
# <div id="maplebirch-character-pet"> container the framework mounted its canvas
# into is replaced by a fresh empty node. Maplebirch only re-syncs the pet from
# its wrapped <<updatesidebarimg>> macro, which is not guaranteed to run on a
# passage change, so the pet stays invisible while the framework still holds the
# detached old container.
#
# The remount must go through <<updatesidebarimg>> rather than calling pet.sync()
# directly: Pet.draw() reads clothing from Renderer.CanvasModelCaches.main.sidebar
# and silently falls back to model.defaultOptions() (an undressed model) when that
# cache is not populated yet. Verified on MuMu 12 - a direct pet.sync() on a fresh
# passage produced 16316 opaque pixels with no sidebar cache, while the macro path
# produced 17588 with clothing layers present. The framework already wraps that
# macro to call pet.sync() after rendering the sidebar, so reusing it keeps the
# pet's appearance identical to upstream behaviour.
MAPLEBIRCH_PET_REMOUNT_MEMBER = "dist/inject_early.js"
MAPLEBIRCH_PET_REMOUNT_OLD = (
    'preInit(){let{core:e,pet:t}=this;e.once(":storyready",()=>{'
    'let n=e.SugarCube.Macro.get("updatesidebarimg");'
    'n&&e.tool.macro.define("updatesidebarimg",function(){'
    'n.handler.call(this),t.sync()})})'
)
MAPLEBIRCH_PET_REMOUNT_NEW = (
    'preInit(){let{core:e,pet:t}=this;e.once(":storyready",()=>{'
    'let n=e.SugarCube.Macro.get("updatesidebarimg");'
    'n&&e.tool.macro.define("updatesidebarimg",function(){'
    'n.handler.call(this),t.sync()})}),'
    'e.on(":passagedisplay",()=>{try{'
    'if(!V.options?.maplebirch?.character?.pet?.enabled)return;'
    'let r=document.getElementById("maplebirch-character-pet");'
    'if(r&&0===r.childElementCount)$.wiki("<<updatesidebarimg>>")'
    '}catch(a){}},"dolxPetRemountAfterPassageDisplay")'
)

MAPLEBIRCH_PET_REMOUNT_MARKER = "dolxPetRemountAfterPassageDisplay"

# DoL assumes every face style has a variant whose code value is "default".
# Third-party AU face styles instead register their real image-directory names,
# so DoL's three face-style UIs create an invalid style/default pair until the
# player also picks a demeanour. These replacements must run after ModI18N: a
# build-time edit to the original passage shifts ModI18N's position-indexed
# rules and leaves the whole character-creation settings passage in English.
AU_FACE_VARIANT_FALLBACK_EXPRESSION = (
    '<<run $facevariant = '
    'Object.values(setup.faceVariantOptions[$facestyle] || {})[0] || "default">>'
)
AU_FACE_VARIANT_SWITCH_NEEDLES = (
    (
        '<<set $facestyle to _facestyle>>\n'
        '\t\t\t<<set $facevariant to "default">>',
        '<<set $facestyle to _facestyle>>\n'
        f'\t\t\t{AU_FACE_VARIANT_FALLBACK_EXPRESSION}',
    ),
    (
        '<<set $facestyle to _faceStyles[_i]>>\n'
        '\t\t\t\t\t<<set $facevariant to "default">>',
        '<<set $facestyle to _faceStyles[_i]>>\n'
        f'\t\t\t\t\t{AU_FACE_VARIANT_FALLBACK_EXPRESSION}',
    ),
    (
        '<<set $facestyle to _styleValue>>\n'
        '\t\t\t\t\t\t\t<<set $facevariant to "default">>',
        '<<set $facestyle to _styleValue>>\n'
        f'\t\t\t\t\t\t\t{AU_FACE_VARIANT_FALLBACK_EXPRESSION}',
    ),
)
AU_FACE_VARIANT_MIGRATION_EXPRESSION = (
    '<<run (() => {'
    'const legalVariants = Object.values('
    'setup.faceVariantOptions[V.facestyle] || {});'
    'if (legalVariants.length && '
    '!legalVariants.includes(V.facevariant)) '
    'V.facevariant = legalVariants[0];'
    '})()>>'
)
AU_FACE_VARIANT_MIGRATION_OLD = (
    '/* Code that should not be moved into a check like above */\n'
    '\t<<set $runWardrobeSanityChecker to true>>'
)
AU_FACE_VARIANT_MIGRATION_NEW = (
    '/* Code that should not be moved into a check like above */\n'
    f'\t{AU_FACE_VARIANT_MIGRATION_EXPRESSION}\n'
    '\t<<set $runWardrobeSanityChecker to true>>'
)

AU_FACE_VARIANT_PASSAGE_PATCH_RULES = (
    ("Widgets Mirror", *AU_FACE_VARIANT_SWITCH_NEEDLES[0]),
    ("Cheats", *AU_FACE_VARIANT_SWITCH_NEEDLES[1]),
    ("Widgets Settings", *AU_FACE_VARIANT_SWITCH_NEEDLES[2]),
    (
        "Widgets variablesVersionUpdate",
        AU_FACE_VARIANT_MIGRATION_OLD,
        AU_FACE_VARIANT_MIGRATION_NEW,
    ),
)
AU_FACE_VARIANT_HTML_SWITCH_NEEDLES = tuple(
    (
        html.escape(old_context, quote=False),
        html.escape(new_context, quote=False),
    )
    for old_context, new_context in AU_FACE_VARIANT_SWITCH_NEEDLES
)
AU_FACE_VARIANT_HTML_MIGRATION_OLD = html.escape(
    AU_FACE_VARIANT_MIGRATION_OLD,
    quote=False,
)
AU_FACE_VARIANT_HTML_MIGRATION_NEW = html.escape(
    AU_FACE_VARIANT_MIGRATION_NEW,
    quote=False,
)

MAPLEBIRCH_AU_FACE_VARIANT_MEMBER = "dist/inject_early.js"
MAPLEBIRCH_AU_FACE_VARIANT_MARKER = "dolxAuFaceVariantAfterI18n"
MAPLEBIRCH_AU_FACE_VARIANT_RULES_JSON = json.dumps(
    AU_FACE_VARIANT_PASSAGE_PATCH_RULES,
    ensure_ascii=False,
    separators=(",", ":"),
)
MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD = (
    'n.content=e.replace(n.content,a,"FaceStyle"),r.set(t,n)}'
    "n.passageDataItems.back2Array(),"
    "e.modUtils.replaceFollowSC2DataInfo(n,t)}"
)
MAPLEBIRCH_AU_FACE_VARIANT_RUNTIME_PATCH = (
    f'(()=>{{const patchName="{MAPLEBIRCH_AU_FACE_VARIANT_MARKER}",'
    f"patchRules={MAPLEBIRCH_AU_FACE_VARIANT_RULES_JSON};"
    "for(const[passageName,oldContext,newContext]of patchRules){"
    "const passage=r.get(passageName);"
    "if(!passage?.content)"
    "throw new Error(`${patchName}: missing passage ${passageName}`);"
    "const contextCount=passage.content.split(oldContext).length-1;"
    "if(1!==contextCount)"
    "throw new Error(`${patchName}: ${passageName} context count ${contextCount}`);"
    "passage.content=passage.content.replace(oldContext,newContext);"
    "r.set(passageName,passage)}})();"
)
MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW = (
    'n.content=e.replace(n.content,a,"FaceStyle"),r.set(t,n)};'
    f"{MAPLEBIRCH_AU_FACE_VARIANT_RUNTIME_PATCH}"
    "n.passageDataItems.back2Array(),"
    "e.modUtils.replaceFollowSC2DataInfo(n,t)}"
)


def patch_maplebirch_au_face_variant_selection(
    source_path: Path,
    target_path: Path,
) -> dict[str, object]:
    """Patch final translated passages instead of ModI18N's source HTML."""
    result: dict[str, object] = {
        "applied": False,
        "member": MAPLEBIRCH_AU_FACE_VARIANT_MEMBER,
        "source": str(source_path),
        "target": str(target_path),
    }

    try:
        with zipfile.ZipFile(source_path, "r") as source_zip:
            if MAPLEBIRCH_AU_FACE_VARIANT_MEMBER not in source_zip.namelist():
                result["status"] = "missing_patch_member"
                return result

            original_script = source_zip.read(
                MAPLEBIRCH_AU_FACE_VARIANT_MEMBER
            ).decode("utf-8", errors="replace")
            if MAPLEBIRCH_AU_FACE_VARIANT_MARKER in original_script:
                marker_count = original_script.count(
                    MAPLEBIRCH_AU_FACE_VARIANT_MARKER
                )
                complete_patch_count = original_script.count(
                    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW
                )
                obsolete_insertion_count = original_script.count(
                    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD
                )
                if (
                    marker_count == 1
                    and complete_patch_count == 1
                    and obsolete_insertion_count == 0
                ):
                    result["status"] = "already_patched"
                else:
                    result["status"] = "partial_patch"
                    result["marker_count"] = marker_count
                    result["complete_patch_count"] = complete_patch_count
                    result["obsolete_insertion_count"] = obsolete_insertion_count
                return result

            insertion_count = original_script.count(
                MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD
            )
            if insertion_count != 1:
                result["status"] = "patch_needle_not_found"
                result["needle_count"] = insertion_count
                return result

            patched_script = original_script.replace(
                MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
                MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW,
                1,
            )
            if (
                patched_script.count(MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW)
                != 1
                or patched_script.count(MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD)
                != 0
            ):
                result["status"] = "patch_verification_failed"
                return result

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_path, "w") as target_zip:
                for member in source_zip.infolist():
                    data = source_zip.read(member)
                    if member.filename == MAPLEBIRCH_AU_FACE_VARIANT_MEMBER:
                        data = patched_script.encode("utf-8")
                    target_zip.writestr(member, data)
    except zipfile.BadZipFile as exc:
        result["status"] = "not_zip"
        result["error"] = str(exc)
        return result

    result["applied"] = True
    result["status"] = "patched"
    return result


def patch_maplebirch_basehead_fallback(
    source_path: Path,
    target_path: Path,
) -> dict[str, object]:
    """Use Maplebirch's completed face index for basehead fallback selection."""
    result: dict[str, object] = {
        "applied": False,
        "member": MAPLEBIRCH_BASEHEAD_MEMBER,
        "source": str(source_path),
        "target": str(target_path),
    }

    try:
        with zipfile.ZipFile(source_path, "r") as source_zip:
            if MAPLEBIRCH_BASEHEAD_MEMBER not in source_zip.namelist():
                result["status"] = "missing_patch_member"
                return result

            original_script = source_zip.read(MAPLEBIRCH_BASEHEAD_MEMBER).decode(
                "utf-8",
                errors="replace",
            )
            face_index_identifier = resolve_maplebirch_face_index_identifier(
                original_script
            )
            if MAPLEBIRCH_BASEHEAD_OLD not in original_script:
                already_patched = bool(
                    face_index_identifier
                    and _maplebirch_basehead_replacement(face_index_identifier)
                    in original_script
                )
                result["status"] = (
                    "already_patched" if already_patched else "patch_needle_not_found"
                )
                return result

            # Fail closed: without a proven face-index Set the replacement would
            # emit a .has() call against whatever that name happens to mean in this
            # build, which is exactly how the aP -> aI rename shipped a basehead
            # srcfn that threw on every render.
            if not face_index_identifier:
                result["status"] = "face_index_identifier_unresolved"
                return result

            result["face_index_identifier"] = face_index_identifier
            patched_script = original_script.replace(
                MAPLEBIRCH_BASEHEAD_OLD,
                _maplebirch_basehead_replacement(face_index_identifier),
                1,
            )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_path, "w") as target_zip:
                for member in source_zip.infolist():
                    data = source_zip.read(member)
                    if member.filename == MAPLEBIRCH_BASEHEAD_MEMBER:
                        data = patched_script.encode("utf-8")
                    target_zip.writestr(member, data)
    except zipfile.BadZipFile as exc:
        result["status"] = "not_zip"
        result["error"] = str(exc)
        return result

    result["applied"] = True
    result["status"] = "patched"
    return result


def patch_maplebirch_pet_passage_remount(
    source_path: Path,
    target_path: Path,
) -> dict[str, object]:
    """Re-sync the Maplebirch desktop pet after each passage rebuilds the footer."""
    result: dict[str, object] = {
        "applied": False,
        "member": MAPLEBIRCH_PET_REMOUNT_MEMBER,
        "source": str(source_path),
        "target": str(target_path),
    }

    try:
        with zipfile.ZipFile(source_path, "r") as source_zip:
            if MAPLEBIRCH_PET_REMOUNT_MEMBER not in source_zip.namelist():
                result["status"] = "missing_patch_member"
                return result

            original_script = source_zip.read(MAPLEBIRCH_PET_REMOUNT_MEMBER).decode(
                "utf-8",
                errors="replace",
            )
            # The replacement keeps the original preInit() text and appends the
            # :passagedisplay subscription, so the marker - not the needle - is
            # what distinguishes an already patched payload.
            if MAPLEBIRCH_PET_REMOUNT_MARKER in original_script:
                result["status"] = "already_patched"
                return result

            if MAPLEBIRCH_PET_REMOUNT_OLD not in original_script:
                result["status"] = "patch_needle_not_found"
                return result

            patched_script = original_script.replace(
                MAPLEBIRCH_PET_REMOUNT_OLD,
                MAPLEBIRCH_PET_REMOUNT_NEW,
                1,
            )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_path, "w") as target_zip:
                for member in source_zip.infolist():
                    data = source_zip.read(member)
                    if member.filename == MAPLEBIRCH_PET_REMOUNT_MEMBER:
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

        # 添加MOD后缀（精简为体型标识，避免文件名冗长；完整 mod 组成见下载说明页）
        mod_suffix = self.mod_code.get_short_suffix()
        if mod_suffix:
            prefix += f"-{mod_suffix}"

        # 不再追加 commit hash：稳定版以 tag 为身份标识，4 个体型标已足以区分同一
        # tag 内的产物；而 hash 会让文件名变长，且与下载说明页 (gen_page.get_filename)
        # 不一致导致链接 404。两处文件名生成保持一致：prefix + 体型标 + 日期。
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

    def _validate_au_face_variant_source(self) -> dict[str, object]:
        """Fail closed if the untranslated DoL face passages drift upstream."""
        result: dict[str, object] = {
            "applied": False,
            "target": str(self.html_path),
        }
        if not self._has_au_feature():
            result["status"] = "not_applicable"
            return result

        if not self.html_path.exists():
            raise RuntimeError(
                f"AU face variant source validation failed: missing HTML {self.html_path}"
            )

        content = self.html_path.read_bytes()
        expected_switch_count = len(AU_FACE_VARIANT_HTML_SWITCH_NEEDLES)
        old_switch_context_counts = [
            content.count(old_text.encode("utf-8"))
            for old_text, _new_text in AU_FACE_VARIANT_HTML_SWITCH_NEEDLES
        ]
        new_switch_context_counts = [
            content.count(new_text.encode("utf-8"))
            for _old_text, new_text in AU_FACE_VARIANT_HTML_SWITCH_NEEDLES
        ]
        migration_old_count = content.count(
            AU_FACE_VARIANT_HTML_MIGRATION_OLD.encode("utf-8")
        )
        migration_new_count = content.count(
            AU_FACE_VARIANT_HTML_MIGRATION_NEW.encode("utf-8")
        )
        source_is_unmodified = (
            old_switch_context_counts == [1] * expected_switch_count
            and new_switch_context_counts == [0] * expected_switch_count
            and migration_old_count == 1
            and migration_new_count == 0
        )
        if not source_is_unmodified:
            raise RuntimeError(
                "AU face variant source validation failed: translated input drift "
                "or obsolete build-time patch detected; "
                f"legacy_switch_contexts={old_switch_context_counts}, "
                f"patched_switch_contexts={new_switch_context_counts}, "
                f"legacy_migration_context={migration_old_count}/1, "
                f"patched_migration_context={migration_new_count}/0"
            )

        result["status"] = "validated"
        return result

    def _modloader_mod_path_for_injection(self, mod_config, mod_path: Path) -> Path:
        """Return the payload path to inject, applying build-local hotfixes."""
        if mod_config.cache_name == MORE_LOVE_CACHE_NAME:
            return self._patch_more_love_payload(mod_config, mod_path)
        if mod_config.cache_name == DOLI_CACHE_NAME:
            return self._patch_doli_payload(mod_config, mod_path)
        if mod_config.cache_name == MAPLEBIRCH_CACHE_NAME:
            return self._patch_maplebirch_payload(mod_config, mod_path)
        return mod_path

    def _patch_more_love_payload(self, mod_config, mod_path: Path) -> Path:
        """Apply the More Love drag-event hardening patch (fail-closed)."""
        patch_surface = compatibility_surface_by_key(MORE_LOVE_DRAG_PATCH_KEY)
        source_errors = compatibility_source_errors(patch_surface, mod_config)
        if source_errors:
            raise RuntimeError(
                "More Love drag event compatibility patch source mismatch: " + "; ".join(source_errors)
            )

        patched_path = (
            self.paths.temp_dir
            / f"{MORE_LOVE_CACHE_NAME}-{self.pack_type}-{self.task.code_str}.patched.mod.zip"
        )
        patch_result = patch_more_love_drag_event_handlers(mod_path, patched_path)
        status = str(patch_result.get("status") or "unknown")
        if status == "patched":
            logger.info("More Love drag event compatibility patch applied")
            return patched_path
        if is_patch_success_status(status):
            logger.info("More Love drag event compatibility patch already present")
            return mod_path
        raise RuntimeError(f"More Love drag event compatibility patch failed: {status}")

    def _patch_doli_payload(self, mod_config, mod_path: Path) -> Path:
        """Rewrite DOLI's stale float-button icon path (fail-closed)."""
        patch_surface = compatibility_surface_by_key(DOLI_FLOAT_ICON_PATCH_KEY)
        source_errors = compatibility_source_errors(patch_surface, mod_config)
        if source_errors:
            raise RuntimeError(
                "DOLI float icon compatibility patch source mismatch: " + "; ".join(source_errors)
            )

        patched_path = (
            self.paths.temp_dir
            / f"{DOLI_CACHE_NAME}-{self.pack_type}-{self.task.code_str}.patched.mod.zip"
        )
        patch_result = patch_doli_float_icon_path(mod_path, patched_path)
        status = str(patch_result.get("status") or "unknown")
        if status == "patched":
            logger.info("DOLI float icon compatibility patch applied")
            return patched_path
        if is_patch_success_status(status):
            logger.info("DOLI float icon compatibility patch already present")
            return mod_path
        raise RuntimeError(f"DOLI float icon compatibility patch failed: {status}")

    def _patch_maplebirch_payload(self, mod_config, mod_path: Path) -> Path:
        """Make Maplebirch choose the indexed basehead fallback synchronously."""
        patch_surface = compatibility_surface_by_key(
            MAPLEBIRCH_BASEHEAD_FALLBACK_PATCH_KEY
        )
        source_errors = compatibility_source_errors(patch_surface, mod_config)
        if source_errors:
            raise RuntimeError(
                "Maplebirch basehead compatibility patch source mismatch: "
                + "; ".join(source_errors)
            )

        patched_path = (
            self.paths.temp_dir
            / f"{MAPLEBIRCH_CACHE_NAME}-{self.pack_type}-{self.task.code_str}.patched.mod.zip"
        )
        patch_result = patch_maplebirch_basehead_fallback(mod_path, patched_path)
        status = str(patch_result.get("status") or "unknown")
        if status == "patched":
            logger.info("Maplebirch basehead compatibility patch applied")
            return self._patch_maplebirch_pet_remount(mod_config, patched_path)
        if is_patch_success_status(status):
            logger.info("Maplebirch basehead compatibility patch already present")
            return self._patch_maplebirch_pet_remount(mod_config, mod_path)
        raise RuntimeError(
            f"Maplebirch basehead compatibility patch failed: {status}"
        )

    def _patch_maplebirch_pet_remount(self, mod_config, mod_path: Path) -> Path:
        """Re-sync the desktop pet after a passage rebuilds the footer container."""
        patch_surface = compatibility_surface_by_key(
            MAPLEBIRCH_PET_PASSAGE_REMOUNT_PATCH_KEY
        )
        source_errors = compatibility_source_errors(patch_surface, mod_config)
        if source_errors:
            raise RuntimeError(
                "Maplebirch pet remount compatibility patch source mismatch: "
                + "; ".join(source_errors)
            )

        patched_path = (
            self.paths.temp_dir
            / f"{MAPLEBIRCH_CACHE_NAME}-{self.pack_type}-{self.task.code_str}.pet-remount.mod.zip"
        )
        patch_result = patch_maplebirch_pet_passage_remount(mod_path, patched_path)
        status = str(patch_result.get("status") or "unknown")
        if status == "patched":
            logger.info("Maplebirch pet remount compatibility patch applied")
            return self._patch_maplebirch_au_face_variants(
                mod_config,
                patched_path,
            )
        if is_patch_success_status(status):
            logger.info("Maplebirch pet remount compatibility patch already present")
            return self._patch_maplebirch_au_face_variants(mod_config, mod_path)
        raise RuntimeError(
            f"Maplebirch pet remount compatibility patch failed: {status}"
        )

    def _patch_maplebirch_au_face_variants(
        self,
        mod_config,
        mod_path: Path,
    ) -> Path:
        """Repair AU style/variant pairs after ModI18N translates passages."""
        if not self._has_au_feature():
            return mod_path

        patch_surface = compatibility_surface_by_key(
            AU_FACE_VARIANT_SELECTION_KEY
        )
        source_errors = compatibility_source_errors(patch_surface, mod_config)
        if source_errors:
            raise RuntimeError(
                "Maplebirch AU face variant compatibility patch source mismatch: "
                + "; ".join(source_errors)
            )

        patched_path = (
            self.paths.temp_dir
            / f"{MAPLEBIRCH_CACHE_NAME}-{self.pack_type}-{self.task.code_str}.au-face.mod.zip"
        )
        patch_result = patch_maplebirch_au_face_variant_selection(
            mod_path,
            patched_path,
        )
        status = str(patch_result.get("status") or "unknown")
        if status == "patched":
            logger.info("Maplebirch AU face variant compatibility patch applied")
            return patched_path
        if is_patch_success_status(status):
            logger.info(
                "Maplebirch AU face variant compatibility patch already present"
            )
            return mod_path
        raise RuntimeError(
            "Maplebirch AU face variant compatibility patch failed: "
            f"{status}"
        )

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
                    raise RuntimeError(
                        "required mod payload cache is missing: "
                        f"{mod_config.cache_name}: {mod_path}"
                    )

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

            self._validate_au_face_variant_source()

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

            self._validate_au_face_variant_source()

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
