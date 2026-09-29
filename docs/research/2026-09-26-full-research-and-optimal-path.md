# DOL-X 全面调研与最优路线(2026-09-26)

本报告是本轮"完全理解项目 + 全量信息搜集 + 找最优解"的综合交付。
核验日期:2026-09-26。所有上游结论均取自当日 GitHub Release API 实况,不是转述旧记录。
本报告只读调研,未改任何配置、未构建、未提交、未推送。

记录分层:第 1-2 节是稳定项目事实;第 3 节是当日上游实况(会过期,下次须重查);
第 4 节是工程分析;第 5 节是推荐路线;第 6 节是待用户决策项。

---

## 1. DOL-X 是什么(项目身份,先固定)

- DOL-X 是 XFoxLG 的**自用整合包构建工程**,不是 DoL / 汉化组 / DoL-Lyra 的官方发布渠道。
- 它是一套 Python 3.12 构建系统(`lyra/` + `main.py`),做三件事:
  1. 从**汉化仓库**下载指定 tag 的游戏本体(HTML zip / APK / 图片包 / ModI18N);
  2. 从各 mod 作者仓库下载**钉死版本**的 mod,做构建期文本补丁与资源别名;
  3. 组合成 4 个构建码 × {ZIP, APK} 共 8 件产物,并做 AU 载荷审计与 APK 签名。
- 直接构建上游是 `DoL-Lyra/Lyra`(默认分支 `vega`),同步方向 `DoL-Lyra/Lyra → DOL-X`。
- 历史稳定基线保存在 `vega-archive-0713`。
- 与独立项目 **DoL-XFox**(TypeScript 重写,本仓库之外的独立 checkout（路径略）)
  是两个仓库。任何文件、构建、Git、拆包操作前必须先过 `project_identity_gate`,不得互相套用结论。

## 2. 仓库当前实况(2026-09-26 快照)

### 2.1 Git 与分支

- 当前分支:`vega-0511-prep`(路线 B 沙盒分支,基于 4.x 公开主线重建)。
- HEAD:`415ab78` `fix: 退役 basehead 补丁并重新归类 AU 换脸桌宠根因`。
- `vega` 主线最后提交同为 `415ab78`;`origin/vega` 指向它。
- 远端:`origin` = XFoxLG/DOL-X;`upstream` = DoL-Lyra/Lyra。

### 2.2 未提交改动(重要:沙盒成果尚未落库)

15 个已跟踪文件改动 + 6 个未跟踪:

| 类别 | 文件 |
|---|---|
| 已跟踪 | `config/build.toml`、`config/mods.lock.json`、`lyra/build.py`、`lyra/compatibility.py`、`lyra/downloader.py`、`lyra/warmup.py`、`tools/artifact_inspection.py`、`tools/au_artifact_check.py`、`docs/CURRENT_PROJECT_STATE.md`、`docs/WAF_TROUBLESHOOTING.md`、`.gitignore`、`.vscode/settings.json`、`tests/test_au_face_compat.py`、`tests/test_compatibility_registry.py`、`tests/test_maplebirch_pet_remount_patch.py` |
| 未跟踪 | `build-manifest-0511.json`、`build-manifest-0511-apk.json`、`docs/SESSION_STATUS_2026-09-15.md`、`docs/research/`、`tests/test_boot_json_parsing.py`、`tests/test_chs_asset_selection.py` |

**这批改动是路线 B 的沙盒升级**(maplebirch 4.1.14→4.2.9、汉化 0.5.10.12→0.5.11.9、
CE dev260719→dev260903、download/缓存闸门加固),从未提交、从未推送。

### 2.3 沙盒构建成果(本机已验证,真机未验收)

- 产出 `output/DoL-0.5.11.9-XFox-1.0.0a-{base,au-f}-0915.{zip,apk}`(4 件,见 `build-manifest-0511*.json`)。
- ZIP:`base` 64,280,464 B / `au-f` 114,798,537 B;APK:`base` 79,661,623 B / `au-f` 130,182,245 B。
- `tools/au_artifact_check.py` 两产物 PASS、`errors` 为空;APK zipalign 与 v1/v2/v3 签名核验通过。
- 本机 `python -m pytest -q` 曾为 286 passed。
- **B2 真机验收(MuMu 12)尚未进行** —— 这是路线 B 唯一未闭环的验证层级。

### 2.4 公开发布状态

- 公开最新 Release 仍是 `v0.5.10.12-1.0.8a-0808`(2026-08-08,8 件产物,已 latest)。
- 也就是说:**沙盒已跑到 0.5.11.9,公开线仍停在 0.5.10.12。** 两条线的事实不同步。

### 2.5 构建矩阵与 mod 栈

四个构建码(位标志):

| 构建码 | 含义 |
|---|---|
| `15704320` | base(无 AU) |
| `15705344` | AU-F |
| `15706368` | AU-M |
| `15708416` | AU-A |

必选 feature(全部进 4 码):UCB、cheatExtended+maplebirch、CustomHair、Mae's Picvary、
maplebirch_expansion、GuideToMe、NeoUI Patch、NPC 社交栏头像、D.O.L.I、More Love、
Legacy-Art-Mods-Compat plus。AU model + AU Face 只进 AU 三码,不进 base。

公开分支推送构建 base + AU-F;tag 发版构建全部四码;`workflow_dispatch` 的 `release` tier
可干跑全四码而 release job 受 `github.ref_type == 'tag'` 保护。

### 2.6 六个构建期兼容 surface(`lyra/compatibility.py`)

全部 `fail-closed`,版本指纹与 `config/build.toml` 逐字段比对,不一致即拒绝构建:

1. `more_love_drag_event_handlers` → More Love `v0.1.7.0`,补丁 `game/More_Love_Interest_Mod_Drag.js`。
2. `doli_float_icon_path` → DOLI `v0.2.3`,补丁 `dist/DOLI.js` 旧图标路径。
3. `maplebirch_pet_passage_remount` → **maplebirch `maplebirch-release-v4.2.9`**,
   补丁 `dist/inject_early.js` 的 `Character.preInit()`。
4. `au_face_default_aliases` → AU `facemod`,资源别名,不 fail-closed 而是 `create-from-existing-assets`。
5. `au_face_variant_selection` → **maplebirch `maplebirch-release-v4.2.9`**,
   补丁 `dist/inject_early.js` 的 `modifyFaceStyle()` 后处理。
6. `apk_cdp_remote_end_reconnect` → 测试工具 CDP 重连,非产品载荷。

其中 3 和 5 绑在 maplebirch 4.2.9 上 —— **升级框架必须同步改这两条指纹 + 两个 needle**。

### 2.7 构建输入的漂移风险(已定位的缺口)

- `lyra/downloader.py` 的 `download_from_chs_repo()` 在**无 `--tag`** 时请求汉化仓库 `releases/latest`。
  汉化仓库最新是 `v0.5.11.9-chs-1.0.0a`(2026-08-14),所以**分支推送构建会拿到 0.5.11.9 本体**,
  而 tag 发版因传 `--tag` 不受影响。0808 是 tag 构建,所以公开线仍可复现 0.5.10.12;
  但下一次分支 CI 会静默换成 0.5.11.9。
- `lyra/warmup.py` 的 fail-closed **digest 锁只覆盖 `au_f/au_m/au_a/au_face` 四个 AU 载荷**。
  maplebirch、cheat_extended 等**不在 digest 强制名单**内。
  (2026-09-15 已补一个"boot.json 版本 vs release_tag"缓存守卫,但只要任一侧版本无法解析就放行。
  cheat_extended 的 `1.20(dev260903)`、`1.20(dev260923)` 都**无法被该正则解析 → 守卫返回 None → 视为可信**。
  即 cheat_extended 仍是"同 tag 原位换包不会被拦"的状态。)
- 好消息:`downloader.py` 已在本沙盒分支加固 —— 扩展名大小写不敏感、关键资产缺失当场 fail-fast
  并打印实际资产列表,不再拖到 build 阶段以"APK 目录不存在"的次生症状失败。

---

## 3. 上游全景实况(2026-09-26 当日 API 实证)

### 3.1 逐项对照

| 组件 | DOL-X 当前锁定 | 上游当日实况 | 结论 |
|---|---|---|---|
| 汉化/本体 | 0.5.10.12 + chs 1.0.8a(公开线)/ 0.5.11.9 + chs 1.0.0a(沙盒) | 汉化最新仍是 `v0.5.11.9-chs-1.0.0a`(2026-08-14)。**chs 仓库没有 0.5.12.x** | 沙盒所用的 0.5.11.9 就是当前汉化天花板 |
| maplebirch | 4.1.14(公开)/ 4.2.9(沙盒) | **v5.0.4**(2026-09-25);链路 4.2.9(09-07)→4.3.5(09-14)→4.4.1(09-22)→5.0.2/5.0.3/5.0.4(09-24/25)。5.x 同时出 `0.5.11.9` 与 `0.5.12.13` 两个资产 | **框架已连跳两个大版本线**,沙盒刚升到的 4.2.9 已落后 |
| Cheat Extended | 沙盒 `dev260903`(350866 B,`f0bcbdaf…`) | **`Pre-release` 同 tag 资产已再次原位换包** → `dev260923`(598600 B,`2c2f5604…`) | 同 tag 换包第 3 次;构建输入持续漂移 |
| LongerCombat | v1.0.1 | v1.0.1 未变(`be1421c8…`,面向 0.5.10.12) | 不动 |
| YanlingCheatCollection | v1.0.1 | v1.0.1 未变(`50e2341e…`) | 不动 |
| DOLI | v0.2.3 | v0.2.3 未变(`82785c3d…`) | 不动 |
| More Love | v0.1.7.0 | v0.1.7.0 未变(`f90dee45…`) | 不动 |
| AU 三 model | v0.9.3 / v0.4.2 / v0.1.1 | 资产 2025-07-20 后未动,digest 与本仓一致 | 不动;授权仍禁止二传 |
| AU Face | facemod | 资产 2025-10-13 后未动(`8f2c1b66…`) | 不动 |
| CustomHair / Mae's / NeoUI / NPC Avatars / GuideToMe | 固定 tag | 全部未变,digest 与本仓一致 | 不动 |
| Deadwood-Reblooms(枯木逢春) | 未接入 | **仓库存在且活跃**(main,最后推送 2026-09-21;TypeScript+bun;README 声明依赖 `maplebirch >=4.3.6`),但 **0 个 release / 0 个 tag** | 暂不接入,留作后续候选;无 tag 就没有可钉死的下载输入 |
| ~~maplebirchEx~~(SCML-DOL-maplebirchExpansion) | 未接入 | **仓库 404(已删除)** | 确认不存在;这才是"被删除的旧版框架扩展模型" |
| DoL-Lyra/Lyra 构建系统 | - | 最新 release `v0.5.11.9-1.0.0a-0815` | 上游自己也停在 0.5.11.9 |

### 3.2 maplebirch 5.0.4 载荷实读(内存解包,未落盘)

资产 `maplebirch-0.5.11.9-v5.0.4.mod.zip`,213331 B,
sha256 `27d1e35f170b0f92a1064864b7970770c03d21d61ab01bc33797b1a670be37d8`。

- `boot.json` `version` = `5.0.4`;`addonPlugin` 条目 **0**。
- `dependenceInfo` 8 条,最后一条 `GameVersion >=0.5.11.9`(其余为 ModLoader/ModLoaderGui/
  ModSubUiAngularJs/ConflictChecker/BeautySelectorAddon/ReplacePatcher/TweeReplacer)。
  → 与 4.1.14/4.2.9 同为 8 条,**没有新增基础依赖**。
- 对照 4.2.9:文件从 180036 B 涨到 213331 B,`inject_early.js` 从 4.x 的约 47 万字符涨到 570634 字符。

### 3.3 cheat_extended 当前载荷实读(内存解包)

资产 `cheat_extended.mod.zip`,598600 B,
sha256 `2c2f5604db3818f1184fd31714bef4529eabacfa19c340b5e63b0fabdc8e42e6`。

- 包内 `boot.json` `version` = `1.20(dev260923)`(非严格 JSON,含尾随逗号,与 dev260903 同形态)。
- 含 `scriptEarly/CE_environmentGuard.js`(环境/版本检测,错误环境弹窗并禁用)、
  `scriptEarly/framework_detector.js`(maplebirch ≥3.2.5 运行时门)、`scriptEarly/CERegist.js`。
- 成员 111 个(dev260903 时为更少),增长来自新增地图 Gui / 简繁转换字库等。

---

## 4. 工程分析:升级到 5.0.4 会碰到什么(决定性发现)

### 4.1 桌宠 remount 补丁的 needle 在 v5.0.4 上 **0 命中 → 构建会被 fail-closed 拦下**

本仓 `MAPLEBIRCH_PET_REMOUNT_OLD` 的期望文本是 4.2.9 形态:

```
preInit(){let{core:e,pet:t}=this;e.on(":language",...),e.once(":storyready",()=>{this.faceStyleSetupOption();
let n=e.SugarCube.Macro.get("updatesidebarimg");n&&e.tool.macro.define("updatesidebarimg",function(){n.handler.call(this),t.sync()})})
```

v5.0.4 实际形态(实读,偏移 439980):

```
preInit(){let{core:e,pet:t}=this;e.on(":language",()=>this.faceStyleSetupOption(),"face style setup options"),
e.once(":storyready",()=>{this.faceStyleSetupOption();
let n=e.host.sugarcube.require().Macro.get("updatesidebarimg");   <-- 变了
n&&e.tool.macro.define("updatesidebarimg",function(){n.handler.call(this),t.sync()})}),
e.on(":passageend",()=>void t.sync()),this.use("pre",aD,"main"),this.use("aD","main")}
```

差异点:4.x 的 `e.SugarCube.Macro` 在 5.x 被改写成 `e.host.sugarcube.require().Macro`。
针尖文本因此**逐字符不匹配**(实测 `count = 0`),构建期 `patch_needle_not_found` 会拒绝构建。
这正是项目在 2026-09-15 已经踩过一次的同类坑(那时是 4.1.14→4.2.9 的 `:language` 插入),
**教训重复出现:锚点存在性无法证明装配顺序,必须用完整 needle 逐字符匹配**。

### 4.2 但 v5.0.4 有可能自己已经补上了桌宠 remount 义务

v5.0.4 的 `Character.preInit()` 多了一行:

```
e.on(":passageend",()=>void t.sync())
```

这**恰好就是本补丁的目标**(passage 重建 StoryFooter 后重新同步桌宠)。历史记录里这条是 4.2.9 引入的,
当时走的是"直接 `pet.sync()`"路径,本项目在 MuMu 12 实测认为不足(裸模 16316 不透明像素
vs 走 `<<updatesidebarimg>>` 宏的 17588/带服装)。所以:

- 若 5.0.4 的 `:passageend` 路径真能带服装正确刷新 → **本补丁可退役**,少一个维护面。
- 若仍走裸模回退 → 仍需保留本补丁,只是 needle 要迁移到 5.x 文本。
- 这**无法静态判定,只能靠单变量真机 A/B**(沿用 8 月退役 basehead 补丁的同一方法论)。

### 4.3 AU face variant 补丁在 v5.0.4 上 needle **仍然 1 命中**

- `MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD` 在 v5.0.4 的 `inject_early.js` 里 `count = 1` → 插入点还在。
- `updatesidebarimg` 30 处、`modifyFaceStyle` 3 处、`faceVariantOptions` 5 处,宿主接口齐备。
- 该补丁还要读"翻译后的最终 passage"的 3 处切换上下文 + 1 处迁移锚。B0(2026-09-14)已在
  0.5.11.9 汉化 HTML 上确认这三组上下文原文保留、`variablesVersionUpdate` 迁移锚存在,
  并发现 0.5.11.9 新增 `$facevariant is undefined` 初始化守卫(与本补丁不冲突)。
- 结论:**AU face 这条面在 5.0.4 + 0.5.11.9 上静态可通过**,只需更新版本指纹。

### 4.4 兼容登记表与构建闸门的连锁改动点

升级 maplebirch 到 5.0.4 至少要同步改:

1. `config/build.toml`:`maplebirch` 的 `release_tag` / `asset_pattern` / `download_url`。
2. `lyra/compatibility.py`:`maplebirch_pet_passage_remount` 与 `au_face_variant_selection`
   的 `release_tag` / `asset_pattern`(`compatibility_source_errors()` 逐字段比对)。
3. `lyra/build.py`:`MAPLEBIRCH_PET_REMOUNT_OLD/NEW` needle(或退役整条补丁)。
4. `config/mods.lock.json`:maplebirch 新 digest 与 notes。
5. 三个测试文件里的 maplebirch 版本期望串。

### 4.5 cheat_extended 的缓存守卫对它无效

`_pinned_version_from_release_tag("Pre-release")` 解析不出语义版本 → 返回 None;
`_payload_boot_version()` 对 `1.20(dev260923)` 也解析失败 → 返回 None。
两个 None 都走"视为可信"分支,所以**同 tag 原位换包不会被缓存守卫拦下**。
要真正钉住它,要么把 `download_url` 改成自建不可变镜像(项目已有 `cheat-extended-mirror-v*` 的灾备 tag 惯例),
要么把 cheat_extended 加进 digest 强制名单。

### 4.6 周检机制现状(对照)

- `Mod Update Check` 每周日 success,但 success ≠ 无更新。
  最近一次 2026-09-20 run `35488533366` 的报告 `mod-updates.json`:
  `has_updates=true`,maplebirch 4.1.14→4.3.5(high)、cheat_extended 同 tag 换包(medium)。
- Issues 通知是**有意退役**(仓库已关 Issues),结果只落 Summary + artifact(保留 30 天)。
  真问题只有一处:`docs/MOD_UPDATE_MONITORING.md` 仍描述旧的 Issue 创建机制。
- 判断"有没有更新"永远看 artifact 的 JSON 或直接查 API,**不看 workflow conclusion**。

---

## 5. 三条候选路线与最优解

### 5.1 筛选前提(来自既有记忆与事实)

- 用户要"成熟汉化"是硬条件 → 汉化仓库没有 0.5.12.x,0.5.12 线**当前不可选**。
- 0.5.11.9 + chs 1.0.0a 是**当前唯一可选的、比公开线新的承载底座**。
- 框架生态已整体迁到 0.5.11.9/0.5.12.13(maplebirch 5.x 同时出两版资产),4.1.14 是被上游抛弃的旧线。
- 构建输入的漂移(分支取 latest 汉化、CE 同 tag 换包)已经让"守住 0.5.10.12 公开线"变成逆水行舟。

### 5.2 路线对照

| 路线 | 内容 | 优点 | 成本/风险 |
|---|---|---|---|
| **A′ 守住已测栈** | 公开 `vega` 继续 0.5.10.12 + maplebirch 4.1.14;但立刻钉住汉化 tag 与 CE digest,并禁止分支构建静默取 0.5.11.9 | 改动面最小,复用已验产物的心理安全感高 | 与漂移对抗;框架生态持续远离;AU face/新功能全部拿不到;不是"最优",只是"最省事" |
| **B′ 升级到 0.5.11.9 线(推荐)** | 沙盒从 4.2.9 再进到 **maplebirch 5.0.4**,汉化钉 `v0.5.11.9-chs-1.0.0a`,CE 钉具体 digest,重定 needle,真机 B2 | 底座与框架都踩在当前上游;AU face 静态已过;5.0.4 可能让桌宠补丁退役 | 5.x 比 4.2.9 跨度更大;两条 fail-closed 面要重定/退役;必须真机 A/B |
| C′ 跳到 0.5.12.13 | 直接用最新游戏本体 | 版本最新 | **被汉化硬阻塞**:chs 仓库无 0.5.12.x 发行,当前不可执行 |

### 5.3 最优解:走 B′,并把它拆成可验证的顺序

推荐目标栈(具体版本号须在动手当天再查一次上游,本节是 2026-09-26 的实况):

```
游戏本体    0.5.11.9  (汉化 tag v0.5.11.9-chs-1.0.0a)
maplebirch  v5.0.4    (资产 maplebirch-0.5.11.9-v5.0.4.mod.zip)
CE          1.20(dev260923)  (digest 2c2f5604…,或自建不可变镜像)
ModLoader   v2.101.1  (随汉化包发布,无独立升级面)
```

执行顺序(每步都可独立回滚):

1. **重定桌宠 needle 或退役补丁(先决条件)。**
   在 v5.0.4 真实载荷上,用单变量对照构建两个 APK:一个保留桌面 remount 补丁(needle 迁移到 5.x 文本),
   一个不含该补丁(依赖上游的 `:passageend`)。MuMu 12 上对比 passage 切换后桌宠是否带服装、
   是否非空(沿用 16316 vs 17588 像素判据)。决定保留或退役,再改 `compatibility.py` 登记。
2. **重定 AU face variant 的版本指纹。** 插入 needle 已 1 命中(见 4.3);把
   `config/build.toml` 与 `compatibility.py` 的 maplebirch 版本从 4.2.9 改为 5.0.4,
   重新跑 `_validate_au_face_variant_source`(读 0.5.11.9 汉化 HTML)。
3. **钉死 CE 构建输入。** 把 `cheat_extended` 的 `download_url` 指向自建不可变镜像,
   或把它加入 warmup 的 digest 强制名单,消除"同 tag 换包静默通过"。
4. **顺序重跑:** `prepare --tag v0.5.11.9-1.0.0a-0915`(或新的日期 tag)
   → `warmup --codes 15704320,15705344` → `build zip` / `build apk`
   → `tools/au_artifact_check.py` → 签名核验。网络必须先设分域路由(见 5.4)。
5. **B2 真机验收(MuMu 12)。** 重点:桌宠存废、More Love 食物偏好页(有恋爱 NPC 时的数据路径)、
   4.2.x→5.x 的方法重构是否影响 LongerCombat/Yanling 实际功能。
6. **收尾提交。** 通过后才把沙盒改动按文件审阅、只暂存相关改动、提交;再单独决定是否
   把 `vega-0511-prep` 的提升回灌 `vega` 并发新 tag。

### 5.4 必须记住的执行细节

- **网络分域路由**:`HTTP_PROXY` / `HTTPS_PROXY` = `http://127.0.0.1:7890`,
  同时 `NO_PROXY` / `no_proxy` = `api.github.com`(大小写都设)。
  `github.com`(release 下载)走代理、`api.github.com` 必须直连,这是 `tools/quick_check.py`
  从 13/13 全红变全绿的关键。
- **tag 格式**:DOL-X 自己的 tag 是 `v{本体}-{汉化}-{日期}`,如 `v0.5.11.9-1.0.0a-0915`。
  不要传汉化仓库的 `v0.5.11.9-chs-1.0.0a`(会被解析成 `chs_ver=chs`)。
- **pack type 是位置参数**(`build zip` / `build apk`),不是 `--pack-type`。
- **缓存陷阱**:改框架版本后先确认 `workspace/temp/` 里没有上一版载荷;warmup 的版本守卫能兜住
  maplebirch,但兜不住 CE。

---

## 6. 待用户决策(不适合由我单方面拍板)

1. **是否走 B′。** 这是"公开线底座换代"级别的决定,涉及后续发版与旧存档兼容。
2. **桌宠补丁保留还是退役**(依赖 B2 真机 A/B 结果)。
3. **画风是否换出 AU。** 既有记忆明确把这个主观偏好留给你决定;换模型会影响服装生态与美化工作量。
4. **CE 钉法**:自建不可变镜像 vs 扩展 digest 名单,二者都可行,取其一即可。

在上述决策落地前,本报告只做"把事实和最优路径摊开",不替你选定。
