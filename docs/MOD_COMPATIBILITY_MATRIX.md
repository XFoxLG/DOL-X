# DOL-X Mod 兼容性矩阵

本文档记录所有候选 mod 的兼容性测试结果，用于决策哪些 mod 可以安全集成到 DOL-X。

**最后更新**: 2026-08-04
**当前公开主线框架 mod**: maplebirch v4.1.13（作者官方 Release）
**当前游戏本体版本**: DoL v0.5.10.12（汉化仓库 tag `v0.5.10.12-chs-1.0.8a`）
**当前公开主线作弊**: Cheat Extended v1.20 betaTest（作者官方 Pre-release）

> **两个版本维度不要混淆**：「框架 mod 版本」（v4.1.13）指秋枫白桦框架这个**前置 mod** 自身的版本；
> 「游戏本体版本」（0.5.10.12）指游戏本身。下方表格的 "DoL 版本" 列一律指**游戏本体版本**，
> "框架要求" 列一律指**框架 mod 版本**。
>
> 当前稳定 Release `v0.5.10.12-1.0.8a-0804` 与 `vega` 均使用 4.x 栈；0713 是保留的历史
> 3.x 回滚版本。

---

## 测试标准

### 测试环境

- **本地配置验证**: `python -m pytest tests/ -v`
- **CI 门禁**: Build workflow 在构建前执行完整 pytest，上传前执行 AU ZIP 产物审计
- **构建产物**: 0804 发版前 dry run `30907723945` 已完成全四码构建（base / AU-F / AU-M / AU-A × ZIP+APK，共 8 件）与 AU ZIP 审计
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
| ✅ 通过 | 已完成该行声明范围内的测试；不自动外推到未列功能 | ✅ |
| ⚠️ 部分通过 | 功能可用但有小问题 | ⚠️ |
| ❌ 失败 | 测试失败，不可集成 | ❌ |
| 🔄 待测试 | 尚未测试 | 🔄 |
| ⏳ 等待中 | 等待条件满足（如 v4.x 升级） | ⏳ |

---

## 当前集成 Mod 状态

### `vega` 必选 Mod（4.x 公开主线）

| Mod 名称 | 版本 | maplebirch 要求 | DoL 版本 | 测试状态 | 已知问题 | 备注 |
|----------|------|-----------------|----------|----------|----------|------|
| maplebirch Framework | **v4.1.13** | - | 0.5.10.12 | ✅ 基础栈 smoke | 全功能未遍历；云存档需自建后端；上游 4.1.14 待另案评估 | 官方资产 digest 一致；用户真机总日志 0 error / 0 warning；本轮不混入恢复 NPC 怀孕流程的 4.1.14 |
| Cheat Extended | **v1.20 betaTest** | **≥v3.2.5**（运行时软门控） | 0.5.10.12 | ✅ 抽样通过 | Pre-release 可在同 tag 下换包，按 digest 跟踪 | UI 可打开、抽样功能正常；头部遮罩相容模式来自该 mod |
| LongerCombat | **v1.0.1** | `^4.1.0`（addonPlugin） | ≥0.5.10.12 | ⚠️ 已挂载 | 具体倍率与长战斗行为未逐项测试 | 作者官方独立继任者，`dist/script.js` 已挂载 |
| YanlingCheatCollection | **v1.0.1** | `^4.1.0`（addonPlugin） | ≥0.5.10.12 | ⚠️ 已挂载 | 言灵命令未逐项遍历 | 作者官方独立继任者，`yanlingCheat` 已暴露 |
| maplebirchEx（旧整包） | v1.2.4 | `^3.1.0` | 0.5.10.12 | ❌ 退役 | 3.2.5 真机出现 dread/sanity/dreadmax undefined | 不再注入；镜像只作历史回滚档案 |
| CustomHair | v1.0.0 | 无要求 | 0.5.2.7-0.5.2.10 | ✅ | 无 | 十六进制输入框需先点击“自定义染发”选项才出现 |
| More Love Interests | **v0.1.7.0** | 无要求 | **≥0.5.10.0** | ⚠️ 空态真机通过 | 有 NPC 的食物数据、Avery/舒芙蕾与旧存档清理行为未覆盖 | 入口、页面跳转和空列表无红框；旧版属版本错配并导致食物偏好爆红 |
| Mae's Picvary NPC | v1.3.2 | 无要求 | 0.5.10.12 | ✅ | 无 | 侧边栏头像 |
| Guide To Me | v1.1.0 | 无要求 | 0.5.10.12 | ✅ | 无 | 控制 NPC 嘴部动作，当前稳定矩阵启用 |
| NeoUI Patch | V1.1.0 | 无要求 | 0.5.10.12 | ✅ | 覆盖式侧边栏遮挡正文为设计本意、非 bug；经对比确认非 AU 错位原因 | 2026-07-05 升为必选，进入全部 4 个 build_codes |
| NPC Social Icon | v1.4.1 | 无要求 | 0.5.10.12 | ✅ | 无 | 当前稳定矩阵启用；与 Mae's Picvary 作用域不同 |
| BunnyTransformation | v0.3.1β | 无要求 | 0.5.10.12 | ❌ | 16 个 TweeReplacer 错误和战斗崩溃 | 已禁用，不进入当前稳定 build_codes |

**2026-07-31 结论修正（4.x 公开主线）**

旧的“v3.2.5 是唯一解”只比较了依赖声明，没有覆盖运行时初始化，现已撤回：

| 组合 | 静态依赖 | 真机结果 | 决策 |
|---|---|---|---|
| 3.1.14 + Cheat Extended 1.20 | CE 门控不满足 | 弹窗，7 个 UI 注册跳过 | 不采用 |
| 3.2.5 + maplebirchEx 1.2.4 + CE 1.20 | 表面满足 | dread/sanity/dreadmax undefined | 不采用 |
| 4.1.13 + CE 1.20 + LongerCombat + Yanling | 现役包要求满足 | 0 error / 0 warning，CE 抽样正常 | 当前主线 |

四个 ZIP 本地构建 `4/4` 成功；base 为 36 个有效 payload，三个 AU 版各 38 个。公共 Actions
run `30709200905` 已完成全四码构建（8 件产物）。3.2.5 重建包显示的 2026.07.27 是重打包时间戳，
不是作者更新顺序。当前事实与产物名见 [CURRENT_PROJECT_STATE.md](CURRENT_PROJECT_STATE.md)。

### AU 美化（公开 AU 构建）

| Mod 名称 | 版本 | maplebirch 要求 | DoL 版本 | 测试状态 | 已知问题 | 备注 |
|----------|------|-----------------|----------|----------|----------|------|
| AU Female model | v0.9.3 | BeautySelector 路径识别 | 下游用于 0.5.10.12 | ⚠️ AU-F 真机代表 | 与 AU Face 的脸红/流泪视觉未完整遍历 | 官方 `mod` Release；分支与 tag 均构建 |
| AU Male model | v0.4.2 | BeautySelector 路径识别 | 下游用于 0.5.10.12 | ⚠️ CI + 静态通过 | 按既定决策不做真机验收 | 官方 `mod` Release；tag 构建 |
| AU Androgynous model | v0.1.1 | BeautySelector 路径识别 | 下游用于 0.5.10.12 | ⚠️ CI + 静态通过 | 按既定决策不做真机验收 | 官方 `mod` Release；tag 构建 |
| AU Face Expansion | Release v1.0.4 / 外层 v1.1.0 / 内层 v1.2.8 | manifest 无 maplebirch 硬依赖 | 0.5.10.12 | ⚠️ 部分真机 | 设置 UI 与交互通过；视觉效果未完整遍历 | 只进 AU 三版；base 明确不注入；0802 起公开发布 |

AU 诊断记录见 [AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md](AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md)。
当前仍使用 model 路线，不使用 AU `imgpack`；
AU Face 是独立脚本 mod，不等同于主 model 里的改脸目录。

### UCB Imagepack（已集成）

| Imagepack | 状态 | 测试状态 | 冲突检测 | 备注 |
|-----------|------|----------|----------|------|
| UCB | 必选 | ✅ | 无冲突 | 唯一战斗美化 |

---

## 历史候选清单（需按当前 4.x 栈重新评估）

以下表格形成于 3.x 阶段，只保留候选来源，不再代表当前兼容结论、优先级或排期。
任何候选都必须重新读取当前 Release、`boot.json` 和运行时依赖后再决定，不能沿用旧的
“兼容 v3.1.14 即可”标准。

### 视觉美化类

| Mod 名称 | 版本 | GitHub | maplebirch 要求 | DoL 版本 | 测试状态 | 测试日期 | 测试结果 | 已知问题 | 决策 |
|----------|------|--------|-----------------|----------|----------|----------|----------|----------|------|
| NPC社交栏头像 | v1.4.1 | [Eudemonism00/DOL-NPC-Avatars-Mod](https://github.com/Eudemonism00/DOL-NPC-Avatars-Mod) | 无要求 | 0.5.8.10 | 🔄 | - | - | - | **Sprint 2 测试** |
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

## 其他框架与高改动候选

框架已升级到 4.1.13，因此“等待 v4.x”不再是有效阻塞原因。Simple Framework 仍是另一个
互斥 provider，不能与 maplebirch 同包启用；其依赖 mod 若要测试，应另开隔离候选。

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
- maplebirch: v4.1.13
- LongerCombat: v1.0.1
- YanlingCheatCollection: v1.0.1
- DoL: 0.5.10.12
- 构建码: 15704320

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
   - 下载: `gh release download 1.4 -R Eudemonism00/DOL-NPC-Avatars-Mod`
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

- [ ] 区分框架 mod 版本要求与 DoL 游戏本体版本要求
- [ ] 检查是否支持 maplebirch v4.1.13 与 DoL 0.5.10.12
- [ ] 检查是否依赖 Simple Framework；它与 maplebirch 是互斥 provider，必须隔离测试
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

- [社区 Mod 调研](COMMUNITY_MOD_RESEARCH_2026.md) - 候选 mod 详细信息
- [Mod 添加清单](MOD_ADDITION_CHECKLIST.md) - 集成流程
- [当前项目状态](CURRENT_PROJECT_STATE.md) - 当前版本锁、验证层级和公开分发边界
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) - 已知问题和 workarounds

---

**文档状态**: 当前稳定版为 `v0.5.10.12-1.0.8a-0804`，发版前全四码 CI 构建与 8 件产物静态审计已验证。
AU-M / AU-A 按既定决策不做真机验收，验证层级止于 CI 构建 + 静态 payload 检查。
**下次更新**: More Love 有 NPC 的食物数据路径复验后，或 maplebirch 4.1.14 另案评估时
**维护者**: DOL-X 项目组
