#!/usr/bin/env python3
"""
boot.json 规范化工具

借鉴 rust-mod-dev 项目的设计思路，用 Python 实现：
- 自动补全文件列表
- 强制路径分隔符为 /
- 验证文件存在性
- 排序并去重

作者: DOL-X 项目组
日期: 2026-06-14
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set
import click


def scan_files(mod_dir: Path, pattern: str) -> List[str]:
    """
    扫描 Mod 目录下匹配的文件
    
    Args:
        mod_dir: Mod 根目录
        pattern: glob 模式（如 **/*.js）
    
    Returns:
        相对路径列表（使用 / 分隔符）
    """
    files = []
    for path in mod_dir.glob(pattern):
        if path.is_file():
            rel_path = path.relative_to(mod_dir)
            # 强制使用 / 分隔符
            normalized = str(rel_path).replace("\\", "/")
            files.append(normalized)
    return sorted(files)


def normalize_paths(paths: List[str]) -> List[str]:
    """
    规范化路径列表
    
    Args:
        paths: 路径列表
    
    Returns:
        规范化后的路径（/ 分隔符，排序去重）
    """
    normalized = set()
    for path in paths:
        if isinstance(path, str):
            # 强制 / 分隔符
            normalized.add(path.replace("\\", "/"))
    return sorted(normalized)


def validate_files(mod_dir: Path, file_list: List[str], list_name: str) -> List[str]:
    """
    验证文件列表中的文件是否存在
    
    Args:
        mod_dir: Mod 根目录
        file_list: 文件路径列表
        list_name: 列表名称（用于错误消息）
    
    Returns:
        不存在的文件列表
    """
    missing = []
    for file_path in file_list:
        full_path = mod_dir / file_path
        if not full_path.exists():
            missing.append(file_path)
    return missing


def normalize_boot_json(
    boot_path: Path,
    auto_fix: bool = False,
    check_only: bool = False
) -> Dict:
    """
    规范化 boot.json 文件
    
    Args:
        boot_path: boot.json 文件路径
        auto_fix: 是否自动修复
        check_only: 仅检查不修改
    
    Returns:
        规范化后的 boot.json 数据
    """
    if not boot_path.exists():
        raise FileNotFoundError(f"boot.json 不存在: {boot_path}")
    
    # 加载现有数据
    with open(boot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    mod_dir = boot_path.parent
    modified = False
    issues = []
    
    # 定义文件列表字段和对应的 glob 模式
    file_lists = {
        "scriptFileList": "**/*.js",
        "tweeFileList": "**/*.twee",
        "imgFileList": "**/*.{png,jpg,jpeg,gif,webp}",
        "styleFileList": "**/*.css",
    }
    
    click.echo(f"📋 检查 {boot_path.name}...")
    
    # 1. 补全文件列表
    for list_key, pattern in file_lists.items():
        if list_key in data:
            # 扫描实际文件
            actual_files = []
            if "{" in pattern:
                # 处理多扩展名模式
                base_pattern = pattern.rsplit(".", 1)[0]
                extensions = pattern.rsplit("{", 1)[1].rstrip("}").split(",")
                for ext in extensions:
                    actual_files.extend(scan_files(mod_dir, f"{base_pattern}.{ext}"))
            else:
                actual_files = scan_files(mod_dir, pattern)
            
            # 规范化现有列表
            current_files = set(normalize_paths(data[list_key]))
            actual_files_set = set(actual_files)
            
            # 检查缺失的文件
            missing_in_config = actual_files_set - current_files
            if missing_in_config:
                issues.append(f"⚠️  {list_key}: {len(missing_in_config)} 个文件未在配置中列出")
                for f in sorted(missing_in_config)[:5]:  # 只显示前5个
                    click.echo(f"   - {f}")
                if len(missing_in_config) > 5:
                    click.echo(f"   ... 还有 {len(missing_in_config) - 5} 个")
                modified = True
            
            # 合并并规范化
            if auto_fix or not check_only:
                all_files = current_files | actual_files_set
                data[list_key] = sorted(all_files)
    
    # 2. 规范化所有路径分隔符
    for key, value in data.items():
        if isinstance(value, list):
            normalized = normalize_paths(value)
            if normalized != value:
                data[key] = normalized
                modified = True
    
    # 3. 验证文件存在性
    for list_key in ["scriptFileList", "tweeFileList", "imgFileList", "styleFileList"]:
        if list_key in data:
            missing = validate_files(mod_dir, data[list_key], list_key)
            if missing:
                issues.append(f"❌ {list_key}: {len(missing)} 个文件不存在")
                for f in missing[:3]:
                    click.echo(f"   - {f}")
                if len(missing) > 3:
                    click.echo(f"   ... 还有 {len(missing) - 3} 个")
    
    # 4. 保存修复结果
    if auto_fix and modified:
        with open(boot_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        click.echo(f"✅ 已规范化: {boot_path}")
    elif check_only:
        if issues:
            click.echo(f"⚠️  发现 {len(issues)} 个问题")
            return data
        else:
            click.echo("✅ 无问题")
    else:
        if modified:
            click.echo("预览模式（使用 --auto-fix 应用更改）:")
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    
    return data


@click.command()
@click.argument("boot_json_paths", nargs=-1, type=click.Path(exists=True))
@click.option("--auto-fix", is_flag=True, help="自动修复并保存")
@click.option("--check", "check_only", is_flag=True, help="仅检查不修改")
def main(boot_json_paths, auto_fix, check_only):
    """
    规范化 boot.json 文件
    
    用法:
        python tools/normalize_boot_json.py path/to/boot.json --auto-fix
        python tools/normalize_boot_json.py mods/*/boot.json --check
    """
    if not boot_json_paths:
        click.echo("错误: 未指定 boot.json 文件路径", err=True)
        click.echo("用法: python tools/normalize_boot_json.py path/to/boot.json [--auto-fix]")
        sys.exit(1)
    
    success_count = 0
    error_count = 0
    
    for path_str in boot_json_paths:
        path = Path(path_str)
        try:
            normalize_boot_json(path, auto_fix=auto_fix, check_only=check_only)
            success_count += 1
        except Exception as e:
            click.echo(f"❌ 处理失败 {path}: {e}", err=True)
            error_count += 1
    
    click.echo(f"\n📊 处理完成: ✅ {success_count} 成功, ❌ {error_count} 失败")
    
    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
