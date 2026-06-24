# DOL-X 全面自动化测试战略方案

**文档版本**: v1.0  
**创建日期**: 2026-06-24  
**目标**: 实现游戏所有功能和细节的完全自动化测试

---

## 执行摘要

基于对 DoL 社区工具的深度调研和 SugarCube 引擎特性分析，本方案提出一套**五层自动化测试体系**，目标是实现：

1. **100% 代码路径覆盖**（所有 passage、所有选项）
2. **100% Mod 功能验证**（所有 mod 的所有功能）
3. **100% UI 交互测试**（所有按钮、输入、显示）
4. **运行时状态深度验证**（游戏变量、NPC 状态、时间系统）
5. **跨平台兼容性验证**（ZIP、APK、浏览器、Android）

**预估工作量**: 6-9 个月（全职开发）  
**技术栈**: Playwright + SugarCube API + Python + Android Emulator

---

## 第一部分：社区工具调研结果

### 1.1 发现的社区工具

根据 https://degreesoflewditycn.miraheze.org/wiki/模组列表 的调研：

#### ✅ 可直接利用的工具

1. **ModLoader (Lyoko-Jeremie)**
   - 官方 mod 框架
   - 提供 JavaScript API 访问游戏状态
   - **测试价值**: 可通过 `window.SugarCube.State.active.variables` 访问所有游戏变量

2. **SugarValidator (社区工具)**
   - 验证 passage 标签完整性
   - 检测断链和语法错误
   - **测试价值**: 集成为 CI pre-check

3. **Selenium/Playwright 社区实践**
   - 已有 DoL 玩家使用 Selenium 进行随机点击测试
   - GitHub Gist: `aucchen/808ebf87a8ebd7d6ecb2d4753eff9ba5`
   - **测试价值**: 可复用自动导航逻辑

4. **DOL-Mod-Created-Helper (NumberSir)**
   - GitHub: `NumberSir/DOL-Mod-Created-Helper`
   - Mod 开发辅助工具
   - **测试价值**: 可参考其 mod 验证逻辑

#### ❌ 不适用的工具

1. **寿里美化/inuno美化** - 纯美术资源，无测试价值
2. **NPC头像mod** - 静态资源，视觉测试不在范围内
3. **简易框架/秋枫白桦框架** - 已集成到构建流程

---

### 1.2 关键技术发现

**SugarCube 引擎可测试性分析**：

```javascript
// 核心可测试 API（来自社区实践）
window.SugarCube.State.active.variables  // 所有游戏变量 ($money, $trauma, etc.)
window.SugarCube.State.passage           // 当前 passage
window.SugarCube.State.history           // 历史记录
window.SugarCube.Engine.play(passageName) // 跳转到指定 passage
window.SugarCube.Macro.get('set').handler // 执行宏命令
```

**可测试性评级**: ⭐⭐⭐⭐⭐ (5/5)  
**理由**: SugarCube 暴露了完整的状态 API，可实现深度状态验证

---

## 第二部分：五层自动化测试架构

### 架构概览

```
Layer 5: 端到端游戏流程测试 (E2E Gameplay Tests)
          ↓
Layer 4: Mod 功能集成测试 (Mod Integration Tests)
          ↓
Layer 3: 游戏逻辑单元测试 (Game Logic Unit Tests)
          ↓
Layer 2: UI 交互测试 (UI Interaction Tests)
          ↓
Layer 1: 静态分析与配置测试 (Static Analysis & Config Tests)
```

---

### Layer 1: 静态分析与配置测试

**目标**: 在不运行游戏的情况下验证配置完整性

**现有实现** (已有 242 个测试):
- ✅ `test_build_matrix.py` - 构建矩阵验证
- ✅ `test_mod_config.py` - Mod URL 验证
- ✅ `test_archive_extraction.py` - 安全性测试
- ✅ `test_au_face_compat.py` - AU 兼容性

**需要新增**:
- [ ] `test_passage_coverage.py` - 验证所有 passage 可达性
- [ ] `test_sugarcube_lint.py` - SugarCube 语法检查
- [ ] `test_mod_dependency_graph.py` - Mod 依赖关系验证

**工具**: pytest + toml + JSON schema

---

### Layer 2: UI 交互测试

**目标**: 验证所有 UI 元素可点击、可输入、正确显示

**技术栈**: Playwright (已在 compatibility.yaml 中使用)

**现有实现**:
- ✅ `test_browser_smoke.py` - 基础启动测试
- ✅ `test_html_smoke.py` - HTML 结构验证

**需要新增**:

```python
# 示例：test_ui_elements_complete.py
def test_all_buttons_clickable(page):
    """验证游戏中所有按钮都可点击"""
    page.goto("file://path/to/game.html")
    
    # 获取所有链接
    links = page.query_selector_all('a.macro-link')
    
    for link in links:
        assert link.is_visible()
        assert link.is_enabled()
        
def test_sidebar_always_present(page):
    """验证侧边栏在所有页面都存在"""
    passages = get_all_passage_names()  # 从 HTML 提取
    
    for passage in passages:
