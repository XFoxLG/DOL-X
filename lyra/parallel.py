"""
并行构建模块

使用进程池并行执行构建任务。
"""

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

from .paths import BuildPaths
from .version import LyraVersion
from .combo import CombinationCalculator
from .code_validation import normalize_build_codes
from .utils import setup_logging

logger = logging.getLogger(__name__)


@dataclass
class ParallelBuildConfig:
    """并行构建配置"""

    pack_types: list[str]  # 要构建的包类型列表 ["zip", "apk"]
    version: Optional[LyraVersion] = None  # 版本信息
    max_workers: Optional[int] = None  # 最大并发数
    include_polyfill: bool = True  # 是否包含polyfill版本
    verbose: bool = False  # 是否详细输出
    codes: Optional[list[str]] = None  # 显式构建代码；为空时使用配置矩阵


@dataclass
class ParallelBuildRecord:
    """One completed parallel build task for manifest/report output."""

    pack_type: str
    code: str
    success: bool
    output_path: str | None = None
    output_name: str = ""
    error: str | None = None
    applied_mods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_type": self.pack_type,
            "code": self.code,
            "success": self.success,
            "output_path": self.output_path,
            "output_name": self.output_name,
            "error": self.error,
            "applied_mods": self.applied_mods,
        }


def _build_task_worker(args: tuple) -> tuple[str, str, dict[str, Any]]:
    """
    并行构建工作函数

    在子进程中执行，需要独立初始化环境。

    Args:
        args: (pack_type, code_str, workspace, version_dict, verbose)

    Returns:
        (pack_type, code_str, BuildResult.to_dict())
    """
    pack_type, code_str, workspace, version_dict, verbose = args

    # 子进程需要独立配置日志
    setup_logging(verbose)

    try:
        # 在子进程中导入以避免序列化问题
        from .paths import BuildPaths
        from .version import LyraVersion
        from .build import BuildTask, build_single

        paths = BuildPaths(workspace=Path(workspace))

        version = None
        if version_dict:
            version = LyraVersion(**version_dict)

        task = BuildTask.from_code_str(
            code_str=code_str,
            pack_type=pack_type,
            version=version,
            paths=paths,
        )

        result = build_single(task)

        return (pack_type, code_str, result.to_dict())

    except Exception as e:
        return (
            pack_type,
            code_str,
            {
                "success": False,
                "output_path": None,
                "output_name": "",
                "error": str(e),
                "applied_mods": [],
            },
        )


class ParallelBuilder:
    """
    并行构建管理器

    协调多个进程并行执行构建任务。
    """

    def __init__(self, paths: BuildPaths, config: ParallelBuildConfig):
        """
        初始化并行构建器

        Args:
            paths: 路径管理器
            config: 并行构建配置
        """
        self.paths = paths
        self.config = config
        self.calculator = CombinationCalculator()

    def build_all(self) -> tuple[int, int]:
        """
        并行构建所有组合

        Returns:
            (成功数, 失败数)
        """
        success_count, fail_count, _records = self.build_all_with_records()
        return success_count, fail_count

    def build_all_with_records(self) -> tuple[int, int, list[ParallelBuildRecord]]:
        """
        并行构建所有组合并保留每个任务的结构化结果。

        Returns:
            (成功数, 失败数, 构建记录)
        """
        codes = self._get_build_codes()

        total_tasks = len(codes) * len(self.config.pack_types)
        logger.info(f"开始并行构建: {total_tasks} 个任务")
        logger.info(f"  包类型: {self.config.pack_types}")
        logger.info(f"  组合数: {len(codes)}")

        success_count = 0
        fail_count = 0
        records: list[ParallelBuildRecord] = []

        # 确定并发数
        max_workers = self.config.max_workers or min(os.cpu_count() or 4, 4)

        # 准备版本信息字典（用于序列化传递）
        version_dict = None
        if self.config.version:
            version_dict = {
                "dol_ver": self.config.version.dol_ver,
                "chs_ver": self.config.version.chs_ver,
                "date": self.config.version.date,
            }

        # 按包类型分批处理
        for pack_type in self.config.pack_types:
            logger.info(f"\n{'='*50}")
            logger.info(f"构建 {pack_type.upper()} 包 ({len(codes)} 个)")
            logger.info(f"{'='*50}")

            if pack_type == "zip":
                # ZIP 可以完全并行
                s, f, pack_records = self._build_parallel(pack_type, codes, version_dict, max_workers)
            else:
                # APK 并行构建
                s, f, pack_records = self._build_parallel(pack_type, codes, version_dict, max_workers)

            success_count += s
            fail_count += f
            records.extend(pack_records)

        # 输出统计
        logger.info(f"\n{'='*50}")
        logger.info(f"构建完成: 成功 {success_count}, 失败 {fail_count}")
        logger.info(f"{'='*50}")

        return success_count, fail_count, records

    def _get_build_codes(self) -> list[str]:
        """Return explicit build codes or the configured default matrix."""
        if self.config.codes is not None:
            return self._sort_codes(normalize_build_codes(self.config.codes))

        codes = self.calculator.get_build_codes(
            include_polyfill=self.config.include_polyfill
        )
        return self._sort_codes(codes)

    def _build_parallel(
        self,
        pack_type: str,
        codes: list[str],
        version_dict: Optional[dict],
        max_workers: int,
    ) -> tuple[int, int, list[ParallelBuildRecord]]:
        """
        并行构建指定类型的包

        Args:
            pack_type: 包类型
            codes: 构建代码列表
            version_dict: 版本信息字典
            max_workers: 最大并发数

        Returns:
            (成功数, 失败数, 构建记录)
        """
        success_count = 0
        fail_count = 0
        records: list[ParallelBuildRecord] = []

        # 准备任务参数
        tasks = [
            (
                pack_type,
                code,
                str(self.paths.workspace),
                version_dict,
                self.config.verbose,
            )
            for code in codes
        ]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_build_task_worker, task): task[1] for task in tasks
            }

            for future in as_completed(futures):
                code = futures[future]
                try:
                    pack_type, code_str, result_dict = future.result()
                    success = bool(result_dict.get("success"))
                    error = result_dict.get("error")
                    record = ParallelBuildRecord(
                        pack_type=pack_type,
                        code=code_str,
                        success=success,
                        output_path=result_dict.get("output_path"),
                        output_name=result_dict.get("output_name") or "",
                        error=error,
                        applied_mods=list(result_dict.get("applied_mods") or []),
                    )
                    records.append(record)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                        logger.error(f"  失败 [{pack_type}] {code_str}: {error}")
                except Exception as e:
                    fail_count += 1
                    records.append(
                        ParallelBuildRecord(
                            pack_type=pack_type,
                            code=code,
                            success=False,
                            error=str(e),
                        )
                    )
                    logger.error(f"  异常 [{pack_type}] {code}: {e}")

        return success_count, fail_count, records

    def _sort_codes(self, codes: list[str]) -> list[str]:
        """
        对构建代码排序

        polyfill 版本排在后面。
        """
        return sorted(
            codes,
            key=lambda x: (x.startswith("polyfill-"), int(x.replace("polyfill-", "0"))),
        )


def build_all_parallel(
    paths: BuildPaths,
    version: Optional[LyraVersion] = None,
    pack_types: Optional[list[str]] = None,
    max_workers: Optional[int] = None,
    include_polyfill: bool = True,
    verbose: bool = False,
    codes: Optional[list[str]] = None,
) -> tuple[int, int]:
    """
    并行构建所有组合的便捷函数

    Args:
        paths: 路径管理器
        version: 版本信息
        pack_types: 包类型列表
        max_workers: 最大并发数
        include_polyfill: 是否包含polyfill
        verbose: 是否详细输出
        codes: 显式构建代码；为空时使用配置矩阵

    Returns:
        (成功数, 失败数)
    """
    config = ParallelBuildConfig(
        pack_types=pack_types or ["zip", "apk"],
        version=version,
        max_workers=max_workers,
        include_polyfill=include_polyfill,
        verbose=verbose,
        codes=codes,
    )

    builder = ParallelBuilder(paths, config)
    return builder.build_all()


def build_all_parallel_with_records(
    paths: BuildPaths,
    version: Optional[LyraVersion] = None,
    pack_types: Optional[list[str]] = None,
    max_workers: Optional[int] = None,
    include_polyfill: bool = True,
    verbose: bool = False,
    codes: Optional[list[str]] = None,
) -> tuple[int, int, list[ParallelBuildRecord]]:
    """Build all combinations and return per-artifact records."""
    config = ParallelBuildConfig(
        pack_types=pack_types or ["zip", "apk"],
        version=version,
        max_workers=max_workers,
        include_polyfill=include_polyfill,
        verbose=verbose,
        codes=codes,
    )

    builder = ParallelBuilder(paths, config)
    return builder.build_all_with_records()
