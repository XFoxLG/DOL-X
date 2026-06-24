# DOL-X 实施计划 (2026-06-24)

## 项目背景

**当前状态**（2026-06-24 20:00）:
- **上次构建**: Build #27995040396（2026-06-23）
- **Build codes**: 4个（499968/500992/502016/504064）
- **新增 mod**: 4个（GuideToMe, BunnyTransformation, NeoUI-Patch, NPC Avatars）
  - ✅ GuideToMe: 集成成功
  - ❌ BunnyTransformation: 战斗崩溃（16个 TweeReplacer 错误）
  - ⚠️ NeoUI-Patch: 用户决定启用（观察阶段）
  - ✅ NPC Avatars: 集成成功

**用户诉求**:
1. 继续集成社区模组相关工具
2. 完善测试系统（自动化覆盖全部游戏和 mod 细节）
3. 启用 NeoUI Patch（观察是否冲突）

---

## 阶段 1: 配置调整与验证 ⏱️ 20 分钟

### 1.1 启用 NeoUI Patch

**背景**: 用户偏好覆盖式侧边栏布局（点击空白关闭）

**配置变更**:
```toml
# config/features.toml
[[features]]
id = "neoui_patch"
name = "NeoUI Patch"
bit = 2097152
required = false
skip = false  # ← 改为 false
depends_on = []
conflicts_with = []
```

**风险评估**:
- ⚠️ **潜在冲突**: 与侧边栏美化 mod（Mae's Picvary）CSS 可能冲突
- ⚠️ **观察项**: 宽屏用户体验、侧边栏贴图展示
- ✅ **可逆**: 通过 `skip = true` 快速回退

**验证步骤**:
1. 更新 `config/combinations.toml`（新增 `neoui_patch` bit 2097152）
2. 运行 `python -m pytest tests/ -v`（确保测试通过）
3. 提交配置变更
4. 推送触发 CI 构建
5. 下载 APK 手动测试侧边栏展示

---

## 阶段 2: 社区模组工具集成 ⏱️ 2 小时

### 2.1 调研社区工具生态

**目标**: 从 DoL 中文 Wiki 提取可用工具，评估对 DOL-X 的价值

**数据源**:
```
https://degreesoflewditycn.miraheze.org/wiki/模组列表#模组相关工具
```

**调研维度**:
| 工具类型 | 评估指标 | 优先级 |
|---------|---------|--------|
| Mod 开发工具 | Python 构建集成可行性 | 高 |
| 测试工具 | 自动化测试覆盖能力 | 高 |
| 解包/打包工具 | 替代当前 `unrar` 依赖 | 中 |
| Mod 管理器 | 用户端工具（非构建系统） | 低 |

**输出产物**:
- `docs/COMMUNITY_TOOLS_RESEARCH_2026-06-24.md`（工具清单 + 可行性分析）
- `tools/integrate_community_tool.py`（集成脚本模板，如适用）

### 2.2 优先集成候选工具

**备选列表**（待调研确认）:
1. **Mod 自动化测试框架**（如存在）
   - 目标: 替代手动测试 checklist
   - 集成方式: 封装为 `pytest` fixture 或独立测试脚本

2. **Imagepack 冲突检测工具**
   - 目标: 增强现有 `tools/analyze_imagepack.py`
   - 集成方式: 作为子模块或依赖库

3. **Mod 依赖解析器**
   - 目标: 自动检测 mod 前置依赖（如 BunnyTransformation 缺失 fox transformation）
   - 集成方式: 静态分析 mod zip 中的 `boot.json` 和 Twee 文件

---

## 阶段 3: 测试系统完善 ⏱️ 4 小时

### 3.1 当前测试覆盖情况

**现有测试**（235 个通过）:
```
tests/
├── test_build_matrix.py          # 构建矩阵验证
├── test_mod_config.py            # Mod 配置完整性
├── test_combinations.py          # Feature 组合逻辑
└── test_version_consistency.py   # 版本一致性检查
```

**覆盖范围**:
- ✅ 配置文件语法正确性
- ✅ Mod URL 可达性
- ✅ Build codes 数学正确性
- ❌ **游戏运行时行为**（ModLoader 加载、战斗系统、UI 渲染）
- ❌ **Mod 功能验证**（快速言灵、自定义染发、NPC 头像）

### 3.2 游戏运行时测试架构设计

**技术选型**:
```
方案 A: Playwright + HTML 游戏本体
  优点: 完整 DOM 访问，可模拟点击、输入
  缺点: 需要本地解压 HTML 版本，setup 复杂

方案 B: SugarCube 2 Headless Runner
  优点: 直接执行游戏逻辑（Twee passages + JS）
  缺点: 可能缺少官方 headless 支持

方案 C: APK 自动化测试（Appium + MuMu）
  优点: 测试真实 APK 构建产物
  缺点: 环境复杂，GitHub Actions 不支持 Android Emulator

推荐: 方案 A（Playwright + HTML）
```

**测试用例设计**（示例）:

```python
# tests/runtime/test_modloader.py
@pytest.mark.runtime
def test_modloader_loads_all_mods(game_session):
    """验证所有 mod 成功加载，无 ModLoader 错误"""
    game_session.start()
    mod_manager = game_session.get_element("#modloader-status")
    assert "error: 0" in mod_manager.text
    assert "loaded: 40" in mod_manager.text  # 期望 mod 数量

@pytest.mark.runtime
def test_combat_renders_without_crash(game_session):
    """验证进入战斗界面不崩溃（BunnyTransformation bug 回归测试）"""
    game_session.start()
    game_session.enable_debug_mode()
    game_session.click_link("加入")
    assert game_session.no_javascript_errors()
    assert game_session.element_exists("#combat-ui")

@pytest.mark.runtime
def test_cheat_extended_quick_yanling(game_session):
    """验证快速言灵功能可用"""
    game_session.start()
    game_session.open_options()
    game_session.navigate_to("Cheat Extended")
    quick_yanling = game_session.get_element("#quick-yanling-panel")
    assert quick_yanling.is_visible()
    # 测试"无限氧气"功能
    game_session.click_button("无限氧气")
    game_session.save_and_reload()
    assert game_session.get_variable("$oxygen") == 9999
```

### 3.3 测试基础设施搭建

**依赖安装**:
```bash
pip install playwright pytest-playwright
playwright install chromium
```

**测试数据准备**:
```
tests/
├── runtime/
│   ├── fixtures/
│   │   ├── game_session.py         # Playwright session wrapper
│   │   ├── mod_versions.json       # 期望的 mod 版本
│   │   └── save_states/            # 预制存档（不同游戏阶段）
│   ├── test_modloader.py
│   ├── test_combat_system.py
│   ├── test_cheat_extended.py
│   └── test_custom_hair.py
└── conftest.py                      # pytest 配置
```

**CI 集成**（GitHub Actions 新增 job）:
```yaml
# .github/workflows/build.yml
runtime-tests:
  runs-on: ubuntu-latest
  needs: build
  steps:
    - name: Download HTML build artifact
      uses: actions/download-artifact@v3
      with:
        name: dol-html-499968  # 基础构建
        path: ./game
    
    - name: Install Playwright
      run: |
        pip install playwright pytest-playwright
        playwright install chromium
    
    - name: Run runtime tests
      run: pytest tests/runtime/ -v --browser=chromium
```

### 3.4 手动测试清单自动化

**当前手动测试**（`docs/MANUAL_TESTING_CHECKLIST.md`）:
- 27 个手动步骤
- 每次构建需 30-60 分钟人工测试

**自动化路径**:
```
手动步骤 → Playwright 脚本 → pytest 用例

示例:
[手动] 打开选项 → 模组设置 → 作弊拓展 → 启用强制作弊
        ↓
[自动] game_session.open_options()
       .navigate_to_tab("模组设置")
       .scroll_to("作弊拓展")
       .toggle_checkbox("强制作弊", True)
       .save_options()
```

**目标**:
- 80% 手动步骤自动化（UI 交互部分）
- 20% 保留人工验证（视觉效果、性能感受）

---

## 阶段 4: NeoUI 集成验证 ⏱️ 1 小时

### 4.1 冲突检测测试

**潜在冲突点**:
1. **CSS 优先级**: NeoUI 的 `margin-left: 3.5em` vs Mae's Picvary 侧边栏宽度
2. **贴图遮挡**: 侧边栏展开时 NPC 头像是否完整显示
3. **响应式布局**: 不同屏幕分辨率下的表现

**测试用例**:
```python
# tests/runtime/test_neoui_compatibility.py
@pytest.mark.runtime
def test_neoui_sidebar_does_not_overlap_content(game_session):
    """验证 NeoUI 侧边栏不遮挡游戏内容"""
    game_session.start()
    game_session.toggle_sidebar(expanded=True)
    
    # 检查主内容区域是否被推开
    story_margin = game_session.get_css_property("#story", "margin-left")
    assert story_margin == "3.5em"  # NeoUI 固定值
    
    # 检查侧边栏是否覆盖
    sidebar_width = game_session.get_element_width("#ui-bar")
    story_offset = game_session.get_element_position("#story")["x"]
    # 如果 story_offset < sidebar_width，则存在覆盖
    assert story_offset < sidebar_width, "NeoUI uses overlay layout by design"

@pytest.mark.runtime
def test_maes_picvary_npc_icons_visible_with_neoui(game_session):
    """验证 NeoUI + Mae's Picvary NPC 头像正常显示"""
    game_session.start()
    game_session.trigger_npc_encounter("Robin")  # 触发 NPC 事件
    
    # 检查侧边栏中的 NPC 头像
    npc_icon = game_session.get_element("#npc-social-robin img")
    assert npc_icon.is_visible()
    assert npc_icon.get_attribute("src").endswith("robin.png")
```

### 4.2 用户验收测试计划

**测试场景**（手动验证）:
1. 不同屏幕分辨率（1920×1080 / 1366×768 / 手机模拟器）
2. 侧边栏展开/收起动画流畅性
3. 点击空白区域关闭侧边栏功能
4. 与其他 UI mod 的视觉一致性

**回退条件**:
- ❌ 侧边栏展开时遮挡关键 UI 元素（存档按钮、状态栏）
- ❌ 与 Mae's Picvary 贴图错位严重
- ❌ 宽屏用户反馈体验下降

---

## 阶段 5: 文档与提交 ⏱️ 30 分钟

### 5.1 更新项目文档

**需要更新的文件**:
1. `AGENTS.md`（更新 mod 状态、build_codes、测试策略）
2. `docs/MOD_MATRIX_RATIONALE.md`（记录 NeoUI 启用决策）
3. `docs/TESTING_STRATEGY.md`（新增：运行时测试架构）
4. `README.md`（更新 build codes、mod 列表）

### 5.2 Git 提交策略

**提交拆分**（每个提交原子化）:
```bash
# 1. 配置变更
git add config/features.toml config/combinations.toml
git commit -m "feat(config): enable neoui_patch for overlay sidebar layout

- Set skip=false for neoui_patch feature (bit 2097152)
- User preference: click-outside-to-close sidebar behavior
- Status: observation phase for potential conflicts"

# 2. 测试系统基础
git add tests/runtime/ tests/conftest.py requirements-test.txt
git commit -m "feat(tests): add runtime testing infrastructure with Playwright

- Add game_session fixture for E2E tests
- Implement ModLoader, combat, cheat_extended test suites
- Update CI workflow to run runtime tests"

# 3. 社区工具调研
git add docs/COMMUNITY_TOOLS_RESEARCH_2026-06-24.md tools/integrate_*
git commit -m "docs(tools): research and evaluate DoL community mod tools

- Extract tool list from DoL CN Wiki
- Assess integration feasibility for DOL-X
- Create integration script templates"

# 4. 文档更新
git add AGENTS.md docs/*.md README.md
git commit -m "docs: update project documentation for NeoUI and testing enhancements

- Record NeoUI integration rationale
- Document runtime testing strategy
- Update build codes and mod list"
```

---

## 时间线与里程碑

### 短期（2026-06-24 完成）
- ✅ NeoUI Patch 启用
- ✅ 配置测试通过
- ✅ CI 构建触发

### 中期（2026-06-25 完成）
- ✅ 社区工具调研报告
- ✅ 运行时测试基础设施
- ⚠️ 至少 3 个运行时测试用例通过

### 长期（2026-06 月底完成）
- ✅ 80% 手动测试自动化
- ✅ CI 集成运行时测试
- ✅ NeoUI 用户验收测试通过

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|-----|-----|---------|
| NeoUI 与 Mae's Picvary 严重冲突 | 中 | 高 | 保留回退选项（`skip=true`）+ 手动测试优先 |
| Playwright 测试环境复杂 | 高 | 中 | 准备详细 setup 文档 + CI 容器化 |
| 社区工具不适配 Python 构建 | 中 | 低 | 仅集成可行部分 + 自研替代方案 |
| 运行时测试不稳定（flaky tests） | 高 | 中 | 增加重试机制 + 固定测试数据 |

---

## 成功标准

### 阶段 1（NeoUI 集成）
- [ ] `python -m pytest tests/ -v` 全部通过
- [ ] CI Build 成功生成 8 个 APK（4 个原有 + 4 个带 NeoUI）
- [ ] 手动测试无严重视觉冲突

### 阶段 2（社区工具）
- [ ] 调研报告包含至少 5 个工具的可行性分析
- [ ] 至少集成 1 个工具到 DOL-X 工具链

### 阶段 3（测试系统）
- [ ] Playwright 测试环境在本地和 CI 成功运行
- [ ] 至少 10 个运行时测试用例通过
- [ ] 手动测试清单 50% 以上自动化

### 阶段 4（NeoUI 验收）
- [ ] 3 种分辨率下侧边栏表现符合预期
- [ ] Mae's Picvary NPC 头像正常显示
- [ ] 用户确认保留或回退

### 整体交付
- [ ] 所有提交 push 到 origin/vega
- [ ] CI 最新构建成功
- [ ] 文档完整更新

---

## 参考资料

- [DoL 中文 Wiki - 模组列表](https://degreesoflewditycn.miraheze.org/wiki/模组列表)
- [Playwright Python Docs](https://playwright.dev/python/)
- [SugarCube 2 Documentation](https://www.motoslave.net/sugarcube/2/)
- DOL-X 项目文档: `docs/`, `AGENTS.md`
