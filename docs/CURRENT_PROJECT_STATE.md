# DOL-X 当前项目状态

**核验日期**：2026-08-12

**事实基线**：`vega` 的 4.x 公开主线 + `vega-archive-0713` 历史稳定归档

本文是 DOL-X 当前状态的唯一总入口。带日期的会话记录、贴吧/Discord 抓取和
`MOD_MATRIX_RATIONALE.md` 中的旧决策只保留历史价值；与本文冲突时，以配置、锁文件、GitHub 实况和
本文列出的验证结果为准。

## 1. 项目与分支

- DOL-X 是 `XFoxLG/DOL-X` 自用整合包，不是 DoL、汉化组或 DoL-Lyra 官方发布渠道。
- 直接构建上游是 `DoL-Lyra/Lyra`，上游默认分支为 `vega`；同步方向是
  `DoL-Lyra/Lyra -> DOL-X`。
- 0713 稳定基线保存在 `vega-archive-0713`，归档分支已在 GitHub 核验存在。
- `vega` 从该干净基线重建为 4.x 公开主线，只包含公共配置、代码、测试和文档。
  当前稳定版本为 `v0.5.10.12-1.0.8a-0808`，已于 2026-08-08 发布：tag 构建
  [`31250980645`](https://github.com/XFoxLG/DOL-X/actions/runs/31250980645) 的 build 与 release
  两个 job 均 success，8 件产物全部通过审计并上传到 Release，标记为 latest。0804 是上一版，
  0802 是首个正式 4.x 版本，0713 是历史 3.x 回滚版。

## 2. 4.x 公开主线栈

当前 `vega` 使用 DoL `0.5.10.12` / 汉化 `1.0.8a`，框架与功能 mod 为：

- maplebirch Framework `4.1.14`（作者官方 Release；已于 2026-08-10 升级并在 MuMu 12 通过
  AU-F 冒烟，状态 `runtime-smoke-passed`，见 `config/mods.lock.json` 与 CHANGELOG Unreleased）。
  未正式发版（`v4.1.14` 仍是 Unreleased），真机遍历尚未全量完成。
- Cheat Extended `1.20(dev2601001)`（作者官方 Release `V1.20Beta`，2026-10-01 由原
  Pre-release 通道转入正式 release；已加入 fail-closed digest 锁）。
- LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`（作者官方独立继任包）。
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`（社区二改，原作者 README 明确允许二改二传）。
- 旧 maplebirchEx `1.2.4` 与 `maplebirch-v3-layer-compat` 只保留作 3.x 回滚资料，不进入 4.x 产物。

用户真机日志证明 4.x 基础栈达到 `0 error / 0 warning`，Cheat Extended UI 可打开且抽样
功能可用。LongerCombat 与 Yanling 已挂载，但没有逐功能遍历，因此状态是“运行时挂载通过”，不是
“全功能通过”。

### 框架版本决策：钉死 v4.1.14，不追 4.2+ / 5.x（2026-09-28）

**2026-10-01 追加定案：DOL-X 只跟随 DoL-Lyra/Lyra，不自行追框架大版本。**

Lyra `vega` 停在 `e61352e`（2026-05-18），DOL-X 领先 230、落后 0，当前没有可跟的上游提交。
因此 maplebirch 5.x 不迁移——判定依据是 Lyra 有没有新动作，不是框架作者发了多少版。框架升级只在
Lyra 自己升级游戏本体或汉化、从而必须重新对齐时才处理。这条原则写进了
[UPSTREAM_FRIENDLY_STRATEGY.md](UPSTREAM_FRIENDLY_STRATEGY.md) 第 1 节「被动跟随原则」。

同时，2026-09-30 的真机 A/B 给出了 5.x 若将来必须迁移时的硬约束：桌宠 remount 补丁仍然必需，
needle 要迁到 `e.host.sugarcube.require().Macro` 形态，且**不能**改用直接 `pet.sync()`——
直接同步渲染的是裸模（16316 px），只有宏路径才是带服装的 17587 px。详见
[docs/SESSION_STATUS_2026-09-30.md](docs/SESSION_STATUS_2026-09-30.md)。

`vega-0511-prep` 这轮实验把框架临时升到 4.2.9 以配对 0.5.11.9 本体，离线浏览器冒烟
（`tools/browser_smoke_test.py --profile ucb-cheat-extended-maplebirch`，同一份 0915 AU-F
产物只替换 maplebirch 载荷）实测出三条真回归，换回 4.1.14 后全部归零：

| 信号 | v4.2.9 | v4.1.14 |
|---|---|---|
| `TypeError: faceStyleSrcFn is not a function` | 3 | 0 |
| `whenSC2PassageEnd` 递归栈溢出 | 2 | 0 |
| `ReferenceError: UIBar is not defined` | 24 | 0 |
| high 级别发现总数 | 26 | 18–19 |

根因：4.2.0 删除了 `FaceStyleOptions` / `FaceStyleNameFn` / `FaceStyleName` / `faceStyleSrcFn`
四个公开导出，4.2.1 恢复了 faceStyle 渲染但没有恢复该导出；AU Face 的调用方打包在运行时解密的
`【AUsDoL】facial expansion.zip.crypt` 里，**静态审计看不到调用点**，所以三个 AU 审计全 PASS
仍然漏检。4.2.9 另外引入了一个自递归的 `EventEmitter.error(e){return this.error(e)}`，
4.1.14 与 5.0.4 都没有。

被删除的版本已经全部找回并逐版核验（GitHub Actions artifacts 仍保留 31 件）：
4.1.2、4.2.0–4.2.8、4.3.1/4.3.3/4.3.4/4.3.5、4.4.0/4.4.1、5.0.0–5.0.4。
结论是**没有一个比 4.1.14 更适合**：4.2.0–4.3.4 全部缺 `faceStyleSrcFn`；
4.3.5/4.4.0 要求本体 ≥0.5.12.11、4.4.1 要求 ≥0.5.12.13，而汉化仓库没有 0.5.12.x 发行；
5.x 重构移除了 `ModuleSystem` / `LanguageManager`，LongerCombat / Yanling / DOLI 的
`addonPlugin` 声明都不覆盖 5.x。

跨本体可行性已实测：0.5.10.12 与 0.5.11.9 的游戏侧宿主锚点计数逐一相同
（`updatesidebarimg`、`Renderer`、`CanvasModels`、`npcPregnancyCycle`、`recordSperm`、
`pregnancyDaysEta`、`getChildDays`、`V.facestyle`、`V.facevariant`），4.1.14 的 boot.json
声明 `GameVersion >=0.5.10.12`，0.5.11.9 满足该下限，因此
**0.5.11.9 本体 + 4.1.14 框架可以直接使用上游现有的 0.5.10.12 命名资产**，
不需要自建框架补丁。

灾备镜像已建立：`XFoxLG/DOL-X` release tag `maplebirch-framework-mirror-v4.1.14`，
资产 `maplebirch-0.5.10.12-v4.1.14.mod.zip`（186903 B，
sha256 `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4`，与官方逐字节相同；
MIT 许可允许再分发）。默认仍走官方源，镜像只在官方资产消失或被换包时人工启用。

`lyra/warmup.py` 的 fail-closed digest 名单已把 `maplebirch` 一并纳入
（原先只覆盖 `au_f`/`au_m`/`au_a`/`au_face`），堵住"陈旧缓存静默产出未测框架组合"的缺口。

### 上游版本核对（2026-08-12）

五个 `track_upstream=true` 的上游在 2026-08-12 用已登录 GitHub API 逐一复核（tag + asset
digest），与 `config/mods.lock.json` 全部逐字节一致，无更新：maplebirch `4.1.14`、
Cheat Extended `1.20(dev260719)`、LongerCombat `1.0.1`、YanlingCheatCollection `1.0.1`、
DOLI Release `v0.2.3`。`maplebirch` 已于 2026-08-02 发布 `4.1.14` 并被本工作区升级（见上），
其余四个无变化。

### 上游复核（2026-10-02）：两个仓库被删，CE 通道改名

本轮复核推翻了 2026-08-12 的\"无变化\"结论，三项上游事实已变：

| 上游 | 2026-10-02 状态 | 影响 |
|---|---|---|
| `MaplebirchLeaf/LongerCombat` | **仓库已删除**（API 与网页均 404） | `longer_combat` 下载与周检失效 |
| `MaplebirchLeaf/YanlingCheatCollection` | **仓库已删除**（API 与网页均 404） | `yanling_cheat` 下载与周检失效 |
| `chris81605/..._Cheat_Extended` | 可变 `Pre-release` tag 已删除，改为正式 release `V1.20Beta` | 旧 `download_url` 返回 404，已重指 |

两个被删的包（LongerCombat 与言灵作弊集）已被作者并入
[`MaplebirchLeaf/Deadwood-Reblooms`](https://github.com/MaplebirchLeaf/Deadwood-Reblooms)
（枯木逢春）作为框架模块，模块名为 `LongerCombat` 与 `IncantationCheatCollection`。该仓库已于
2026-09-30 发布正式版 `v1.1.2`，同时提供 DoL `0.5.11.9` 与 `0.5.12.13` 两套 `.modpack`
资产，但包内要求 `maplebirch >= 5.1.3`，与当前钉死的 `4.1.14` 冲突。因此本轮**不接入**枯木逢春，
仅记录为后续迁移候选；本地 `workspace/temp` 中 v1.0.1 的旧缓存仍可支撑构建，但上游已无法再取。
枯木逢春的 `.modpack` 资产带 `JeremieModLoader` 文件头，不是普通 zip，接入前需要新增格式支持。

### 枯木逢春深度评估（2026-10-03）：不接入

对上述候选做了一轮完整实测（Release API 实况 + 两个 `.modpack` 逐字节下载 + 文件头解析 +
加载器解密 + 内层 zip 解包），结论是**不接入**，三条理由：

1. **上游已放弃 0.5.11.9 线**。v1.1.2 是最后一个带 0.5.11.9 资产的版本；v1.2.0 起只发 0.5.12.13，
   且 `.github/workflows/release.yml` 硬校验 `GameVersion == ">=0.5.12.13"`，不满足即拒绝发布。
   配套 maplebirch 的 0.5.11.9 资产也停在 v5.1.3（5.2.x 只出 0.5.12.13）。
2. **硬阻塞在框架版本**。0.5.11.9 线的最后一个版本 v1.1.2 也要求 `maplebirch >= 5.1.3`，
   与 DOL-X 钉死的 `4.1.14`（沙盒 4.2.9）不兼容。ModLoader 在加载前校验 `dependenceInfo`，
   不满足会被直接拒绝加载。接入前提是一次完整 5.x 迁移，而不是加一个 mod。
3. **现有功能面已保住**。LongerCombat / Yanling v1.0.1 已镜像到自建不可变 Release 并纳入
   fail-closed digest 锁，不再依赖已删除的上游仓库。

`.modpack` 格式与加密链路已完整破解（`JeremieModLoader` 头 + PBKDF2 210000 次 + AES-GCM，
口令写死在包内的 `maplebirch-auth-loader.js`，解密后是标准 ModLoader zip），因此"加密导致无法
静态审计"不成立——本轮已解包 836 个成员逐一核对。对 DOL-X 现有补丁面的冲突扫描结果：
`updatesidebarimg`、`pet.sync`、`modifyFaceStyle`、`faceVariantOptions`、`DOLI`、`More_Love`
全部 **0 命中**，即枯木逢春与桌宠 remount 补丁、AU face variant 补丁没有直接竞争面。

完整报告见 [docs/research/2026-10-03-deadwood-reblooms-assessment.md](research/2026-10-03-deadwood-reblooms-assessment.md)。

### 三个 mod 的镜像灾备（2026-10-03）

上面两个被删仓库，加上持续原位换包的 Cheat Extended，三者都已不再是可信的构建输入。DOL-X 把
经过核对的构建上传为自建不可变 Release，`download_url` 全部改指镜像，digest 纳入
`LOCKED_AU_PAYLOAD_CACHE_NAMES` 的 fail-closed 校验：

| mod | 原上游 | 现状 | 自建镜像 tag | sha256 |
|---|---|---|---|---|
| `longer_combat` | `MaplebirchLeaf/LongerCombat` | 仓库已删除（404） | `longer-combat-mirror-v1.0.1` | `be1421c8…` |
| `yanling_cheat` | `MaplebirchLeaf/YanlingCheatCollection` | 仓库已删除（404） | `yanling-cheat-mirror-v1.0.1` | `50e2341e…` |
| `cheat_extended` | `chris81605/Degrees-of-Lewdity_Cheat_Extended` | 仍在，但 `V1.20Beta` 通道已原位换包 5 次 | `cheat-extended-mirror-v1.20` | `9d318e81…` |

LongerCombat 与 Yanling 的上游仓库已被作者删除，功能并入枯木逢春，官方资产不复存在，因此
`track_upstream=false`（已无可追对象），`github_repo` 保留上游值仅作来源标注。

Cheat Extended 的 `V1.20Beta` 资产在 2026-10-02T18:46Z 被第 5 次原位替换：`boot.json` 版本号从
`1.20(dev2601001)` 变为纯 `1.20`，新增 `scripts/CE_customerHairColor.js`（发色自定义：头发／
眉毛／私处毛可分别染色），并改动 `changeLog.md`、`readme.md`、`css/CE_CSS.css`、
`CE_customerEyesColor.js`、`CE_customerSkinColor.js`、`CE_sideBarIcon.js` 共 7 个成员；
`dependenceInfo` 与 `addonPlugin` 条目数不变，`GameVersion` 门槛仍为 `>=0.5.11.9`，
`CE_environmentGuard.js` 逐字节不变，仍只把匹配 `/\bDoLP\b/i` 的版本判为 DolPlus，
DOL-X 的 `0.5.11.9` 不会被自动禁用。CE 的 `track_upstream` 保持 true，只为让周检继续发现新版本。

**周检语义**：镜像化之后，周检对 `cheat_extended` 会持续报 `asset digest changed`（medium）。
这是"上游又换包了"的预警，不是构建失败信号；构建走镜像，不再受上游漂移影响。

**验证**：291 passed；`quick_check` 13/13 恢复全绿（此前因两个仓库删除掉到 11/13）；三个镜像
逐一实测下载且 sha256 与 `config/mods.lock.json` 逐字节一致；`warmup` 实测从镜像下载成功；
`build zip` 2/2 成功；两个 1003 产物内嵌的 CE 载荷 sha256 实测等于 `9d318e81…`；
`au_artifact_check` 对两个产物 `success=true, errors=[]`。**边界**：这两个新 CE 版本尚未真机复测，
以上一个通过 B2 的 `dev260928` 结果不追溯套用。

`4.1.14` 不只包含 0.5.11.x 怪兽服遮罩路径兼容，还恢复 NPC 怀孕扩展、每日周期、受孕和
分娩流程，行为面大于本轮 More Love 修复。它在本工作区已通过 `runtime-smoke-passed`
（MuMu 12 实测冷启动、八人脸型、桌宠；详见 `config/mods.lock.json`），但尚未作为正式版本
发布、全功能遍历也未完成。升级不能等同于发版。

More Love Interests Mod 已升级 `v0.1.6.0` → `v0.1.7.0`，详见下一节。

AU 四个资产（三个 model + AU Face）与 Cheat Extended 的官方 asset digest 逐一比对
`config/mods.lock.json`，全部一致，无同 tag 原位换包。

### More Love 版本错配的发现与修复（2026-08-02）

**这是修 bug，不是可选升级。此前把它记录为「刻意不升的保守选择」是错误判断，已撤回。**

作者 README 提供游戏版本与 mod 版本的对照表：`v0.5.10.x` 的游戏必须用 `v0.1.7.0`，
`v0.1.6.0` 对应的是 `v0.5.7.x`。本项目游戏本体是 `0.5.10.12`，此前钉 `v0.1.6.0`
属于版本错配，不是稳妥。

上游 issue #1「关于 v0.5.10.12 后，查看食物偏好爆红的问题」记录了该错配的实际后果，
作者当天回复已发布 0.5.10 适配版，即 `v0.1.7.0`。根因是游戏本体重命名，五处均已在
`v0.1.7.0` 包内逐条核对落实：

| 游戏本体改动 | v0.1.6.0 | v0.1.7.0 |
|---|---|---|
| 食材集合重命名 | `setup.plants` | `setup.foodstuff` |
| 配方结构下移 | `_foodInfo.ingredients` | `_foodInfo.recipe.ingredients` |
| 图标宏替换 | `<<tendingicon>>`（传图标路径） | `<<foodstufficon>>`（直接收 key） |
| 状态变量重命名 | `$plants` | `$foodstuff` |
| 舒芙蕾键名去重音 | `soufflé` | `souffle` |

最后一项只影响 Avery，是 issue 反馈者在修好前四项后才发现的独立问题。

上述五项已直接对着随汉化 `v0.5.10.12-chs-1.0.8a` 发布的游戏本体 HTML
（`DoL-ModLoader-0.5.10.12-v2.101.1.zip` 内 `Degrees of Lewdity.html`，6266 万字符）
核实，不只采信作者与 issue 反馈者的说法：

- `setup.foodstuff` 出现 237 次，`setup.plants` **0 次**
- `foodstufficon` 出现 167 次，`tendingicon` **0 次**
- `recipe: {` 出现 81 次，确认配方对象结构存在

舒芙蕾一项需要精确表述，不能简单说成「旧写法已消失」：带重音的 `soufflé` 在本体里
仍有 11 处，但**全部是显示文本或迁移逻辑，不是键**。数据定义为
`souffle: { index: 95, name: "soufflé", singular: "soufflé", plural: "soufflés" }`
——键不带重音，重音只留在给玩家看的名称上。本体自身还带一段存档迁移
`<<if $foodstuff.soufflé>><<updateFoodstuffKey "soufflé" "souffle">>`，主动把旧存档的
带重音键改写为不带重音。Avery 的喜爱食物也以 `saveFavoriteFood "Avery" "souffle"`
注册。因此 v0.1.6.0 用 `"soufflé"` 作键去查必然查不到，这正是 Avery 单独报错的机制。

改动面（逐文件 diff）：仅 `boot.json`、`game/foodPreference.js`、
`game/more_love_interest_food_preference.twee`、`game/more_love_interest_main.twee`
四个文件不同，无增删文件。`main.twee` 另有一处行为改动：`$auriga_artefact` 缺失或
Avery 已 dismissed 时会把 Avery 从 `$loveInterestList` 移除，属上游有意的状态清理，
已把 Avery 设为恋人的旧存档值得留意。

**风险复核推翻了先前假设**：`boot.json` 的 5 条 addonPlugin 替换规则（3 条 TweeReplacer
命中 `Widgets Attitudes` / `Widgets`，2 条 ReplacePatcher 命中 `time.js`）在两个版本
之间逐条指纹比对**完全一致**，因此升级不改变本 mod 对游戏本体的 patch 面。先前
「恋人系统改动会碰这些规则」的判断没有证据支持。

`GameVersion` 门槛由 `>=0.5.5.0` 收紧到 `>=0.5.10.0`，当前 `0.5.10.12` 满足。

2026-08-04 真机复验确认：正式游戏的“态度”页出现“查看NPC喜爱的食物”入口，链接可进入
食物偏好页，无恋爱兴趣 NPC 时空列表正常显示、没有红框。该存档没有恋爱兴趣 NPC，因此
`setup.foodstuff`、`recipe.ingredients`、`foodstufficon` 与 Avery/舒芙蕾的数据渲染路径尚未
实际执行；状态是“空态真机通过”，不是食物偏好全功能通过，也不把未覆盖部分写成发版阻塞。

回滚：`v0.1.6.0` 资产已归档到仓库外 `mod-archive/more-love-interests/v0.1.6.0`，
sha256 `7c63f642…`，归档时已与 GitHub 报告的 digest 核对一致。

### Release tag 与包内声明版本不一致的两个 mod

以下差异属上游作者未同步 manifest，不是构建取错版本：

| Mod | Release tag | 包内 `boot.json` | 运行时显示 |
|-----|------------|-----------------|-----------|
| DOLI | `v0.2.3` | `0.2.2` | `0.2.2` |
| NPC Avatars | `1.4` | `1.4.1` | `1.4.1` |

ModLoader 读取包内 `boot.json`，所以 Mod 管理器里看到的版本以该列为准。

DOLI 的 `dependenceInfo` 只要求 ModLoader `^2.0.0`；`addonPlugin` 虽声明 maplebirch
`^3.1.0`，用户真机已确认 DOLI 在当前 4.1.13 栈中可运行，因此不能仅凭声明范围推断框架入口
不注册。DOLI 自带的 `patches/overlay-replace.json` 与 DOL-X 的构建期图标补丁是两件事：后者
只修复右下角智能助手悬浮按钮的旧图片路径，不负责补配置入口。

## 3. 构建矩阵与公开分发边界

`config/combinations.toml` 仍保留四个本地构建码：

- base `15704320`
- AU-F `15705344`
- AU-M `15706368`
- AU-A `15708416`

公开 CI 分支推送构建 base + AU-F，tag 发版构建全部四码。手动触发
（`workflow_dispatch`）新增 `build_tier` 输入，选 `release` 可在不打 tag 的前提下
干跑全四码，release job 仍受 `github.ref_type == 'tag'` 保护、不会误发 Release。

Build workflow 现在在构建前执行完整 pytest，在构建后、上传 artifact 前执行
`tools/au_artifact_check.py`。AU 审计按三种官方 model 的共同真实契约检查嵌套
`blush-1.png` 至 `blush-5.png`，并排除独立的 `blusher.png`；旧检查器曾只接受外层
`blush1.png`、错误要求 6 个编号层，导致真实 AU-F 产物被误判。修正后的工具已对
base/AU-F 当前候选及上一轮 base/AU-F/AU-M/AU-A 全矩阵 ZIP 复验通过。

0802 与 0804 的 GitHub Release 原本由上传 action 自动创建但正文为空，已于 2026-08-05 补齐
面向玩家的版本说明。后续 tag workflow 从 `docs/release-notes/<tag>.md` 读取正文；对应文件缺失
时 release job fail-closed，不再允许发布空白说明。

AU-M 与 AU-A 在此之前从未经 CI 构建过（分支档只含 base + AU-F）。首次全四码干验证由
run [`30709200905`](https://github.com/XFoxLG/DOL-X/actions/runs/30709200905) 完成，
8 个产物（四体型 × ZIP/APK）全部生成，证明这两个组合的资源链可用。

真机测试只覆盖 AU-F。base / AU-M / AU-A 使用同一套 mod、仅体型资源不同，构建成功但
未逐个上机验证。

**这是既定决策，不是待办**（2026-08-02 用户确认）：不为 AU-M / AU-A 安排真机验收。
维护者只使用 AU-F，另外两个体型作为构建产物提供，验证层级止于「CI 构建成功 +
静态 payload 检查」。后续会话不应再把它们列为待验证项或阻塞发版的理由。

## 4. AU Face 与 plus

AU Face 官方资产存在三层版本身份：Release 正文 `1.0.4`、外层 `boot.json` `1.1.0`、解密后内层
`1.2.8`。AU-F 真机已验证设置 UI 和交互可用，但内层会请求旧式 `blushN` / `tearN` 图片名。

社区 plus 增加对应 `blush-N` / `tears-N` 映射。用户旁加载 A/B 后，旧路径红框消失、独立嘴部仪态
有效；面纹和流泪视觉仍未完整验收。plus 通过 additive ImageLoaderHook side hook 工作，不修改
`lyra/` 核心。DOL-X Release `legacy-art-compat-plus-v1.1` 的资产 SHA-256 为：

`df1debd4425467c60553a15e090a870b6924c2102614ccab4ff716776d17a727`

## 5. 已知产品边界

- maplebirch “PC 模型模式”需要 NPC wardrobe 数据。当前没有 mod 注册衣柜，动态 NPC 回落
  `naked` 是数据缺失后的设计行为；使用 Mae's Picvary 静态侧边栏图即可规避。
- maplebirch 云存档没有公共服务地址。官方只提供 Go+SQLite 与 Cloudflare Worker+R2+D1 自建源码；
  Go 后端还缺客户端会调用的 `/save-code` 路由。
- AU model 的 `kiss改脸/.../eyes.png` 缺图与 AU Face 的 `blushN`/`tearN` 是两类问题，不应混记。
- AU Face 面纹/流泪剩余视觉问题位于加密内层运行时边界，DOL-X 没有白盒修复手段，不阻塞 base 主线。
  **（2026-10-04 更新：加密内层已被完整解开，见下方新增小节。结论从"看不见"改为"看见了但接口对不上"。）**

### AU Face 加密内层解密与兼容性判定（2026-10-04）

此前记录写「AU Face 调用方在运行时解密，静态审计抓不到」。本轮已完整解开该加密层，
前半句作废：**它抓得到**。

AU 用的与枯木逢春**不是同一套**：外层是普通 zip，内层用 **Argon2id + ChaCha20-Poly1305**
（libsodium），`.salt`(16B) / `.nonce`(8B) / `.crypt` 是独立成员。
上游原本会弹窗向用户索取口令，但本分发包里的 `SimpleCryptWrapper.js` **被二次改写为硬编码口令**，
因此密钥随包分发、可本地复现。实测解出内层标准 zip，8 个成员（`js/faceSelector.js`、
`addon/svr.js` 等），三层版本身份（Release `1.0.4` / 外层 `1.1.0` / 内层 `1.2.8`）全部可复现。

**但"能解"不等于"能修"。** 解出后确认 `faceStyleSrcFn` 是**双向不匹配**，不是单向缺失：

- 4.1.14 的契约是单参数（字符串或函数），`facestyle`/`facevariant` 取自 options 对象；
- AU 1.2.8 有四种调用形态，其中 `faceStyleSrcFn('eyes', { variant: true })` 的第二参数会被
  整体忽略；`faceStyleSrcFn(o => \`blush${o.blush}\`)` 生成的是**缺连字符**的 `blush1`
  （而游戏资产是 `blush-1`）——补默认值也修不好；
- maplebirch **5.1.3 中 `faceStyleSrcFn` 计数为 0**，且无改名后的等价导出，
  该层已被 `faceStyleMap` 重写。删除发生在 4.2.0，5.x 未恢复；AU 1.2.8（2025-10-13）从未适配。

因此 shim 不是可行路线。可选方向只有三条：等 AU 作者适配、停在 4.1.14、或放弃 AU 的基础脸层路径
仅保留不依赖该 API 的图片资源。

顺带得到一个可落地的构建期防线：现在能在构建期静态统计两侧计数，
**框架载荷 `faceStyleSrcFn` 为 0 而 AU 载荷引用数 > 0 时直接 fail-fast**，
不必等运行时红框才发现。

完整报告见 [docs/research/2026-10-04-au-face-decryption-and-shim-feasibility.md](research/2026-10-04-au-face-decryption-and-shim-feasibility.md)。

## 6. 来源与验证

主要原始来源：

- DOL-X：https://github.com/XFoxLG/DOL-X
- DoL-Lyra：https://github.com/DoL-Lyra/Lyra
- 汉化：https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization
- maplebirch：https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework
- Cheat Extended：https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended
- LongerCombat：https://github.com/MaplebirchLeaf/LongerCombat
- Yanling：https://github.com/MaplebirchLeaf/YanlingCheatCollection
- AU：https://github.com/AOKIUTAGE/UTAGEsDOL3.0
- Legacy compat：https://github.com/mirrormirroronwall/Legacy-Art-Mods-Compat

本轮已核验：GitHub Release/branch 实况、官方资产 digest、主动跟踪 mod 的上游版本实况、
包内 `boot.json` 声明版本、plus ZIP manifest、配置加载与 Python 编译。本机 `python -m pytest -q`
为 274 passed，其中 **259 项属于公开仓库**，另 15 项来自 `.gitignore:155` 排除的私有 MuMu 诊断
工具 `tests/test_mumu_apk_smoke.py`。远端 CI 只能看到公开的 259 项，因此引用测试数时必须说明是
哪一个口径，本机总数不能冒充远端 CI 覆盖。

0808 候选提交 `cf60d15` 的分支 run [`31239491888`](https://github.com/XFoxLG/DOL-X/actions/runs/31239491888)
已实际执行并通过测试、base + AU-F 构建、ZIP/APK 产物审计和双格式上传；release job 按分支语义
skipped。同一提交的全四码 `release-tier` dry run
[`31239641405`](https://github.com/XFoxLG/DOL-X/actions/runs/31239641405) 随后 success：四码构建、
ZIP/APK 审计与上传均通过，release job 正确 skipped，未创建 Release。8 件产物全部通过新严格审计
（AU 三码各命中 3 个换脸 + 1 个迁移 + 1 个后汉化 marker 与 5 个互异腮红层，base 干净）。四个 APK
的签名指纹均为正式证书 `b21cd15b9ff02d603a20d94b8403d5d9661946518f88e0551474c93ab829ece6`。
两个 run 的 `conclusion=success` 与 `headSha=cf60d154` 已于 2026-08-08 经 GitHub API 复核。

上一版 0804 的证据（提交 `186fc463` / `713924b4`，run `30907013186` / `30907723945`，当时 193 项
公开测试、More Love `0.1.7.0` 与拖拽防护逐件解码复验、四个 APK `jarsigner -verify` 返回 0）保留在
`CHANGELOG.md` 的 0804 条目中，不再复述于本节。本机始终没有 `apksigner`，因此任何轮次都不把
`jarsigner -verify` 外推为 APK v2/v3 完整验证。

More Love 升级后的补丁复验是对仓库外归档的真实 v0.1.7.0 资产跑构建期改写函数完成的：
`game/More_Love_Interest_Mod_Drag.js` 两版同为 3178 字节、同一 sha256
`cd9c9a48ee2bfa06…`；改写后 `ev.preventDefault(` / `ev.stopPropagation(` /
`ev.dataTransfer.getData` / `ev.dataTransfer.setData` 的直接调用点均为 0，9 个 ZIP
条目全部保留，除被改写的成员外字节一致。

注意区分「字符串出现次数」与「直接调用点」：改写后的文件里仍能搜到
`stopPropagation` 字样，那是注入的辅助函数内部 `var stopPropagation = ev && ev.stopPropagation;`，
即防护本身，不是漏改。判断是否漏改要用 `\bev\.stopPropagation\s*\(` 这类调用点正则。

真机验收只覆盖 AU-F；AU-M / AU-A 仅有构建成功记录，无上机验证，且按既定决策不再补。
More Love `v0.1.7.0` 的入口、页面跳转和空列表已真机通过；有恋爱兴趣 NPC 时的食物数据渲染、
Avery/舒芙蕾以及既有存档的恋人列表清理行为仍未覆盖。
