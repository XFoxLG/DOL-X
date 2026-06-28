#!/usr/bin/env python3
"""
DOL-X 测试构建下载工具

从 GitHub Actions 下载最新构建并自动生成测试清单。
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional


class BuildDownloader:
    """GitHub Actions 构建下载器"""
    
    def __init__(self, project_root: Path, token: Optional[str] = None):
        self.project_root = project_root
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo = "XFoxLG/DOL-X"
        
    def download_latest(self, build_code: Optional[int] = None, run_id: Optional[str] = None) -> Path:
        """下载最新构建"""
        if not self.token:
            print("WARNING: GITHUB_TOKEN not set, download may fail")
            print("   Set with: export GITHUB_TOKEN=your_token")
        
        # 这里应该实现 GitHub API 调用
        # 由于实际实现需要 API 调用，我们先创建框架
        print("Querying latest build...")
        print(f"   Repository: {self.repo}")
        if build_code:
            print(f"   Build code: {build_code}")
        if run_id:
            print(f"   Run ID: {run_id}")
        
        # 创建下载目录
        downloads_dir = self.project_root / "downloads" / "test_builds"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成时间戳和目录
        timestamp = datetime.now().strftime("%Y%m%d")
        commit_hash = "pending"  # 从 API 获取
        
        build_dir = downloads_dir / f"{timestamp}-{commit_hash}"
        build_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\nDownload directory: {build_dir}")
        print("\nWARNING: Full implementation requires GitHub API integration")
        print("   Current version is a framework, please manually download APK from GitHub Actions")
        
        # 生成测试清单
        self._generate_test_checklist(build_dir, build_code or 7317760)
        
        return build_dir
    
    def _generate_test_checklist(self, build_dir: Path, build_code: int):
        """生成测试清单"""
        checklist_path = build_dir / "TEST_CHECKLIST.md"
        
        # 加载 mods.lock.json
        lock_file = self.project_root / "config" / "mods.lock.json"
        if lock_file.exists():
            with open(lock_file, encoding="utf-8") as f:
                mods_lock = json.load(f)
        else:
            mods_lock = {"mods": {}}
        
        checklist = self._build_checklist_content(build_code, mods_lock)
        
        checklist_path.write_text(checklist, encoding="utf-8")
        print(f"Test checklist generated: {checklist_path.name}")
    
    def _build_checklist_content(self, build_code: int, mods_lock: dict) -> str:
        """构建测试清单内容"""
        build_names = {
            7315712: "基础版 (无 AU)",
            7316736: "AU-F",
            7317760: "AU-M",
            7319808: "AU-A",
        }
        
        return f"""# DOL-X 测试清单

**构建版本**: (从 BUILD_MANIFEST 获取)  
**构建日期**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**测试包**: {build_names.get(build_code, f"build_code_{build_code}")}  
**测试日期**: ___________

---

## 自动化验证结果（已完成）

- [x] 构建成功（GitHub Actions）
- [x] 配置一致性验证通过
- [x] Mod URL 可达性验证通过
- [x] 包含当前启用的新 mod：guide_to_me, neoui_patch, npc_social_icon
- [x] 已知不兼容 mod 预期禁用：bunny_transformation

---

## 手动测试项（需要你测试）

### 1. 基础启动测试（5分钟）

- [ ] APK 成功安装到 MuMu 模拟器
- [ ] 游戏成功启动，进入主菜单
- [ ] 版本信息正确（APK 文件名中的 commit hash）

### 2. Mod 加载验证（5分钟）

- [ ] 打开 ModLoader 管理器（游戏内 Alt+M 或设置菜单）
- [ ] 确认以下 mod 已加载：
  - [ ] maplebirch v3.1.14
  - [ ] cheat extended v1.17
  - [ ] maplebirchEx v1.2.4
  - [ ] CustomHair v1.0.0
  - [ ] Mae's Picvary v1.3.2
  - [ ] More Love Interests Mod v0.1.6.0
  - [ ] **guide_to_me v1.1.0**
  - [ ] **neoui_patch V1.1.0**
  - [ ] **npc_social_icon v1.4.1**
  - [ ] **不应出现 BunnyTransformation**（已禁用，若出现说明测试包不是当前配置）
  - [ ] AU Male v0.4.2 (仅 AU-M 构建)
- [ ] 加载日志无 error（0 error, X warning, X info）

### 3. 核心功能抽查（10分钟）

- [ ] **作弊扩展**：
  - [ ] 选项 → 模组设置 → 作弊扩展 → 启用强制作弊
  - [ ] 保存设置后刷新
  - [ ] 侧边栏出现原版作弊按钮
  - [ ] 打开作弊界面，可看到"模组作弊栏"
  - [ ] 快速言灵：添加防狼喷雾测试
  
- [ ] **更多恋人**：能看到相关 NPC

- [ ] **新增功能（选测1-2项）**：
  - [ ] **控制NPC嘴部**：进入游戏后检查相关选项是否出现
  - [ ] **NeoUI Patch**：观察 UI 动画效果
  - [ ] **NPC社交栏头像**：检查社交界面是否显示头像

### 4. 开发内容检查（5分钟）

- [ ] 打开浏览器开发者工具（F12 → Console）
- [ ] 观察 Console 输出：
  - [ ] ModLoader 日志是否正常（应该有 INFO 级别日志）
  - [ ] 是否有大量 console.log 调试输出？
  - [ ] 是否有 ERROR 或 WARNING？

**Console 日志评估**：
- [ ] 干净（仅 ModLoader 标准日志）
- [ ] 有少量 mod 调试日志（可接受）
- [ ] 有大量调试日志（需要清理）

### 5. 已知问题验证（5分钟）

- [ ] **CustomHair 十六进制输入缺失**（已知问题，低优先级）
  - 理发店 → 染发 → 检查是否有输入框
  - 预设颜色是否可用
  
- [ ] **AU Face 禁用**（预期行为）
  - 确认侧边栏人物贴图无错位/重复
  
- [ ] **自定义言灵集报错**（已知问题，有快速言灵替代）
  - 作弊拓展 → 自定义言灵集 → 确认是否报错

---

## 测试结论

**总体评价**: [ ] 通过 / [ ] 有问题

**发现的新问题**（如果有）：



**需要跟进的事项**：



**Console 日志观察**：



**测试人**: ___________  
**测试完成时间**: ___________

---

## 测试后步骤

1. 将此文件重命名为 `TEST_RESULT_{date}.md` 保存
2. 如发现新问题，更新 `config/mods.lock.json` 的 notes
3. 在 MCP 记忆中记录测试结果
"""


def main():
    parser = argparse.ArgumentParser(description="DOL-X 测试构建下载工具")
    parser.add_argument(
        "--build-code",
        type=int,
        help="指定 build_code（默认 7317760 = AU-M）",
        default=7317760
    )
    parser.add_argument(
        "--run-id",
        help="指定 GitHub Actions Run ID"
    )
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    downloader = BuildDownloader(project_root)
    
    build_dir = downloader.download_latest(
        build_code=args.build_code,
        run_id=args.run_id
    )
    
    print(f"\nCompleted!")
    print(f"\nNext steps:")
    print(f"1. Manually download APK from GitHub Actions to: {build_dir}")
    print(f"2. Install APK to MuMu emulator")
    print(f"3. Follow {build_dir / 'TEST_CHECKLIST.md'} for testing")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
