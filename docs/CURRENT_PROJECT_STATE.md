# DOL-X 当前项目状态

**核验日期**：2026-08-05

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
  当前稳定版本为 `v0.5.10.12-1.0.8a-0804`；0802 是首个正式 4.x 版本，0713 是历史 3.x 回滚版。

## 2. 4.x 公开主线栈

当前 `vega` 使用 DoL `0.5.10.12` / 汉化 `1.0.8a`，框架与功能 mod 为：

- maplebirch Framework `4.1.13`（作者官方 Release）。
- Cheat Extended `1.20(dev260719)`（作者官方 Pre-release）。
- LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`（作者官方独立继任包）。
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`（社区二改，原作者 README 明确允许二改二传）。
- 旧 maplebirchEx `1.2.4` 与 `maplebirch-v3-layer-compat` 只保留作 3.x 回滚资料，不进入 4.x 产物。

用户真机日志证明 4.x 基础栈达到 `0 error / 0 warning`，Cheat Extended UI 可打开且抽样
功能可用。LongerCombat 与 Yanling 已挂载，但没有逐功能遍历，因此状态是“运行时挂载通过”，不是
“全功能通过”。

### 上游版本核对（2026-08-04）

当前主动跟踪的五个上游中，LongerCombat `1.0.1`、YanlingCheatCollection `1.0.1`、
Cheat Extended `1.20(dev260719)` 与 DOLI Release `v0.2.3` 没有变化。maplebirch 已于
2026-08-02 发布 `4.1.14`；当前主线仍锁定已通过真机基础栈验证的 `4.1.13`。

`4.1.14` 不只包含 0.5.11.x 怪兽服遮罩路径兼容，还恢复 NPC 怀孕扩展、每日周期、受孕和
分娩流程，行为面大于本轮 More Love 修复。它已被更新检查器正确报告，但不临发版前混入；另案
评估、构建和真机验证后再决定升级。这里的“发现新版本”不等于“当前候选已过时不可发布”。

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
包内 `boot.json` 声明版本、plus ZIP manifest、配置加载与 Python 编译。本机运行 210 项自动测试
通过，其中 195 项属于公开仓库，另 15 项来自 `.gitignore` 排除的私有 MuMu 诊断工具，不能冒充
远端 CI 覆盖。

候选提交 `186fc463` 的分支 run [`30907013186`](https://github.com/XFoxLG/DOL-X/actions/runs/30907013186)
已实际执行并通过公开 193 项测试、base + AU-F 构建、AU ZIP 产物审计和双格式上传；release job
按分支语义 skipped。最终候选 HEAD `713924b4` 的全四码 dry run
[`30907723945`](https://github.com/XFoxLG/DOL-X/actions/runs/30907723945) 随后通过：公开 193 项测试、
四码构建、AU ZIP 审计、ZIP/APK 上传均 success，release job 正确 skipped。下载后的两个 artifact
archive SHA-256 与 GitHub digest 完全一致；8 件产物逐件解码确认 More Love `0.1.7.0`、四个拖拽
防护函数、四类未防护调用为 0、DOLI 新图标路径存在且旧路径为 0。四个 APK 的
`jarsigner -verify` 均返回 0；本机没有 `apksigner`，不外推为 APK v2/v3 完整验证。

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
