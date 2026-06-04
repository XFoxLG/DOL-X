#!/usr/bin/env python3
"""
DoL-Lyra 构建系统

统一的 CI 构建入口，提供以下命令：

  prepare   - 下载并预处理游戏资源（生成基包）
  warmup    - 预热美化资源（下载并解压所有美化包）
  build     - 并行构建所有组合
  page      - 生成下载页面
  matrix    - 生成 GitHub Actions 构建矩阵
  check     - 检查是否需要更新

典型 CI 流程：
  1. lyra prepare --tag v0.5.7.9-5.0.2a-0112
  2. lyra warmup
  3. lyra build --tag v0.5.7.9-5.0.2a-0112
  4. lyra page --tag v0.5.7.9-5.0.2a-0112
"""

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lyra import __version__
from lyra.paths import BuildPaths
from lyra.version import LyraVersion, VersionRegistry
from lyra.utils import setup_logging

logger = logging.getLogger(__name__)


def _split_build_codes(raw_codes: list[str] | None) -> list[str] | None:
    """Parse comma-separated and repeated --codes values."""
    if not raw_codes:
        return None

    codes: list[str] = []
    for raw_code in raw_codes:
        for item in str(raw_code).split(","):
            item = item.strip()
            if item:
                codes.append(item)
    return codes


def _file_sha256(path: Path) -> str | None:
    """Return sha256 for an existing artifact path."""
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_artifact_path(path: Path, workspace: Path) -> str:
    """Prefer workspace-relative artifact paths in build manifests."""
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return str(path)


def _write_build_manifest(
    manifest_path: Path,
    *,
    workspace: Path,
    pack_types: list[str],
    requested_codes: list[str] | None,
    validation_results: list[dict],
    success_count: int,
    fail_count: int,
    records: list,
) -> None:
    """Write the machine-readable build manifest used by candidate gates."""
    from lyra.config_loader import get_config_loader

    artifacts = []
    for record in records:
        item = record.to_dict()
        output_path = item.get("output_path")
        if output_path:
            artifact_path = Path(output_path)
            item["relative_path"] = _relative_artifact_path(artifact_path, workspace)
            item["sha256"] = _file_sha256(artifact_path)
        else:
            item["relative_path"] = None
            item["sha256"] = None
        artifacts.append(item)

    manifest = {
        "success": fail_count == 0,
        "success_count": success_count,
        "fail_count": fail_count,
        "pack_types": pack_types,
        "requested_codes": requested_codes,
        "default_build_codes": list(get_config_loader().combinations.build_codes),
        "default_matrix_mutated": False,
        "validation": validation_results,
        "artifacts": artifacts,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_prepare(args) -> int:
    """
    准备游戏资源命令

    下载游戏文件、额外 mod，生成 ZIP 基包和 APK 解包目录。
    """
    from lyra.downloader import Downloader, GamePreparer
    from lyra.prepare import GamePreparer as FullPreparer

    setup_logging(args.verbose)
    logger.info(f"DoL-Lyra 构建系统 v{__version__}")

    # 解析版本
    version = LyraVersion.from_tag(args.tag) if args.tag else None
    if version:
        logger.info(f"目标版本: {version}")

    # 初始化路径
    paths = BuildPaths(workspace=Path(args.workspace))
    paths.ensure_dirs()

    # 下载资源
    downloader = Downloader(paths)
    downloaded_files = downloader.download_from_chs_repo(version)
    extra_mods = downloader.download_extra_mods()

    # 下载工具
    downloader.download_apktool()
    downloader.download_apksign()

    # 处理 i18n mod (从下载的文件中)
    if "i18n" in downloaded_files:
        extra_mods["i18n"] = downloaded_files["i18n"]

    # 预处理
    preparer = FullPreparer(paths)
    preparer.prepare_all(downloaded_files, extra_mods)

    # 合并并保存版本信息
    registry = VersionRegistry()
    registry.extend(list(downloader.registry))
    registry.extend(list(preparer.registry))
    registry.save(paths.versions_file)

    logger.info("准备完成！")
    return 0


def cmd_warmup(args) -> int:
    """
    预热美化资源命令

    下载并解压所有美化资源，避免并行构建时的冲突。
    """
    from lyra.warmup import ResourceWarmer

    setup_logging(args.verbose)
    logger.info(f"DoL-Lyra 构建系统 v{__version__}")

    # 初始化路径
    paths = BuildPaths(workspace=Path(args.workspace))
    paths.ensure_dirs()

    # 预热资源
    warmer = ResourceWarmer(paths)
    registry = warmer.warmup_all()

    # 加载已有版本信息并合并
    existing_registry = VersionRegistry.load(paths.versions_file)
    existing_registry.extend(list(registry))
    existing_registry.save(paths.versions_file)

    logger.info("预热完成！")
    return 0


def cmd_build(args) -> int:
    """
    构建命令

    并行构建所有 MOD 组合。
    """
    from lyra.code_validation import normalize_build_codes, validate_build_codes
    from lyra.parallel import build_all_parallel, build_all_parallel_with_records

    setup_logging(args.verbose)
    logger.info(f"DoL-Lyra 构建系统 v{__version__}")

    # 解析版本
    version = LyraVersion.from_tag(args.tag) if args.tag else None
    if version:
        logger.info(f"构建版本: {version}")

    # 初始化路径
    paths = BuildPaths(workspace=Path(args.workspace))
    paths.ensure_dirs()

    # 确定包类型
    pack_types = [args.pack_type] if args.pack_type else ["zip", "apk"]
    requested_codes = _split_build_codes(args.codes)
    validation_results = []
    normalized_codes = None

    if requested_codes is not None:
        validation = validate_build_codes(requested_codes)
        validation_results = [result.to_dict() for result in validation]
        invalid = [result for result in validation if not result.valid]
        if invalid:
            for result in invalid:
                logger.error(f"无效构建代码 {result.raw}: {result.findings}")
            if args.manifest:
                _write_build_manifest(
                    Path(args.manifest),
                    workspace=paths.workspace,
                    pack_types=pack_types,
                    requested_codes=requested_codes,
                    validation_results=validation_results,
                    success_count=0,
                    fail_count=len(invalid),
                    records=[],
                )
            return 1
        normalized_codes = normalize_build_codes(requested_codes)

    # 并行构建
    if args.manifest:
        success, fail, records = build_all_parallel_with_records(
            paths=paths,
            version=version,
            pack_types=pack_types,
            max_workers=args.jobs,
            include_polyfill=True,
            verbose=args.verbose,
            codes=normalized_codes,
        )
        _write_build_manifest(
            Path(args.manifest),
            workspace=paths.workspace,
            pack_types=pack_types,
            requested_codes=requested_codes,
            validation_results=validation_results,
            success_count=success,
            fail_count=fail,
            records=records,
        )
    else:
        success, fail = build_all_parallel(
            paths=paths,
            version=version,
            pack_types=pack_types,
            max_workers=args.jobs,
            include_polyfill=True,
            verbose=args.verbose,
            codes=normalized_codes,
        )

    return 0 if fail == 0 else 1


def cmd_page(args) -> int:
    """
    生成下载页面命令
    """
    from lyra.gen_page import generate_download_page

    setup_logging(args.verbose)

    # 解析版本
    version = args.version or (args.tag if args.tag else None)

    output_path = Path(args.output) if args.output else None
    versions_file = Path(args.versions_file) if args.versions_file else None

    content = generate_download_page(
        version=version,
        output_path=output_path,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
        versions_file=versions_file,
    )

    if not output_path:
        print(content)
    else:
        logger.info(f"下载页面已生成: {output_path}")

    return 0


def cmd_matrix(args) -> int:
    """
    生成构建矩阵命令（用于 GitHub Actions）
    """
    from lyra.combo import CombinationCalculator

    calculator = CombinationCalculator()
    codes = calculator.get_build_codes(include_polyfill=True)

    codes = sorted(
        codes,
        key=lambda x: (x.startswith("polyfill-"), int(x.replace("polyfill-", "0"))),
    )

    if args.output_format == "shell":
        # Shell 数组格式
        print("CODES=(" + " ".join(f'"{c}"' for c in codes) + ")")
    else:
        # JSON 格式
        print(json.dumps(codes))

    return 0


def cmd_list(args) -> int:
    """
    列出所有 MOD 组合
    """
    from lyra.combo import CombinationCalculator

    calculator = CombinationCalculator()
    print(calculator.to_string())
    return 0


def cmd_check(args) -> int:
    """
    检查是否需要更新
    """
    import requests

    setup_logging(args.verbose)

    # 获取汉化仓库最新 release
    url = "https://api.github.com/repos/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases/latest"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        origin_tag = response.json().get("tag_name", "")
    except Exception as e:
        logger.error(f"获取汉化仓库版本失败: {e}")
        return 1

    # 解析版本号
    # 格式: v0.5.7.9-chs-5.1.0a
    game_ver = origin_tag.split("-")[0].lstrip("v")
    chs_ver = origin_tag.split("-")[2]

    # 获取本仓库最新 tag
    try:
        mods_url = f"https://api.github.com/repos/{args.github_owner}/{args.github_repo}/releases/latest"
        response = requests.get(mods_url, timeout=30)
        response.raise_for_status()
        lyra_tag = response.json().get("tag_name", "")
        lyra_game_ver = lyra_tag.split("-")[0].lstrip("v")
        lyra_chs_ver = lyra_tag.split("-")[1]
    except Exception as e:
        logger.warning(f"获取本仓库版本失败（可能是首次发布）: {e}")

    need_update = chs_ver != lyra_chs_ver

    from datetime import datetime, timezone, timedelta

    # UTC+8 时间
    tz = timezone(timedelta(hours=8))
    date_str = datetime.now(tz).strftime("%m%d")

    result = {
        "need_update": need_update,
        "origin_tag": origin_tag,
        "game_ver": game_ver,
        "chs_ver": chs_ver,
        "lyra_game_ver": lyra_game_ver,
        "lyra_chs_ver": lyra_chs_ver,
        "new_tag": f"v{game_ver}-{chs_ver}-{date_str}",
    }

    if need_update:
        logger.info("需要更新！")
        logger.info(f"  汉化仓库: {origin_tag}")
        logger.info(f"  本仓库: {lyra_tag}")

    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"need_update={'true' if need_update else 'false'}\n")
            f.write(f"origin_tag={origin_tag}\n")
            f.write(f"new_tag={result['new_tag']}\n")
    else:
        print(json.dumps(result))

    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="DoL-Lyra 构建系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # prepare 命令
    prep_parser = subparsers.add_parser(
        "prepare",
        help="下载并预处理游戏资源",
        description="下载游戏文件、额外 mod，生成 ZIP 基包和 APK 解包目录。",
    )
    prep_parser.add_argument(
        "--tag",
        help="版本 tag（格式: v0.5.7.9-5.0.2a-0112）",
    )
    prep_parser.add_argument("--workspace", default=".", help="工作目录")
    prep_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # warmup 命令
    warmup_parser = subparsers.add_parser(
        "warmup",
        help="预热美化资源",
        description="下载并解压所有美化资源，避免并行构建时的冲突。",
    )
    warmup_parser.add_argument("--workspace", default=".", help="工作目录")
    warmup_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # build 命令
    build_parser = subparsers.add_parser(
        "build",
        help="并行构建所有组合",
        description="使用进程池并行构建所有 MOD 组合。",
    )
    build_parser.add_argument(
        "pack_type",
        nargs="?",
        choices=["zip", "apk"],
        help="包类型（可选，默认构建两种）",
    )
    build_parser.add_argument(
        "--tag",
        help="版本 tag（格式: v0.5.7.9-5.0.2a-0112）",
    )
    build_parser.add_argument(
        "--codes",
        nargs="+",
        help="显式构建代码（可重复或逗号分隔），不修改 combinations.toml",
    )
    build_parser.add_argument(
        "--manifest",
        help="写入结构化构建 manifest JSON（用于候选门禁证据）",
    )
    build_parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        help="并发进程数（默认: min(CPU核心数, 4)）",
    )
    build_parser.add_argument("--workspace", default=".", help="工作目录")
    build_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # page 命令
    page_parser = subparsers.add_parser(
        "page",
        help="生成下载页面",
    )
    page_parser.add_argument("--version", dest="version", help="版本号")
    page_parser.add_argument("--tag", help="版本 tag（替代 --version）")
    page_parser.add_argument("--output", help="输出文件路径")
    page_parser.add_argument("--github-owner", default="sakarie9", help="GitHub 用户名")
    page_parser.add_argument("--github-repo", default="DoL-Lyra", help="GitHub 仓库名")
    page_parser.add_argument("--versions-file", help="版本信息文件路径")
    page_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # matrix 命令
    matrix_parser = subparsers.add_parser(
        "matrix",
        help="生成构建矩阵",
    )
    matrix_parser.add_argument(
        "--output-format",
        choices=["json", "shell"],
        default="json",
        help="输出格式",
    )

    # list 命令
    list_parser = subparsers.add_parser(
        "list",
        help="列出所有 MOD 组合",
    )

    # check 命令
    check_parser = subparsers.add_parser(
        "check",
        help="检查是否需要更新",
    )
    check_parser.add_argument("--github-output", help="GitHub Actions 输出文件")
    check_parser.add_argument(
        "--github-owner", default="sakarie9", help="GitHub 用户名"
    )
    check_parser.add_argument("--github-repo", default="DoL-Lyra", help="GitHub 仓库名")
    check_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "prepare": cmd_prepare,
        "warmup": cmd_warmup,
        "build": cmd_build,
        "page": cmd_page,
        "matrix": cmd_matrix,
        "list": cmd_list,
        "check": cmd_check,
    }

    try:
        return commands[args.command](args)
    except KeyboardInterrupt:
        logger.info("用户中断")
        return 130
    except Exception as e:
        logger.error(f"执行失败: {e}")
        if args.verbose if hasattr(args, "verbose") else False:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
