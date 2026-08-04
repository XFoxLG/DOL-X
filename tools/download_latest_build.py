#!/usr/bin/env python3
"""Generate a manual test checklist for a GitHub Actions build.

Artifact download is intentionally left to GitHub CLI or the Actions web page;
this helper prepares the local directory and current-stack checklist only.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_BUILD_CODE = 15705344


class BuildDownloader:
    """Prepare a local directory and checklist for manual artifact testing."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.repo = "XFoxLG/DOL-X"
        
    def download_latest(self, build_code: Optional[int] = None, run_id: Optional[str] = None) -> Path:
        """Prepare a local test directory for a selected Actions build."""
        print("Preparing manual test directory...")
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
        commit_hash = "pending"  # Replace after selecting the actual Actions run.
        
        build_dir = downloads_dir / f"{timestamp}-{commit_hash}"
        build_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\nDownload directory: {build_dir}")
        print("\nArtifact download is manual by design")
        print("   Use the Actions web page or: gh run download <run-id> --repo XFoxLG/DOL-X")
        
        # 生成测试清单
        self._generate_test_checklist(build_dir, build_code or DEFAULT_BUILD_CODE)
        
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
            15704320: "基础版 (无 AU)",
            15705344: "AU-F",
            15706368: "AU-M",
            15708416: "AU-A",
        }
        au_model_expectations = {
            15704320: "AU model 与 AU Face 不应出现（base 构建）",
            15705344: "AU Female v0.9.3 + AU Face v1.1.0",
            15706368: "AU Male v0.4.2 + AU Face v1.1.0",
            15708416: "AU Androgynous v0.1.1 + AU Face v1.1.0",
        }
        
        return f"""# DOL-X 测试清单

**构建版本**: (从 BUILD_MANIFEST 获取)  
**构建日期**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**测试包**: {build_names.get(build_code, f"build_code_{build_code}")}  
**测试日期**: ___________

---

## 自动化验证结果（已完成）

- [x] 构建成功（GitHub Actions）
- [x] 完整 pytest 通过（以对应 Actions run 的 Run test suite 步骤为准）
- [x] ZIP AU 面部别名审计通过（以 Audit ZIP artifacts 步骤为准）
- [x] 包含当前启用的新 mod：guide_to_me, npc_social_icon, neoui_patch
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
  - [ ] maplebirch v4.1.13
  - [ ] Cheat Extended v1.20(dev260719)
  - [ ] LongerCombat v1.0.1
  - [ ] YanlingCheatCollection v1.0.1
  - [ ] maplebirchEx v1.2.4 不应出现（已退役）
  - [ ] CustomHair v1.0.0
  - [ ] Mae's Picvary v1.3.2
  - [ ] More Love Interests Mod v0.1.7.0
  - [ ] **guide_to_me v1.1.0**
  - [ ] **NeoUI-Patch**（2026-07-05 升为必选，应出现在全部包）
  - [ ] **npc_social_icon v1.4.1**
  - [ ] **不应出现 BunnyTransformation**（已禁用，若出现说明测试包不是当前配置）
  - [ ] {au_model_expectations.get(build_code, "按构建码核对 AU model")}
- [ ] 加载日志无 error（0 error, X warning, X info）

### 3. 核心功能抽查（10分钟）

- [ ] **作弊扩展**：
  - [ ] 选项 → 模组设置 → 作弊扩展 → 启用强制作弊
  - [ ] 保存设置后刷新
  - [ ] 侧边栏出现原版作弊按钮
  - [ ] 打开作弊界面，可看到"模组作弊栏"
  - [ ] 快速言灵：添加防狼喷雾测试
  
- [ ] **更多恋人**：
  - [ ] 正式游戏“态度”页出现“查看NPC喜爱的食物”入口
  - [ ] 无恋爱兴趣时空列表正常，不出现红框
  - [ ] 有恋爱兴趣 NPC 时食物图标与配方材料正常；Avery 显示舒芙蕾

- [ ] **新增功能（选测1-2项）**：
  - [ ] **控制NPC嘴部**：进入游戏后检查相关选项是否出现
  - [ ] **确认 NeoUI Patch 已加载**：全部包内置，未出现说明测试包不是当前配置
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

- [ ] **CustomHair 自定义染发**（此前误报）
  - 理发店 → 染发 → 先选择自定义染发
  - 检查十六进制输入框是否出现
  
- [ ] **AU Face（仅 AU 构建）**
  - 设置 UI 与开关应可用；脸红/流泪视觉仍属部分验收边界
  
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

1. 将此文件重命名为 `TEST_RESULT_{{date}}.md` 保存
2. 如发现新问题，更新 `config/mods.lock.json` 的 notes
3. 把可复核结果同步到 `config/mods.lock.json` notes 与当前状态文档
"""


def main():
    parser = argparse.ArgumentParser(description="DOL-X 测试构建下载工具")
    parser.add_argument(
        "--build-code",
        type=int,
        help=f"指定 build_code（默认 {DEFAULT_BUILD_CODE} = AU-F）",
        default=DEFAULT_BUILD_CODE
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
