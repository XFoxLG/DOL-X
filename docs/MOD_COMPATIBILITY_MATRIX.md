# DOL-X Mod 兼容性矩阵

本文档记录所有候选 mod 的兼容性测试结果，用于决策哪些 mod 可以安全集成到 DOL-X。

**最后更新**: 2026-06-28  
**当前框架**: maplebirch v3.1.14 + expansion v1.2.4  
**当前游戏版本**: DoL v0.5.8.10  
**当前作弊**: Cheat Extended v1.17

---

## 测试标准

### 测试环境

- **本地配置验证**: `python -m pytest tests/ -v`
- **构建产物**: GitHub Actions `Build` workflow（本地不执行完整构建）
- **浏览器测试**: `python tools/browser_smoke_test.py output/*.zip`
- **模拟器测试**: APK 在 MuMu 模拟器上运行
- **ModLoader 日志**: 检查加载错误和冲突

### 测试项目

1. **加载成功**: ModLoader 成功加载 mod
2. **无冲突**: 不与现有 mod 冲突
3. **功能正常**: mod 的核心功能可用
4. **性能影响**: 不显著影响游戏性能
5. **稳定性**: 不引入新的 crash 或 bug

### 测试状态说明

| 状态 | 说明 | 图标 |
|------|------|------|
| ✅ 通过 | 所有测试通过，可以集成 | ✅ |
| ⚠️ 部分通过 | 功能可用但有小问题 | ⚠️ |
| ❌ 失败 | 测试失败，不可集成 | ❌ |
| 🔄 待测试 | 尚未测试 | 🔄 |
| ⏳ 等待中 | 等待条件满足（如 v4.x 升级） | ⏳ |

---

## 当前集成 Mod 状态

### 必选 Mod（已集成）

| Mod 名称 | 版本 | maplebirch 要求 | DoL 版本 | 测试状态 | 已知问题 | 备注 |
|----------|------|-----------------|----------|----------|----------|------|
| maplebirch Framework | v3.1.14 | - | 0.5.8.10 | ✅ | 无 | 核心框架，稳定版 |
| Cheat Extended | v1.17 | v3.x | 0.5.8.10 | ⚠️ | 自定义言灵集 widget 报错 | Workaround: 使用快速言灵 |
| maplebirch Expansion | v1.2.4 | v3.1.14 | 0.5.8.10 | ✅ | 无 | 完全兼容 |
| CustomHair | v1.0.0 | 无要求 | 0.5.2.7-0.5.2.10 | ⚠️ | 十六进制颜色输入缺失 | 预设颜色正常可用 |
| More Love Interests | v0.1.6.0 | 无要求 | 0.5.8.10 | ✅ | 无 | 独立功能 |
| Mae's Picvary NPC | v1.3.2 | 无要求 | 0.5.8.10 | ✅ | 无 | 侧边栏头像 |
| Guide To Me | v1.1.0 | 无要求 | 0.5.8.10 | ✅ | 无 | 控制 NPC 嘴部动作，当前稳定矩阵启用 |
| NeoUI Patch | V1.1.0 | 无要求 | 0.5.8.10 | ✅ | 需继续观察 AU 侧边栏交互 | 当前稳定矩阵启用 |
| NPC Social Icon | v1.4.1 | 无要求 | 0.5.8.10 | ✅ | 无 | 当前稳定矩阵启用；与 Mae's Picvary 作用域不同 |
| BunnyTransformation | v0.3.1β | 无要求 | 0.5.8.10 | ❌ | 16 个 TweeReplacer 错误和战斗崩溃 | 已禁用，不进入当前稳定 build_codes |

### AU 美化（已集成，可选）

| Mod 名称 | 版本 | maplebirch 要求 | DoL 版本 | 测试状态 | 已知问题 | 备注 |
|----------|------|-----------------|----------|----------|----------|------|
| AU Female model | v0.9.3 | 无要求 | 0.5.8.10 | ⚠️ | 侧边栏人物预览贴图错位 | 使用 `mod` release 的 model 直装模组，诊断中 |
| AU Male model | v0.4.2 | 无要求 | 0.5.8.10 | 🔄 | 待最新构建复测 | 使用 `mod` release 的 model 直装模组 |
| AU Androgynous model | v0.1.1 | 无要求 | 0.5.8.10 | 🔄 | 待最新构建复测 | 使用 `mod` release 的 model 直装模组 |
| AU Face Expansion | v1.2.8 | v4.1.7+ | 0.5.8.10 | ❌ | 已禁用；不要与 AU model 本体混淆 | `facemod` release，等待 v4.x 升级或重新验证 |

AU 诊断记录：`docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md`。当前默认不使用 AU `imgpack`，因为覆盖 imagepack 层会增加与 UCB 的路径冲突风险。

### UCB Imagepack（已集成）

| Imagepack | 状态 | 测试状态 | 冲突检测 | 备注 |
|-----------|------|----------|----------|------|
| UCB | 必选 | ✅ | 无冲突 | 唯一战斗美化 |

---

## 高优先级候选（maplebirch v3.1.14 兼容）

### 视觉美化类

| Mod 名称 | 版本 | GitHub | maplebirch 要求 | DoL 版本 | 测试状态 | 测试日期 | 测试结果 | 已知问题 | 决策 |
|----------|------|--------|-----------------|----------|----------|----------|----------|----------|------|
| NPC社交栏头像 | v1.4.1 | [Eudemonism00/DOL-npcicon-mods](https://github.com/Eudemonism00/DOL-npcicon-mods) | 无要求 | 0.5.8.10 | 🔄 | - | - | - | **Sprint 2 测试** |
| 降低天气图层 | 3.0 | [miyakoAki4828/Dol-Miyako-Mods](https://github.com/miyakoAki4828/Dol-Miyako-Mods) | 无要求 | 0.5.8.10 | 🔄 | - | - | - | Sprint 2/3 测试 |

### 体验优化类

| Mod 名称 | 版本 | GitHub | maplebirch 要求 | DoL 版本 | 测试状态 | 测试日期 | 测试结果 | 已知问题 | 决策 |
|----------|------|--------|-----------------|----------|----------|----------|----------|----------|------|
| 厨房优化 | 5.3.7.2 | [Lethivia/DoL-mod-kitchenplus](https://github.com/Lethivia/DoL-mod-kitchenplus) | 无要求 | 0.5.8.10 | 🔄 | - | - | - | **Sprint 2 测试** |
| 时间流速控制 | 5.4.6.1 | [Lethivia/DoL-timemulti](https://github.com/Lethivia/DoL-timemulti) | 无要求 | 0.5.8.10 | 🔄 | - | - | 可能影响游戏平衡 | Sprint 3 测试 |
| 公交车防骚扰 | v1.0.0 | [Ayndpa/NoBusHarassmentMod](https://github.com/Ayndpa/NoBusHarassmentMod) | **v3.1.14** | 0.5.8.10 | 🔄 | - | - | - | Sprint 3 测试 |

---

## 中优先级候选（需验证兼容性）

### 战斗辅助类

| Mod 名称 | 版本 | GitHub | maplebirch 要求 | DoL 版本 | 测试状态 | 测试日期 | 测试结果 | 已知问题 | 决策 |
|----------|------|--------|-----------------|----------|----------|----------|----------|----------|------|
| 战斗状态显示 | v1.0.1 | [DoL-Lyra/CombatStatusDisplay](https://github.com/DoL-Lyra/CombatStatusDisplay) | 无要求 | 0.5.8.10 | 🔄 | - | - | 2.5年未更新 | Sprint 3/4 测试 |

### 内容扩展类

| Mod 名称 | 版本 | GitHub | maplebirch 要求 | DoL 版本 | 测试状态 | 测试日期 | 测试结果 | 已知问题 | 决策 |
|----------|------|--------|-----------------|----------|----------|----------|----------|----------|------|
| 同心吊坠文本拓展 | v0.5 | [koooooiCarp/DOL-Love-Locket-Text-Expansion-Mod](https://github.com/koooooiCarp/DOL-Love-Locket-Text-Expansion-Mod) | 无要求 | **0.5.7.x** | 🔄 | - | - | 版本不匹配 | Sprint 4 测试（需确认兼容性） |
| 鹰宝宝 | v1.7 | [koooooiCarp/DOL-BabyHawk-Mod](https://github.com/koooooiCarp/DOL-BabyHawk-Mod) | 无要求 | 0.5.8.10 | 🔄 | - | - | - | Sprint 4 或后续 |

---

## 等待 v4.x 升级后测试

### Simple Framework 依赖

| Mod 名称 | 版本 | GitHub | 依赖 | DoL 版本 | 测试状态 | 阻塞原因 | 预计测试时间 |
|----------|------|--------|------|----------|----------|----------|--------------|
| 侧边栏背景 | v1.0.2 | [LooopSpiner/DOL-UI-Bar-Background](https://github.com/LooopSpiner/DOL-UI-Bar-Background) | Simple Framework | 0.5.8.10 | ⏳ | 需 Simple Framework 支持 | v4.x 升级后 |

### 需深入测试

| Mod 名称 | 版本 | GitHub | maplebirch 要求 | DoL 版本 | 测试状态 | 阻塞原因 | 预计测试时间 |
|----------|------|--------|-----------------|----------|----------|----------|--------------|
| 极致动态 | v.2.7 | [ANLINSTUDIO/Degrees-of-Lewdity-DolDynamicest](https://github.com/ANLINSTUDIO/Degrees-of-Lewdity-DolDynamicest) | 需评估 | 0.5.8.10 | ⏳ | UI 修改较多，需全面测试 | Sprint 4 或 v4.x 后 |
| 原版优化 | v.1.0.7 | [ANLINSTUDIO/Degrees-of-Lewdity-DolOptimization](https://github.com/ANLINSTUDIO/Degrees-of-Lewdity-DolOptimization) | 需评估 | 0.5.8.10 | ⏳ | 修改较多，需全面测试 | Sprint 4 或 v4.x 后（**高价值**） |
| 万能智能手机 | v.alpha.3.84.1 | [ANLINSTUDIO/Degrees-of-Lewdity-DolSmartPhone](https://github.com/ANLINSTUDIO/Degrees-of-Lewdity-DolSmartPhone) | 需评估 | 0.5.8.10 | ⏳ | Alpha 版本，等待稳定版 | Sprint 4 或 v4.x 后（**高价值**） |

---

## 测试记录模板

### 新 Mod 测试记录

```markdown
## [Mod 名称] 测试记录

**测试日期**: YYYY-MM-DD  
**测试者**: [姓名]  
**版本**: [mod 版本]  
**DOL-X 版本**: [当前 commit]

### 测试环境
- maplebirch: v3.1.14
- expansion: v1.2.4
- DoL: 0.5.8.10
- 构建码: 7315712

### 测试步骤
1. 下载 mod: `gh release download ...`
2. 添加到 build.toml
3. 构建: GitHub Actions `Build` workflow
4. 浏览器测试: `python tools/browser_smoke_test.py ...`
5. 模拟器测试: 安装 APK 到 MuMu 模拟器

### 测试结果

#### 加载成功
- [ ] ModLoader 成功加载
- [ ] 无加载错误日志
- [ ] boot.json 信息正确显示

#### 功能测试
- [ ] 核心功能可用
- [ ] UI 显示正常
- [ ] 无明显 bug

#### 兼容性测试
- [ ] 与现有 mod 无冲突
- [ ] ModLoader 日志无警告
- [ ] 游戏性能正常

#### 稳定性测试
- [ ] 游戏启动正常
- [ ] 无 crash
- [ ] 长时间运行稳定

### 已知问题
[列出发现的问题]

### 决策
- [ ] ✅ 通过，可以集成
- [ ] ⚠️ 部分通过，需修复已知问题后集成
- [ ] ❌ 失败，不推荐集成
- [ ] 🔄 需要更多测试

### 集成计划
[如果通过，说明何时集成到哪个 sprint]
```

---

## 测试工作流

### Sprint 2 测试计划（下周）

**目标**: 测试 2 个高优先级 mod

1. **NPC社交栏头像**
   - 下载: `gh release download v1.4.1 -R Eudemonism00/DOL-npcicon-mods`
   - 测试: 本地构建 + 浏览器 + 模拟器
   - 决策: 通过则集成

2. **厨房优化**
   - 下载: `gh release download 5.3.7.2 -R Lethivia/DoL-mod-kitchenplus`
   - 测试: 本地构建 + 浏览器 + 模拟器
   - 决策: 通过则集成

**验收标准**:
- 至少 1 个 mod 通过测试并集成
- 更新本矩阵的测试结果
- 更新 [config/build.toml](../config/build.toml)

### Sprint 3 测试计划（两周后）

**目标**: 测试 2-3 个候选 mod

1. 降低天气图层
2. 时间流速控制（需评估游戏平衡影响）
3. 公交车防骚扰（需验证 maplebirch v3.1.14 兼容性）

### Sprint 4 测试计划（一个月后）

**目标**: 测试中优先级和高价值 mod

1. 战斗状态显示
2. 同心吊坠文本拓展（需确认 0.5.8.10 兼容性）
3. 极致动态（全面测试）
4. 原版优化（**高价值**，全面测试）

---

## 兼容性检查清单

### 添加新 Mod 前必查

- [ ] 检查 maplebirch 版本要求（v3.1.14 或更低）
- [ ] 检查 DoL 版本要求（0.5.8.10）
- [ ] 检查是否依赖 Simple Framework（当前不支持）
- [ ] 检查 GitHub 最后更新时间（6 个月内）
- [ ] 检查是否开源且无密码保护
- [ ] 阅读 mod README 和 boot.json

### 集成后必验证

- [ ] 运行 `pytest tests/` 验证构建矩阵
- [ ] 运行 `python tools/browser_smoke_test.py` 验证功能
- [ ] 检查 ModLoader 日志无错误
- [ ] 在 MuMu 模拟器测试 APK
- [ ] 更新 [config/mods.lock.json](../config/mods.lock.json)
- [ ] 更新本兼容性矩阵

---

## 参考文档

- [社区 Mod 调研](COMMUNITY_MOD_RESEARCH.md) - 候选 mod 详细信息
- [Mod 添加清单](MOD_ADDITION_CHECKLIST.md) - 集成流程
- [AGENTS.md](../AGENTS.md) - 版本锁定和升级策略
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) - 已知问题和 workarounds

---

**文档状态**: ✅ 初始版本完成  
**下次更新**: Sprint 2 测试完成后  
**维护者**: DOL-X 项目组
