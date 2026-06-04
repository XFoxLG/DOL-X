#!/usr/bin/env python3
"""
Audit cheatExtended as a replacement candidate for the legacy cheat stack.

This script does not enable cheatExtended. It downloads the latest release,
parses boot.json/readme.md, and writes an advisory report about dependencies,
coverage, overlap, and coupling with the current DOL-X configuration.
"""

import argparse
import hashlib
import json
import os
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import requests

# Allow running this script directly from the repository root or CI.
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lyra.config_loader import load_build_config


REPO = "chris81605/Degrees-of-Lewdity_Cheat_Extended"
ASSET_NAME = "cheat_extended.mod.zip"

LEGACY_BASE_KEYS = {"cheat", "csd"}
LEGACY_MODLOADER_KEYS = {"bjx_word_unlock", "bjx_portable_word", "bccm"}
FRAMEWORK_REPOS = {
    "MaplebirchLeaf/SCML-DOL-maplebirchframework": "maplebirch >= 3.0.0",
    "emicoto/SCMLSimpleFramework": "Simple Frameworks >= 2.0.5",
}
CORE_PATCH_PASSAGES = {
    "Widgets",
    "StoryCaption",
    "Widgets State Man",
    "Widgets Market",
    "Widgets Dance Audience",
    "Widgets Orgasm",
    "Pregnancy",
    "FeatsUI",
}


def safe_print(message: str = "") -> None:
    """Print safely on Windows consoles with non-UTF-8 encodings."""
    encoding = sys.stdout.encoding or "utf-8"
    print(message.encode(encoding, errors="replace").decode(encoding))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@dataclass
class ReplacementAssessment:
    legacy_mod: str
    status: str
    confidence: str
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PatchSurface:
    twee_replacer_passages: list[str] = field(default_factory=list)
    replace_patcher_js_files: list[str] = field(default_factory=list)
    replace_patcher_twee_passages: list[str] = field(default_factory=list)
    core_patch_passages: list[str] = field(default_factory=list)


@dataclass
class CurrentConfigAssessment:
    cheat_extended_enabled: bool
    active_legacy_base_mods: list[str]
    active_legacy_modloader_mods: list[str]
    configured_frameworks: list[str]
    conflicts: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AssetResolution:
    release: dict[str, Any]
    asset: dict[str, Any]
    source: str
    warning: str = ""


@dataclass
class FrameworkMatrixResult:
    framework: str
    repo: str
    configured: bool
    enabled: bool
    feature_ids: list[str]
    release_tag: str
    download_url: str
    status: str
    notes: list[str] = field(default_factory=list)


@dataclass
class CheatExtendedAuditReport:
    audit_timestamp: str
    repo: str
    release_tag: str
    asset_name: str
    asset_url: str
    asset_resolution_source: str
    asset_resolution_warning: str
    sha256: str
    file_size: int
    boot_version: str
    dependencies: list[dict[str, Any]]
    framework_options: list[str]
    recommended_framework: str
    framework_matrix: list[FrameworkMatrixResult]
    replacement_assessment: list[ReplacementAssessment]
    patch_surface: PatchSurface
    current_config: CurrentConfigAssessment
    au_ucb_coupling_notes: list[str]
    risk_level: str
    risk_notes: list[str]
    recommended_next_tests: list[str]


def fetch_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=github_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def download_bytes(url: str) -> bytes:
    headers = github_headers() if "github.com" in url else {}
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.content


def fetch_latest_asset(repo: str, asset_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    release = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    assets = release.get("assets", [])
    for asset in assets:
        if asset.get("name") == asset_name:
            return release, asset
    available = ", ".join(asset.get("name", "") for asset in assets)
    raise RuntimeError(f"Asset {asset_name!r} not found. Available: {available}")


def is_github_rate_limited(error: Exception) -> bool:
    """Return True when GitHub API access failed due to rate limiting."""
    if not isinstance(error, requests.HTTPError):
        return False

    response = error.response
    status_code = getattr(response, "status_code", None)
    response_text = getattr(response, "text", "") or str(error)
    return status_code == 403 and "rate limit" in response_text.lower()


def resolve_asset(repo: str = REPO, asset_name: str = ASSET_NAME) -> AssetResolution:
    """
    Resolve the cheatExtended asset, falling back to pinned config on API limits.

    The project pins cheatExtended in config/build.toml, so a GitHub latest API
    rate limit should not block local advisory runs.
    """
    try:
        release, asset = fetch_latest_asset(repo, asset_name)
        return AssetResolution(release=release, asset=asset, source="github_latest")
    except requests.HTTPError as error:
        if not is_github_rate_limited(error):
            raise

        build_config = load_build_config()
        configured_mod = next(
            (
                mod
                for mod in build_config.modloader_mods
                if mod.github_repo == repo or mod.key in {"cheat_extended", "cheatExtended"}
            ),
            None,
        )
        if not configured_mod or not configured_mod.download_url:
            raise

        warning = (
            "GitHub latest release API was rate limited; using pinned "
            "config/build.toml download_url instead."
        )
        return AssetResolution(
            release={"tag_name": configured_mod.release_tag or "configured"},
            asset={
                "name": configured_mod.asset_pattern or asset_name,
                "browser_download_url": configured_mod.download_url,
            },
            source="configured_download_url",
            warning=warning,
        )


def build_framework_matrix() -> list[FrameworkMatrixResult]:
    """Summarize framework choices for isolated cheatExtended canary testing."""
    build_config = load_build_config()
    rows: list[FrameworkMatrixResult] = []

    for repo, label in FRAMEWORK_REPOS.items():
        mods = [mod for mod in build_config.modloader_mods if mod.github_repo == repo]
        if not mods:
            rows.append(
                FrameworkMatrixResult(
                    framework=label,
                    repo=repo,
                    configured=False,
                    enabled=False,
                    feature_ids=[],
                    release_tag="",
                    download_url="",
                    status="not_configured",
                    notes=[
                        "Not configured in config/build.toml; test only as a separate canary.",
                        "Do not combine this framework with maplebirch in the same build.",
                    ],
                )
            )
            continue

        for mod in mods:
            status = "configured_enabled" if mod.enabled else "configured_disabled"
            notes = ["Configured with dedicated cheat_extended_maplebirch feature bit."]
            if repo == "MaplebirchLeaf/SCML-DOL-maplebirchframework":
                status = "configured_pinned_canary_only" if mod.enabled else status
                notes.append(
                    "Pinned maplebirch is used for downloadability and canary builds; "
                    "runtime validation still applies the canary IDB schema recovery patch "
                    "and browser/manual gates before merge readiness."
                )
            else:
                notes.append(
                    "Simple Framework must be tested as an alternate pinned canary, not alongside maplebirch."
                )

            rows.append(
                FrameworkMatrixResult(
                    framework=label,
                    repo=repo,
                    configured=True,
                    enabled=mod.enabled,
                    feature_ids=mod.required_feature_ids,
                    release_tag=mod.release_tag,
                    download_url=mod.download_url,
                    status=status,
                    notes=notes,
                )
            )

    return rows


def read_zip_text(zf: zipfile.ZipFile, basename: str) -> str:
    target = basename.lower()
    for name in zf.namelist():
        if Path(name).name.lower() == target:
            return zf.read(name).decode("utf-8", errors="replace")
    raise RuntimeError(f"{basename} not found in {ASSET_NAME}")


def build_search_text(boot: dict[str, Any], readme: str) -> str:
    payload = json.dumps(boot, ensure_ascii=False).lower()
    return f"{payload}\n{readme.lower()}"


def has_any(search_text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword.lower() in search_text]


def assess_replacement(boot: dict[str, Any], readme: str) -> list[ReplacementAssessment]:
    search_text = build_search_text(boot, readme)

    cheat_evidence = has_any(
        search_text,
        [
            "CE_cheatExtendedMenu",
            "CE_statControl",
            "CE_MoneyCheat",
            "CE_timeMultiplier",
            "CE_featBypass",
            "强制显示作弊按钮",
            "作弊拓展选单",
        ],
    )
    csd_evidence = has_any(
        search_text,
        [
            "CE_EnemyState",
            "CE_EnemyStateCss",
            "战斗中敌人状态显示",
            "血条显示",
            "敌人状态显示",
        ],
    )
    yanling_evidence = has_any(
        search_text,
        [
            "CE_yanling",
            "言灵系统",
            "快速言灵",
            "可同时新增多个言灵",
            "調用遊戲內 `widget` / `JS`".lower(),
        ],
    )
    bccm_evidence = has_any(
        search_text,
        [
            "widget",
            "js",
            "言灵",
            "Tony70124",
            "bccm",
        ],
    )

    return [
        ReplacementAssessment(
            legacy_mod="DoL-Lyra/Cheat",
            status="likely_covered",
            confidence="high" if cheat_evidence else "low",
            evidence=cheat_evidence,
            notes=[
                "cheatExtended provides its own cheat menu, stat controls, money/time controls, and feat/debug bypasses.",
            ],
        ),
        ReplacementAssessment(
            legacy_mod="CombatStatusDisplay",
            status="likely_covered",
            confidence="medium" if csd_evidence else "low",
            evidence=csd_evidence,
            notes=[
                "Enemy state display is present, but combat UI parity still needs browser/runtime validation.",
            ],
        ),
        ReplacementAssessment(
            legacy_mod="BJX word unlock / portable word",
            status="partially_covered",
            confidence="medium" if yanling_evidence else "low",
            evidence=yanling_evidence,
            notes=[
                "Yanling features exist, but exact parity with unlock and portable-word mods is not guaranteed statically.",
            ],
        ),
        ReplacementAssessment(
            legacy_mod="BCCM / BetterCheatCommandManagement",
            status="uncertain_partial",
            confidence="low" if bccm_evidence else "unknown",
            evidence=bccm_evidence,
            notes=[
                "The readme says scene creation was removed, and BCCM-style command management needs hands-on validation.",
            ],
        ),
    ]


def extract_patch_surface(boot: dict[str, Any]) -> PatchSurface:
    surface = PatchSurface()
    plugins = boot.get("addonPlugin") or []

    for plugin in plugins:
        mod_name = plugin.get("modName")
        params = plugin.get("params")

        if mod_name == "TweeReplacer" and isinstance(params, list):
            for item in params:
                passage = item.get("passage")
                if passage and passage not in surface.twee_replacer_passages:
                    surface.twee_replacer_passages.append(passage)

        if mod_name == "ReplacePatcher" and isinstance(params, dict):
            for item in params.get("js", []):
                filename = item.get("fileName")
                if filename and filename not in surface.replace_patcher_js_files:
                    surface.replace_patcher_js_files.append(filename)
            for item in params.get("twee", []):
                passage = item.get("passageName")
                if passage and passage not in surface.replace_patcher_twee_passages:
                    surface.replace_patcher_twee_passages.append(passage)

    all_passages = set(surface.twee_replacer_passages)
    all_passages.update(surface.replace_patcher_twee_passages)
    surface.core_patch_passages = sorted(all_passages & CORE_PATCH_PASSAGES)
    surface.twee_replacer_passages.sort()
    surface.replace_patcher_js_files.sort()
    surface.replace_patcher_twee_passages.sort()
    return surface


def assess_current_config() -> CurrentConfigAssessment:
    build_config = load_build_config()

    cheat_extended_mods = [
        mod
        for mod in build_config.modloader_mods
        if mod.github_repo == REPO or mod.key in {"cheat_extended", "cheatExtended"}
    ]
    cheat_extended_enabled = any(getattr(mod, "enabled", True) for mod in cheat_extended_mods)

    active_legacy_base_mods = [
        mod.key
        for mod in build_config.base_mods
        if mod.key in LEGACY_BASE_KEYS and mod.feature_id == "cheat_csd"
    ]
    active_legacy_modloader_mods = [
        mod.key
        for mod in build_config.modloader_mods
        if mod.key in LEGACY_MODLOADER_KEYS and getattr(mod, "enabled", True)
    ]
    configured_frameworks = []
    for mod in build_config.modloader_mods:
        label = FRAMEWORK_REPOS.get(mod.github_repo)
        if label and getattr(mod, "enabled", True):
            configured_frameworks.append(label)

    conflicts = []
    recommendations = []
    if cheat_extended_enabled and (active_legacy_base_mods or active_legacy_modloader_mods):
        conflicts.append(
            "cheatExtended is enabled together with legacy cheat/CSD/BJX/BCCM mods."
        )
        recommendations.append(
            "Use a separate canary build: enable cheatExtended, disable cheat/csd/bjx/bccm."
        )
    if cheat_extended_enabled and len(configured_frameworks) != 1:
        conflicts.append("cheatExtended requires exactly one framework option.")
        recommendations.append(
            "Prefer maplebirch >= 3.0.0; do not install maplebirch and Simple Framework together."
        )
    if not cheat_extended_enabled:
        recommendations.append(
            "Current stable builds are not affected; this report is only a replacement candidate audit."
        )

    return CurrentConfigAssessment(
        cheat_extended_enabled=cheat_extended_enabled,
        active_legacy_base_mods=active_legacy_base_mods,
        active_legacy_modloader_mods=active_legacy_modloader_mods,
        configured_frameworks=configured_frameworks,
        conflicts=conflicts,
        recommendations=recommendations,
    )


def determine_risk(
    replacement: list[ReplacementAssessment],
    patch_surface: PatchSurface,
    current_config: CurrentConfigAssessment,
) -> tuple[str, list[str]]:
    risk_notes = []
    risk_level = "medium"

    if current_config.conflicts:
        risk_level = "high"
        risk_notes.extend(current_config.conflicts)

    if patch_surface.core_patch_passages:
        risk_level = "high"
        risk_notes.append(
            "cheatExtended patches core passages: "
            + ", ".join(patch_surface.core_patch_passages)
        )

    uncertain = [item.legacy_mod for item in replacement if "uncertain" in item.status]
    if uncertain:
        risk_notes.append(
            "Static audit cannot prove full replacement parity for: " + ", ".join(uncertain)
        )

    return risk_level, risk_notes


def run_audit() -> CheatExtendedAuditReport:
    asset_resolution = resolve_asset(REPO, ASSET_NAME)
    release = asset_resolution.release
    asset = asset_resolution.asset
    asset_url = asset["browser_download_url"]
    content = download_bytes(asset_url)
    sha256 = hashlib.sha256(content).hexdigest()

    with zipfile.ZipFile(BytesIO(content), "r") as zf:
        zf.testzip()
        boot = json.loads(read_zip_text(zf, "boot.json"))
        readme = read_zip_text(zf, "readme.md")

    dependencies = boot.get("dependenceInfo") or []
    replacement = assess_replacement(boot, readme)
    patch_surface = extract_patch_surface(boot)
    current_config = assess_current_config()
    framework_matrix = build_framework_matrix()
    risk_level, risk_notes = determine_risk(replacement, patch_surface, current_config)

    au_ucb_notes = [
        "UCB risk is low because cheatExtended declares no imgFileList entries; it mainly patches JS/Twee/UI.",
        "AU face risk is medium because cheatExtended includes custom skin/eye color scripts and Widgets Text patches.",
        "AU-F/AU-M/AU-A must still be browser-tested because face and sidebar UI can fail at runtime.",
    ]

    next_tests = [
        "Create a canary build with UCB + cheatExtended + exactly one framework, with Cheat/CSD/BJX/BCCM disabled.",
        "Repeat the canary for AU-F, AU-M, and AU-A with the AU face expansion enabled.",
        "Open the game in a browser smoke test and fail on console errors, missing framework popups, or red SugarCube errors.",
        "Check cheat menu entry, enemy state bars, yanling actions, time travel, stat controls, save/load, and AU face/eye display.",
    ]

    return CheatExtendedAuditReport(
        audit_timestamp=utc_now_iso(),
        repo=REPO,
        release_tag=release.get("tag_name", "unknown"),
        asset_name=asset.get("name", ASSET_NAME),
        asset_url=asset_url,
        asset_resolution_source=asset_resolution.source,
        asset_resolution_warning=asset_resolution.warning,
        sha256=sha256,
        file_size=len(content),
        boot_version=boot.get("version", "unknown"),
        dependencies=dependencies,
        framework_options=[
            "maplebirch >= 3.0.0",
            "Simple Frameworks >= 2.0.5",
        ],
        recommended_framework="maplebirch >= 3.0.0",
        framework_matrix=framework_matrix,
        replacement_assessment=replacement,
        patch_surface=patch_surface,
        current_config=current_config,
        au_ucb_coupling_notes=au_ucb_notes,
        risk_level=risk_level,
        risk_notes=risk_notes,
        recommended_next_tests=next_tests,
    )


def write_json_report(path: Path, report: CheatExtendedAuditReport) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)


def write_markdown_report(path: Path, report: CheatExtendedAuditReport) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("# cheatExtended 替代性审计报告\n\n")
        f.write(f"**审计时间**: {report.audit_timestamp}\n\n")
        f.write(f"**Release**: `{report.release_tag}`\n\n")
        f.write(f"**Asset**: `{report.asset_name}`\n\n")
        f.write(f"**Asset resolution**: `{report.asset_resolution_source}`\n\n")
        if report.asset_resolution_warning:
            f.write(f"**Asset resolution warning**: {report.asset_resolution_warning}\n\n")
        f.write(f"**SHA256**: `{report.sha256}`\n\n")
        f.write(f"**总体风险**: `{report.risk_level}`\n\n")

        f.write("## 框架结论\n\n")
        f.write("- 支持二选一：`maplebirch >= 3.0.0` 或 `Simple Frameworks >= 2.0.5`。\n")
        f.write("- 不要同时安装两个框架。\n")
        f.write(f"- 推荐：`{report.recommended_framework}`。\n\n")

        f.write("## 框架矩阵\n\n")
        f.write("| 框架 | repo | 配置 | 启用 | feature | release | 状态 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for item in report.framework_matrix:
            feature_ids = ", ".join(item.feature_ids) if item.feature_ids else "N/A"
            f.write(
                f"| {item.framework} | {item.repo} | {item.configured} | "
                f"{item.enabled} | {feature_ids} | {item.release_tag or 'N/A'} | "
                f"{item.status} |\n"
            )
        f.write("\n")
        for item in report.framework_matrix:
            for note in item.notes:
                f.write(f"- `{item.framework}`: {note}\n")
        f.write("\n")

        f.write("## 替代性评估\n\n")
        f.write("| 旧 mod | 状态 | 置信度 | 证据 |\n")
        f.write("|---|---|---|---|\n")
        for item in report.replacement_assessment:
            evidence = ", ".join(item.evidence) if item.evidence else "N/A"
            f.write(
                f"| {item.legacy_mod} | {item.status} | {item.confidence} | {evidence} |\n"
            )
        f.write("\n")

        f.write("## 当前配置检查\n\n")
        f.write(f"- cheatExtended 已启用: `{report.current_config.cheat_extended_enabled}`\n")
        f.write(
            "- 旧 base mods: "
            + (", ".join(report.current_config.active_legacy_base_mods) or "无")
            + "\n"
        )
        f.write(
            "- 旧 modloader mods: "
            + (", ".join(report.current_config.active_legacy_modloader_mods) or "无")
            + "\n"
        )
        f.write(
            "- 已配置框架: "
            + (", ".join(report.current_config.configured_frameworks) or "无")
            + "\n\n"
        )

        if report.current_config.conflicts:
            f.write("### 冲突\n\n")
            for conflict in report.current_config.conflicts:
                f.write(f"- {conflict}\n")
            f.write("\n")

        if report.current_config.recommendations:
            f.write("### 配置建议\n\n")
            for recommendation in report.current_config.recommendations:
                f.write(f"- {recommendation}\n")
            f.write("\n")

        f.write("## Patch 面\n\n")
        f.write(
            "- TweeReplacer passages: "
            + (", ".join(report.patch_surface.twee_replacer_passages) or "无")
            + "\n"
        )
        f.write(
            "- ReplacePatcher JS: "
            + (", ".join(report.patch_surface.replace_patcher_js_files) or "无")
            + "\n"
        )
        f.write(
            "- ReplacePatcher Twee: "
            + (", ".join(report.patch_surface.replace_patcher_twee_passages) or "无")
            + "\n\n"
        )

        f.write("## AU / UCB 耦合\n\n")
        for note in report.au_ucb_coupling_notes:
            f.write(f"- {note}\n")
        f.write("\n")

        f.write("## 风险说明\n\n")
        for note in report.risk_notes:
            f.write(f"- {note}\n")
        f.write("\n")

        f.write("## 下一步测试\n\n")
        for item in report.recommended_next_tests:
            f.write(f"- {item}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit cheatExtended replacement risk")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="输出目录（默认: output）",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run_audit()

    json_path = args.output_dir / "cheat-extended-replacement-report.json"
    md_path = args.output_dir / "cheat-extended-replacement-report.md"
    write_json_report(json_path, report)
    write_markdown_report(md_path, report)

    safe_print(f"[OK] JSON 报告: {json_path}")
    safe_print(f"[OK] Markdown 报告: {md_path}")
    safe_print(f"[INFO] 总体风险: {report.risk_level}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
