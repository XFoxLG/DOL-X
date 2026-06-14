#!/usr/bin/env python3
"""
插件配置向导 - 交互式生成 boot.json 插件配置

支持的插件类型:
1. TweeReplacer: 替换 Twee passage 中的文本
2. ReplacePatch: 游戏运行时替换内容  
3. ImageLoaderHook: 替换图片资源

用法:
    python tools/plugin_wizard.py
    python tools/plugin_wizard.py --plugin TweeReplacer
    python tools/plugin_wizard.py --plugin TweeReplacer --output my-mod/boot.json

作者: DOL-X 项目组
日期: 2026-06-14
状态: 框架（待完整实现）
"""

import click
import json
from pathlib import Path
from typing import Dict, Any


def generate_twee_replacer() -> Dict[str, Any]:
    """生成 TweeReplacer 配置"""
    click.echo("\n=== TweeReplacer 配置向导 ===\n")
    
    passage = click.prompt("Passage 名称")
    find_string = click.prompt("查找字符串")
    replace_string = click.prompt("替换字符串")
    
    config = {
        "addonPlugin": [{
            "modName": "ModUtils",
            "addonName": "TweeReplacer",
            "params": [{
                "passage": passage,
                "findString": find_string,
                "replaceString": replace_string
            }]
        }]
    }
    
    return config


def generate_replace_patch() -> Dict[str, Any]:
    """生成 ReplacePatch 配置"""
    click.echo("\n=== ReplacePatch 配置向导 ===\n")
    click.echo("⚠️  TODO: 实现 ReplacePatch 配置生成")
    
    return {
        "addonPlugin": [{
            "modName": "ModUtils",
            "addonName": "ReplacePatch",
            "params": []
        }]
    }


def generate_image_loader_hook() -> Dict[str, Any]:
    """生成 ImageLoaderHook 配置"""
    click.echo("\n=== ImageLoaderHook 配置向导 ===\n")
    click.echo("⚠️  TODO: 实现 ImageLoaderHook 配置生成")
    
    return {
        "addonPlugin": [{
            "modName": "ModLoader",
            "addonName": "ImageLoaderHook",
            "params": []
        }]
    }


PLUGIN_GENERATORS = {
    'TweeReplacer': generate_twee_replacer,
    'ReplacePatch': generate_replace_patch,
    'ImageLoaderHook': generate_image_loader_hook,
}


@click.command()
@click.option(
    '--plugin',
    type=click.Choice(['TweeReplacer', 'ReplacePatch', 'ImageLoaderHook']),
    help='插件类型'
)
@click.option(
    '--output',
    type=click.Path(),
    default='boot.json',
    help='输出文件路径'
)
@click.option(
    '--merge',
    is_flag=True,
    help='合并到现有 boot.json（而非覆盖）'
)
def main(plugin, output, merge):
    """
    交互式生成插件配置
    
    示例:
        # 交互式选择插件类型
        python tools/plugin_wizard.py
        
        # 直接指定插件类型
        python tools/plugin_wizard.py --plugin TweeReplacer
        
        # 合并到现有配置
        python tools/plugin_wizard.py --plugin TweeReplacer --output my-mod/boot.json --merge
    """
    click.echo("=" * 60)
    click.echo("📝 插件配置向导")
    click.echo("=" * 60)
    
    # 选择插件类型
    if not plugin:
        click.echo("\n可用的插件类型:")
        click.echo("  1. TweeReplacer - 替换 Twee passage 文本")
        click.echo("  2. ReplacePatch - 运行时内容替换")
        click.echo("  3. ImageLoaderHook - 替换图片资源")
        click.echo()
        
        plugin = click.prompt(
            '选择插件类型',
            type=click.Choice(['TweeReplacer', 'ReplacePatch', 'ImageLoaderHook'])
        )
    
    # 生成配置
    generator = PLUGIN_GENERATORS[plugin]
    config = generator()
    
    # 处理输出
    output_path = Path(output)
    
    if merge and output_path.exists():
        # 合并模式
        with open(output_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        
        if 'addonPlugin' in existing:
            existing['addonPlugin'].extend(config['addonPlugin'])
        else:
            existing['addonPlugin'] = config['addonPlugin']
        
        final_config = existing
        click.echo(f"\n✅ 已合并到现有配置")
    else:
        # 覆盖模式
        final_config = config
        if output_path.exists():
            click.echo(f"\n⚠️  将覆盖现有文件: {output_path}")
    
    # 保存配置
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_config, f, indent=2, ensure_ascii=False)
    
    click.echo(f"\n📄 配置已保存到: {output_path}")
    click.echo("\n生成的配置:")
    click.echo(json.dumps(final_config, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
