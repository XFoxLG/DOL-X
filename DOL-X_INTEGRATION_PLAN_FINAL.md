# DOL-X 模组工具完整集成计划 - 最终版

**生成时间**: 2026-06-14  
**决策者**: 用户  
**目标**: 全方位提升（扩展测试 + 自动回退 + 主动同步）

---

## 决策摘要

基于深度追问，你的最终决策：

| 维度 | 决策 | 影响 |
|------|------|------|
| **时间表** | 先研究最优解（1-2 周研究 + 4-5 周实施） | 避免返工，保证质量 |
| **必需功能** | 全部 6 项（Commit2Mod + 游戏逻辑 + 热加载 + CI） | 全方位覆盖 |
| **实现策略** | 先研究后决定（保持灵活性） | 基于证据决策 |
| **风险容忍度** | 允许暂时破坏 CI + 严格门禁 + 快速迭代 | 高质量 + 快速试错 |
| **测试覆盖** | **扩展场景**（基础 + More Love + Spellbook + 存档） | 最高质量 |
| **失败处理** | **自动回退** | 自动恢复，降低风险 |
| **上游同步** | **主动同步**（每周检查） | 提前发现兼容性问题 |

---

## 阶段 1: 深度研究（1-2 周）

### 目标
研究 DoL-Commit2Mod 和 MCH 源码，确定最优实现方案

### 1.1 研究 DoL-Commit2Mod

**任务**:
```bash
# 克隆到临时目录
git clone https://github.com/Lethivia/DoL-Commit2Mod.git /tmp/c2m-research
cd /tmp/c2m-research

# 阅读核心代码
cat main.py  # 分析主逻辑
```

**关键研究点**:
1. **Git Diff 解析**:
   - 如何提取新增文件？
   - 如何提取 Twee/JS 文件的行级差异？
   - 如何处理删除文件？

2. **boot.json 生成**:
   - TweeReplacer 参数格式（passage 名称 + 替换规则）
   - ReplacePatcher 参数格式（JS 文件路径 + 行号 + 替换内容）
   - dependenceInfo 如何自动推断？

3. **边界情况**:
   - 如果 commit 删除了整个功能？
   - 如果 commit 涉及二进制文件（图片）？
   - 如果 commit 涉及多个 passage？

**输出文档**: `docs/COMMIT2MOD_RESEARCH.md`（记录上述发现 + 代码片段）

---

### 1.2 研究 MCH REMOTE_TEST

**任务**:
```bash
# 克隆 MCH
git clone https://github.com/NumberSir/DOL-Mod-Created-Helper.git /tmp/mch-research
cd /tmp/mch-research

# 搜索关键代码
rg "REMOTE_TEST" -A 10
rg "Playwright" -A 10
rg "passage" -A 5
```

**关键研究点**:
1. **测试框架**:
   - 使用 Playwright 还是 Puppeteer？
   - 如何启动本地 HTTP 服务器？
   - 如何注入游戏全局变量检查？

2. **测试用例结构**:
   ```python
   # 示例：推测的 MCH 测试用例结构
   def test_orphanage_intro():
       page.goto("file://DoL.html")
       page.wait_for_selector("#passage")
       assert page.locator("#passage").inner_text() == "Orphanage Intro"
       page.click("text=Continue")
       assert page.evaluate("V.money") >= 0
   ```

3. **Mod 功能验证**:
   - 如何检查 ModLoader 加载状态？
   - 如何验证 AU Face blush 层？（检查 `img/face/default/default/blush*.png` 请求）
   - 如何验证 maplebirch 框架？（检查 `window.maplebirchFrameworks` 全局变量）

**输出文档**: `docs/MCH_REMOTE_TEST_RESEARCH.md`

---

### 1.3 决策实现策略

基于研究结果，在 `docs/INTEGRATION_STRATEGY.md` 中记录：

**DoL-Commit2Mod 实现方案对比**:

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| Fork 适配 | 快速（直接修改现有代码） | 维护成本高（需同步上游更新） | ⭐⭐⭐ |
| 重新实现 | 代码风格一致，完全可控 | 开发时间长（2-3 周） | ⭐⭐⭐⭐⭐ |
| 外部调用 | 实现简单（只需封装调用） | 依赖外部工具（用户需单独安装） | ⭐⭐ |

**游戏逻辑测试实现方案对比**:

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| 扩展 browser_smoke_test.py | 复用现有基础设施（HTTP 服务器、Playwright） | 单文件可能过大 | ⭐⭐⭐⭐ |
| 独立模块 tools/dev/game_test.py | 模块化，职责清晰 | 需重复实现 HTTP 服务器 | ⭐⭐⭐⭐⭐ |

**最终推荐**:
- DoL-Commit2Mod: **重新实现**（保持代码风格一致，长期维护成本低）
- 游戏逻辑测试: **独立模块**（职责清晰，易于扩展）

---

## 阶段 2: DoL-Commit2Mod 集成（2 周）

### 目标
实现 `python main.py dev commit-to-mod <hash>` + 自动构建

### 2.1 目录结构

```
DOL-X/
├── tools/
│   └── dev/
│       ├── __init__.py
│       ├── commit_to_mod.py      # 核心实现
│       └── git_diff_parser.py    # Git diff 解析
├── main.py                       # 添加 dev 子命令
└── docs/
    └── COMMIT2MOD_USAGE.md       # 使用指南
```

---

### 2.2 核心实现

**`tools/dev/commit_to_mod.py`**:

```python
from pathlib import Path
import json
import subprocess
from typing import Dict, List

class CommitToModConverter:
    def __init__(self, repo_path: Path, commit_hash: str):
        self.repo_path = repo_path
        self.commit_hash = commit_hash
    
    def extract_changes(self) -> Dict[str, List[str]]:
        """提取 commit 变更"""
        # 获取 diff
        diff = subprocess.run(
            ["git", "show", self.commit_hash],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        ).stdout
        
        # 解析 diff
        return self._parse_diff(diff)
    
    def generate_boot_json(self, changes: Dict) -> Dict:
        """生成 boot.json"""
        return {
            "name": f"Upstream-{self.commit_hash[:7]}",
            "version": "1.0.0",
            "author": "DOL-X Auto-generated",
            "description": f"Auto-generated from commit {self.commit_hash}",
            "additionFile": changes.get("new_files", []),
            "TweeReplacer": self._build_twee_replacer(changes.get("twee_diffs", [])),
            "ReplacePatcher": self._build_replace_patcher(changes.get("js_diffs", [])),
        }
    
    def build_mod_zip(self, output_dir: Path) -> Path:
        """构建 mod.zip"""
        # 实现打包逻辑
        pass
```

**`main.py` 添加 dev 子命令**:

```python
def cmd_dev(args) -> int:
    """开发工具命令"""
    if args.dev_command == "commit-to-mod":
        from tools.dev.commit_to_mod import CommitToModConverter
        
        converter = CommitToModConverter(
            repo_path=Path(args.repo) if args.repo else Path("."),
            commit_hash=args.commit
        )
        
        changes = converter.extract_changes()
        boot_json = converter.generate_boot_json(changes)
        mod_zip_path = converter.build_mod_zip(Path(args.workspace) / "experimental_mods")
        
        logger.info(f"Mod 生成成功: {mod_zip_path}")
        
        if args.auto_build:
            # 触发构建
            subprocess.run([
                "python", "main.py", "build",
                "--codes", args.codes or "57600",
                "--workspace", args.workspace
            ])
        
        return 0
```

---

### 2.3 集成到构建流程

**用法示例**:

```bash
# 基础用法：测试上游最新提交
python main.py dev commit-to-mod HEAD --repo https://github.com/DoL-Lyra/Lyra.git

# 自动构建：生成 mod 后立即构建基础版
python main.py dev commit-to-mod abc1234 --auto-build --codes 57600

# 批量测试：测试最近 5 个提交
for hash in $(git log upstream/vega -5 --format=%H); do
    python main.py dev commit-to-mod $hash --auto-build
done
```

---

### 2.4 主动同步上游（每周自动化）

**创建 `.github/workflows/upstream-sync.yml`**:

```yaml
name: Upstream Sync Check

on:
  schedule:
    - cron: '0 0 * * 0'  # 每周日 00:00 UTC
  workflow_dispatch:

jobs:
  check-upstream:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      
      - name: Fetch upstream
        run: |
          git remote add upstream https://github.com/DoL-Lyra/Lyra.git || true
          git fetch upstream vega
      
      - name: Check new commits
        id: check
        run: |
          NEW_COMMITS=$(git log HEAD..upstream/vega --oneline | wc -l)
          echo "count=$NEW_COMMITS" >> $GITHUB_OUTPUT
          
          if [ $NEW_COMMITS -gt 0 ]; then
            echo "## 🚨 上游有 $NEW_COMMITS 个新提交" >> $GITHUB_STEP_SUMMARY
            git log HEAD..upstream/vega --oneline | head -5 >> $GITHUB_STEP_SUMMARY
          fi
      
      - name: Test new commits
        if: steps.check.outputs.count > 0
        run: |
          for hash in $(git log HEAD..upstream/vega --format=%H | head -5); do
            python main.py dev commit-to-mod $hash --auto-build || echo "::warning::Commit $hash 测试失败"
          done
      
      - name: Create issue if incompatible
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '⚠️ 上游兼容性问题',
              body: '最近的上游提交与 DOL-X 配置冲突，请查看 Actions 日志。',
              labels: ['upstream-sync', 'needs-attention']
            })
```

---

## 阶段 3: 游戏逻辑测试集成（2-3 周）

### 目标
实现全面的游戏逻辑测试 + 自动回退 + CI 严格门禁

### 3.1 目录结构

```
DOL-X/
├── tools/
│   └── dev/
│       ├── game_logic_test.py    # 游戏逻辑测试框架
│       └── test_server.py        # 测试用 HTTP 服务器
├── tests/
│   ├── game_logic/
│   │   ├── __init__.py
│   │   ├── test_basic_flow.py        # 基础流程（开场 + 命名 + 第一天）
│   │   ├── test_cheat_extended.py    # 作弊菜单
│   │   ├── test_au_face.py           # AU Face 渲染
│   │   ├── test_more_love.py         # More Love Interests
│   │   ├── test_custom_spellbook.py  # Custom Spellbook
│   │   └── test_save_compat.py       # 存档兼容性
│   └── conftest.py               # Pytest 配置（共享 fixtures）
└── docs/
    └── GAME_LOGIC_TEST_MAINTENANCE.md  # 测试维护指南
```

---

### 3.2 测试框架实现

**`tools/dev/game_logic_test.py`**:

```python
from playwright.sync_api import sync_playwright, Page
from pathlib import Path
import http.server
import threading
import time

class GameLogicTestRunner:
    def __init__(self, zip_path: Path, headless: bool = True):
        self.zip_path = zip_path
        self.headless = headless
        self.server = None
        self.server_thread = None
    
    def __enter__(self):
        # 启动 HTTP 服务器
        self._start_server()
        # 启动 Playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        return self
    
    def __exit__(self, *args):
        self.browser.close()
        self.playwright.stop()
        self._stop_server()
    
    def goto_game(self):
        """打开游戏"""
        self.page.goto(f"http://localhost:8000/Degrees of Lewdity.html")
        self.page.wait_for_selector("#passage", timeout=10000)
    
    def get_passage(self) -> str:
        """获取当前 passage 名称"""
        return self.page.locator("#passage").get_attribute("data-passage")
    
    def click_option(self, text: str):
        """点击选项"""
        self.page.click(f"text={text}")
        self.page.wait_for_load_state("networkidle")
    
    def evaluate_game_var(self, var_name: str):
        """获取游戏变量"""
        return self.page.evaluate(f"{var_name}")
    
    def check_mod_loaded(self, mod_name: str) -> bool:
        """检查 mod 是否加载"""
        mod_list = self.page.evaluate("window.modDataValueZipList || []")
        return any(mod_name in str(mod) for mod in mod_list)
```

---

### 3.3 完整测试用例（扩展场景）

#### 3.3.1 基础流程测试

**`tests/game_logic/test_basic_flow.py`**:

```python
import pytest
from tools.dev.game_logic_test import GameLogicTestRunner

@pytest.mark.parametrize("build_code", ["57600", "58624", "59648", "61696"])
def test_orphanage_intro_flow(build_code, game_zip_path):
    """测试开场流程（孤儿院 → 命名 → 第一天）"""
    with GameLogicTestRunner(game_zip_path(build_code)) as runner:
        runner.goto_game()
        
        # 断言：初始 passage
        assert runner.get_passage() == "Start"
        
        # 点击开始游戏
        runner.click_option("Begin")
        assert runner.get_passage() == "Characteristics"
        
        # 输入名字
        runner.page.fill("#text-box", "TestPlayer")
        runner.click_option("Next")
        
        # 断言：进入孤儿院
        assert runner.get_passage() == "Orphanage"
        assert runner.evaluate_game_var("V.player.name") == "TestPlayer"
        assert runner.evaluate_game_var("V.money") >= 0
        
        # 第一天：起床
        runner.click_option("Get up")
        assert "Bedroom" in runner.get_passage()
```

---

#### 3.3.2 作弊菜单测试

**`tests/game_logic/test_cheat_extended.py`**:

```python
def test_cheat_extended_menu_available(game_zip_path):
    """测试 cheatExtended + maplebirch 菜单可用性"""
    with GameLogicTestRunner(game_zip_path("57600")) as runner:
        runner.goto_game()
        
        # 检查 maplebirch 框架加载
        assert runner.evaluate_game_var("typeof window.maplebirchFrameworks") == "object"
        assert runner.evaluate_game_var("typeof window.CE_options") == "object"
        
        # 打开作弊菜单（假设快捷键是 F12）
        runner.page.keyboard.press("F12")
        runner.page.wait_for_selector("#cheat-menu", timeout=5000)
        
        # 验证作弊选项存在
        assert runner.page.locator("text=无限金钱").is_visible()
        assert runner.page.locator("text=时间控制").is_visible()
```

---

#### 3.3.3 AU Face 渲染测试

**`tests/game_logic/test_au_face.py`**:

```python
@pytest.mark.parametrize("au_variant", ["58624", "59648", "61696"])  # AU-F/M/A
def test_au_face_blush_rendering(au_variant, game_zip_path):
    """测试 AU Face blush 层加载"""
    with GameLogicTestRunner(game_zip_path(au_variant)) as runner:
        runner.goto_game()
        
        # 进入角色查看界面
        runner.click_option("Begin")
        # ... 导航到显示角色立绘的 passage
        
        # 监听图片请求
        image_requests = []
        runner.page.on("request", lambda req: image_requests.append(req.url) if "blush" in req.url else None)
        
        # 触发 blush 层（假设通过某个选项）
        runner.page.wait_for_timeout(2000)  # 等待立绘渲染
        
        # 断言：至少请求了 blush 图片
        blush_requests = [r for r in image_requests if "face/default/default/blush" in r]
        assert len(blush_requests) > 0, "AU Face blush 层未加载"
        
        # 检查兼容性别名是否生效
        assert any("face/default/default/blush" in r for r in blush_requests)
```

---

#### 3.3.4 More Love Interests 测试

**`tests/game_logic/test_more_love.py`**:

```python
def test_more_love_npc_interaction(game_zip_path):
    """测试 More Love Interests 新 NPC 可交互"""
    with GameLogicTestRunner(game_zip_path("57600")) as runner:
        runner.goto_game()
        
        # 导航到新 NPC 出现的位置（假设是学校）
        runner.click_option("Begin")
        # ... 导航到学校
        
        # 检查新 NPC 是否出现
        assert runner.page.locator("text=Jordan").is_visible()  # More Love 新增 NPC
        
        # 尝试互动
        runner.click_option("Talk to Jordan")
        assert "Jordan" in runner.page.content()
```

---

#### 3.3.5 Custom Spellbook 测试

**`tests/game_logic/test_custom_spellbook.py`**:

```python
def test_custom_spellbook_open(game_zip_path):
    """测试 Custom Spellbook 打开功能"""
    with GameLogicTestRunner(game_zip_path("57600")) as runner:
        runner.goto_game()
        
        # 检查 spellbook 全局变量
        assert runner.evaluate_game_var("typeof window.spellBookMobileClicked") == "function"
        
        # 点击魔法书按钮
        runner.page.click('[onclick*="spellBookMobileClicked"]')
        runner.page.wait_for_selector("#spellbook-dialog", timeout=5000)
        
        # 验证对话框打开
        assert runner.page.locator("#spellbook-dialog").is_visible()
        assert runner.page.locator("text=自定义魔法书").is_visible()
```

---

#### 3.3.6 存档兼容性测试

**`tests/game_logic/test_save_compat.py`**:

```python
def test_save_load_compatibility(game_zip_path):
    """测试存档加载兼容性"""
    with GameLogicTestRunner(game_zip_path("57600")) as runner:
        runner.goto_game()
        
        # 创建存档
        runner.click_option("Begin")
        runner.page.fill("#text-box", "SaveTest")
        runner.click_option("Next")
        runner.click_option("Save to Slot 1")
        
        # 重新加载游戏
        runner.page.reload()
        runner.page.wait_for_selector("#passage")
        
        # 加载存档
        runner.click_option("Load from Slot 1")
        
        # 验证存档数据
        assert runner.evaluate_game_var("V.player.name") == "SaveTest"
        assert runner.evaluate_game_var("V.money") >= 0
```

---

### 3.4 自动回退机制

**创建 `.github/workflows/auto-revert.yml`**:

```yaml
name: Auto Revert on Test Failure

on:
  push:
    branches:
      - vega

jobs:
  test-and-revert:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 2  # 需要获取前一次提交
      
      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install playwright pytest
          playwright install chromium
      
      - name: Run game logic tests
        id: test
        continue-on-error: true
        run: |
          pytest tests/game_logic/ -v --tb=short
      
      - name: Auto revert if tests fail
        if: steps.test.outcome == 'failure'
        run: |
          # 获取失败的提交 hash
          FAILED_COMMIT=$(git rev-parse HEAD)
          
          # Revert
          git config user.name "DOL-X Auto-Revert Bot"
          git config user.email "bot@dol-x"
          git revert --no-edit $FAILED_COMMIT
          git push origin vega
          
          # 创建 issue 通知
          gh issue create \
            --title "🚨 自动回退: $FAILED_COMMIT 破坏了游戏逻辑测试" \
            --body "提交 $FAILED_COMMIT 导致游戏逻辑测试失败，已自动回退。请查看 Actions 日志。" \
            --label "auto-revert,needs-fix"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

### 3.5 CI 严格门禁

**修改 `.github/workflows/build.yaml`**:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      # ... 现有构建步骤 ...
      
      - name: Run game logic tests (strict gate)
        run: |
          pytest tests/game_logic/ -v --tb=short --maxfail=1
          # --maxfail=1: 第一个失败立即停止
      
      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: game-logic-test-reports
          path: |
            pytest-report.html
            screenshots/  # Playwright 失败截图
```

---

## 阶段 4: 热加载开发（可选，1 周）

### 目标
文件变更 → 自动重新打包 → 浏览器刷新

### 4.1 实现方案

**`tools/dev_server.py`**:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time

class ModChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith((".json", ".js", ".twee")):
            print(f"检测到变更: {event.src_path}")
            # 重新打包
            subprocess.run(["python", "main.py", "build", "--codes", "57600"])
            # 通知浏览器刷新（通过 WebSocket）
            self.notify_browser_refresh()

# 启动文件监控
observer = Observer()
observer.schedule(ModChangeHandler(), path="workspace/", recursive=True)
observer.start()
```

---

## 总结：预估时间与投资回报

### 时间预估

| 阶段 | 任务 | 时间 |
|------|------|------|
| 1 | 深度研究 | 1-2 周 |
| 2 | DoL-Commit2Mod | 2 周 |
| 3 | 游戏逻辑测试（扩展 + 自动回退 + CI） | 2-3 周 |
| 4 | 热加载开发（可选） | 1 周 |
| **总计** | | **6-8 周**（约 1.5-2 个月） |

### 投资回报分析

**投入**: 6-8 周开发时间

**回报**:
- **即时收益**（每次构建节省 15-20 分钟手动测试）
- **质量提升**（自动回退机制避免发布破损产物）
- **上游同步**（每周自动检查，提前发现兼容性问题）
- **长期维护成本降低**（自动化测试覆盖核心功能）

**ROI**: 如果你每周构建 3 次，每次节省 15 分钟 = **45 分钟/周**。8 周后回本，之后持续收益。

---

## 下一步行动

请确认以下问题后，我将开始执行：

1. ✅ **测试覆盖**: 扩展场景（基础 + More Love + Spellbook + 存档）
2. ✅ **失败处理**: 自动回退
3. ✅ **上游同步**: 主动同步（每周检查）

**准备好开始了吗？** 请回复 "开始执行" 或提出最后的调整建议。
