# DOL-X 测试能力全面评估报告

**评估日期**: 2026-06-24  
**评估目标**: 分析当前自动化测试覆盖范围，评估"全面自动化游戏测试"的技术可行性

---

## 执行摘要

DOL-X 项目已建立**三层测试体系**：

1. **静态配置测试** (235+ 测试用例) - ✅ 成熟
2. **HTML/ZIP 结构测试** - ✅ 成熟
3. **浏览器运行时测试** (Browser/APK Smoke) - ✅ 生产就绪

**核心发现**:
- ✅ 当前测试覆盖：构建正确性、基础启动、Mod 加载验证
- ❌ 测试缺口：游戏逻辑、完整流程、UI 深度交互
- ⚠️ 社区方案：无完整的全自动游戏测试方案

**可行性评估**:
- **技术上可行** (SugarCube 引擎提供完整 API)
- **工程上需大量投入** (估计 6-9 个月全职开发)
- **维护成本高** (游戏内容更新需同步测试脚本)

---

## 第一部分：当前测试能力清单

### 1.1 Layer 1: 静态配置测试

**位置**: `tests/` 目录  
**测试用例数**: 235+ 个  
**运行环境**: pytest (本地 + CI)

**覆盖范围**:

| 测试文件 | 功能 | 状态 |
|----------|------|------|
| `test_build_matrix.py` | 构建矩阵完整性验证 | ✅ |
| `test_mod_config.py` | Mod URL 可用性检查 | ✅ |
| `test_archive_extraction.py` | 安全性测试 (路径遍历) | ✅ |
| `test_au_face_compat.py` | AU Face 兼容性验证 | ✅ |
| `test_combinations.py` | build_codes 冲突检测 | ✅ |

**能力边界**:
- ✅ 验证配置文件语法正确性
- ✅ 检测 Mod 下载链接有效性
- ✅ 验证构建矩阵无冲突
- ❌ 无法验证游戏运行时行为
- ❌ 无法验证 Mod 功能是否正常工作

---

### 1.2 Layer 2: HTML/ZIP 结构测试

**工具**: `tools/html_smoke_test.py`  
**测试内容**: 静态 HTML 文件分析 (不启动浏览器)

**检查项**:
1. HTML 文件存在性
2. `modDataValueZipList` 存在且为有效 JSON
3. 内嵌 Mod ZIP 包可解压
4. `boot.json` 存在性检查

**示例输出**:
```
[OK] output/dol.zip!Degrees of Lewdity.html: mods=7, valid_zip=7, non_zip=0
```

**能力边界**:
- ✅ 快速验证构建产物结构完整性
- ✅ 发现 Mod 打包错误
- ❌ 无法验证 Mod 是否能在游戏中加载
- ❌ 无法检测运行时错误

---

### 1.3 Layer 3: 浏览器运行时测试

#### 3.1 Browser Smoke Test (`browser_smoke_test.py`)

**技术栈**: Playwright + Chromium  
**测试范围**: ZIP 构建产物

**核心功能**:
1. **启动验证**: 游戏能否正常加载到 "Start" 页面
2. **Mod 加载检查**: 验证 ModLoader 成功加载所有 Mod
3. **控制台监控**: 捕获 JavaScript 错误/警告
4. **游戏状态检测**: 验证是否进入可玩状态

**检查的 Mod 运行时证据**:

```python
# browser_smoke_test.py 中的核心检查
PROFILES = {
    "ucb-cheat-extended-maplebirch": SmokeProfile(
        required_mod_names=("ModLoaderGui", "maplebirch", "cheatExtended"),
        diagnostic_globals=("maplebirchFrameworks", "CE_options"),
    )
}
```

**能力边界**:
- ✅ 验证游戏启动到 "Orphanage Intro"
- ✅ 验证 Mod 列表中出现预期 Mod
- ✅ 检测 JavaScript 控制台错误
- ✅ 验证特定全局变量存在 (如 `window.maplebirchFrameworks`)
- ❌ 不验证 Mod 功能是否真正工作 (仅检查加载)
- ❌ 不测试游戏流程和交互

**测试用例示例**:
```python
# 实际检查内容 (从代码推断)
assert page.locator('text="Start"').is_visible()  # 启动按钮
assert page.evaluate("typeof SugarCube !== 'undefined'")  # 引擎加载
assert no_critical_errors_in_console()  # 无严重错误
```

#### 3.2 APK Emulator Smoke Test (`apk_emulator_smoke_test.py`)

**技术栈**: Android Emulator + Chrome DevTools Protocol (CDP)  
**测试范围**: APK 构建产物

**核心功能**:
1. 安装 APK 到 Android 模拟器
2. 通过 CDP 连接到 WebView
3. 执行与 Browser Smoke 相同的检查
4. 验证 Cordova 插件加载

**能力边界**:
- ✅ 验证 APK 能在 Android 环境启动
- ✅ 验证 WebView 中的游戏逻辑
- ✅ 检测 Android 特有问题
- ❌ 不测试移动端特有交互 (触摸、手势)
- ❌ 不测试 Cordova 插件功能

---

### 1.4 CI 集成测试流程

**工作流**: `.github/workflows/baseline-candidate-gate.yml`

**测试流程**:
```
Phase 1A: 静态验证
  ├── 配置验证 (validate-config)
  ├── 稳定性检查 (stable-replacement-readiness)
  └── 构建 ZIP/APK

Phase 2: 结构验证
  ├── ZIP 审计 (audit-zip)
  ├── APK 审计 (audit-apk)
  └── APK 等价性检查 (audit-apk-equivalence)

Phase 3: 运行时验证
  ├── Browser Smoke (所有 build variants)
  ├── APK CDP Smoke (Android 模拟器)
  └── 报告汇总
```

**测试覆盖的 Build Variants**:
- Base (无 AU)
- AU-F (女性 AU)
- AU-M (男性 AU)
- AU-A (雌雄同体 AU)

**测试矩阵**:
- 4 个 build_codes × 2 个平台 (ZIP/APK) = 8 个测试目标

---

## 第二部分：测试缺口分析

### 2.1 未覆盖的测试场景

#### ❌ 游戏逻辑测试

**缺失内容**:
- 游戏流程完整性 (从开场到任意场景的路径)
- 选项分支逻辑 (所有选择是否导致正确结果)
- 游戏变量状态验证 (金钱、创伤、NPC 好感度等)
- 时间系统验证 (时间流逝、事件触发)

**示例场景** (未测试):
```
用户操作: 点击 "Go to School" → 选择 "Attend Class" → 完成一天
预期结果: 
  - $time 增加 480 (8小时)
  - $school 变量更新
  - 无 JavaScript 错误
实际情况: ❌ 当前测试不覆盖
```

#### ❌ Mod 功能深度验证

**Cheat Extended 测试缺口**:

| 功能 | 手动测试清单 | 自动化状态 |
|------|-------------|-----------|
| 侧边栏快捷功能 (一键恢复/传送) | ✅ | ❌ |
| 言灵系统 (创建/执行/编辑) | ✅ | ❌ |
| 属性控制面板 | ✅ | ❌ |
| 战斗设置 (伤害倍率) | ✅ | ❌ |
| 时间控制 | ✅ | ❌ |

**当前状态**: 仅验证 `CE_options` 全局变量存在，不验证功能可用

#### ❌ UI 交互完整性

**缺失内容**:
- 所有按钮可点击性验证
- 所有输入框功能验证
- 所有 Passage 可达性验证
- 侧边栏在所有页面都正常显示

#### ❌ 跨浏览器兼容性

**当前测试**: 仅 Chromium  
**缺失**: Firefox, Safari, 移动端浏览器

---

### 2.2 与手动测试清单的对比

**文档**: `docs/MANUAL_TESTING_CHECKLIST.md`

**手动测试覆盖但自动化未覆盖的内容**:

1. **言灵系统完整测试** (详细步骤已文档化)
   - 创建言灵 → 验证执行 → 编辑 → 删除
   - 当前自动化: ❌ 无

2. **Cheat Extended 分散式 UI 验证**
   - 侧边栏、Options 菜单、场景内 Widget
   - 当前自动化: ❌ 无

3. **AU Variants 特定测试**
   - AU 角色显示、AU Passage 可访问性
   - 当前自动化: ⚠️ 仅检查启动，不验证功能

4. **性能测试**
   - 加载时间、内存使用、长时间稳定性
   - 当前自动化: ❌ 无

**结论**: 手动测试清单提供了完整的功能验证方案，但几乎完全依赖人工执行

---

## 第三部分：社区测试方案调研

### 3.1 社区工具分析

**文档来源**: `docs/COMMUNITY_TOOLS_COMPARISON.md`

#### 工具 1: DOL-Mod-Created-Helper

**仓库**: NumberSir/DOL-Mod-Created-Helper  
**测试相关功能**: `REMOTE_TEST` 模式

**功能描述**:
- 启动本地测试服务器
- 自动复制 Mod 到 ModLoader
- 支持热重载 (修改代码 → 刷新浏览器)

**测试能力评估**:
- ✅ 加速开发迭代
- ✅ 简化 Mod 加载流程
- ❌ **不提供自动化测试** (需手动在浏览器中测试)
- ❌ 无测试脚本或断言机制

**结论**: 是开发辅助工具，不是自动化测试框架

#### 工具 2: SugarValidator

**功能**: Passage 标签完整性验证、断链检测

**测试能力**:
- ✅ 静态分析 Twee 代码
- ✅ 检测语法错误
- ❌ 不验证运行时逻辑

**DOL-X 集成建议**: 可作为 Layer 1 静态测试的补充

#### 工具 3: Selenium/Playwright 社区实践

**来源**: GitHub Gist (aucchen/808ebf87a8ebd7d6ecb2d4753eff9ba5)

**内容**: 随机点击测试脚本

```python
# 社区玩家的随机测试方法
while True:
    links = page.query_selector_all('a')
    random.choice(links).click()
    time.sleep(1)
```

**评估**:
- ✅ 能发现崩溃和明显错误
- ❌ 无目标、无断言、无覆盖率统计
- ❌ 不适合作为正式测试方案

---

### 3.2 社区测试方案总结

**核心发现**: ❌ **社区没有完整的全自动游戏测试方案**

**原因分析**:
1. **DoL 是单机游戏**, 传统上依赖人工测试
2. **Mod 开发者规模小**, 没有企业级测试需求
3. **SugarCube 引擎复杂**, 自动化测试成本高
4. **游戏内容频繁更新**, 测试脚本维护成本高

**可借鉴内容**:
- ✅ `REMOTE_TEST` 热重载思路 (加速手动测试)
- ✅ SugarValidator 静态分析 (补充 Layer 1)
- ❌ 无完整端到端测试框架可复用

---

## 第四部分：技术可行性评估

### 4.1 SugarCube 引擎可测试性分析

**核心 API** (已验证可用):

```javascript
// 1. 状态访问
window.SugarCube.State.active.variables  // 所有游戏变量 ($money, $trauma, etc.)
window.SugarCube.State.passage           // 当前 passage 名称
window.SugarCube.State.history           // 历史记录栈

// 2. 导航控制
window.SugarCube.Engine.play("PassageName")  // 跳转到指定 passage
window.SugarCube.Engine.backward()           // 后退
window.SugarCube.Engine.forward()            // 前进

// 3. 宏执行
window.SugarCube.Macro.get('set').handler(...)  // 执行 <<set>> 宏
window.SugarCube.Macro.get('run').handler(...)  // 执行 <<run>> 宏

// 4. 变量操作 (通过 Playwright)
page.evaluate("State.variables.money = 10000")  // 设置金钱
page.evaluate("State.variables.time")           // 读取时间
```

**可测试性评级**: ⭐⭐⭐⭐⭐ (5/5)

**理由**:
- ✅ 完整的状态访问权限
- ✅ 可编程的导航控制
- ✅ 可直接操作游戏变量
- ✅ 可通过 Playwright 的 `page.evaluate()` 调用

**技术结论**: SugarCube 引擎为自动化测试提供了**充分的技术支持**

---

### 4.2 完整游戏测试方案设计

基于 SugarCube API，可实现**五层测试架构**：

#### Layer 1: 静态分析 (✅ 已实现)
- 配置文件验证
- Mod URL 检查
- 构建矩阵验证

#### Layer 2: HTML 结构验证 (✅ 已实现)
- HTML 文件完整性
- Mod ZIP 包解析

#### Layer 3: 启动与加载验证 (✅ 已实现)
- 游戏启动到首页
- Mod 加载验证
- 控制台错误监控

#### Layer 4: 游戏逻辑单元测试 (❌ 未实现)

**示例实现**:

```python
# tests/test_game_logic.py
def test_orphanage_intro_flow(browser_page):
    """测试孤儿院开场流程"""
    # 启动游戏
    page = browser_page
    page.goto("file://path/to/game.html")
    
    # 点击 Start
    page.locator('text="Start"').click()
    
    # 验证进入 "Orphanage Intro"
    passage = page.evaluate("State.passage")
    assert passage == "Orphanage Intro"
    
    # 验证初始状态
    money = page.evaluate("State.variables.money")
    assert money == 0
    
    # 点击第一个选项
    page.locator('.macro-link').first.click()
    
    # 验证状态变化
    new_passage = page.evaluate("State.passage")
    assert new_passage != "Orphanage Intro"
```

#### Layer 5: 端到端流程测试 (❌ 未实现)

**示例场景**:

```python
def test_full_day_cycle():
    """测试完整一天的游戏流程"""
    # 1. 起床
    # 2. 去学校
    # 3. 上课
    # 4. 回家
    # 5. 睡觉
    # 验证: 时间流逝、事件触发、状态变化
```

---

### 4.3 工作量估算

#### 阶段 1: 基础框架搭建 (2-3 个月)

**任务**:
- 扩展 `browser_smoke_test.py` 支持游戏逻辑断言
- 创建 `tests/test_game_logic.py` 框架
- 实现 Passage 导航自动化
- 实现游戏变量断言工具

**交付物**:
- 10-20 个基础游戏逻辑测试
- 测试报告框架

#### 阶段 2: Mod 功能验证 (2-3 个月)

**任务**:
- Cheat Extended 完整测试 (言灵、侧边栏、Options)
- More Love 内容测试
- Custom Spellbook 测试
- Maplebirch 框架 API 测试

**交付物**:
- 50-100 个 Mod 功能测试
- Mod 测试模板

#### 阶段 3: 完整流程覆盖 (2-3 个月)

**任务**:
- 主线流程测试 (学校、孤儿院、街道)
- 支线任务测试
- NPC 交互测试
- 随机事件测试

**交付物**:
- 200-500 个端到端测试
- 覆盖率报告

**总工作量**: 6-9 个月 (1 名全职开发者)

---

### 4.4 维护成本分析

#### 高维护场景

**游戏内容更新** (上游 Lyra 每周更新):
- 新增 Passage → 需更新测试
- 修改对话选项 → 需更新测试脚本
- 调整游戏变量名 → 需批量更新断言

**Mod 版本更新**:
- Cheat Extended UI 改版 → 需重写测试
- Maplebirch API 变更 → 需更新测试

**估计维护工作量**: 每周 4-8 小时 (持续性任务)

#### 降低维护成本的策略

1. **使用 Page Object Pattern**
   ```python
   class GamePage:
       def start_game(self):
           self.page.locator('text="Start"').click()
       
       def get_passage(self):
           return self.page.evaluate("State.passage")
   ```

2. **参数化测试**
   ```python
   @pytest.mark.parametrize("passage", ALL_PASSAGES)
   def test_passage_accessible(passage):
       navigate_to(passage)
       assert no_console_errors()
   ```

3. **测试优先级分级**
   - P0: 启动、基础导航 (必须通过)
   - P1: 核心功能 (Mod 加载、主线流程)
   - P2: 边缘功能 (支线、随机事件)

---

## 第五部分：可行性结论与建议

### 5.1 技术可行性: ✅ 可行

**支持因素**:
- SugarCube 提供完整 API
- Playwright 成熟稳定
- DOL-X 已有良好的测试基础

**阻碍因素**:
- ❌ 工作量巨大 (6-9 个月)
- ❌ 维护成本高 (每周 4-8 小时)
- ❌ 游戏内容变更频繁

---

### 5.2 投入产出比分析

**投入**:
- 开发: 6-9 个月全职工作
- 维护: 每周 4-8 小时 (持续性)
- 学习成本: SugarCube API、游戏机制深度理解

**产出**:
- ✅ 自动发现回归问题
- ✅ 减少手动测试工作量
- ✅ 提高 CI 信心
- ⚠️ **但**: DOL-X 是自用项目，发布频率低

**结论**: **投入产出比不高** (对于自用项目而言)

---

### 5.3 推荐方案: 渐进式增强

鉴于完整自动化测试的高成本，推荐采用**渐进式增强策略**：

#### 阶段 0: 维持现状 (✅ 已完成)
- 静态配置测试
- HTML 结构测试
- Browser/APK Smoke Test

**覆盖范围**: 构建正确性、启动验证、Mod 加载  
**维护成本**: 低  
**适用场景**: 当前 DOL-X 的实际需求

#### 阶段 1: 轻量级增强 (可选，1-2 周)

**目标**: 增加关键 Mod 功能的浅层验证

**实现**:
```python
# 扩展 browser_smoke_test.py
def test_cheat_extended_sidebar_visible(page):
    """验证 Cheat Extended 侧边栏可见"""
    assert page.locator('#ui-bar').is_visible()
    assert page.evaluate("typeof CE_options !== 'undefined'")

def test_yanling_system_accessible(page):
    """验证言灵系统可访问"""
    page.locator('text="Options"').click()
    page.wait_for_selector('text="作弊扩展"')
    # 不深入测试功能，仅验证入口存在
```

**工作量**: 1-2 周  
**维护成本**: 低  
**价值**: 捕获 UI 重大破坏性变更

#### 阶段 2: 关键路径测试 (按需，1-2 个月)

**目标**: 测试核心游戏流程

**实现**:
```python
def test_orphanage_to_school_flow(page):
    """测试孤儿院到学校的基本流程"""
    start_game(page)
    click_link(page, "Go to School")
    assert_passage(page, "School")
    assert_no_console_errors(page)
```

**工作量**: 1-2 个月  
**维护成本**: 中等  
**触发条件**: 如果 DOL-X 开始公开发布或团队扩大

#### 阶段 3: 完整自动化 (不推荐)

**仅在以下情况考虑**:
- DOL-X 成为公开项目
- 有专职测试人员
- 发布频率显著提高 (每周 > 1 次)

---

### 5.4 最终建议

#### 对于当前 DOL-X 项目

**推荐策略**: **维持现状 + 选择性手动测试**

**理由**:
1. ✅ 当前测试已覆盖最高风险区域 (构建失败、启动崩溃)
2. ✅ 手动测试清单已文档化且可执行
3. ✅ 自用项目，可接受一定程度的手动验证
4. ❌ 完整自动化的 ROI 不足

**行动项**:
- ✅ 继续维护现有 3 层测试
- ✅ 遵循 `MANUAL_TESTING_CHECKLIST.md` 进行关键发布前测试
- ⚠️ 可选: 实施"阶段 1: 轻量级增强" (1-2 周工作量)

#### 如果未来需要完整自动化

**触发条件**:
- DOL-X 转为团队协作项目
- 发布频率 > 每周 2 次
- 用户量显著增长
- 有专职测试资源

**实施路径**:
1. 参考本文档第 4.2 节的五层架构
2. 从"阶段 1: 基础框架"开始
3. 优先实现 P0/P1 级别测试
4. 逐步扩展覆盖范围

---

## 附录 A: 快速参考

### A.1 当前测试能力速查表

| 测试层级 | 工具 | 覆盖内容 | 状态 |
|---------|------|---------|------|
| Layer 1 | pytest | 配置文件、构建矩阵 | ✅ 成熟 |
| Layer 2 | html_smoke_test.py | HTML 结构、Mod ZIP | ✅ 成熟 |
| Layer 3 | browser_smoke_test.py | 启动、Mod 加载 | ✅ 生产就绪 |
| Layer 4 | (未实现) | 游戏逻辑、Mod 功能 | ❌ 无 |
| Layer 5 | (未实现) | 完整游戏流程 | ❌ 无 |

### A.2 测试缺口优先级

| 缺口 | 风险等级 | 当前缓解措施 | 推荐方案 |
|------|---------|-------------|---------|
| 游戏逻辑错误 | 中 | 手动测试 | 维持现状 |
| Mod 功能失效 | 中 | 手动测试 | 可选增强 |
| UI 交互破坏 | 低 | Smoke Test | 维持现状 |
| 性能问题 | 低 | 无 | 按需手动测试 |

### A.3 社区工具推荐

| 工具 | 用途 | 是否集成 |
|------|------|---------|
| DOL-Mod-Created-Helper | 开发热重载 | 可参考 |
| SugarValidator | 静态分析 | 可集成 |
| 社区 Playwright 脚本 | 随机测试 | 不推荐 |

---

## 附录 B: 技术资源

### B.1 SugarCube API 文档

**官方文档**: https://www.motoslave.net/sugarcube/2/docs/

**关键 API**:
- `SugarCube.State` - 游戏状态管理
- `SugarCube.Engine` - 导航控制
- `SugarCube.Macro` - 宏执行

### B.2 Playwright 游戏测试示例

**官方示例**: https://playwright.dev/docs/evaluating

**DOL-X 相关用法**:
```python
# 获取游戏变量
money = page.evaluate("State.variables.money")

# 执行游戏命令
page.evaluate("Engine.play('School')")

# 监听控制台
page.on("console", lambda msg: print(msg.text))
```

### B.3 相关文档

- `docs/MANUAL_TESTING_CHECKLIST.md` - 手动测试清单
- `docs/COMMUNITY_TOOLS_COMPARISON.md` - 社区工具对比
- `docs/COMPREHENSIVE_TESTING_STRATEGY.md` - 完整测试战略 (已归档)
- `.github/workflows/baseline-candidate-gate.yml` - CI 测试流程

---

**报告完成日期**: 2026-06-24  
**作者**: DOL-X 项目组  
**版本**: v1.0

**结论**: DOL-X 当前测试体系**已足够满足自用项目需求**。完整自动化测试**技术上可行但投入产出比不高**。推荐**维持现状 + 选择性手动测试**的策略。
