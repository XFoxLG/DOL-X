#!/usr/bin/env python3
"""检查 imagepack 缓存状态和内容"""

from pathlib import Path
import sys

def check_cache():
    """检查所有美化包的缓存状态"""
    base_dir = Path(__file__).parent.parent
    cache_dir = base_dir / "workspace" / "cache" / "beautify"
    
    print("=== 美化包缓存状态 ===\n")
    
    imagepacks = ["ucb", "besc", "hikari", "goose"]
    cache_status = {}
    
    for pack in imagepacks:
        pack_dir = cache_dir / pack / "img"
        exists = pack_dir.exists()
        cache_status[pack] = exists
        
        status_icon = "✓" if exists else "✗"
        status_text = "已缓存" if exists else "未缓存"
        print(f"{status_icon} {pack.upper()}: {status_text}")
        
        if exists:
            # 统计文件数量
            files = list(pack_dir.rglob("*.png")) + list(pack_dir.rglob("*.gif")) + list(pack_dir.rglob("*.jpg"))
            print(f"  文件数: {len(files)}")
            
            # 统计顶层目录
            top_dirs = [d.name for d in pack_dir.iterdir() if d.is_dir()]
            if top_dirs:
                print(f"  顶层目录: {', '.join(sorted(top_dirs)[:5])}")
                if len(top_dirs) > 5:
                    print(f"  (还有 {len(top_dirs) - 5} 个目录)")
        print()
    
    # 检查 ModLoader mods
    mods_cache = base_dir / "workspace" / "cache" / "mods"
    print("=== ModLoader Mods 缓存 ===\n")
    if mods_cache.exists():
        mod_files = list(mods_cache.glob("*.zip"))
        print(f"✓ Mods 缓存: 已缓存 ({len(mod_files)} 个文件)")
        for mod in sorted(mod_files)[:5]:
            print(f"  - {mod.name}")
        if len(mod_files) > 5:
            print(f"  (还有 {len(mod_files) - 5} 个文件)")
    else:
        print("✗ Mods 缓存: 未缓存")
    
    # 返回状态
    all_cached = all(cache_status.values())
    return 0 if all_cached else 1

if __name__ == "__main__":
    sys.exit(check_cache())
