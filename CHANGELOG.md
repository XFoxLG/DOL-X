# 更新日志

本文件记录 DOL-X 的所有重要变更。

格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)。

> **版本号说明**：DOL-X 是整合包，版本号采用 `v{游戏版本}-{整合版本}a-{日期}` 的复合格式
> （例如 `v0.5.10.12-1.0.8a-0713`），用于对应所跟随的 DoL 游戏版本与汉化版本，**不是严格的
> [语义化版本 SemVer](https://semver.org/lang/zh-CN/)**。其中「整合版本」部分（如 `1.0.8`）
> 参照 SemVer 的主.次.修订思路递增：不兼容的构建体系改动进主版本、向下兼容的 mod 集合新增进
> 次版本、修复类改动进修订号。变更分类使用 Keep a Changelog 的六类：
> `Added`（新增）/`Changed`（变更）/`Deprecated`（弃用）/`Removed`（移除）/`Fixed`（修复）/`Security`（安全）。

## [Unreleased]

暂无未发布变更。

## [v0.5.10.12-1.0.8a-0713] - 2026-07-13

稳定包更新发布（B 线 / vega）。在 tag `v0.5.10.12-1.0.8a-0707` 基础上重新出包，携带
DOLI 悬浮窗图标修复与完整的 NPC 侧边栏图层命名兼容修复，四体型（base / AU-F / AU-M /
AU-A）× 双格式（ZIP + APK）共 8 个产物。MuMu 模拟器 + 浏览器实测通过：DOLI 悬浮窗图标
正常、NPC 侧边栏立绘（身体与衣服层）正常。旧的 `-0707` 版本经用户确认后归档/移除。

### Fixed

- **DOLI 悬浮窗图标 404（图裂）**：DOLI v0.2.3 在 `dist/DOLI.js` 硬编码悬浮按钮图标为
  `img/ui/sym_awareness.png`（下划线），这是 0.5.9.8 之前的旧资源名。游戏 0.5.9.8+ 将
  全部 `sym_*.png` 重命名为 `sym-*.png`（连字符），当前 0.5.10.12 栈中旧路径不存在，导致
  悬浮窗图标破图。修复为构建期 payload 重打包（`patch_doli_float_icon_path()`），只改这一个
  字符串，其余 zip 条目字节不变，**fail-closed**（源数据漂移或找不到目标字符串则中止构建）。
  与 AU 改脸 `eyes.png` 报错无关——后者是 AU 改脸包自身缺合并图层导致的无害噪音（图像仍能
  加载），不属于 DOL-X。

- **NPC 侧边栏图层命名兼容（身体 + 衣服全层）**：maplebirch v3.1.14（B 线保留的最后 3.x
  版，因 maplebirchExpansion v1.2.4 无 4.x 构建）用旧的无连字符命名请求侧边栏图层路径，游戏
  0.5.9.8+ 与 AU 美化包已改为连字符命名，导致身体层显示破损轮廓、衣服层静默消失。自研兼容 mod
  `maplebirch-v3-layer-compat` 通过公开 API `char.use()` 把 v4.1.6–v4.1.12 的连字符路径逻辑
  （身体 5 层 + blush + 约 90 个衣服层 srcfn）back-port 到 v3，只覆盖 srcfn 叶子、不改框架源码、
  无副作用。注：具名原版 NPC（如萨姆）默认无衣服是框架设计边界（NPC 无衣柜数据，`worn()` 回落
  naked），与本命名兼容修复是两回事，不在本修复范围。

### Changed

- **NeoUI Patch 升为全部内置**（2026-07-05）：此前 NeoUI 只在单独的对比包里用于隔离
  AU 侧边栏诊断，经对比测试确认 sprite 在带/不带 NeoUI 时都正常渲染、NeoUI 非错位原因
  后，将其从可选升为必选，进入全部构建。矩阵由"基础 + 3 AU + 1 个 AU-F+NeoUI 对比包"
  收敛为 4 个包（base / AU-F / AU-M / AU-A），全部内置 NeoUI，不再构建无 NeoUI 变体。
  当前 build code：base `15704320` / AU-F `15705344` / AU-M `15706368` / AU-A `15708416`。

### Removed

- **移除 fork 实验脚手架**（2026-07-06）：cheatExtended 走自建镜像稳定后，退役废弃的
  canary/gate 实验。删除 16 个 fork 专属文件（4 个 workflow、5 个 tool、7 个对应测试），
  并清理 `lyra/compatibility.py`、`build.yaml`、`lyra/build.py` 里的 4 处引用（含从未存在
  patch 文件的 `expansion_v4_compat.js` v4.x shim）。只动 fork 新增的脚手架，上游 Lyra
  核心文件保持上游友好。验证：全仓扫描无悬空导入，测试全绿。`docs/` 下历史决策记录保留。
- **清理 CI 构建产物**（2026-07-01）：GitHub Actions artifact 存储涨到 573 个 / ~89 GB
  超配额，删至只留最新 3 次构建（9 个产物），释放约 86.5 GB。这些是可从源码复现的历史 CI
  产物，删除不可逆但无损。

## [v0.5.10.12-1.0.8a-0628] - 2026-06-28

在此版本前后完成 D.O.L.I 集成与构建体系修复。（此区间的 `-0707` 中间版本已于 0713 发布后移除，
其内容并入 `-0713` 稳定版。）

### Added

- **集成 D.O.L.I**（2026-07-01）：`ArsNativa/Degrees-of-Lewdity-Intelligence` 钉死
  `v0.2.3`（asset `DOLI.mod.zip`）。LLM 驱动的 AI 对话 / 战斗文本增强，ReAct 模式，接
  OpenAI 兼容后端。它是 maplebirch 插件（`boot.json` 要求 ModLoader `^2.0.0` + maplebirch
  `^3.1.0`，当前 2.101.1 + 3.1.14 满足）。作为必选 mod（feature bit `8388608`）进入全部
  构建。**构建系统绝不嵌入 API key**，玩家在游戏内自填，未配置时 mod 仍能加载、只是 AI
  功能不工作。许可证 CC BY-NC-SA 4.0。
- **记录当前启用 mod 集**（2026-06-29）：`guide_to_me` v1.1.0（控制NPC嘴部）、
  `npc_social_icon` v1.4.1（NPC社交栏头像）。
- AU 模型 asset 钉死到精确 release 文件，新增 `docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md`。
- APK 文件名加入 commit hash（如 `-e0b1a4b`）用于版本追踪；新增 `BUILD_MANIFEST.json`
  构建溯源；新增 `tools/quick_check.py`（本地快速校验）、`tools/download_latest_build.py`
  （测试管理）、自动生成的 TEST_CHECKLIST。

### Fixed

- **构建产物文件名冲突**（2026-06-30）：`ModCode.get_suffix()` 未识别较新的 mod bit
  （`guide_to_me`/`bunny_transformation`/`neoui_patch`/`npc_social_icon`），导致带/不带
  NeoUI 的 AU-F 生成相同 APK 文件名、在 `output/` 里互相覆盖。为这 4 个 bit 注册了不同的
  文件名后缀，并加 `test_build_codes_have_unique_output_suffixes` 防止再次冲突。提交 `0197f79`。

### Changed

- **NeoUI Patch 诊断结论**（2026-06-30）：NeoUI 一度被列为 AU 侧边栏 sprite 错位的头号
  嫌疑并隔离到单独对比包。CI run `28461618104` 上带/不带 NeoUI 的对比构建（游戏/mod 版本
  完全一致）实测：两者 sprite 都正常渲染，**NeoUI 不是错位原因**。其覆盖式侧边栏遮挡正文
  是设计本意、非 bug。错位根因（最强推断、非铁证）指向早期 maplebirch v4.x 栈 +
  `expansion_v4_compat.js` shim（已在 commit `d3bcd47` 移除）。
- **BunnyTransformation 禁用**：v0.3.1β 触发 16 个 TweeReplacer 错误并导致战斗系统崩溃。
- AU-F 回退到与上游对齐的 asset `AUfemale.model_v0.9.3.zip`。

## [v3.1.14-stable] - 2026-06-23

### Changed

- **Rolled back to maplebirch v3.1.14** (from v4.1.8)
- **Rolled back to cheat extended v1.17** (from v1.19)
- **Disabled AU Face expansion** (enabled=false in build.toml)

### Reason

- **expansion v1.2.4 incompatible with maplebirch v4.x**
  - Multiple runtime errors in game
  - AU Face has basehead.png path issue on v3.x (fixed in v4.1.7)
  - Will upgrade when expansion v1.2.5+ releases with native v4.x support

### Fixed

- Stabilized build stack with proven compatible versions
- Prevented mod version conflicts

## [v4.1.8-experimental] - 2026-06-23

### Changed

- Upgraded to maplebirch v4.1.8
- Upgraded to cheat extended v1.19

### Reverted

- Rolled back due to expansion compatibility issues
- See v3.1.14-stable for details

---

## Version History Notes

### Mod Version Strategy

DOL-X uses a **conservative version locking strategy**:

1. **Lock tested versions** in `config/mods.lock.json`
2. **Only upgrade when**:
   - Upstream game version updates
   - Critical bug fixes
   - New features with verified compatibility
3. **Test before upgrade**:
   - Manual testing on MuMu emulator
   - CI automated smoke tests
   - Community feedback review

### Build Code Calculation

Build codes are calculated from feature bits in `config/features.toml`:

```
base_code = sum(required_features.bit)
AU variants = base_code + AU_bit

当前矩阵（4 个包，全部内置 NeoUI + DOLI，见 config/combinations.toml）：
- base : 15704320（UCB + more_love + cheat_extended_maplebirch + custom_hair
         + mae_picvary + maplebirch_expansion + guide_to_me + neoui_patch
         + npc_social_icon + doli）
- AU-F : 15705344（base + 1024）
- AU-M : 15706368（base + 2048）
- AU-A : 15708416（base + 4096）
```

### Upstream Sync Policy

DOL-X syncs with upstream Lyra selectively:

- ✅ **Sync**: Core build system, game version updates, localization updates
- ❌ **No sync**: Mod matrix decisions (DOL-X decides independently)
- 📋 **Review**: Documentation and workflow improvements

See `UPSTREAM_SYNC_CHECKLIST.md` for sync procedures.
