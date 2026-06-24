# DoL 社区模组调研报告 2026

**调研日期**: 2026-06-24  
**调研来源**: https://degreesoflewditycn.miraheze.org/wiki/模组列表

---

## 调研目标

评估社区模组列表中的候选 mod，确定可集成到 DOL-X 的优质 mod。

---

## 调研结果总结

## 集成状态（4个新mod）

### ✅ 已集成（2个）

#### 1. 控制NPC嘴部 (Ayndpa v1.1.0)

- **GitHub**: https://github.com/Ayndpa/DOL-GuideToMe
- **功能**: 在战斗中控制 NPC 嘴部行为
- **测试结果**: 无冲突，正常工作
- **集成时间**: 2026-06-23
- **Feature ID**: `guide_to_me`
- **Bit**: 524288

#### 2. NPC社交栏头像 (Eudemonism00 v1.4.1)

- **GitHub**: https://github.com/Eudemonism00/DOL-npcicon-mods
- **功能**: NPC 社交关系栏显示头像
- **测试结果**: 无冲突，与 Mae's Picvary 互补
- **集成时间**: 2026-06-23
- **Feature ID**: `npc_social_icon`
- **Bit**: 4194304

### ❌ 已拒绝（2个）

#### 1. 变身兔兔 (WinterPeach v0.3.1β) - 已禁用

**拒绝原因**: 战斗系统崩溃

- **GitHub**: https://github.com/sylphiet/Bunny-TransformationCN
- **不兼容原因**:
  - 16 个 TweeReplacer 错误
  - mod 期望游戏内置狐狸变身系统（当前版本不存在）
  - 导致战斗系统崩溃：`Cannot use 'in' operator to search for 'wings' in undefined`
- **决策**: 禁用，等待 v0.3.2+ 稳定版
- **详细分析**: 见 `MOD_INTEGRATION_LOG_2026-06-24.md`

#### 2. NeoUI Patch (依雅莱 V1.1.0) - 已禁用

**拒绝原因**: 覆盖式布局设计冲突

- **GitHub**: https://github.com/RyaraSUKI/dol-neoui-patch
- **设计冲突**:
  - NeoUI 采用移动端抽屉菜单设计（覆盖式布局）
  - DOL-X 采用推开式布局
  - CSS 固定 `#story { margin-left: 3.5em }`，侧边栏展开时遮挡内容
- **决策**: 禁用，设计理念不兼容
- **详细分析**: 见 `MOD_INTEGRATION_LOG_2026-06-24.md` 和 `workspace/temp/neoui_analysis/`

---

### 已确认无需添加（5个）

#### 5. 更长的遭遇战 (狐千月)

- **状态**: ✅ 已在 maplebirch expansion v1.2.4
- **原因**: 功能已包含

#### 6. 治疗NPC阳痿 (狐千月)

- **状态**: ✅ 就是"更长的遭遇战"
- **原因**: 同一个 mod

#### 7. 作弊扩展 HSSkyBoy v1.1.3

- **状态**: ✅ 已被 cheat extended v1.17 代替
- **原因**: 已有更新版本

#### 8. 自定义染发 (-Nora--)

- **状态**: ✅ 就是 CustomHair v1.0.0
- **原因**: 同一个 mod，已集成

#### 9. site098 战斗美化

- **状态**: ✅ 就是 UCB
- **原因**: 同一个 mod，已集成

---

### 深度调研 - inuno/犬野美化

**仓库**: https://github.com/inuno-233/DOL-inuno-image-pack  
**版本**: v0.0.6 (2026-03-17)

**功能范围**:
- 面部特写图层
- 私处特写图层
- 小规模美化（非全面改造）

**兼容性分析**:
- 与 AU: ✅ 理论兼容（不同作用域）
- 与 UCB: ✅ 无冲突（不同图层）
- 与 maplebirch v3.1.14: ✅ 应该兼容

**社区集成度**: 低（主流整合包未采用）

**决策**: 低优先级，等主线 mod 稳定后再考虑

---

### 深度调研 - 爱、糖果和机器人

**仓库**: https://github.com/emicoto/DOLMods  
**版本**: v2.4.4.2.3 (官方) + v0.1.4 (修复版)

**类型**: 大型剧情/系统扩展 mod

**核心特性**:
- 新 NPC
- 唐人街地图
- 道具系统
- 上瘾系统
- 新技能（机械、化学）
- 新工作场所

**依赖**: Simple Framework（必需）

**稳定性**: ⚠️ 开发中，有已知 bug

**决策**: 暂不集成
- 原因 1: 依赖 Simple Framework（另一套框架）
- 原因 2: 与 maplebirch 可能冲突
- 原因 3: 稳定性不足
- 未来: 等 v2.5+ 稳定版

---

### 深度调研 - D.O.L.I (LLM)

**仓库**: https://github.com/ArsNativa/DOLI  
**版本**: V0.2.3 (2026-03-28)

**功能**:
- 将 LLM 引入游戏
- AI Agent 对话
- AI 战斗文本生成

**技术栈**: （待深度调研）
- API 依赖: 未知
- 本地 LLM 支持: 未知
- 配置复杂度: 未知

**决策**: 立即深度技术调研
- 优先级: 高（用户明确需要）
- 下一步: 克隆仓库，分析依赖和配置

---

## 决策矩阵

| Mod | 状态 | 优先级 | 原因 |
|-----|------|--------|------|
| 控制NPC嘴部 | ✅ 立即集成 | 高 | 稳定，独立功能 |
| 变身兔兔 | ❌ 已拒绝 | N/A | v0.3.1β 战斗崩溃 |
| NeoUI Patch | ❌ 已拒绝 | N/A | 覆盖式布局冲突 |
| NPC社交栏头像 | ✅ 测试共存 | 高 | 与 Mae's 互补 |
| inuno 美化 | ⏸️ 低优先级 | 低 | 社区集成度低 |
| 爱糖机器人 | ❌ 暂不集成 | - | 依赖复杂，不稳定 |
| D.O.L.I (LLM) | 🔍 调研中 | 高 | 用户需要，待评估 |

---

## 后续行动

1. 立即集成 4 个稳定 mod
2. 深度调研 D.O.L.I (LLM)
3. 测试 Mae's + NPC社交栏共存
4. inuno 美化：等主线稳定后再评估
