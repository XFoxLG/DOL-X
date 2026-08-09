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

### Changed

- **maplebirch 框架升级 v4.1.13 -> v4.1.14（尚未发布）**：官方资产
  `maplebirch-0.5.10.12-v4.1.14.mod.zip`，186903 字节，
  sha256 `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4`，
  与 GitHub Release digest 逐字一致，上游构建 commit `cf57f88c`。
  这推翻了 0808 当时"不混入 4.1.14"的决策，理由是升级面经字节级核对后确认为纯钉版号替换。
  - **三个本地补丁全部保留且无需重新定位**：basehead fallback、pet remount、AU face variant
    的定位串在 4.1.14 的 `dist/inject_early.js` 中各命中恰好 1 次，三个 marker 均为 0 次。
    压缩变量名 `aO` / `aP` 未发生漂移，上游也未修掉这三个缺陷（旧代码原样保留），
    因此不存在"上游已修复"与"仅变量改名"的歧义，无需按 `removal_condition` 退役任何补丁。
  - **实物验证**：三个补丁按构建顺序链式套用到真实官方资产后全部返回 `patched`，
    产物中每个 marker 各 1 次、旧定位串归零，成员清单与 `boot.json` 保持字节不变，
    官方源文件未被修改。这是对真实资产的验证，不是夹具断言。
  - **结构面无变化**：成员数 4 -> 4 无增删，`boot.json` 除 `version` 外字节不变，
    `dependenceInfo` 八条逐字一致（`GameVersion` 仍为 `>=0.5.10.12`，不强制 0.5.11），
    `addonPlugin` 两版均为 0 条，即对游戏本体的 patch 面没有扩大。
    改动集中在 `dist/inject_early.js`（+3432 字符）与类型声明 `.d.ts`（-30 字节）。
  - **上游改动面**（单 commit，8 文件）：`Character.ts` 只新增 `kaiju_mask()` 并接入
    `hair_sides` / `hair_sides_close_up` / `hair_fringe` / `hair_fringe_close_up` 四处
    `masksrcfn`，未触及桌宠的 `:storyready` + `<<updatesidebarimg>>` 接线，也未触及 `basehead`；
    `Time.ts` 恢复每日 NPC 怀孕周期入口；`base_layers.ts` 为 NPC 侧边栏加同一遮罩。
  - **依赖链不变**：LongerCombat v1.0.1、YanlingCheatCollection v1.0.1、DOLI 的
    `addonPlugin` 均声明 maplebirch `^4.1.0`，4.1.14 落在 caret 范围内；
    Cheat Extended v1.20 的运行时门控要求 `>= 3.2.5`，同样放行。
  - **验证状态**：本机 274 项测试（公开 259 + 私有 15）与 `compileall` 全部通过，
    但**真机完全未测**，怀孕扩展的实际游玩表现也完全未测。

### Added

- **上游解封框架 NPC 怀孕扩展（随 4.1.14 引入，带不可逆存档风险）**：
  `NPCPregnancy` 删除 `disabled = true` 字段与七处守卫，构造函数改为主动注册默认怀孕种族与
  NPC 配置，并在 `:storyready` 时注入 `NPCPregnancyPatch`。
  - 接管面：覆写 `window.recordSperm`、`window.pregnancyDaysEta`、`window.getChildDays`
    三个全局函数与 `playerPregnancyAttempt`、`namedNpcPregnancy`、`endNpcPregnancy`、
    `pregnancyBabyText`、`updateChildActivity`、`updateRecordedSperm` 六个宏，均先备份原版；
    生成器写入 `window.pregnancyGenerator[type]`。
  - **与 DOL-X 补丁交集为空**：这六个宏不含 `updatesidebarimg`，三个函数与侧边栏渲染无关，
    两者仅共用 `:storyready` 事件，同一事件的多个监听器互不冲突。
  - **不可逆方向**：会向 `setup.pregnancy.canBePregnant` 与 `canImpregnatePlayer` 单向追加
    NPC 名单，未见迁移或回滚逻辑。**若从 4.1.14 退回 4.1.13，存档中已写入的怀孕数据将失去
    处理方**（4.1.13 的 `savedPregnancy()` 在 disabled 下直接返回）。这是本次升级唯一的
    不可逆风险，回滚前需自行备份存档。
  - 上游 4.1.9 封印该扩展的理由是"避免与原版 0.6 怀孕系统改动冲突"，而本项目锁定
    0.5.10.12 而非 0.6，该冲突前提在本栈不成立。

## [v0.5.10.12-1.0.8a-0808] - 2026-08-08

### Added

- **补齐玩家向 Release 正文与写作规范**：新增 0802、0804 两份可审查的版本说明和
  `docs/DOCUMENTATION_GUIDE.md`。Release 正文只写玩家能观察到的现象、下载选择、实测范围与
  已知边界，技术根因继续留在 CHANGELOG。GitHub 上 0802 / 0804 原本为空的正文已分别补齐，
  0802 同时明确提示其 More Love 版本错配并指向 0804 修复版。

### Changed

- **Release 正文改为发版门禁**：tag workflow 会读取
  `docs/release-notes/${GITHUB_REF_NAME}.md` 并传给上传 action；缺文件时 fail-closed，避免再次
  发布空白正文。新增边界测试，要求 CHANGELOG 最新正式版本存在非空的玩家向说明。
- **重写快速参考与文档索引**：`QUICK_REFERENCE.md` 改用当前四码、真实 CLI 参数、现有配置路径
  和两档 CI 流程；移除旧 499968 系列、不存在的 profile / dev 子命令及无证据的健康分数。

### Security

- **构建 job 收窄为只读权限，写 Release 的能力限定在 tag-only job**：`build.yaml` 顶层改为
  `permissions: contents: read`，并移除 build job 的 job 级 `GITHUB_TOKEN`；只有带
  `if: github.ref_type == 'tag'` 的 release job 单独声明 `contents: write`。构建过程会下载并执行
  第三方 mod 资产，此前 build job 持有仓库写权限，收窄后第三方输入不再触及写能力。
- **签名密钥不再插值进生成的 shell 源码**：`Setup signing key` 改为通过 step `env` 传入
  `SIGNING_KEY_BASE64`，配合 `set -euo pipefail` 与 `umask 077` 解码；新增 `Remove signing key`
  步骤以 `if: always()` 在任务结束时 `shred -u`。新增边界测试断言 run 块内不出现
  `${{ secrets.` 插值。

### Fixed

- **修复 AU 换脸后仪态不同步、未再选择仪态时眼睛消失，并迁移已保存的非法组合**：
  DoL 0.5.10.12 约定每个脸型的首个仪态代码值必须是 `default`，角色创建、镜子和作弊页三个
  交互入口在切换脸型后都把 `$facevariant` 硬设为 `default`。AU model 脸型实际注册值则是
  “大眼鼠鼠”“猫猫脸”“Q萌一号”等真实图片目录名，没有非传统脸型的 `default` 目录；因此只点
  脸型会形成无效的 `facestyle/default` 组合，模型不立即同步，并可能请求不存在的 eyes、sclera、
  iris、eyelids、lashes 等图片，直到玩家再点一个仪态。AU 三码现在复用 Maplebirch 已有的
  `modifyFaceStyle()` owner，在 `ModI18N` 完成翻译后修改最终 Passage：角色创建、镜子和作弊页
  三个入口从 `setup.faceVariantOptions[$facestyle]` 选择第一个注册值，并沿用原入口自身的
  `<<updatesidebarimg>>` 刷新。`backComp` 每次加载都会额外检查当前组合：只有当前脸型存在注册仪态
  且当前值不在合法列表中时，才改成第一个合法值；合法选择和未注册仪态列表的第三方脸型保持
  不变。最初的构建期主 HTML 改写已退役：A/B 证明它会改变 `Widgets Settings` 的原始 Passage，
  使 `ModI18N 1.0.8a` 的位置型规则整组失效，导致开局设置与角色创建变回英文。构建现在只读验证
  原 HTML 的四个翻译输入仍各出现一次，再对 Maplebirch payload 做 fail-closed 精确补丁；base
  构建不应用。AU ZIP/APK 产物审计同时要求原 HTML 保持四个未改写输入、内嵌 payload 含唯一的
  后汉化 marker 和完整 3+1 行为规则，避免修好换脸却破坏汉化，也拒绝 marker 错位或旧预汉化
  补丁残留。

  MuMu 12 的汉化安全隔离 AU-F 候选中，`ModI18N 1.0.8a` 主语言为 `zh`，`Widgets Settings` 的“请选择游戏模式、角色创建、
  体型、脸型、仪态”均为中文，对应英文源串均不存在；三个最终 UI Passage 各有一条换脸规则，
  `Widgets variablesVersionUpdate` 有一条迁移规则，且无 reporter。角色创建真实 UI 逐个点击八脸且
  不再点击仪态时，8/8 都立即形成合法组合，人物 canvas 有 8 个不同内容哈希。旧存档路径也用
  完整有效游戏状态验证：在可保存 passage
  中提交并保存 `kiss改脸/default`，把当前状态提交回 `default/default` 后真实加载槽位，加载结果为
  `kiss改脸/大眼鼠鼠`，正常进入 `Orphanage Intro`，无红框；页面有 4 个 canvas，最大非透明像素数
  为 49972。测试槽位已删除。更早存档中的 `eyesFacestyle`、`mouthFacestyle`、
  `eyeColor` 报错因原问题存档已删除，仍无证据确定迁移值，本修复不对此作过度声明。

- **修复 Maplebirch 桌宠切换段落后消失（开启也看不到、偶尔一闪）**：
  SugarCube 每次渲染段落都会重建 StoryFooter，因此框架挂载 canvas 的
  `<div id="maplebirch-character-pet">` 会被替换成一个全新的空节点。v4.1.13 只在
  `Character.preInit()` 包装的 `<<updatesidebarimg>>` 宏里重新同步桌宠，而切换段落并不
  必然触发该宏，于是桌宠虽为启用状态却不再出现，框架仍持有已脱离文档的旧容器。
  MuMu 12 实测：切段落后页面上的活容器 0 个子元素，而 `pet.container` 已脱离且仍带 1 个
  子元素；手动调用一次 `<<updatesidebarimg>>` 可恢复 17588 个非透明像素。修复在构建期
  把框架自己的 `:passagedisplay` 事件订阅到它自己的 `<<updatesidebarimg>>` 宏，且仅在桌宠
  已启用且活容器为空时触发，因此幂等、不改变桌宠外观与设置。这里必须走宏而不是直接调用
  `pet.sync()`：`Pet.draw()` 从 `Renderer.CanvasModelCaches.main.sidebar` 读取穿着，缓存
  未建立时会静默退回 `model.defaultOptions()`（未穿衣模型）——实测直接 `pet.sync()` 得到
  16316 个非透明像素且无侧边栏缓存，走宏得到 17588 且穿着图层齐全。上游 v4.1.14 的
  `Pet.ts` 与 v4.1.13 逐字节相同、同步接线未变，升级无法替代本补丁。补丁 fail-closed，
  只改官方资产的 `dist/inject_early.js`，成员列表与 `boot.json` 均不变。
- **修复 Maplebirch 桌宠启用时切换改脸，桌宠头脸暂时消失并弹出 `base-head.png` 红框**：
  用户补充确认主侧边栏模型始终正常；桌宠是独立显示、从 `main` 模型派生图层的固定位置画布，
  本问题只发生在桌宠自身启用并切换脸型时。Maplebirch 4.1.13 的桌宠模型刷新会请求不存在的
  `img/face/<facestyle>/base-head.png`。上游源码本意是在风格未提供专属头部底图时回退到
  `img/body/base-head.png`，但同步的 `resolveFaceImagePath()` 调用了异步 `loadImage()`，把首次
  返回的 Promise 当成“未知但可用”路径，因此先选择不存在的候选。构建期补丁现在使用框架已在
  `afterRegisterMod2Addon()` 中同步建立完成的 face 图片索引判断：索引命中才使用风格专属底图，
  否则立即回退到 body 底图。补丁不复制图片、不修改 AU 加密包，且只对官方 v4.1.13 的精确
  仓库/tag/asset 和唯一压缩代码指纹生效；上游漂移时 fail-closed。官方 186010 B 资产实物验证
  sha256 为 `f5161eed8a4828baac8d7667ad4311fa214f02855c32c190ac1087902e9be955`，补丁仅改变
  `dist/inject_early.js`，成员列表与 `boot.json` 均不变。MuMu 12 对 CI run `31015066739` 的
  AU-F 0805 候选完成运行时复验：按各脸型注册的有效变体，使用 UI 实际采用的单次
  `<<updatesidebarimg>>` 刷新依次切换传统、kiss、nss、Twinkle、兔子、加辣、沅芷、碱性糖，
  8/8 桌宠 canvas 均非空，0 条图片加载错误、0 个 page error，且始终回退到正确的
  `img/body/base-head.png`。测试后已恢复传统脸型、25px 遮罩与桌宠关闭。

  base 0805 对照包的桌宠 canvas 只有完整小人，AU-F canvas 额外带右侧 close-up 大脸；框架又
  明确用可配置的“桌宠遮罩分割线”（默认 25px）裁切桌宠容器。因此反馈中的“大脸显示不全”
  属于 AU 画布布局叠加框架遮罩的设计/调节边界，不是 `base-head.png` 缺图修复的残留故障。

- **纠正 DOLI 4.x 记录**：用户真机证据表明 DOLI 在当前 maplebirch 4.1.13 栈中可以运行，不能
  仅凭 `addonPlugin` 的声明范围推断框架入口不注册。DOLI 自带的 overlay patch 与 DOL-X 的
  构建期补丁也不是一件事；后者只修复右下角智能助手悬浮按钮的破图。

## [v0.5.10.12-1.0.8a-0804] - 2026-08-04

修复 More Love 与 DoL 0.5.10.x 的版本错配，并把完整 pytest 与 AU 产物审计接入发版门禁。
发版前全四码干跑由 run [`30907723945`](https://github.com/XFoxLG/DOL-X/actions/runs/30907723945)
完成：公开 193 项测试、base / AU-F / AU-M / AU-A 四码构建、4 ZIP 静态审计和 8 件产物上传
全部成功，release job 按非 tag 语义 skipped。下载后的两个 artifact archive 与 GitHub digest
一致；8 件解包产物中的 More Love `0.1.7.0`、拖拽防护、DOLI 图标路径均逐件复验通过。

### Fixed

- **修复 AU 产物审计器与官方资源契约漂移**：官方 AU-F/M/A 的嵌套脸红资源是
  `blush-1.png` 至 `blush-5.png`，另有独立的 `blusher.png`。旧检查器只接受外层
  `blush1.png`、错误要求 6 个编号层，并把 `blusher.png` 混入计数，导致真实 AU-F 产物误判
  失败。检查器现在同时兼容新旧连字符命名、只统计编号层，三种 AU 真实产物均通过；新增真实
  `1..5 + blusher` 回归样本。

- **修复 More Love Interests 版本错配**：mod 从 `v0.1.6.0` 升级到 `v0.1.7.0`。这是修 bug，
  不是尝鲜。作者 README 给出游戏版本与 mod 版本的对照表：`v0.5.10.x` 的游戏必须用 `v0.1.7.0`，
  `v0.1.6.0` 对应 `v0.5.7.x`。本项目游戏本体是 `0.5.10.12`，此前钉 `v0.1.6.0` 属于错配。
  上游 issue #1「关于 v0.5.10.12 后，查看食物偏好爆红的问题」记录了错配后果，作者当天回复已
  发布 0.5.10 适配版。根因是游戏本体五处重命名（`setup.plants` → `setup.foodstuff`、
  `_foodInfo.ingredients` → `_foodInfo.recipe.ingredients`、`<<tendingicon>>` 宏删除并改为
  `<<foodstufficon>>`、`$plants` → `$foodstuff`、舒芙蕾键名 `soufflé` → `souffle`），五处均已
  对着真实游戏 HTML 独立核实。改动面只有 4 个文件，无增删文件。`GameVersion` 门槛由
  `>=0.5.5.0` 收紧到 `>=0.5.10.0`，当前版本满足。
  **注意**：`more_love_interest_main.twee` 另有一处上游有意的状态清理——`$auriga_artefact`
  缺失或 Avery 已 dismissed 时会把 Avery 从 `$loveInterestList` 移除。旧存档若已把 Avery
  设为恋人，条件不满足时该条目会消失。

  2026-08-04 真机确认正式“态度”页入口、食物偏好页面跳转和空列表无红框。因测试存档尚无
  恋爱兴趣 NPC，食物图标、配方材料、Avery/舒芙蕾和旧存档列表清理仍属未覆盖边界。

### Changed

- **加强 GitHub Actions 发版门禁**：Build workflow 现在在构建前运行完整 pytest，并在构建后、
  上传 artifact 前运行 AU ZIP 产物审计。此前 CI 只安装 pytest 而从不执行测试，产物审计工具也
  未接入 workflow；因此“build 成功”不能证明完整测试或 AU 资源门禁通过。新增 workflow
  边界测试，防止这两个步骤被静默移除。

- **校准真机测试工具与文档**：测试清单默认体型从 AU-M 改为实际维护者使用的 AU-F，清除
  maplebirch 3.1.14、Cheat Extended 1.18、maplebirchEx 启用、AU Face 禁用等旧矩阵残留。
  `download_latest_build.py` 明确为测试目录/清单生成器，artifact 下载仍由 Actions 页面或
  `gh run download` 完成。

- **记录 maplebirch 4.1.14 延后决策**：更新检查已发现正式版 4.1.14，但它恢复 NPC 怀孕扩展、
  每日周期、受孕和分娩流程，行为面大于本轮 More Love 修复；当前候选继续锁定已真机验证的
  4.1.13，4.1.14 另案评估，不在发版前混入。

- **同步 fork 兼容补丁登记表**：`lyra/compatibility.py` 中 More Love 拖拽补丁登记项的
  `release_tag` 随之更新。该补丁是 DOL-X 专属、上游没有的构建期 payload 修改，因此升级走
  登记表流程而非绕过护栏。`compatibility_source_errors()` 的 fail-closed 校验在改登记表前
  正确拦下了构建（报 `release_tag expected ... got ...`），证明护栏按设计生效。
  `More_Love_Interest_Mod_Drag.js` 在两版之间**字节完全相同**（同一 sha256、同样 3178 字节），
  上游仍未对非 DOM 拖拽事件参数加防护，故补丁依然必要且原样适用，`removal_condition` 不变。
  CI run [`30833299579`](https://github.com/XFoxLG/DOL-X/actions/runs/30833299579) 日志确认
  补丁在 base 与 AU-F 两码上均命中（`More Love drag event compatibility patch applied`，
  非 `already_patched`）。

## [v0.5.10.12-1.0.8a-0802] - 2026-08-02

4.x 公开主线的首个 tag 发版，取代 0713 的 maplebirch 3.x 稳定栈成为最新稳定版。
四体型（base / AU-F / AU-M / AU-A）× 双格式（ZIP + APK）共 8 个产物。

> **2026-07-31 4.x 公开主线迁移**：从 0713 的干净 `vega` 基线重建 4.x 公共主线（maplebirch 4.1.13 + CE 1.20 + LongerCombat + Yanling + Legacy-Art-Mods-Compat plus）。旧 0713 稳定栈已存档为远程分支 `vega-archive-0713`，plus 已上传到 `XFoxLG/DOL-X` Release `legacy-art-compat-plus-v1.1`。

> **构建矩阵**：分支推送构建 base + AU-F，tag 发版构建全部四码（base / AU-F / AU-M / AU-A）。
> 手动触发（`workflow_dispatch`）可选 `build_tier=release`，在不打 tag 的前提下干跑全四码。

> **发版前验证**：AU-M 与 AU-A 此前从未在 CI 里构建过（分支档只含 base + AU-F）。首次全四码
> 干验证由 run [`30709200905`](https://github.com/XFoxLG/DOL-X/actions/runs/30709200905) 完成，
> 8 个产物全部生成，证明这两个组合的资源链可用。真机测试只覆盖 AU-F。

> **2026-07-29 后续**：AU-F 0728 本地候选的用户真机测试已经把"AU Face 尚未验收"拆成两层：设置 UI 和配置交互已通过，但运行时仍请求旧式 `blushN` / `tearN` 路径，当前包内 canonical 资源是新式 `blush-N` / `tears-N`。官方 `Legacy-Art-Mods-Compat` 1.0.3 不含这些 AU Face 通配符规则；社区二改 `1.0.3-plusV1.1` 精确包含。用户旁加载 plus 后 `blushN`/`tearN` 报错消失、独立嘴部仪态有效，面纹和流泪视觉效果不碍事、不阻塞主线——属上游 AU Face 加密内层运行时边界，DOL-X 无白盒修复手段。同时确认 maplebirch `PC模型模式` 需要独立 NPC wardrobe 数据，当前 38 个 payload 均未注册衣柜，因此具名剧情 NPC 动态模型回落 `naked` 是设计内行为，不是图片路径 bug。云存档服务端源码位于官方 `cloud-services/`，提供 Go+SQLite 与 Cloudflare Worker+R2+D1 两种自建方案，无公共实例；Go 后端当前缺少客户端会调用的 `/save-code` 路由。

### Added

- **接入官方拆分继任者**：新增 LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`，
  分别承接旧 maplebirchEx 的更长遭遇战和言灵功能。两个包均来自作者官方仓库，声明
  maplebirch `^4.1.0`。
- **AU Face 进入公开 AU 构建**：官方 `AUsDoL.facial.expansion.mod.zip` 仅绑定 AU-F/M/A，不进入基础版。
  Release 正文版本为 `1.0.4`，包内 manifest 为 `1.1.0`，内层解密后实际注册为 `AU面部扩展 1.2.8`；
  本地锁定官方 SHA-256 `8f2c1b66f0104e51e4f1c91f8f3a4873db517997a390c1037f4de811d387ecf6`。
  AU-F 已确认设置 UI 可打开、配置可交互；运行时旧式 `blushN` / `tearN` 路径由社区 plus
  提供兼容，视觉效果仍属部分验收边界。0802 Release 已公开四体型双格式产物。
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
  AU Face 作为起因。AU 面部扩展是另一个独立 mod，0802 起进入公开 AU 构建；其设置 UI 与交互
  已通过，脸红/流泪等视觉仍未完整验收。
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
