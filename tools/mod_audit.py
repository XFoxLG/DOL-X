#!/usr/bin/env python3
"""
Phase 2: Mod 资源审计工具

功能：
- 下载所有 modloader_mods 和 base_mods 的 GitHub release assets
- 验证文件完整性（sha256）
- 检查 zip 文件是否可解压
- 生成兼容性报告（JSON + Markdown）
- 识别 mod 版本变化

输出：
- output/mod-compatibility-report.json
- output/mod-compatibility-report.md
"""
import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from tqdm import tqdm

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lyra.config_loader import load_build_config
from lyra.utils import get_github_release_asset


@dataclass
class ModAuditResult:
    """单个 mod 的审计结果"""
    key: str
    name: str
    github_repo: str
    asset_pattern: str
    release_tag: str
    
    # 下载结果
    download_success: bool
    download_url: Optional[str] = None
    download_error: Optional[str] = None
    
    # 文件信息
    file_size: Optional[int] = None
    sha256: Optional[str] = None
    
    # 解压测试
    is_zip: bool = False
    zip_valid: Optional[bool] = None
    zip_error: Optional[str] = None
    zip_file_count: Optional[int] = None
    
    # 元数据
    release_version: Optional[str] = None
    audit_timestamp: Optional[str] = None
    
    # 风险评估
    risk_level: str = "unknown"  # low, medium, high, unknown
    risk_notes: list = None
    
    def __post_init__(self):
        if self.risk_notes is None:
            self.risk_notes = []


class ModAuditor:
    """Mod 资源审计器"""
    
    def __init__(self, output_dir: Path, use_cache: bool = True):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.cache_dir = output_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
    
    def audit_all_mods(self) -> list[ModAuditResult]:
        """审计所有 mod"""
        build_config = load_build_config()
        results = []
        
        print("=" * 70)
        print("DoL-X Mod 资源审计")
        print("=" * 70)
        print()
        
        # 审计 modloader_mods
        print(f"审计 {len(build_config.modloader_mods)} 个 modloader mods...")
        for mod_config in tqdm(build_config.modloader_mods, desc="Modloader mods"):
            result = self.audit_mod(
                key=mod_config.key or mod_config.asset_pattern,
                name=mod_config.name or mod_config.asset_pattern,
                github_repo=mod_config.github_repo,
                asset_pattern=mod_config.asset_pattern,
                release_tag=mod_config.release_tag,
            )
            results.append(result)
        
        # 审计 base_mods（如果有 github_repo）
        base_mods_with_repo = [
            mod for mod in build_config.base_mods 
            if hasattr(mod, 'github_repo') and mod.github_repo
        ]
        
        if base_mods_with_repo:
            print(f"\n审计 {len(base_mods_with_repo)} 个 base mods...")
            for mod_config in tqdm(base_mods_with_repo, desc="Base mods"):
                result = self.audit_mod(
                    key=mod_config.key,
                    name=mod_config.key,
                    github_repo=mod_config.github_repo,
                    asset_pattern=mod_config.asset_pattern,
                    release_tag=getattr(mod_config, 'release_tag', 'latest'),
                )
                results.append(result)
        
        return results
    
    def audit_mod(
        self,
        key: str,
        name: str,
        github_repo: str,
        asset_pattern: str,
        release_tag: str,
    ) -> ModAuditResult:
        """审计单个 mod"""
        result = ModAuditResult(
            key=key,
            name=name,
            github_repo=github_repo,
            asset_pattern=asset_pattern,
            release_tag=release_tag,
            audit_timestamp=datetime.utcnow().isoformat() + "Z",
        )
        
        # 1. 获取 release asset 信息
        try:
            asset_info = get_github_release_asset(
                repo=github_repo,
                asset_pattern=asset_pattern,
                tag=release_tag,
            )
            
            if not asset_info:
                result.download_success = False
                result.download_error = f"未找到匹配 '{asset_pattern}' 的 asset"
                result.risk_level = "high"
                result.risk_notes.append("Release asset 不存在或已被删除")
                return result
            
            result.download_url = asset_info.url
            result.release_version = asset_info.version
            
        except Exception as e:
            result.download_success = False
            result.download_error = f"获取 release 信息失败: {str(e)}"
            result.risk_level = "high"
            result.risk_notes.append(f"GitHub API 错误: {str(e)}")
            return result
        
        # 2. 下载文件
        try:
            file_content = self._download_file(result.download_url, key)
            result.download_success = True
            result.file_size = len(file_content)
            
        except Exception as e:
            result.download_success = False
            result.download_error = f"下载失败: {str(e)}"
            result.risk_level = "high"
            result.risk_notes.append(f"下载错误: {str(e)}")
            return result
        
        # 3. 计算 sha256
        result.sha256 = hashlib.sha256(file_content).hexdigest()
        
        # 4. 检查是否为 zip 并尝试解压
        result.is_zip = asset_pattern.endswith('.zip') or asset_pattern.endswith('.mod.zip')
        
        if result.is_zip:
            try:
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                    tmp_file.write(file_content)
                    tmp_path = Path(tmp_file.name)
                
                try:
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        # 测试完整性
                        bad_file = zf.testzip()
                        if bad_file:
                            result.zip_valid = False
                            result.zip_error = f"损坏的文件: {bad_file}"
                            result.risk_level = "high"
                            result.risk_notes.append(f"ZIP 文件损坏: {bad_file}")
                        else:
                            result.zip_valid = True
                            result.zip_file_count = len(zf.namelist())
                            
                            # 检查是否包含常见 mod 文件
                            has_boot_json = any('boot.json' in name.lower() for name in zf.namelist())
                            has_js_files = any(name.endswith('.js') for name in zf.namelist())
                            
                            if not (has_boot_json or has_js_files):
                                result.risk_level = "medium"
                                result.risk_notes.append("未发现 boot.json 或 .js 文件，可能不是有效的 mod")
                            else:
                                result.risk_level = "low"
                
                finally:
                    tmp_path.unlink()
            
            except zipfile.BadZipFile:
                result.zip_valid = False
                result.zip_error = "不是有效的 ZIP 文件"
                result.risk_level = "high"
                result.risk_notes.append("ZIP 格式错误")
            
            except Exception as e:
                result.zip_valid = False
                result.zip_error = f"解压测试失败: {str(e)}"
                result.risk_level = "medium"
                result.risk_notes.append(f"ZIP 测试异常: {str(e)}")
        
        else:
            # 非 zip 文件
            result.risk_level = "low"
        
        return result
    
    def _download_file(self, url: str, cache_key: str) -> bytes:
        """下载文件（带缓存）"""
        cache_file = self.cache_dir / f"{cache_key}.cache"
        
        if self.use_cache and cache_file.exists():
            return cache_file.read_bytes()
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        content = response.content
        
        if self.use_cache:
            cache_file.write_bytes(content)
        
        return content
    
    def generate_reports(self, results: list[ModAuditResult]):
        """生成 JSON 和 Markdown 报告"""
        # JSON 报告
        json_path = self.output_dir / "mod-compatibility-report.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    "audit_timestamp": datetime.utcnow().isoformat() + "Z",
                    "total_mods": len(results),
                    "results": [asdict(r) for r in results],
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        
        print(f"\n✓ JSON 报告: {json_path}")
        
        # Markdown 报告
        md_path = self.output_dir / "mod-compatibility-report.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            self._write_markdown_report(f, results)
        
        print(f"✓ Markdown 报告: {md_path}")
    
    def _write_markdown_report(self, f, results: list[ModAuditResult]):
        """写入 Markdown 报告"""
        f.write("# DoL-X Mod 兼容性审计报告\n\n")
        f.write(f"**审计时间**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n")
        f.write(f"**总计**: {len(results)} 个 mods\n\n")
        
        # 统计
        success_count = sum(1 for r in results if r.download_success)
        high_risk = [r for r in results if r.risk_level == "high"]
        medium_risk = [r for r in results if r.risk_level == "medium"]
        
        f.write("## 概览\n\n")
        f.write(f"- ✓ 下载成功: {success_count}/{len(results)}\n")
        f.write(f"- ⚠️ 高风险: {len(high_risk)}\n")
        f.write(f"- ⚡ 中风险: {len(medium_risk)}\n\n")
        
        # 高风险 mods
        if high_risk:
            f.write("## ⚠️ 高风险 Mods\n\n")
            for r in high_risk:
                f.write(f"### {r.name}\n\n")
                f.write(f"- **Key**: `{r.key}`\n")
                f.write(f"- **Repo**: {r.github_repo}\n")
                f.write(f"- **Asset**: {r.asset_pattern}\n")
                f.write(f"- **Tag**: {r.release_tag}\n")
                f.write(f"- **风险原因**:\n")
                for note in r.risk_notes:
                    f.write(f"  - {note}\n")
                if r.download_error:
                    f.write(f"- **错误**: {r.download_error}\n")
                f.write("\n")
        
        # 中风险 mods
        if medium_risk:
            f.write("## ⚡ 中风险 Mods\n\n")
            for r in medium_risk:
                f.write(f"### {r.name}\n\n")
                f.write(f"- **Key**: `{r.key}`\n")
                f.write(f"- **风险原因**:\n")
                for note in r.risk_notes:
                    f.write(f"  - {note}\n")
                f.write("\n")
        
        # 详细列表
        f.write("## 详细列表\n\n")
        f.write("| Mod | 下载 | 大小 | ZIP | 风险 |\n")
        f.write("|-----|------|------|-----|------|\n")
        
        for r in results:
            download_icon = "✓" if r.download_success else "✗"
            size_str = f"{r.file_size // 1024} KB" if r.file_size else "N/A"
            zip_icon = "✓" if r.zip_valid else ("✗" if r.zip_valid is False else "N/A")
            risk_icon = {"low": "✓", "medium": "⚡", "high": "⚠️", "unknown": "?"}.get(r.risk_level, "?")
            
            f.write(f"| {r.name} | {download_icon} | {size_str} | {zip_icon} | {risk_icon} |\n")
        
        f.write("\n")
        
        # SHA256 列表
        f.write("## SHA256 校验和\n\n")
        f.write("```\n")
        for r in results:
            if r.sha256:
                f.write(f"{r.sha256}  {r.key}\n")
        f.write("```\n")


def main():
    parser = argparse.ArgumentParser(description="DoL-X Mod 资源审计工具")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="输出目录（默认: output）",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用下载缓存",
    )
    
    args = parser.parse_args()
    
    auditor = ModAuditor(
        output_dir=args.output_dir,
        use_cache=not args.no_cache,
    )
    
    results = auditor.audit_all_mods()
    auditor.generate_reports(results)
    
    # 退出码
    high_risk_count = sum(1 for r in results if r.risk_level == "high")
    if high_risk_count > 0:
        print(f"\n⚠️  发现 {high_risk_count} 个高风险 mod")
        sys.exit(1)
    else:
        print("\n✓ 所有 mod 审计通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
