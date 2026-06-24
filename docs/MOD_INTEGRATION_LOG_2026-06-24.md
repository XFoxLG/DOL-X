# MOD 集成日志 - 2026-06-24

## 摘要

4 个社区 mod 集成测试，2 个成功，2 个因技术原因拒绝。

---

## ✅ 成功集成（2个）

### 1. 控制NPC嘴部 (GuideToMe v1.1.0)

- **GitHub**: https://github.com/Ayndpa/DOL-GuideToMe
- **功能**: 在战斗中控制 NPC 嘴部行为
- **测试结果**: 无冲突，正常工作
- **集成时间**: 2026-06-23
- **Feature ID**: `guide_to_me`
- **Bit**: 524288

### 2. NPC社交栏头像 (v1.4.1)

- **GitHub**: https://github.com/Eudemonism00/DOL-npcicon-mods
- **功能**: NPC 社交关系栏显示头像
- **测试结果**: 无冲突，正常工作
- **集成时间**: 2026-06-23
- **Feature ID**: `npc_social_icon`
- **Bit**: 4194304

---

## ❌ 拒绝集成（2个）

### 1. 变身兔兔 (BunnyTransformation v0.3.1β)

**拒绝原因**: 战斗系统崩溃

#### 技术细节

**TweeReplacer 错误（16个）**:
```
[TweeReplacer] cannot find findString: [BunnyTransformation] 
findString:[<<if $fox gte 6>><<set $allure += 750>><</if>>] 
in:[Widgets Clothing Caption]

[TweeReplacer] cannot find findString: [BunnyTransformation] 
findString:[<<earnFeat "Fox">>] 
in:[Transformation Widgets]
```

**战斗错误**:
```javascript
Error: Cannot use 'in' operator to search for 'wings' in undefined
Location: PlayerCombatMapper.mapToTransformationWingOptions
Context: canvasmodel-combat-pc.js:xxx
```

#### 根因分析

1. **前置依赖缺失**: mod 期望游戏内置狐狸变身系统（fox transformation）
2. **版本不匹配**: 当前 DoL v0.5.8.10 + Lyra 没有 fox transformation
3. **破坏现有逻辑**: patch 失败导致天使/堕天使/鸟类翅膀渲染破坏

#### 测试环境

```
Mod加载列表（2026-06-24 09:34:26）:
- maplebirch v3.1.14
- cheat extended v1.17
- CustomHair v1.0.0
- Mea's Picvary NPC all mod v1.3.2
- maplebirchEx v1.2.4
- BunnyTransformation v0.3.1β  ← 问题源
```

#### 测试步骤

1. 正常进入游戏 ✅
2. 开启作弊拓展（选项→模组设置→作弊拓展） ✅
3. 点击"加入"进入战斗 ❌ **崩溃**

#### 决策

- **状态**: 禁用
- **Feature ID**: `bunny_transformation`
- **Skip**: `true`
- **Commit**: `d9b6e3e`
- **可能的未来**: 等待 v0.3.2+ 稳定版或联系作者确认前置依赖

---

### 2. NeoUI Patch (v1.1.0)

**拒绝原因**: 覆盖式布局设计冲突

#### 技术细节

**CSS 源码证据（ui.css:50）**:
```css
#story {
    /* 确保passage内容被uibar展开时遮挡，覆盖引擎内置的宽屏对齐方式 */
    margin-left: 3.5em;  /* ← 固定不变，阻止动态调整 */
    transition: margin-left 600ms cubic-bezier(0.7, -1, 0.3, 2);
}
```

**作者设计意图（readme.txt）**:
> "打开侧边栏时点击空白区域也能关闭侧边栏，符合现代应用操作逻辑"

#### 工作机制对比

```
原版游戏：
侧边栏收起 → #story { margin-left: 3.5em }
侧边栏展开 → #story { margin-left: 20em }  ← 推开内容

NeoUI 修改：
任何状态 → #story { margin-left: 3.5em }  ← 固定不变
         + transition 动画锁定
结果：侧边栏遮挡内容
```

#### 测试结果

**观察到的问题**:
1. 侧边栏展开时遮挡游戏内容（特别是宽屏用户）
2. 与侧边栏美化 mod 布局冲突
3. 需频繁点击关闭侧边栏，影响游戏体验

**测试环境**:
```
Mod加载列表（2026-06-24 18:50:17）:
- maplebirch v3.1.14
- cheat extended v1.17
- CustomHair v1.0.0
- Mea's Picvary NPC all mod v1.3.2  ← 布局冲突
- maplebirchEx v1.2.4
- GuideToMe v1.1.0
- NeoUI-Patch v1.1.0  ← 问题源
- NPC Avatars Mod v1.4.1  ← 布局冲突
```

#### 深度分析

**文件结构**:
```
neoui_patch_1.1.0.zip
├── boot.json          # Mod 配置
├── readme.txt         # 作者说明
├── sidebar.js         # 点击空白关闭功能
└── ui.css             # 样式修改（问题根源）
```

**设计理念**: 移动端抽屉菜单（Material Design Drawer）
- 侧边栏作为临时弹出层
- 覆盖在内容上，而非推开内容
- 使用后立即关闭（点击空白）

**与 DOL-X 的冲突**:
- DOL-X 采用推开式布局（侧边栏展开时内容区右移）
- NeoUI 强制覆盖式布局（侧边栏展开时内容区不动）
- 两种设计理念存在根本性冲突

#### 解决方案评估

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| A. 不集成 NeoUI | 彻底解决遮挡 | 失去弹性动画和点击关闭 | ⭐⭐⭐⭐⭐ |
| B. 修改 NeoUI CSS | 保留动画，解决遮挡 | 需重新打包，违背作者意图 | ⭐⭐⭐ |
| C. 提高美化侧边栏优先级 | 强制覆盖 NeoUI | 可能破坏动画效果 | ⭐⭐ |
| D. 调整加载顺序 | 无需改代码 | 无法解决固定 margin-left | ⭐ |

#### 决策

- **状态**: 禁用
- **Feature ID**: `neoui_patch`
- **Skip**: `true`
- **Commit**: `167d2b0`
- **替代方案**: 
  - 点击空白关闭功能可用轻量级独立脚本实现
  - 弹性动画为非核心功能，可放弃

#### 详细分析文档

完整技术报告位于:
- `workspace/temp/neoui_analysis/ANALYSIS_REPORT.md` (10章节完整报告)
- `workspace/temp/neoui_analysis/KEY_FINDINGS.md` (快速参考)

---

## 构建矩阵变化

### 旧配置（7个mod，4个构建）

```
Build Codes: 7315712, 7316736, 7317760, 7319808
包含：UCB + more_love + cheat + custom_hair + mae_picvary + expansion 
     + guide_to_me + neoui_patch + npc_icon + (bunny_transformation - 禁用)
```

### 新配置（6个mod，4个构建）

```
Build Codes: 5218560, 5219584, 5220608, 5222656
包含：UCB + more_love + cheat + custom_hair + mae_picvary + expansion 
     + guide_to_me + npc_icon
移除：bunny_transformation (bit 1048576), neoui_patch (bit 2097152)
```

---

## Git 提交记录

```bash
d9b6e3e - fix: disable BunnyTransformation mod due to combat crash (2026-06-24)
167d2b0 - fix: remove NeoUI Patch due to design conflict (2026-06-24)
```

---

## 测试清单

### ✅ 已测试

- [x] GuideToMe 正常工作
- [x] NPC 社交栏头像正常工作
- [x] BunnyTransformation 导致战斗崩溃
- [x] NeoUI Patch 侧边栏遮挡内容
- [x] 移除两个问题 mod 后构建矩阵正确
- [x] 所有单元测试通过（`pytest tests/test_build_matrix.py -v`）

### 🔄 待测试

- [ ] 新构建的 APK 下载测试
- [ ] 实机测试（MuMu 模拟器）
- [ ] 验证侧边栏无遮挡问题
- [ ] 验证战斗系统正常

---

## 经验教训

1. **Beta 版 mod 需谨慎**: BunnyTransformation v0.3.1β 不稳定
2. **设计理念冲突比代码 bug 更难解决**: NeoUI 的覆盖式布局不是 bug，是设计选择
3. **深度源码分析的重要性**: 通过阅读 CSS 注释确认 NeoUI 的设计意图
4. **实测优于推测**: 16 个 TweeReplacer 错误的具体位置帮助定位问题

---

## 下一步

1. 等待 GitHub Actions 构建新 APK（commit `167d2b0`）
2. 下载测试新构建
3. 实机验证：
   - 侧边栏展开不遮挡内容
   - 战斗系统正常运行
   - GuideToMe 和 NPC 社交栏头像工作正常

---

**日志完成时间**: 2026-06-24 19:30 UTC+8  
**维护者**: XFox  
**状态**: 已完成
