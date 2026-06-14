# DOL-X 下一步实施计划

**计划版本**: v1.0  
**制定日期**: 2026-06-14  
**当前系统状态**: ✅ 健康 (95/100)

---

## 📋 概述

DOL-X 项目已完成核心配置修复和系统清理。本文档规划接下来的实施路径，包括：

1. **Phase 2**: DoL-Commit2Mod 转换器集成
2. **Phase 3**: Playwright 游戏测试框架
3. **Phase 4**: 热加载开发环境
4. **上游同步策略**
5. **社区工具集成**

---

## 🎯 Phase 2: DoL-Commit2Mod 转换器集成

### 目标
将 DoL-Commit2Mod 功能重新实现为 DOL-X 的内置工具，用于快速验证上游 commit 的兼容性。

### 现状
- ✅ 核心模块已实现 (commit f38e910)
- ⏳ CLI 集成待完成
- ⏳ 测试覆盖待增强

### 实施计划

#### 2.1 审查现有代码 (1天)

**任务**:
1. 阅读 `tools/commit2mod_converter.py` (如存在)
2. 理解转换逻辑和依赖关系
3. 识别需要补充的功能

**验证**:
```bash
# 检查 Phase 2 相关文件
find . -name "*commit2mod*" -o -name "*converter*"
git log --grep="Phase 2" --oneline
```

#### 2.2 集成到 main.py CLI (2天)

**新增命令**:
```bash
# 转换单个 commit
python main.py convert-commit <commit-sha> --output output/commit-mod.zip

# 批量转换 commit 范围
python main.py convert-commits <start>..<end> --output-dir output/commits/

# 验证转换结果
python main.py verify-commit-mod output/commit-mod.zip
```

**实现**:
1. 在 `main.py` 添加 `convert-commit` 子命令
2. 调用 `tools/commit2mod_converter.py` 核心逻辑
3. 添加进度显示和错误处理
4. 生成转换报告 (JSON + Markdown)

#### 2.3 增强测试覆盖 (1天)

**新增测试**:
- `tests/test_commit2mod_converter.py` - 转换逻辑测试
- `tests/test_commit2mod_cli.py` - CLI 接口测试

**测试场景**:
1. 单文件 commit 转换
2. 多文件 commit 转换
3. 包含 Twee/JavaScript/CSS 的 commit
4. 错误处理 (无效 commit, 网络错误)

**验证命令**:
```bash
python -m pytest tests/test_commit2mod_* -v
```

#### 2.4 文档更新 (0.5天)

**新增文档**:
- `docs/COMMIT2MOD_USAGE.md` - 使用指南
- 更新 `QUICK_REFERENCE.md` - 添加 convert-commit 命令
- 更新 `README.md` - Phase 2 完成状态

**交付成果**:
- ✅ CLI 命令可用
- ✅ 测试覆盖 >80%
- ✅ 文档完整

**预计时间**: 4.5 天

---

## 🧪 Phase 3: Playwright 游戏测试框架

### 目标
构建独立的游戏逻辑测试框架，用于验证扩展场景、Mod 交互和存档兼容性。

### 现状
- ✅ Playwright 已安装 (用于 browser smoke tests)
- ✅ 基础烟雾测试框架存在
- ⏳ 深度游戏逻辑测试待开发

### 实施计划

#### 3.1 设计测试框架架构 (1天)

**核心组件**:
```
tests/gameplay/
├── framework/
│   ├── game_session.py      - 游戏会话管理
│   ├── page_objects/         - 页面对象模式
│   │   ├── start_page.py
│   │   ├── passage_page.py
│   │   └── save_page.py
│   ├── assertions.py         - 自定义断言
│   └── fixtures.py           - pytest fixtures
├── scenarios/
│   ├── test_character_creation.py
│   ├── test_basic_gameplay.py
│   ├── test_mod_interactions.py
│   └── test_save_compatibility.py
└── README.md                 - 测试框架文档
```

**设计原则**:
1. 页面对象模式 - 解耦测试逻辑和页面结构
2. 可复用 fixtures - 通用的游戏状态设置
3. 清晰的断言 - 专用于游戏状态的断言
4. 并行执行 - 独立的测试会话

#### 3.2 实现核心框架 (3天)

**game_session.py** - 游戏会话管理器:
```python
class GameSession:
    def __init__(self, browser, game_zip):
        self.browser = browser
        self.page = None
        
    async def start(self):
        """启动游戏并等待加载完成"""
        
    async def navigate_to_passage(self, passage_name):
        """导航到指定 passage"""
        
    async def get_variable(self, var_name):
        """获取游戏变量值"""
        
    async def save_game(self, slot=1):
        """保存游戏到指定槽位"""
        
    async def load_game(self, slot=1):
        """加载指定槽位的存档"""
```

**page_objects** - 页面对象:
- `StartPage` - 开始页面 (新游戏, 加载存档, 设置)
- `PassagePage` - 游戏场景页面 (文本, 选项, 状态栏)
- `SavePage` - 存档页面 (保存, 加载, 删除)

#### 3.3 编写测试场景 (2天)

**基础游戏测试**:
```python
# tests/gameplay/scenarios/test_basic_gameplay.py
async def test_character_creation(game_session):
    """测试角色创建流程"""
    await game_session.start()
    await game_session.navigate_to_passage("Start")
    # 设置角色属性
    await game_session.set_character_name("Test")
    # 验证角色创建成功
    name = await game_session.get_variable("$player.name")
    assert name == "Test"

async def test_save_load_cycle(game_session):
    """测试存档保存和加载"""
    await game_session.start()
    # 进行一些游戏操作
    await game_session.navigate_to_passage("Bedroom")
    # 保存游戏
    await game_session.save_game(slot=1)
    # 重启游戏
    await game_session.restart()
    # 加载存档
    await game_session.load_game(slot=1)
    # 验证状态恢复
    current_passage = await game_session.get_current_passage()
    assert current_passage == "Bedroom"
```

**Mod 交互测试**:
```python
# tests/gameplay/scenarios/test_mod_interactions.py
async def test_modloader_initialization(game_session):
    """测试 ModLoader 初始化"""
    await game_session.start()
    # 验证 ModLoader 加载
    modloader = await game_session.get_variable("window.modUtils")
    assert modloader is not None

async def test_cheat_extended_integration(game_session):
    """测试 cheatExtended 集成"""
    await game_session.start()
    # 打开作弊菜单
    await game_session.open_cheat_menu()
    # 修改金钱
    await game_session.set_variable("$money", 1000)
    # 验证修改成功
    money = await game_session.get_variable("$money")
    assert money == 1000
```

#### 3.4 集成到 CI/CD (1天)

**新增 GitHub Actions workflow**:
```yaml
# .github/workflows/gameplay-tests.yml
name: Gameplay Tests

on:
  workflow_dispatch:
  schedule:
    - cron: '0 2 * * *'  # 每天 2:00 AM

jobs:
  gameplay-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - name: Install Playwright
        run: |
          pip install playwright pytest-playwright
          playwright install chromium
      - name: Run gameplay tests
        run: |
          pytest tests/gameplay/ -v --html=report.html
      - name: Upload test report
        uses: actions/upload-artifact@v6
        with:
          name: gameplay-test-report
          path: report.html
```

**交付成果**:
- ✅ 游戏会话管理框架
- ✅ 10+ 基础测试场景
- ✅ CI/CD 集成
- ✅ 测试报告生成

**预计时间**: 7 天

---

## 🔥 Phase 4: 热加载开发环境

### 目标
实现代码更改后自动重新构建和刷新游戏，提升开发效率。

### 现状
- ⏳ 尚未开始 (优先级较低)
- ⏳ 需要先完成 Phase 2 和 3

### 实施计划

#### 4.1 文件监控系统 (1天)

**工具选择**: `watchdog` Python 库

**实现**:
```python
# tools/dev_server.py
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class GameSourceWatcher(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(('.twee', '.js', '.css')):
            print(f"Detected change: {event.src_path}")
            self.rebuild_game()
```

#### 4.2 增量构建系统 (2天)

**目标**: 只重新构建变更的文件

**实现**:
- 文件哈希缓存
- 依赖关系图
- 增量打包

#### 4.3 浏览器自动刷新 (1天)

**工具**: WebSocket + Browser Extension

**实现**:
- 后端 WebSocket 服务器通知文件变更
- 前端注入脚本监听刷新信号

**交付成果**:
- ✅ 文件监控工具
- ✅ 增量构建系统
- ✅ 浏览器自动刷新

**预计时间**: 4 天 (推迟到 Phase 2/3 完成后)

---

## 🔄 上游同步策略

### 目标
定期同步 DoL-Lyra 上游的有价值更新，同时保持 DOL-X 的独立性。

### 同步频率
- **每周检查**: 查看上游新 commits
- **每月合并**: 选择性合并有价值的上游更新
- **重大版本**: 上游发布新版本时评估全面合并

### 同步流程

#### 步骤 1: 检查上游更新
```bash
cd /e/game/repo/DOL-X
git fetch upstream
git log upstream/vega..vega --oneline --graph
git log vega..upstream/vega --oneline --graph
```

#### 步骤 2: 审查差异
```bash
# 生成差异报告
git diff upstream/vega...vega -- lyra/ > upstream_diff_lyra.patch
git diff upstream/vega...vega -- config/ > upstream_diff_config.patch

# 统计差异
git diff --stat upstream/vega...vega
```

#### 步骤 3: 选择性合并

**优先合并**:
- 核心构建系统 bug 修复 (`lyra/build.py`, `lyra/combo.py`)
- 安全补丁
- 性能优化
- 新的测试用例

**谨慎合并**:
- Mod 配置更改 (可能与 DOL-X 矩阵冲突)
- 文档更新 (需要调整为 DOL-X 语境)
- CI/CD 更改 (需要适配 DOL-X 工作流)

**不合并**:
- 与 DOL-X 策略冲突的更改
- 已被 DOL-X 重新实现的功能
- 纯上游特定的配置

#### 步骤 4: 测试验证
```bash
# 合并后运行完整测试
python -m pytest tests/ -v
python tools/system_health_check_simple.py

# 本地构建验证
python main.py build --jobs 4
```

#### 步骤 5: 记录差异
更新 `UPSTREAM_DIFF_SUMMARY.md` 记录：
- 合并的 commits
- 跳过的 commits 及原因
- DOL-X 独有的修改

---

## 🛠️ 社区工具集成

### 已调研工具

#### 1. DoL-Commit2Mod (Lethivia)
- **仓库**: https://github.com/Lethivia/DoL-Commit2Mod
- **状态**: 已调研，计划重新实现
- **用途**: 快速验证上游 commit
- **实施**: Phase 2

#### 2. rust-mod-dev (Paul-16098)
- **仓库**: https://github.com/Paul-16098/rust-mod-dev
- **状态**: 已归档
- **用途**: Rust 工具链支持
- **决策**: 暂不集成 (已归档，且 Python 工具链足够)

#### 3. DoLModRspackExampleTS (Muromi-Rikka)
- **仓库**: https://github.com/Muromi-Rikka/DoLModRspackExampleTS
- **状态**: 待评估
- **用途**: TypeScript Mod 开发示例
- **决策**: 待评估 (可能作为 Mod 开发模板)

#### 4. DOL-Mod-Created-Helper (NumberSir)
- **仓库**: https://github.com/NumberSir/DOL-Mod-Created-Helper
- **状态**: 待评估
- **用途**: Mod 创建辅助工具
- **决策**: 待评估 (可能整合到 `tools/add_mod.py`)

### 集成计划

**短期** (本月):
- ✅ DoL-Commit2Mod 重新实现 (Phase 2)
- ⏳ 评估 DOL-Mod-Created-Helper

**中期** (下月):
- ⏳ 评估 DoLModRspackExampleTS
- ⏳ 考虑创建 DOL-X 专属 Mod 开发模板

**长期** (季度):
- ⏳ 建立 DOL-X 社区工具生态
- ⏳ 贡献优化回上游项目

---

## 📅 时间线总结

### 本周 (2026-06-14 ~ 2026-06-21)
- [x] Phase 1: 修复 CI/CD 构建 (完成)
- [x] 工作区清理和同步 (完成)
- [x] 生成系统健康报告 (完成)
- [ ] 验证 GitHub Actions 构建
- [ ] Phase 2.1: 审查 commit2mod 代码

### 下周 (2026-06-21 ~ 2026-06-28)
- [ ] Phase 2.2-2.4: 完成 commit2mod 集成
- [ ] Phase 3.1: 设计游戏测试框架

### 本月 (2026-06)
- [ ] Phase 3.2-3.4: 实现游戏测试框架
- [ ] 首次上游同步
- [ ] 评估社区工具

### 下月 (2026-07)
- [ ] Phase 4: 热加载开发环境 (如需要)
- [ ] 建立 Mod 开发模板
- [ ] 增强测试覆盖

---

## ✅ 成功指标

### Phase 2 完成标准
- ✅ `python main.py convert-commit <sha>` 命令可用
- ✅ 测试覆盖率 >80%
- ✅ 文档完整 (COMMIT2MOD_USAGE.md)
- ✅ 本地和 CI 测试通过

### Phase 3 完成标准
- ✅ 10+ 游戏场景测试用例
- ✅ CI/CD 集成 (每日自动运行)
- ✅ 测试报告生成 (HTML + JSON)
- ✅ 框架文档完整

### Phase 4 完成标准
- ✅ 文件监控工具可用
- ✅ 增量构建时间 <5秒
- ✅ 浏览器自动刷新延迟 <1秒
- ✅ 开发体验文档

---

## 📞 反馈与调整

本计划是动态的，会根据实际进展调整。如有建议或优先级变更：

1. 更新本文档
2. 提交 git commit
3. 在 GitHub Issues 记录决策

**计划维护**: 每周五更新进度  
**下次审查**: 2026-06-21

---

**计划制定者**: DOL-X 系统恢复计划  
**版本**: v1.0  
**状态**: ✅ 就绪
