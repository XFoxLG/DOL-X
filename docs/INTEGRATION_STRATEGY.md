# DOL-X 模组工具集成策略决策文档

**决策时间**: 2026-06-14  
**基于**: DoL-Commit2Mod 研究 + MCH REMOTE_TEST 研究  
**目标**: 确定最优实现方案

---

## 执行摘要

经过深度研究 DoL-Commit2Mod 和 MCH 的源码与实现细节，现制定以下集成策略：

| 功能 | 推荐方案 | 理由 |
|------|---------|------|
| **DoL-Commit2Mod** | **重新实现** | 代码量小（~500 行），易于集成到 DOL-X 架构 |
| **游戏逻辑测试** | **独立模块** | 职责清晰，易于扩展，复用 Playwright |
| **热加载开发** | **Phase 4 实现** | 优先级较低，在核心功能稳定后再考虑 |

---

## 第一部分：DoL-Commit2Mod 集成策略

### 1.1 方案对比

| 方案 | 优点 | 缺点 | 开发时间 | 推荐度 |
|------|------|------|---------|--------|
| **方案 A: Fork 适配** | 快速（直接修改现有代码）<br>无需从头实现 | 维护成本高（需同步上游更新）<br>代码风格不一致<br>难以集成到 DOL-X 架构 | 3-5 天 | ⭐⭐⭐ |
| **方案 B: 重新实现** | 代码风格一致<br>完全可控<br>易于扩展（依赖推断、CSS 支持）<br>无上游同步负担 | 开发时间较长<br>需要理解 ModLoader 格式 | 1-2 周 | ⭐⭐⭐⭐⭐ |
| **方案 C: 外部调用** | 实现简单（只需封装调用）<br>快速原型验证 | 依赖外部工具（用户需单独安装）<br>调试困难<br>无法定制化 | 2-3 天 | ⭐⭐ |

### 1.2 最终决策：方案 B（重新实现）

**核心理由**:
1. **代码量可控**: DoL-Commit2Mod 核心逻辑仅 ~500 行，重写成本合理
2. **架构一致性**: 可完美集成到 DOL-X 的 `tools/dev/` 架构
3. **易于扩展**: 
   - 添加依赖推断（自动检测 maplebirch、Simple Framework）
   - 支持 CSS 文件差异提取
   - 优雅的错误处理（而非直接退出）
4. **长期维护**: 无需担心上游 DoL-Commit2Mod 的破坏性更新

---

### 1.3 实现架构

**目录结构**:
```
DOL-X/
├── tools/
│   └── dev/
│       ├── __init__.py
│       ├── commit_to_mod.py       # 核心转换逻辑
│       ├── git_diff_parser.py     # Git diff 解析器
│       ├── dependency_inferrer.py # 依赖推断器
│       └── boot_json_builder.py   # boot.json 构建器
├── main.py                        # 添加 dev 子命令
└── docs/
    └── COMMIT2MOD_USAGE.md        # 使用指南
```

**核心类设计**:
```python
# tools/dev/commit_to_mod.py
from pathlib import Path
from typing import Dict, List
import logging

class CommitToModConverter:
    """Git Commit → ModLoader mod.zip 转换器"""
    
    def __init__(self, repo_path: Path, commit_hash: str, 
                 mod_name: str = None, logger: logging.Logger = None):
        self.repo_path = repo_path
        self.commit_hash = commit_hash
        self.mod_name = mod_name or f"Upstream-{commit_hash[:7]}"
        self.logger = logger or logging.getLogger(__name__)
    
    def convert(self, output_dir: Path) -> Path:
        """执行转换，返回生成的 mod.zip 路径"""
        # 1. 提取变更
        changes = self._extract_changes()
        
        # 2. 生成 boot.json
        boot_json = self._generate_boot_json(changes)
        
        # 3. 打包为 zip
        zip_path = self._build_zip(output_dir, changes, boot_json)
        
        return zip_path
    
    def _extract_changes(self) -> Dict:
        """提取 commit 变更（新增/修改文件）"""
        from .git_diff_parser import GitDiffParser
        parser = GitDiffParser(self.repo_path, self.commit_hash)
        return parser.parse()
    
    def _generate_boot_json(self, changes: Dict) -> Dict:
        """生成 boot.json"""
        from .boot_json_builder import BootJsonBuilder
        from .dependency_inferrer import DependencyInferrer
        
        builder = BootJsonBuilder(self.mod_name)
        
        # 添加新增文件
        builder.add_addition_files(changes["new_files"])
        
        # 添加 Twee 替换参数
        builder.add_twee_replacer(changes["twee_diffs"])
        
        # 添加 JS 替换参数
        builder.add_replace_patcher(changes["js_diffs"])
        
        # 推断依赖
        inferrer = DependencyInferrer(changes)
        dependencies = inferrer.infer()
        builder.add_dependencies(dependencies)
        
        return builder.build()
    
    def _build_zip(self, output_dir: Path, changes: Dict, 
                   boot_json: Dict) -> Path:
        """打包为 mod.zip"""
        # 实现打包逻辑
        pass
```

---

### 1.4 改进点（相比上游）

**必须实现的改进**:

1. **依赖推断**（上游缺失）:
   ```python
   class DependencyInferrer:
       def infer(self, changes: Dict) -> List[str]:
           dependencies = []
           
           # 检查是否使用 maplebirch 框架
           for content in changes["twee_contents"]:
               if "maplebirchFrameworks" in content:
                   dependencies.append("Simple Framework")
                   break
           
           return dependencies
   ```

2. **优雅的错误处理**（上游直接 sys.exit(1)）:
   ```python
   try:
       result = subprocess.run([...], check=True)
   except subprocess.CalledProcessError as e:
       self.logger.warning(f"处理 {file_path} 失败: {e}")
       continue  # 跳过该文件，继续处理
   ```

3. **DOL-X 日志系统集成**:
   ```python
   from lyra.logging import get_logger
   logger = get_logger(__name__)
   logger.info(f"新增文件: {len(new_files)}")
   ```

**可选改进**（Phase 2 扩展）:
- CSS 文件差异提取
- 批量处理多个 commit
- 测试模式（生成 mod 后自动触发构建）

---

### 1.5 集成到 main.py

**命令格式**:
```bash
python main.py dev commit-to-mod <hash> [options]

Options:
  --repo URL           Git 仓库 URL（默认当前仓库）
  --name NAME          Mod 名称（默认 Upstream-<hash>）
  --auto-build         生成 mod 后自动触发构建
  --codes CODES        构建哪个版本（如 57600，多个用逗号分隔）
```

**实现**:
```python
# main.py
def cmd_dev(args) -> int:
    """开发工具命令"""
    if args.dev_command == "commit-to-mod":
        from tools.dev.commit_to_mod import CommitToModConverter
        
        converter = CommitToModConverter(
            repo_path=Path(args.repo) if args.repo else Path("."),
            commit_hash=args.commit,
            mod_name=args.name
        )
        
        mod_zip = converter.convert(output_dir=Path("workspace/experimental_mods"))
        logger.info(f"Mod 生成成功: {mod_zip}")
        
        if args.auto_build:
            # 触发构建
            for code in args.codes.split(","):
                subprocess.run(["python", "main.py", "build", "--codes", code.strip()])
        
        return 0
```

---

## 第二部分：游戏逻辑测试集成策略

### 2.1 方案对比

| 方案 | 优点 | 缺点 | 开发时间 | 推荐度 |
|------|------|------|---------|--------|
| **方案 A: 扩展 browser_smoke_test.py** | 复用现有基础设施<br>快速上手 | 单文件可能过大<br>职责不够清晰 | 1-2 周 | ⭐⭐⭐⭐ |
| **方案 B: 独立模块** | 职责清晰<br>易于扩展<br>测试用例独立 | 需实现 HTTP 服务器封装 | 2-3 周 | ⭐⭐⭐⭐⭐ |
| **方案 C: 集成 MCH** | 快速原型验证 | MCH 无自动化测试能力<br>仅是热加载工具 | N/A | ❌ 不可行 |

### 2.2 最终决策：方案 B（独立模块）

**核心理由**:
1. **职责清晰**: `browser_smoke_test.py` 专注基础启动测试，`game_logic/` 专注游戏逻辑
2. **易于扩展**: 6 大测试套件独立文件，便于维护
3. **pytest 友好**: 标准的 pytest 项目结构，支持 fixtures、parametrize

---

### 2.3 实现架构

**目录结构**:
```
DOL-X/
├── tools/
│   └── dev/
│       ├── game_logic_test.py    # 测试框架核心
│       └── test_server.py        # HTTP 服务器封装
├── tests/
│   ├── game_logic/
│   │   ├── __init__.py
│   │   ├── test_basic_flow.py        # 基础流程（开场 + 命名 + 第一天）
│   │   ├── test_cheat_extended.py    # 作弊菜单
│   │   ├── test_au_face.py           # AU Face 渲染
│   │   ├── test_more_love.py         # More Love Interests
│   │   ├── test_custom_spellbook.py  # Custom Spellbook
│   │   └── test_save_compat.py       # 存档兼容性
│   └── conftest.py               # Pytest fixtures
└── docs/
    └── GAME_LOGIC_TEST_MAINTENANCE.md  # 测试维护指南
```

**核心类设计**:
```python
# tools/dev/game_logic_test.py
from playwright.sync_api import sync_playwright, Page
from pathlib import Path
import http.server
import threading
import zipfile
import tempfile
import shutil

class GameLogicTestRunner:
    """游戏逻辑测试运行器
    
    用法:
        with GameLogicTestRunner(zip_path) as runner:
            runner.goto_game()
            assert runner.get_passage() == "Start"
            runner.click_option("Begin")
    """
    
    def __init__(self, zip_path: Path, headless: bool = True):
        self.zip_path = zip_path
        self.headless = headless
        # ... 初始化
    
    def __enter__(self):
        """启动 HTTP 服务器 + Playwright"""
        # 1. 解压 ZIP
        self.temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(self.zip_path, 'r') as zf:
            zf.extractall(self.temp_dir)
        
        # 2. 启动 HTTP 服务器
        self._start_server()
        
        # 3. 启动 Playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        
        return self
    
    def __exit__(self, *args):
        """清理资源"""
        # 关闭浏览器、服务器、删除临时文件
        pass
    
    # API 方法
    def goto_game(self):
        """打开游戏"""
        pass
    
    def get_passage(self) -> str:
        """获取当前 passage"""
        pass
    
    def click_option(self, text: str):
        """点击选项"""
        pass
    
    def evaluate_game_var(self, var_name: str):
        """获取游戏变量"""
        pass
    
    def check_mod_loaded(self, mod_name: str) -> bool:
        """检查 mod 是否加载"""
        pass
```

---

### 2.4 测试覆盖范围

**6 大测试套件**:

| 测试套件 | 文件 | 测试内容 | 优先级 |
|---------|------|---------|--------|
| **基础流程** | test_basic_flow.py | 开场 → 命名 → 孤儿院 → 第一天 | ⭐⭐⭐⭐⭐ |
| **作弊菜单** | test_cheat_extended.py | maplebirch 框架加载<br>CE_options 全局变量<br>作弊菜单可见性 | ⭐⭐⭐⭐⭐ |
| **AU Face** | test_au_face.py | blush 层图片请求<br>兼容性别名路径 | ⭐⭐⭐⭐⭐ |
| **More Love** | test_more_love.py | 新 NPC 可见性<br>互动功能 | ⭐⭐⭐⭐ |
| **Spellbook** | test_custom_spellbook.py | 魔法书打开<br>全局变量检查 | ⭐⭐⭐⭐ |
| **存档兼容** | test_save_compat.py | 存档创建<br>存档加载<br>数据完整性 | ⭐⭐⭐ |

**预估测试用例数量**: 
- 每个套件 3-5 个测试用例
- 总计约 20-30 个测试用例
- 参数化后覆盖 4 个 build_codes（57600/58624/59648/61696）
- **总测试数**: 80-120 个（参数化展开后）

---

### 2.5 CI 集成策略

**GitHub Actions 配置**:

```yaml
# .github/workflows/build.yaml
jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      # ... 现有构建步骤 ...
      
      - name: Install Playwright
        run: |
          pip install playwright
          playwright install chromium
      
      - name: Run game logic tests (strict gate)
        id: game_tests
        run: |
          pytest tests/game_logic/ -v --tb=short --maxfail=1
      
      - name: Auto revert on failure
        if: failure() && steps.game_tests.outcome == 'failure'
        run: |
          FAILED_COMMIT=$(git rev-parse HEAD)
          git config user.name "DOL-X Auto-Revert Bot"
          git config user.email "bot@dol-x"
          git revert --no-edit $FAILED_COMMIT
          git push origin vega
          
          gh issue create \
            --title "🚨 自动回退: $FAILED_COMMIT 破坏游戏逻辑测试" \
            --body "测试失败，已自动回退。查看 Actions 日志。" \
            --label "auto-revert"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Upload test artifacts
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: test-reports
          path: |
            pytest-report.html
            screenshots/
```

---

## 第三部分：热加载开发功能（可选）

### 3.1 优先级评估

**收益分析**:
- ✅ 开发体验提升：修改代码后自动刷新浏览器
- ⚠️ 收益有限：DOL-X 构建已经很快（< 5 秒）
- ⚠️ 复杂度高：需要 WebSocket + 文件监控

**决策**: **Phase 4 实现**（在核心功能稳定后）

---

### 3.2 简化实现方案

**仅实现核心价值部分**:
1. 文件监控（watchdog）
2. 自动重新打包
3. ~~WebSocket 自动刷新~~（用户手动按 F5）

**理由**: WebSocket 实现复杂，收益较小。用户手动刷新浏览器的成本可接受。

---

## 第四部分：实施路线图

### Phase 1: 深度研究（1-2 周）✅ 已完成

- ✅ 研究 DoL-Commit2Mod 实现
- ✅ 研究 MCH REMOTE_TEST 实现
- ✅ 决策实现策略（本文档）

---

### Phase 2: DoL-Commit2Mod 集成（2 周）

**Week 1: 核心实现**
- 创建 `tools/dev/commit_to_mod.py`
- 实现 `GitDiffParser`（Git diff 解析）
- 实现 `BootJsonBuilder`（boot.json 生成）
- 基础测试（单个 commit 转换）

**Week 2: 扩展功能**
- 实现 `DependencyInferrer`（依赖推断）
- 集成到 `main.py dev` 子命令
- 编写单元测试
- 编写使用文档

**验收标准**:
```bash
# 测试上游最新提交
python main.py dev commit-to-mod HEAD --repo https://github.com/DoL-Lyra/Lyra.git

# 自动构建
python main.py dev commit-to-mod abc1234 --auto-build --codes 57600

# 产物验证
ls workspace/experimental_mods/DoL-Upstream-abc1234-1.0.0.zip
```

---

### Phase 3: 游戏逻辑测试（2-3 周）

**Week 1: 测试框架**
- 创建 `tools/dev/game_logic_test.py`
- 实现 `GameLogicTestRunner` 类
- 实现 HTTP 服务器封装
- 编写 1-2 个简单测试验证可行性

**Week 2: 测试套件**
- 实现 `test_basic_flow.py`（基础流程）
- 实现 `test_cheat_extended.py`（作弊菜单）
- 实现 `test_au_face.py`（AU Face 渲染）
- 添加 pytest fixtures（`conftest.py`）

**Week 3: CI 集成 + 扩展**
- 实现 `test_more_love.py`
- 实现 `test_custom_spellbook.py`
- 实现 `test_save_compat.py`
- CI 集成 + 自动回退机制
- 编写测试维护文档

**验收标准**:
```bash
# 本地运行测试
pytest tests/game_logic/ -v

# CI 通过
# GitHub Actions 绿色✓

# 自动回退验证
# 提交破坏性改动 → CI 失败 → 自动 revert → 创建 issue
```

---

### Phase 4: 热加载开发（可选，1 周）

**仅在 Phase 2、3 稳定后考虑**

- 实现文件监控（watchdog）
- 自动重新打包
- 启动本地 HTTP 服务器
- 编写使用文档

---

## 第五部分：风险与缓解

### 5.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **Playwright 环境问题** | CI 失败 | 中 | Docker 缓存<br>提供一键安装脚本 |
| **游戏更新破坏测试** | 测试全失败 | 中 | 版本号标记<br>同步更新检查清单 |
| **ModLoader 格式变化** | mod.zip 加载失败 | 低 | 监控 ModLoader 更新<br>测试套件覆盖 |
| **依赖推断不准确** | 生成的 mod 缺少依赖 | 低 | 手动指定依赖参数<br>逐步完善推断规则 |

---

### 5.2 项目风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **开发时间超预期** | 延迟交付 | 中 | 保持灵活性<br>优先核心功能 |
| **测试覆盖率不足** | 遗漏回归问题 | 低 | 逐步扩展测试场景<br>社区反馈 |
| **维护成本高** | 长期负担 | 低 | 模块化设计<br>完善文档 |

---

## 第六部分：成功标准

### 6.1 Phase 2 成功标准（DoL-Commit2Mod）

- ✅ 能够将任意 commit 转换为 mod.zip
- ✅ 生成的 mod 能被 ModLoader 正常加载
- ✅ 自动推断依赖（maplebirch、Simple Framework）
- ✅ 支持 `--auto-build` 参数触发构建
- ✅ 单元测试覆盖率 > 80%

---

### 6.2 Phase 3 成功标准（游戏逻辑测试）

- ✅ 6 大测试套件全部实现
- ✅ 测试覆盖 4 个 build_codes
- ✅ CI 集成 + 自动回退机制
- ✅ 测试失败率 < 5%（假阳性）
- ✅ 平均测试时间 < 10 分钟

---

### 6.3 整体成功标准

**量化指标**:
- 手动测试时间减少 80%（从 15 分钟 → 3 分钟）
- 测试覆盖率从 0% → 80%+
- 回归问题发现时间从 1-2 天 → < 1 小时
- 上游同步频率从月度 → 每周

**定性指标**:
- 开发者信心提升（敢于重构代码）
- 用户信任度提升（产物质量稳定）
- 维护成本降低（自动化代替人工）

---

## 第七部分：下一步行动

### 7.1 立即开始（本周）

1. ✅ 完成 Phase 1 研究（已完成）
2. ⏳ 创建 Phase 2 工作分支
   ```bash
   git checkout -b feature/commit-to-mod
   ```
3. ⏳ 开始实现 `tools/dev/commit_to_mod.py`

---

### 7.2 验收里程碑

| 里程碑 | 交付物 | 预计完成 |
|--------|--------|---------|
| **M1: Phase 1 完成** | 研究文档 × 3 | ✅ 2026-06-14 |
| **M2: Phase 2 Week 1** | 核心转换逻辑 | 2026-06-21 |
| **M3: Phase 2 Week 2** | 集成到 main.py | 2026-06-28 |
| **M4: Phase 3 Week 1** | 测试框架核心 | 2026-07-05 |
| **M5: Phase 3 Week 2** | 3 个测试套件 | 2026-07-12 |
| **M6: Phase 3 Week 3** | CI 集成完成 | 2026-07-19 |

---

## 附录 A: 技术栈总结

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| **Commit 转换** | Python + subprocess | 与 DOL-X 一致<br>Git 命令调用简单 |
| **游戏逻辑测试** | Playwright (Python) | DOL-X 已使用<br>CI 友好<br>调试工具强大 |
| **测试框架** | pytest | Python 生态标准<br>fixtures 强大 |
| **文件监控** | watchdog | Python 生态成熟<br>跨平台 |
| **HTTP 服务器** | http.server (stdlib) | 无额外依赖<br>足够简单 |

---

## 附录 B: 参考文档

- DoL-Commit2Mod 研究: `docs/COMMIT2MOD_RESEARCH.md`
- MCH REMOTE_TEST 研究: `docs/MCH_REMOTE_TEST_RESEARCH.md`
- 完整集成计划: `DOL-X_INTEGRATION_PLAN_FINAL.md`

---

**决策完成时间**: 2026-06-14  
**下一步**: 开始 Phase 2 实施
