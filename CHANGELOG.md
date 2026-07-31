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

> **2026-07-31 4.x 公开主线迁移**：从 0713 的干净 `vega` 基线重建 4.x 公共主线（maplebirch 4.1.13 + CE 1.20 + LongerCombat + Yanling + Legacy-Art-Mods-Compat plus）。旧 0713 稳定栈已存档为远程分支 `vega-archive-0713`，plus 已上传到 `XFoxLG/DOL-X` Release `legacy-art-compat-plus-v1.1`。GitHub Actions run [`30610401219`](https://github.com/XFoxLG/DOL-X/actions/runs/30610401219) 已成功生成并上传 base ZIP/APK；该次运行由分支推送触发，未创建新 Release，因此最新已打 tag 的稳定 Release 仍是 0713。

> **公开分发边界**：AU 作者 README 明确禁止二传、拆包和未经授权搬运。四个 build code 继续保留本地自构建能力，但公共 Actions 只构建并上传 base `15704320`；获得作者明确授权前不新增公开 AU artifact 或 Release。

> **2026-07-29 后续**：AU-F 0728 本地候选的用户真机测试已经把"AU Face 尚未验收"拆成两层：设置 UI 和配置交互已通过，但运行时仍请求旧式 `blushN` / `tearN` 路径，当前包内 canonical 资源是新式 `blush-N` / `tears-N`。官方 `Legacy-Art-Mods-Compat` 1.0.3 不含这些 AU Face 通配符规则；社区二改 `1.0.3-plusV1.1` 精确包含。用户旁加载 plus 后 `blushN`/`tearN` 报错消失、独立嘴部仪态有效，面纹和流泪视觉效果不碍事、不阻塞主线——属上游 AU Face 加密内层运行时边界，DOL-X 无白盒修复手段。同时确认 maplebirch `PC模型模式` 需要独立 NPC wardrobe 数据，当前 38 个 payload 均未注册衣柜，因此具名剧情 NPC 动态模型回落 `naked` 是设计内行为，不是图片路径 bug。云存档服务端源码位于官方 `cloud-services/`，提供 Go+SQLite 与 Cloudflare Worker+R2+D1 两种自建方案，无公共实例；Go 后端当前缺少客户端会调用的 `/save-code` 路由。详见 `docs/MAPLEBIRCH_CLOUD_NPC_AUFACE_RESEARCH_2026-07-29.md`。

### Added

- **接入官方拆分继任者**：新增 LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`，
  分别承接旧 maplebirchEx 的更长遭遇战和言灵功能。两个包均来自作者官方仓库，声明
  maplebirch `^4.1.0`。
- **AU Face 本地候选**：官方 `AUsDoL.facial.expansion.mod.zip` 仅绑定 AU-F/M/A，不进入基础版。
  Release 正文版本为 `1.0.4`，包内 manifest 为 `1.1.0`，内层解密后实际注册为 `AU面部扩展 1.2.8`；
  本地锁定官方 SHA-256 `8f2c1b66f0104e51e4f1c91f8f3a4873db517997a390c1037f4de811d387ecf6`。
  AU-F 已确认设置 UI 可打开、配置可交互，但运行时仍请求旧式 `blushN` / `tearN` 路径，视觉效果
  尚未通过；尚未上传。
- **预发布资产更新追踪**：Mod 配置新增默认关闭的 `include_prerelease_updates`。Cheat Extended
  v1.20 使用官方 `Pre-release` 通道，更新检查除 tag 外还比较 GitHub asset digest 与
  `mods.lock.json`，可发现同一 tag 下的原位换包。
- **GitHub API 认证支持**：本地 downloader 在存在 `GITHUB_TOKEN` 或 `GH_TOKEN` 时附加认证头，
  避免全量准备过程中耗尽匿名 API 配额；无 token 时保持原行为。
- **当前事实与治理文档**：新增 `docs/CURRENT_PROJECT_STATE.md`、`UPSTREAM_FRIENDLY_STRATEGY.md`
  和 `UPSTREAM_DIFF_SUMMARY.md`，统一记录当前栈、发布边界、上游差异和验证层级。
- **Legacy-Art-Mods-Compat plus 常驻集成**：社区二改 `1.0.3-plusV1.1`（作者：鎖鏈蝴蝶＠百度貼吧，
  上游 mirrormirroronwall README 允许二改二传）从旁载 A/B 候选升为常驻内置。绑定
  `cheat_extended_maplebirch` feature（必选位 32768，存在于全部四码），不占独立 bit，四码不变。
  plus 通过 additive hook（`window.modImgLoaderHooker.addSideHooker`）注入，不 patch `lyra/` 核心。
  已上传 `XFoxLG/DOL-X` Release `legacy-art-compat-plus-v1.1`，SHA-256
  `df1debd4425467c60553a15e090a870b6924c2102614ccab4ff716776d17a727`。
- **上游友好策略文档**：新建 `UPSTREAM_FRIENDLY_STRATEGY.md` 和 `UPSTREAM_DIFF_SUMMARY.md`，
  修复 `docs/INDEX.md` 和 `MOD_MATRIX_RATIONALE.md` 中的悬空引用。

### Changed

- **迁移到 maplebirch 4.x 当代生态**：框架从重建的 `3.2.5` 实验方案改为作者官方 `4.1.13`；
  Cheat Extended 使用作者官方 `1.20(dev260719)` Pre-release。游戏本体版本仍是 `0.5.10.12`，
  不能把框架版本与游戏版本混淆。
- **官方源优先**：maplebirch、Cheat Extended、LongerCombat、YanlingCheatCollection 的日常下载
  与更新检查都改回作者官方仓库。已经存在的 `XFoxLG/DOL-X` 镜像只保留为人工灾备，不做静默
  自动 fallback，防止上游删包、换包或缓存漂移被掩盖。
- **运行时验证升级**：用户真机日志确认 4.x 基础栈为 `0 error / 0 warning / 340 info`；
  Cheat Extended 界面可打开，抽样的一两个功能正常。LongerCombat 与 YanlingCheatCollection
  均已挂载，但其全部功能仍未逐项遍历。
- **四变体本地 ZIP 候选**：base/AU-F/AU-M/AU-A 构建 `4/4` 成功。静态 smoke 为 base
  `36/36`、三个 AU 版各 `38/38` 个有效内嵌 ZIP；base 无 AU payload，AU 三版各只含正确体型
  model 与 AU Face `1.1.0`。该记录证明本地构建能力，不构成公共转载授权。
- **明确 NPC 动态模型裸装边界**：maplebirch `PC模型模式` 需要独立 NPC wardrobe 数据；当前
  38 个 payload 没有任何 mod 注册 `npc.Sidebar.clothes`，框架默认衣柜只有 `naked`，因此
  具名剧情 NPC 在动态模式下不穿衣服是数据回落，不是图片路径错误。当前建议关闭动态模式，改用
  Mae's Picvary 静态侧边栏图；完整修复需制作独立 wardrobe mod，尚未实现。

### Removed

- **退役 maplebirchEx v1.2.4**：静态依赖虽允许 maplebirch 3.2.5，真机却出现
  `dread`、`sanity`、`dreadmax` 未初始化错误；不再注入，只保留旧镜像作回滚档案。
- **退役 `maplebirch-v3-layer-compat` 注入**：4.x 已原生包含相关图片命名处理，构建不再注入
  本项目的 v3 backport；源码保留用于 0713 稳定栈历史和回滚。

### Fixed

- **纠正“v3.2.5 是唯一解”**：该说法只成立于静态版本范围，已被旧扩展包的真机初始化失败推翻。
- **纠正 3.2.5 更新时间解释**：游戏中显示的 2026.07.27 来自 ZIP 重建时间戳，不是作者发布时间，
  不能据此判断 3.2.5 比 4.x 更新。
- **明确头部遮罩功能归属**：当前“头部遮罩相容模式”由 Cheat Extended v1.20 的
  `scripts/CE_HeadMaskCompat.js` 提供，与 `Legacy-Art-Mods-Compat.zip` 无关。
- **纠正 AU Face 版本身份记录**：官方同一个资产有三层版本号，Release 正文 `1.0.4`、外层
  `boot.json` `1.1.0`、解密后内层 `AU面部扩展 1.2.8`。外层包在 earlyload 解密 `.crypt` 并
  lazy-register 内层，因此 ModLoader 会同时列出 `1.1.0` 与 `[SideLoadLazy] 1.2.8`。这是加密 mod
  的正常内外差异，3.x 时期测试已记录；此前把 `v1.2.8` 写成“无官方证据”属于误判，已改回。
- **纠正改脸报错归属**：`img/face/kiss改脸/...` 的缺图报错来自 AU 美化本体自带的改脸目录，
  与 AU 面部扩展无关。0713 稳定版 `au_face` 为 `enabled = false` 时同样存在该红框，可直接排除
  AU Face 作为起因。AU 面部扩展是另一个独立 mod，本轮才首次进入本地候选，其自身功能尚未验收。
- **修复 Quick Check 的 GitHub URL 误报**：原有 Python `urllib` 在连续处理 GitHub Release
  重定向时会随机 `RemoteDisconnected`，导致有效官方链接被判为不可达。改用项目已有的
  `requests` 客户端并显式跟随重定向，不添加重试或镜像 fallback；复验 12/12 个启用直链通过。
- **定位 AU Face 图片命名漂移**：运行时请求的是旧式 `img/face/default/blushN.png`、
  `img/face/default/default/blushN.png`、`img/face/default/tearN.png`，当前包内 canonical
  资源是新式 `blush-N.png` 与 `tears-N.png`。这不是 AU model `kiss改脸` 的已知缺图，也不是
  ModLoader error；它是 AU Face 旧路径合同与 DoL 0.5.10.12 新资源命名之间的不匹配。
  官方 `Legacy-Art-Mods-Compat` 1.0.3 不包含这些 AU Face 通配符规则；社区二改
  `1.0.3-plusV1.1` 精确包含，并已作为 4.x 主线的常驻命名兼容层接入。

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
