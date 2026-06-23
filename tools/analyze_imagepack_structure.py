#!/usr/bin/env python3
"""分析 imagepack 的目录结构和文件路径"""

from pathlib import Path
import json
from collections import defaultdict

def analyze_structure(pack_name: str, pack_dir: Path) -> dict:
    """分析单个 imagepack 的结构"""
    if not pack_dir.exists():
        return {"error": "Path not exists"}
    
    result = {
        "name": pack_name,
        "path": str(pack_dir),
        "total_files": 0,
        "directories": {},
        "file_list": []
    }
    
    # 统计每个顶层目录下的文件数
    for root, dirs, files in pack_dir.walk():
        for file in files:
            if file.lower().endswith(('.png', '.gif', '.jpg', '.jpeg')):
                file_path = root / file
                rel_path = file_path.relative_to(pack_dir)
                result["file_list"].append(str(rel_path).replace('\\', '/'))
                result["total_files"] += 1
                
                # 统计顶层目录
                parts = rel_path.parts
                if len(parts) > 0:
                    top_dir = parts[0]
                    if top_dir not in result["directories"]:
                        result["directories"][top_dir] = 0
                    result["directories"][top_dir] += 1
    
    return result

def main():
    base_dir = Path(__file__).parent.parent
    cache_dir = base_dir / "workspace" / "cache" / "beautify"
    output_dir = base_dir / "output"
    output_dir.mkdir(exist_ok=True)
    
    print("=== 分析 Imagepack 结构 ===\n")
    
    imagepacks = ["ucb", "besc", "hikari", "goose"]
    all_results = {}
    
    for pack in imagepacks:
        pack_dir = cache_dir / pack / "img"
        print(f"正在分析 {pack.upper()}...")
        
        result = analyze_structure(pack, pack_dir)
        all_results[pack] = result
        
        if "error" in result:
            print(f"  ✗ {result['error']}\n")
            continue
        
        print(f"  ✓ 文件总数: {result['total_files']}")
        print(f"  ✓ 顶层目录: {len(result['directories'])}")
        
        # 显示前5个目录的统计
        sorted_dirs = sorted(result["directories"].items(), key=lambda x: x[1], reverse=True)
        for dir_name, count in sorted_dirs[:5]:
            print(f"     - {dir_name}/: {count} 个文件")
        
        print()
    
    # 保存完整结果到 JSON
    output_file = output_dir / "imagepack_structure_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"✓ 完整分析结果已保存到: {output_file}\n")
    
    # 生成路径重叠分析
    print("=== 路径重叠分析 ===\n")
    
    file_sources = defaultdict(list)
    for pack, data in all_results.items():
        if "file_list" in data:
            for file_path in data["file_list"]:
                file_sources[file_path].append(pack)
    
    overlaps = {path: sources for path, sources in file_sources.items() if len(sources) > 1}
    
    if overlaps:
        print(f"发现 {len(overlaps)} 个重叠路径\n")
        
        # 显示前10个重叠
        for i, (path, sources) in enumerate(list(overlaps.items())[:10], 1):
            print(f"{i}. {path}")
            print(f"   存在于: {', '.join(sources)}")
        
        if len(overlaps) > 10:
            print(f"\n(还有 {len(overlaps) - 10} 个重叠路径)")
        
        # 保存重叠分析
        overlap_file = output_dir / "imagepack_overlaps.json"
        with open(overlap_file, 'w', encoding='utf-8') as f:
            json.dump(overlaps, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 重叠分析已保存到: {overlap_file}")
    else:
        print("未发现路径重叠")

if __name__ == "__main__":
    main()
