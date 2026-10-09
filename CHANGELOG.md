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

### Fixed

- **战斗轴 soft_fail 三类测试器根因修复（2026-10-09）**：动态回合上限改为
  “当前上限 + 剩余血量所需回合 + 5”，不再把剩余血量误当成新总上限；无控件续进
  会记录 HP/arousal 证据，只有连续 3 次有意义状态不变才停止，状态推进时可以继续
  到终局；384 条同时具备 `$sexstart` / `consensual` / `<<actionsman>>` /
  `_combatend` 的共识性场景改为源码证据明确的 `not_applicable`，静态台账新增
  `sexual_encounter` shape。`Abduction`、`Adult Shop Clerk Angel Molestation`、
  `Livestock Return Horse Rape` 等真实样本由 `soft_fail` 变为 `ok`；
  `pytest` **735 passed**。
- **战斗特殊血量终局误报（2026-10-09）**：`Brothel Show Machine` 的胜利终局由
  `$machineHealth` 驱动（20 → -1），旧测试器只检查 `$enemyhealth`，导致已结束的
  机器战被误报为“无敌人失败证据”。终局判定与动态回合上限现在识别
  `enemyhealth` / `machineHealth` / `tentacleHealth` / `swarmActive`，并优先采用
  最近回合里真正下降的血量字段；新增 4 条回归测试，`pytest` **729 passed**。
- **combat-full 前 4 片 26 条 hard_fail 归因与修复（2026-10-09）**：run
  `37899995638`（head `a2e324f`）前 4 个分片暴露 26 条 hard_fail，分三类：
  15 条 Finish/出口缺父事件状态、6 条 `personselect` 读未初始化 NPC 槽、
  5 条把 widget 库 / SugarCube chrome 当成可玩入口。修复全部在测试器侧：
  `person_reference_max` 支持 `<<personselect random(0, N)>>` 并沿
  Finish → widget 闭包推导槽位；新增 11 条只补真实出口/分支状态的
  status-bootstrap；`resolve_widget_entry` 拒绝 widget 库与 chrome caller；
  `derive_precursor` 对自带 combat starter 的行允许状态引导；Brothel Show
  按游戏源码初始化完整 `$brothelshowdata`。最终对 26 条原 hard_fail 全量
  定向复跑：`ok=15 / not_applicable=10 / hard_fail=1 / soft_fail=0 /
  fixture_insufficient=0`。唯一剩余 hard_fail 是
  `Estate Manor Approach Fight`：源码出口链接指向当前产物不存在的
  `Estate Manor Intro Entrance`，保留为上游断链证据，不造假出口。
  `pytest` **725 passed**。
- **战斗轴无动作场景空转（2026-10-09）**：daily 报告里的
  `named-bailey:win` 证明测试器仍会在“只有 Next、没有战斗控件”的
  场景里连续点 80 次 continuation，并把 passage 来回切换误当成有效回合。
  修复：`combat_sweep` 为无动作 continuation 设置 3 次预算，超过后立即
  记录 `offered_controls`、分类为 `soft_fail` 并停止，不再消耗回合上限。
  定向复跑 `named-bailey:win`：1 次 continuation 后到达
  `Bailey Beating Finish`，如实记为 `soft_fail`（scene end，非胜利），
  不再出现 80 回合空转。
  新增回归测试锁住“3 次后必须停、不能提交动作回合”；`pytest` **719 passed**。
- **云端 daily 汇总误判辅助报告（2026-10-09）**：run `37884127706` 的四个主轴
  （passage / scenario / combat / env）全部完整且 `hard_fail=0`，但 summary 把
  daily 新增的 mod 盘点与 mod passage 辅助报告也当成主轴 shard，导致
  `expected 4, got 6`；同时 env 报告的 identity 位于 `meta.ledger`，汇总器只读
  顶层 `ledger` 而误报缺 identity。修复：summary 只聚合四个主轴报告，辅助报告仍由
  daily job 自身 fail-closed 校验并上传；`sweep_summary` 兼容读取
  `meta.ledger.identity`。用该失败 run 的真实四主轴报告本地复验汇总为 `ok=True`。
- **dayloop 真实一日流程收口（2026-10-09）**：`scenario_sweep` 的上课 effect 阶段
  此前只按 passage/时钟判定进度，把已经真实换上学校泳衣的原地动作误判为
  `stalled`；且换装成功后没有记入 `swimwear_attempted`，导致下一跳无法进入泳池。
  修复：换泳衣按 `worn` 槽位变化判定（必须出现 `school swimsuit` +
  `school swimsuit bottom`），effect 阶段复用同一判定并记录已尝试；放学恢复衣服时
  优先选择"校服"而不是列表更靠前的"便服"，合成夹具同时把校服/泳装放进
  schoolGirls / schoolBoys 两个位置衣柜。实测同一 1004 产物：
  dayloop `ok`，9 个步骤全部完成，时间推进 **16.20h**、地点切换 70 次、
  存档往返 PASS、`hard_errors=0`；完整剧情轴复跑 331 行保持
  `ok=319 / soft_fail=2 / hard_fail=0 / fixture_insufficient=9 / not_applicable=1`，
  无新增回归。`pytest` **716 passed**。
- **CI 冷启动 Maplebirch 欢迎框死循环（2026-10-07 同日第六轮）**：daily / combat-full /
  full 三个云端 run 全部红在 `bootstrap did not reach gameplay; last passage='Start'
  after 1245-1252 steps (deadline_hit=True)`，action trail 全是
  `click_startup_control` 点击 `I Understand`。根因是 maplebirch 4.1.14 框架欢迎框的
  确认按钮只在 `<<checkbox '_maplebirchNoticeVerify'>>`（真实 input
  `checkbox--maplebirchnoticeverify`）勾选后才关闭对话框，而测试器只点按钮不勾选、
  英文勾选说明 `I have read and understood the notice above` 又不在 consent 名单里，
  重复断路器也不覆盖页面级 confirm。修复：`browser_smoke_test` 新增
  `accept_framework_notice` 分支与通用 `ensureGateCheckboxes`（confirm 前自动勾选最近
  门控容器内的 checkbox）、`skipKeys` 支持按候选按钮文本匹配，`STARTUP_CONSENT_LABELS`
  补中文/英文两条 maplebirch 勾选说明；`passage_sweep` 重复 key 扩到
  `click_startup_control` / `accept_consent_gate` / `accept_framework_notice` 并改按
  `button_text` 记 key，trail 记录 `checkbox_checked`。真实产物（base-1003，37 mod）
  本机 bootstrap **4 步**进入 `Orphanage Intro`（`.local/sweep/bootcheck/`，含
  `accept_framework_notice` 勾选后点击证据）；新增 2 条真实 DOM 测试（Chromium 驱动
  `_startup_interaction_script`）+ 3 条 passage_sweep 单测，`pytest` **647 passed**。

### Added

- **mod passage 盘点 + `--allow-runtime-only`（2026-10-07 同日第七轮）**：静态
  `extract_passages` 只能看到 HTML 文件里的 15,627 条 vanilla passage，37 个内嵌 mod 的
  twee 是 base64 payload、由 ModLoader 在运行时合并——此前"15,627 全通过"不含任何 mod
  内容。新增 `tools/mod_passage_inventory.py`：一次真实启动后取运行时 DOM passage /
  `SugarCube.Story.lookup('passages')` / `Macro.has`，按 payload 里的 `:: Name` 与
  `<<widget "name">>` 反查来源，产出 JSON+MD 与可游玩清单；实测 au-f-1003：静态 15,627、
  运行时 15,664（+37 mod passage）= 4 条可游玩（`CE_Wardrobe` / `CustomDyeHair` /
  `CustomHairPassage` / `Food Preference`）+ 33 条 widget 定义（34 个 widget 宏，启动
  已注册 32）+ 1 个加密不透明 mod（`【AUsDoL】facial expansion`，`.zip.crypt/.salt/.nonce`，
  按既定策略不解密、只走运行时黑盒）。`passage_sweep` 新增 `--allow-runtime-only`，让
  `--only-file` 里静态看不到的 mod passage 也进入扫描（本机 4/4 ok，报告记录
  `only_file.runtime_only`）；daily 云端档接入"盘点 → 扫可游玩 mod passage"，空清单
  视为覆盖回归。加密 mod 的可测路径 = Engine A `au-face` 流 + Engine B MuMu 真机。
  新增 13 条单测，`pytest` **660 passed**。
- **剧情轴行分类 + 深度摘要 + 赋值前置检查（2026-10-07 同日第五轮）**：1006 剧情跑分
  82 条 `soft_fail` 里有 80 条是同一句"widgets produced no observable state delta"——
  浅层摘要只取一层、数组/对象前 8 个成员，嵌套写入（`<<learn_recipe_all>>` / `<<undress>>` /
  `<<updateMuseumAntiques>>`）看起来像没生效。`scenario_sweep` 三处升级：
  `classify_interaction` 把 331 个可点击项分成 `state` 212（`stayOnPassageFn` =
  `() => V.passage`，游戏源码可验证）/ `scene` 94（字面跳转）/ `display` 24（widget 源
  全空白，纯渲染页）；`__dolxDeepSnapshot` + `__dolxDeepDelta` 做全变量树深度摘要
  （节点预算 15 万、深度 12、循环保护）与路径级 diff；`__dolxAssignChecks` 对
  `<<set $path to <literal>>` 与 `+=/-=` 做最终值比对，非字面 RHS 与 function widget
  记 `checked: false`（`String(fn)` 假阳性已修并留单测）。判定语义：无 delta 降级为
  `ok` 的 note（报告新增 "ok rows with notes" 一节）；赋值检查失败 → `soft_fail`。
  本机全量复跑 331 行：`ok` 239 → 319、`soft_fail` 82 → 2（仅剩两条上游未注册宏缺陷）、
  `baseline_diff` new_regressions 0 / fixed 80；`pytest` **642 passed**。
  另：修复前派出的 combat-full run 37542211811（head `05b3b95`）头 4 片全部因
  `Start` 上 788 步 dismiss 撞 720s 冷启动预算而全 0 结果，佐证上一轮 CI 修复的必要性，
  其报告不采信、需在修复后的新 run 重跑。
- **战斗状态引导 status-bootstrap + CI 冷启动预算修复（2026-10-07 同日第四轮）**：
  `combat-personn-1007i` 剩下的 6 条 `fixture_insufficient` 都是**事件链中段**入口
  （Finish 读父事件已建好的状态）。`derive_precursor` 新增 6 条 status-bootstrap
  （`pubfame-bailey` / `farm_assault_init` / `pubfame-hospital` / `island_init` /
  `street-bus` / `sydney-init`），只补 Finish 真正读的字段，basis 追加
  `|status-bootstrap:<name>`；本机复跑（`combat-status-1007p`）6 条全部翻正，
  1 条 `Bailey Sheet Fight` 以 `soft_fail` 记录（实走 `Rent Intro` 失败结局分支，
  属预期走向而非缺陷），4 控制模式 4/4 ok。同日 CI daily 档（run 37536425118）的失败
  归因为**贴边预算**而非卡死（`Start` 上 789 步 dismiss 撞 720s deadline；prepare
  同产物 capture 12m27s）：`STARTUP_STEPS` 1000 → 1500、`STARTUP_DEADLINE_S`
  720 → 1140，并新增重复点击断路器（同一 dismiss 目标 120 字符文本样本重复 25 次后
  加入 `skipKeys`，action trail 记录 root/sample/repeat）。`pytest` **636 passed**。
- **战斗台账深层前驱 fallback（2026-10-07 同日第二轮）**：`candidate-probe-1007.json` 的
  5 条真机 A/B 证明"深度 3-4 跳 / 父 widget 链"的 `$beasttype` 来源可以重放：4/5 行从
  `leftActionInit` DOM 错误变为 19-25 回合干净胜利，`Forest Wolf Molestation Resist`
  的 fox 是反例（仍 `soft_fail`，不修成通过）。`combat_sweep` 的 `PRECURSOR_SCHEMA`
  升 `combat-precursor-v2`，浅搜索（2 跳）失败后走 `deep_beast_precursors`
  （BFS 4 跳 + 父节点 widget 链），basis 记 `deep-predecessor:...` 且
  `confidence: low`、`token` 入 info；`combat_ledger` 新增 `deep_predecessor` 分类与
  "Deep (low-confidence) derivations" 清单，候选函数与 sweep 共用。台账复跑：
  `unresolved` 30 → 14、`deep` 16、shape 与 drift（19）不变；`pytest` **626 passed**。
  本机 16 条 deep 行复跑（`.local/sweep/combat-deep-1007j/`）：`ok` 10（9 条翻正）、
  `fixture_insufficient` 5（全部卡在 Finish 后置 widget：`setTowerTemp` / `pound_status` /
  `person1`）、`soft_fail` 1（Forest Wolf 反例）、`hard_fail` 0；失败面从"进不去战斗"
  推进到"退出时缺状态"，4 种控制模式全 ok。
- **战斗区域引导 area-bootstrap（2026-10-07 同日第三轮）**：深层前驱之后仍卡住的 5 条
  token-less 兽类行都死在战斗*之后*的出口 passage（`setTowerTemp` 读 `$bird.upgrades.shelter`、
  `pound_status` 读 `$pound.status`、`prison_attention` 读 `$prison.*`、`person1` 需要 slot 0）。
  `derive_precursor` 对 `^Bird` / `^Pound` / `^Prison` 的行先重放游戏自己的区域初始化
  （`bird_init` / `pound_init` / `prison_init`），basis 追加 `|area-bootstrap:<widget>`；
  Prison 另设 `$prison_intro=1` 并按监狱流程预置 slot 0 的 `anxious_guard` 存档
  （`generate_anxious_guard` 的 else 分支硬编码 slot 1，只有 `loadNPC` 路径对得上 `person1`）。
  16 条 deep 行一次跑完（`combat-deep-1007m`）：`ok` 15 / `soft_fail` 1（Forest Wolf 反例）/
  `hard_fail` 0 / `fixture_insufficient` 0，4 控制模式 ok；模式放宽到 `^Bird` 后 Bird Hunt 的
  `flight_hunt_return`（读 `$bird.hunts.duo`）一并修复（`combat-bird-1007n` 3/3 ok）；
  `pytest` **630 passed**。
- **战斗覆盖台账 `tools/combat_ledger.py`（2026-10-07）**：把 1,570 条战斗 initiator
  逐条落成带源码依据的静态台账（JSON + MD），分 entry shape（`entry` 1300 /
  `entry_via_link` 127 / `widget_definition` 73 / `helper_only` 69 / `unresolved` 1）
  与 derivation（`upstream_predecessor` 470 / `synthetic_generator` 392 /
  `named_npc_plus_generator` 173 / `beast_token` 247 / `named_beast_npc` 26 /
  `self_generation` 20 / `not_needed` 212 / `unresolved` 30）两个维度；可 `--report`
  关联一次跑分结果（不凭空造判定），未覆盖条目单列一节并附来源证据：保存兽类 NPC 的
  变量（`$dock_dog` @ `Docks Watch`）、是否用 `$beasttype`、以及沿链接图最多 4 跳找到的
  **未验证**候选 token（depth / 来源 passage / 正文或 widget）。`--fail-on-unresolved`
  作为可选 CI 门；`sweep.yaml` 的 `combat-shards` 新增 "Build static coverage ledger"
  步骤（`if: always()`，缺 `HTML_PATH` 时明确跳过），台账随报告脱敏上传。验证：
  `pytest` **621 passed**（台账轴 19 条：分类映射、widget 调用点、五种 shape、
  前驱证据、候选 token、fail-closed 退出码）。
- **云端分片验收基础设施（2026-10-07）**：把 Engine A 的完整验收搬到 GitHub Actions
  分片执行，覆盖范围不因分片而缩小。新增 `tools/sweep_ledger.py`（长跑身份台账：
  `html_sha256` / 夹具摘要 / 测试器版本 / 计划摘要 + 原子检查点与完整性校验；旧版只有
  完成键的检查点被显式拒绝，损坏或不匹配不可恢复）与 `tools/sweep_summary.py`
  （fail-closed 汇总：预期分片数、逐份 completeness、键重复/缺失、身份一致性，任何异常
  退出码 1，不允许封存"假完整"基线）；`combat_sweep` / `env_matrix` / `passage_sweep` /
  `scenario_sweep` 全部支持 `--shard-index/--shard-count` 与完整性块，战斗 `--resume`
  改为从台账合并历史结果，环境每 500 条重建浏览器、崩溃最多重启 2 次并把基础设施中断
  与用例结果分开记录。`.github/workflows/sweep.yaml` 重写为四阶段（prepare → 分片 →
  白名单脱敏导出 → summary）：`full` = 4 passage 分片 + 场景 + 8 环境分片，
  `combat-full` / `env-full` = 8 分片，`fail-fast: false`、`max-parallel: 4`、
  每分片上限 210 分钟。验证：`pytest` **545 passed**、`tools/quick_check.py` 13/13。
- **Engine A 自动化测试第二期：剧情 · 战斗 · 环境（2026-10-05）**：在全 passage 扫描之上
  新增多轴覆盖，全部运行时注入、不改构建配置、不进发行包；日常档 ≤60 分钟，发版档 3-4 小时。
  - `tools/scenario_sweep.py`：游戏内置 debug 菜单 363 行（331 可点击 + 32 分隔标题）全部深挖，
    另加一条真实游玩 `dayloop`（未走满一天的步骤如实记 `not_applicable`/`soft_fail`，不造假）；
    `tools/combat_sweep.py`：敌人原型矩阵 × 胜/败/逃/屈服四路径 + 4 种战斗控制模式的真实 DOM
    测试 + 全量战斗入口（实测清单 1,570，可 `--resume`）；
    `tools/env_matrix.py`：日常 8 个具名时间/天气/节日上下文、发版 4 个，设置后读回校验
    fail-closed。
  - `tools/fixture_ladder.py`（夹具阶梯：capture/from-save/sanitize/verify/list，
    `.local/fixtures/` + index.json，永不入库）、`tools/save_safety_guard.py`（仓库
    fail-closed 守卫：`*.save` / LZString / 绝对路径 / `.local` 外的夹具载荷）、
    `tools/report_sanitize.py`（CI 上传前脱敏 + `--check` 复核）；`tools/passage_sweep.py`
    新增 `--fixture / --fixture-patch / --context / --only-file`，基线按
    `{fixture}__{context}` 分组封存。
  - 历史 8 条 `fixture_insufficient`（`TimeTest` + 7 条 `Skyscraper *`）用游戏自身初始化值
    补丁修到 `ok`；合并夹具 `base-1004-fix8.json` 单独复跑 8/8 通过。
  - 新增 `.github/workflows/sweep.yaml`（仅 `workflow_dispatch`；tier =
    daily / full / combat-full / env-full；`concurrency` 与 Build 分开排队；
    `timeout-minutes: 210`；报告先脱敏再上传 Artifact）。
  - 验证：`pytest` **504 passed**；夹具/守卫/脱敏取证测试与真机小样本证据见
    `docs/AUTOMATED_PASSAGE_SWEEP.md` §4 与 §8。
- **战斗原型矩阵入口选择修复（同日第二轮，2026-10-05）**：`beastNEWinit` 无
  starter 的静态行（如 `Farmland Pigs`）只生成怪物，战斗在后续 passage 才开；
  原型矩阵最初把它们当可玩入口，实机全部 `not_applicable`。修复：
  `find_combat_link_target` 支持最多 2 跳的 wiki/`<<link>>` 链接跟随 +
  `choose_entry` 按 link_depth 重新排序 + 矩阵/控制模式跑前强制 restore +
  `mode_entry is None` 分支错误；8 个兽类原型（pig/cat/fox/lizard/hawk/bear/
  boar/snake）改为真实战斗入口。修复后 28 规格全量实测：
  `ok=28 / soft_fail=14 / hard_fail=0 / fixture_insufficient=46 /
  not_applicable=16`，4 控制模式 `mode:ok`；`pytest` **510 passed**。

### Changed

- **三个 mod 改走自建不可变镜像（2026-10-03）**：两个上游仓库被作者删除、一个上游通道
  持续原位换包，三者都无法再作为可信的构建输入。DOL-X 把这最后一份 4.x 兼容构建上传为
  自建不可变 Release，`download_url` 改指镜像，并把 digest 纳入 fail-closed 名单。

  | mod | 原上游 | 现状 | 自建镜像 tag | sha256 |
  |---|---|---|---|---|
  | longer_combat | MaplebirchLeaf/LongerCombat | 仓库已删除（404） | `longer-combat-mirror-v1.0.1` | `be1421c8…` |
  | yanling_cheat | MaplebirchLeaf/YanlingCheatCollection | 仓库已删除（404） | `yanling-cheat-mirror-v1.0.1` | `50e2341e…` |
  | cheat_extended | chris81605/..._Cheat_Extended | 仍在，但 V1.20Beta 通道已原位换包 5 次 | `cheat-extended-mirror-v1.20` | `9d318e81…` |

  - **LongerCombat / Yanling**：作者删库，功能并入枯木逢春（Deadwood-Reblooms）作为
    `LongerCombat` / `IncantationCheatCollection` 模块。官方资产不复存在，故
    `track_upstream` 关闭（已无可追对象），`github_repo` 保留上游值仅作来源标注。
  - **Cheat Extended 第 5 次换包**：V1.20Beta 资产在 2026-10-02T18:46Z 又被替换，
    从 dev2601001（599033 B, `1a89383f…`）变为 `boot.json` 版本号为纯 `1.20` 的新构建
    （606561 B, `9d318e81…`），新增 `scripts/CE_customerHairColor.js`（发色自定义）并改动
    7 个成员；`dependenceInfo` 与 `addonPlugin` 条目数不变，`GameVersion` 门槛仍为
    `>=0.5.11.9`，`CE_environmentGuard.js` 逐字节不变（仍只对 `/\bDoLP\b/i` 生效，
    DOL-X 0.5.11.9 不受影响）。因该通道不可信，DOL-X 钉住这一版并改走镜像；
    `track_upstream` 保留为 true，只为让周检继续发现新版本。
  - **周检语义说明**：镜像化之后，周检对 cheat_extended 会持续报
    `asset digest changed`（medium）。那是"上游又换包了"的预警信号，不是构建失败；
    构建走镜像，不再受上游漂移影响。
  - **验证**：291 passed；`quick_check` 13/13 恢复全绿（此前因两个仓库删除掉到 11/13）；
    三个镜像逐一实测下载且 sha256 与 `config/mods.lock.json` 逐字节一致；
    `warmup` 实测从镜像下载成功（并先按设计拒绝了本地残留的旧 CE 缓存）；
    `build zip` 2/2 成功；两个 1003 产物内嵌的 CE 载荷 sha256 实测等于 `9d318e81…`；
    `au_artifact_check` 对两个产物 `success=true, errors=[]`。
  - **状态边界**：三个镜像的载荷字节与换包前/删库前一致或已静态核对，但
    `dev2601001` 与 `1.20` 这两版 **尚未真机复测**；上一个通过 B2 的
    `dev260928` 结果不被追溯套用。

- **Cheat Extended 换通道并纳入 digest 锁（2026-10-02）**：作者的
  `chris81605/Degrees-of-Lewdity_Cheat_Extended` 删除了可变 `Pre-release` tag，DOL-X 原
  `releases/download/Pre-release/cheat_extended.mod.zip` 开始返回 404。作者把同一开发线提升为
  正式 release `V1.20Beta`（`prerelease=false`，2026-10-01T15:19:17Z），资产
  `cheat_extended.mod.zip`，599033 字节，sha256
  `1a89383f1ae8dfe1a88ed84729bcf04f63c0545dc95d074cf80416779bb275ec`（与 GitHub digest 一致），
  `boot.json` 声明 `1.20(dev2601001)`、`GameVersion >=0.5.11.9`。
  - **静态差异（dev260928 -> dev2601001）只有三个成员**：`boot.json`（版本串）、
    `game/CE_Wardrobe.twee`（简繁标签）、`scripts/CE_safehouseCheat.js`（安全屋助手在解锁
    巨鹰飘窗前先初始化 `V.bird.materials` 与 `V.loftIngredients`，并加显式提前解锁警告——
    即反馈中的爆红修复）。`CE_environmentGuard.js` 行为字节不变：只把匹配 `/\bDoLP\b/i`
    的版本判为 DolPlus，DOL-X 的 `0.5.11.9` 不在其中，不会被自动禁用。
  - **`cheat_extended` 加入 `LOCKED_AU_PAYLOAD_CACHE_NAMES`**：该通道已被作者原位换包四次，
    tag 名从来不能标识字节。加入 fail-closed digest 锁后，陈旧缓存或换包资产会在构建前被拒绝
    并删除，而不是被静默打进产物。验证时该锁按预期先拒绝了本地残留的 dev260928 缓存，随后
    重新下载成功。
  - **`release_tag` / `download_url` 重指**到 `V1.20Beta`；`config/mods.lock.json` 的
    `last_tested_version` / `last_tested_sha256` / `last_tested_date` 同步更新。因资产会原位换包，
    继续保留 `include_prerelease_updates = true` 让周检比较 asset digest。
  - **状态边界**：上一个钉住的 dev260928 已于 2026-09-30 通过 B2 真机验收（CE 界面可开、
    渲染九个分类加言靈集面板）；dev2601001 本轮只做了静态差异核对与摘要锁定，**尚未真机复测**，
    因此状态记为 `digest-pinned-awaiting-device-recheck`，不计入已验证。

- **maplebirch 框架升级 v4.1.13 -> v4.1.14（尚未发布）**：官方资产
  `maplebirch-0.5.10.12-v4.1.14.mod.zip`，186903 字节，
  sha256 `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4`，
  与 GitHub Release digest 逐字一致，上游构建 commit `cf57f88c`。
  这推翻了 0808 当时"不混入 4.1.14"的决策，理由是升级面经字节级核对后确认为纯钉版号替换。
  - **只保留两个经真机证明仍有净收益的本地补丁**：pet remount 与 AU face variant。
    basehead fallback 已在本次单变量真机对照后退役，详见下方 Removed 段；构建不再解析或引用
    `aO` / `aP` / `aI` 等压缩局部名，也不再改写 `basehead.srcfn`。
  - **实物验证**：保留的 pet remount 与 AU face variant 两个补丁按构建顺序链式套用到真实
    官方资产后各返回 `patched`，每个 marker 各 1 次，成员清单与 `boot.json` 保持字节不变；
    `basehead.srcfn` 保持上游 `aO([候选, 回退])` 原样。新增回归测试明确拒绝重新引入
    对脸型 base-head 候选的直接 `.has()` 改写。
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
  - **验证状态**：basehead 退役并补齐 CRLF 门禁回归后的本机完整套件为 **269 passed**；
    从当前源代码构建的 AU-F APK 成功通过 zipalign、v1/v2/v3 签名验证和 AU 产物门禁，随后以
    本地测试证书原位覆盖安装到 MuMu 12。冷首开、八脸真实点击及 Start → Start2 桌宠重挂均通过，
    因此状态提升为 `runtime-smoke-passed`。该结论不外推到正式签名、base/AU-M/AU-A 或全功能。

### Removed

- **退役 Maplebirch basehead fallback 本地补丁**。这不是把修法从“硬编码压缩名”换成“动态解析
  压缩名”，而是完整删除该兼容面：`lyra/build.py` 不再改写 `basehead.srcfn`，
  `lyra/compatibility.py` 不再注册它，专属测试与夹具依赖一并删除。理由来自同一 AU-F 0810 APK
  制作的单变量 A/B 包：两包只在内嵌 Maplebirch 的一条 `basehead.srcfn` 表达式上不同，使用同一
  本地签名、同一份已校验恢复的 48,619,488 字节 WebView profile，在 MuMu 12 上各做两轮冷启动。
  - **未补丁组 2/2**：首次点击真实“角色创建 *”按钮时，会短暂请求
    `img/face/default/base-head.png`；`Renderer.ImageErrors` 分别在约 **0.84 秒**与 **1.64 秒**
    捕获一次后自动清除。桌宠最终分别在约 **1.81 秒**与 **4.05 秒**达到 17587/17588 个不透明
    像素，整个过程无可见错误红框。热状态逐个点击八个真实脸型链接时，8/8 都回退到
    `img/body/base-head.png`，没有 basehead 错误或可见 reporter，画布稳定在 17587–17626 像素；
    部分合法脸型路径仍有独立的 eyes/mouth ImageErrors，不属于本补丁退役结论。
  - **补丁组 2/2**：没有错误请求，但首次打开角色创建面板后 **17 秒内桌宠都未挂载**；末帧截图
    只有侧边栏小图，没有浮动桌宠。与此同时此前那个硬编码 `aP` 的 4.1.14 补丁曾在真实开局
    40 步制造 **81 条** `Error evaluating layer basehead property src`。动态解析版虽修掉当次改名，
    仍保留对第三方压缩局部结构的耦合，维护成本与失败面高于其避免的短暂自愈请求。
  - **结论边界**：0805 的 v4.1.13 用户录像仍是有效历史证据，本次 v4.1.14 A/B 不能反向否定它；
    但在当前待发布栈上，补丁没有证明净收益，因此选择最小改动：恢复上游行为、不另做独立 mod，
    也不把这个短暂且自愈的内部请求升级成玩家已知问题。新增负向回归断言，确保构建继续保留
    上游 `aO([候选, 回退])`，不再把脸型 base-head 候选改写成直接 `.has()` 判断。

### Fixed

- **整合包在 CI 上仍然进不了游戏：引导预算第二轮（2026-10-07，run 37532832848）**：
  240 步（约 240 s）仍然差一口气——四轴全部 `last passage='Start' after 240 steps`，
  最后 4 个动作都是 `dismiss_modal`（点击成功所以早停不触发）。同一 run 的
  `prepare` 里 `fixture_ladder capture` 用同一个（同样失败的）`_reach_gameplay` 之后
  继续 snapshot，却拿到 732 键夹具，证明包没问题、是共享 runner 上 37 个 mod 冷启动
  真的慢（capture 从启动到成功 250 s）。修复：`STARTUP_STEPS` 240 → **1,000**
  （约 15 分钟）并新增 **12 分钟墙钟硬上限** `STARTUP_DEADLINE_S`（`time.monotonic()`
  计量），boot 报告新增 `deadline_hit` / `elapsed_ms`，`_boot_failed` 报错文本带上
  这两项以便区分"慢"与"卡死"；新增 4 条单测（离开 Start 立即返回、无动作早停、
  重复 modal 点击不算早停、墙钟 deadline 生效）。
- **战斗前置保真 v3 全量回归（2026-10-07，`combat-personn-1007i`）**：119 行用最终 v3
  代码复跑，`ok 110 / soft_fail 2 / hard_fail 0 / fixture_insufficient 7 / mode:ok 4`
  （1007h 为 72/0/0/9）。两条 `soft_fail` 如实记为待归因：`Island Fight` /
  `Island Trap Fight` 的 win 路径结束时敌人还活着（`enemyhealth≈320/295`、
  `enemyarousal≈45`）；7 条 `fixture_insufficient` 全部是落点场景状态不足
  （`$pubfame.bailey` / farm `teams` / `robin` / `water` / `duo` / `status` /
  Island Wood 与 Street Car 的落点状态），台账见 `docs/AUTOMATED_PASSAGE_SWEEP.md` §8.11-8.12。
- **修复战斗前置的槽位不连续、分支串线与起始 flag 丢失（2026-10-07）**：41 条战斗入口复跑
  （`.local/sweep/combat-personn-1007f/`）暴露三个叠加根因，全部属于"合成前置不够像上游真实
  路径"，不改游戏数据、只改前置重放：
  - **链必须连续覆盖槽 1..N**：旧逻辑只看 `max(slot) >= need`，单条 `<<generate2>>` 被当成
    合法前置，槽 0 仍是夹具空壳；`combatinit` 把空壳标 `active` 后 `leftgrabnew` 读
    `$NPCList[undefined].penis` 抛错（Courtyard Crush / Docks / Home Intervene /
    Soup Kitchen / Street Collar 等）。`_maninit_slot_range` + `_maninit_run_covers` 现在要求
    生成串**连续覆盖 1..need** 且含递增 `$enemyno` 的宏，纯 `<<npc "Name" 3>>` 串不算。
  - **场景起始 flag 只写在 link body 里**：`<<link [[Fight them both|Courtyard Crush
    Fight]]>><<set $fightstart to 1>><</link>>` 的 flag 不在 passage 正文，只重放生成链会让
    `maninit` 被 `<<if $fightstart is 1>>` 跳过（`$combat`/`$enemynomax` 停在 0）。
    `LINK_BODY_RE` + `LINK_BODY_ALLOWED_MACROS` 白名单重放这些 flag，并**排除
    `<<endevent>>`**（它会清掉刚生成的 NPC）。
  - **链与 flag 必须来自同一分支**：`Widgets Street` 的夜分支（`beastNEWinit` + `generate2/3`，
    `$phase 1`）与昼分支（`generate1/2`，`$phase 2`）并存时，旧逻辑混用两边，导致
    `Street Collar Molestation` 的 phase-1 路径把空壳克隆进槽 1。`_maninit_slot_chain` 改为
    遍历每个 link 出现位置**各自的邻近窗口**，链与该 link 的 flag 取自同一候选。
  复跑（`.local/sweep/combat-personn-1007f/`）：Street Collar 由 hard_fail 转 ok。
- **修复 `<<personN>>` 引用闭包漏扫后继 passage 与 widget（2026-10-07）**：`Balloon Sex`
  入口正文没有任何 `person` 引用，落点 `Balloon Sex Finish` 渲染的
  `<<balloonRobinHelped>>` widget 内却调用 `<<person2>>`，因此夹具只造 1 个槽位并在落点抛
  `Undefined NPC in personselect 1`。新增 `build_widget_index`（从 passage store 抽取
  `<<widget "name">>` 正文）与 `person_reference_closure`（入口正文 + 最多 8 个直接后继 +
  widget 深度 2），闭包并入 `derive_precursor` 的槽位需求；同时修正 `personselect` 索引映射
  （widget 自述"calls are 0-5 corresponding to NPCs 1-6"，`<<personselect 3>>` 读的是
  `$NPCList[3]`，旧代码错映射成 `$NPCList[2]`）。复跑：Balloon Sex 由 hard_fail 转 ok。
- **修复标题含 NPC 名的战斗行只造一个槽位（2026-10-07）**：`Underground Robin Stage
  Molestation` 正文只 `<<set $enemyno to 1>>`，落点 `… Finish` 的**两个分支**都渲染
  `<<person2>>`；旧 `title-npc` 前置只重放 `<<npc "Robin">><<person1>>`，槽 1 是空壳。实测
  1007e/1007f 两次"通过"是靠上一个用例残留的 `NPCList[1]` 侥幸不留错（落点其实什么都没渲染），
  1007g 残留消失后暴露真实崩溃。修复：引用闭包对**所有** maninit 行生效（不再因标题含名而
  跳过），且在"场景需要多于 `$enemyno` 的槽位"时**优先采用上游自己的前驱生成链**
  （该行真实路径是 `Underground Robin Stage Intro` 的 `<<generate1>><<generate2>>`——
  Robin 在台上，不在 `$NPCList` 里）；只有找不到真实链时才回退到
  `<<npc "Name">><<generate2..N>>` 保留具名 NPC。静态影响面 1,570 行中 220 行
  （30 行改用真实前驱链、190 行补足槽位），全部是"多造槽位/更接近上游"方向；1,570 行
  重演 0 异常，`pytest` 95 passed（combat 轴）。
- **补全战斗槽位宏识别（2026-10-07）**：`Widgets NPC Generation` 的 121 个 widget 里，
  旧正则只认 `generateN` / `generatePolice N` / `generateBEAST N` / `beastNEWinit N` /
  `npc Name N`。逐个体检后补全：`<<generateRole N …>>` 的 `N` 是 **0-based** 槽
  （widget 自述 "Slot one would be 0"、内部调用 `generateNPC N+1`，所以
  `<<generateRole 1 0 "x">>` 单独出现**不算**覆盖槽 0）；数字粘在名字里的变体
  （`generatecf1` / `generatey3` / `generatep2` / `generatePlant1` / `generateym3`）与首参
  形式（`generatePolice` / `Temple` / `Demon` / `Security` / `Sailor` / `Confessor` /
  `Cultist` / `Doctor` / `SweaterWearer` / `NPC N`）一律 1-based 槽——它们最终都调用
  `generateNPC`，而 `generateNPC` 内部就是 `_n = N - 1` 且 `$enemyno += 1`；
  `<<generatel>>` 动态取 `$enemyno + 1`，只计递增、不证明槽位；`<<clearnpc>>`（含带参
  形式）作为**链边界**，任何链都不得跨过它，且它本身不被重放（每个用例前都恢复夹具，
  没有陈旧槽要清）。静态影响面 v2 → v3 共 155 行改用真实链或更贴合的链（96 行
  debug-menu → predecessor、41 行 predecessor → predecessor、18 行 title-npc →
  predecessor），例：`Bailey Sheet Fight` 由兜底的 `Farm Road Widgets` 链改为上游真实链
  `<<generateRole 0 0 "thug">>…<<generateRole 3 0 "thug">>`。真机复跑 1007h
  （81 行）：`ok 72 / soft_fail 0 / hard_fail 0 / fixture_insufficient 9 / mode:ok 4`，
  9 条 `fixture_insufficient` 全部是落点场景状态不足（`$pubfame.bailey` / farm `teams` /
  `robin` / `water` / `duo` / `status`），逐条台账见 `docs/AUTOMATED_PASSAGE_SWEEP.md` §8.11。
- **修复整合包在 CI 上无法进入游戏（引导步数不足，2026-10-07）**：run 37513170382 的
  prepare 全绿（真实整合包 + 身份核验 + 现场 capture 夹具都成功），daily 四轴却全部
  返回 0 结果，报 `bootstrap did not reach gameplay; last passage='Start' after 60 steps`。
  同一 runner 上 `fixture_ladder capture` 用 90 步引导成功——整合包要等 30+ 个 mod
  加载完才离开 `Start`，CI 冷启动远超本机（本机 4 步进入 gameplay）。修复：
  `tools/passage_sweep._reach_gameplay` 预算 60 → **240 步**并新增早停（连续 40 步
  无可点击动作立即退出、记录步数/动作轨迹/耗时），`sweep_flow_assertions._session`
  与 `env_matrix` 同步使用同一预算，五个 sweep 工具不再各写各的步数。
- **修复战斗"无控件"误判与终局判定被状态重置骗过（2026-10-07）**：11 soft_fail +
  3 fixture_insufficient 逐条现场取证后确认两条旧判定错误。其一，`#listContainer`
  无控件是 DoL 的"无力"机制（双臂 bound + `pain≥100` 且 `willpowerpain=0`，或窒息
  两段式），游戏唯一出路是点击过场"继续"链接；`drive_combat` 现在调用新增
  `_advance_passage`（优先 `#next`、兼容淡入链接的最多 8 次轮询）照常推进，
  只有连继续链接都没有才保留 soft_fail。其二，兽交 `Finish` 会重置
  `$enemyarousal`（573.66 → 26.66），旧判定只看最终状态因此报 unknown；
  `classify_outcome` 现在同时参考**最后一个战斗活跃回合**快照与落点 passage 源码的
  `<<endcombat>>`，新增 `end` / `end_player_orgasm` 如实终局；原型矩阵 win 路径仍
  强制 `win`（`end*` 依旧 soft_fail），口径不放松。
- **修复战斗入口缺少游戏自身生成前置链**（2026-10-07）：20 条战斗硬失败逐条归因后确认，
  全部源于"直接跳入"绕过了上游自己的 `generate1/person1`、`beastNEWinit` 等生成步骤，
  空壳 `NPCList` 让手部渲染读到 undefined 而抛错（`NPC hand action unaccounted for` /
  `frontarm property src`）。`tools/combat_sweep.py` 的 `derive_precursor` 现在按源码顺序
  重放规范链——`$enemyno` 为 N 时生成 `generate1..N + person1..N`；野兽场景重放前驱事件里
  的完整链（如 Beach Phallus Dog 的作者注释链 `<<clearnpc>><<beastNEWinit 1 dog>><<generate2>>`，
  先清槽再生成野兽、人类放后面）；每条结果记录 derivation basis。定向复跑 20 条：
  `hard_fail` 2 → 0，Beach 与 StreetEx4 均进入战斗并产出终局路径证据（随后归入
  soft_fail 待继续归因，未洗绿）。
- **修复控制模式检查的假 hard_fail 与不可见的 SugarCube 内联报错（2026-10-07）**：归因复跑
  （`.local/sweep/combat-hardfail-attr-1007c/`）里 4 种控制模式全部 `hard_fail`，报
  `NPC hand action unaccounted for`；逐条取证后确认是测试器缺陷而非游戏缺陷——`--tier
  initiators` 下 `pick_mode_entry` 只认 archetype 矩阵才有的 `path=="win"`，退化到第一行，
  且重进战斗时不重放 `<<generate1>><<person1>>` 前置链，`$NPCList` 只剩 5 key 空壳。
  修复后复跑：`mode:ok 4`，控制模式入口与 precursor basis 写入报告 `modes_entry`。同一次复核
  还发现 SugarCube 把 widget 报错渲染成 `#passages .error-view`（`span.error`），JS 错误钩子
  看不到，于是一个"报错后原地循环"的场景只表现为 `stalled: 3 rounds without state change`；
  `COMBAT_STATE_JS` 现在采集该内联错误（`kind: sugarcube.dom`）并保留 `domErrors`，
  `Undefined NPC in personselect N` 会被提取成 `missing: NPCList[N-1]` 写进台账。
- **新增战斗"场景自身退出口"终局判定（2026-10-07）**：部分场景不写 `<<endcombat>>`，而是在战斗
  passage 内判断 `<<if _combatend or $timer lte 0>>` 后跳到 `... Finish`（1007c 观测到
  `Underground Film Molestation` 24 回合 `$timer` 归零）。`classify_outcome` 现在回读最后一个
  战斗活跃 passage 的源码，命中该守卫时记为 `scene_end` 并在 detail 明确写 "enemy not
  defeated"，不再报 unknown；原型矩阵 win 路径仍只接受 `win`（`scene_end` 依旧 soft_fail），
  报告新增 `outcome_counts` 与 `landing_evidence`（落点源码长度 / 是否含 `<<endcombat>>`）。
- **修复 `<<personN>>` 直接渲染导致的战斗前置不足（2026-10-07）**：`Underground Robin Kiss
  Molestation` 自身 `<<set $enemyno to 2>>` 却直接渲染 `<<person4>>`，命中游戏自己的
  `Undefined NPC in personselect 3`（旧版被误记为 stalled）。上游真实路径是前驱
  `Underground Robin Kiss Intro` 的
  `<<generate1>><<npc Robin 2>><<generate3>><<generate4>>`。`derive_precursor` 现在对 maninit
  行先比对该行引用的最大 `<<personN>>` 与 `$enemyno`，不足时在关卡图（深度 ≤2）里寻找前驱
  自己的连续槽位生成串并原样重放（basis `predecessor:<passage>:slotsN(personN)`），找不到才
  退化为 `debug-menu:generate1..N+person1..N(personN)`。全量 1,570 行中 26 行命中该分支
  （12 行前驱串、14 行 debug-menu 兜底），不修改任何全局夹具字段。
- **修复云端验收载体身份（2026-10-07）**：run 37500965698 暴露两个静默缺陷——
  `.github/workflows/sweep.yaml` 的 prepare 没有传 `--tag`（构建成上游最新 0.5.12.13，
  不是仓库锁定的 0.5.11.9），且只上传 prepare 产出的 HTML（既没有 `img/`，导致天气
  画布 `drawImage` 把战斗原型矩阵打成 104/104 假失败；也没有 DOL-X mod 栈——prepare
  HTML 内嵌 24 个 payload，真实整合包 37 个）。工作流现在在 prepare 内完成
  `prepare --tag` → `warmup --codes` → `build zip --codes`，用新增
  `tools/target_package_check.py`（`StartConfig.version` + 期望 Mod 名单 + 最少 payload
  数）在 prepare 与每个浏览器分片启动前 fail-closed 复核，只上传已核验构建产物；
  四个 sweep 工具原生接受 `.zip` 载体。本地证据：整合包 `ok version=0.5.11.9 mods=37`、
  prepare 空壳同命令 exit 1、整合包 passage 抽样 20/20 ok。
- （证据归类修正，无运行逻辑变化）**AU 换脸的玩家可见故障主要出现在桌宠，但根因仍是共享的
  `facestyle/facevariant` 非法组合，不是桌宠没有收到刷新**。MuMu 12 上对当前 AU-F 候选做了
  调用链追踪与单变量 APK A/B：八个真实脸型入口都会执行
  `updatesidebarimg -> pet.sync -> requestAnimationFrame -> pet.render`，且 `pet.sync()` 开始前
  sidebar cache 已经提交新脸型；去掉且只去掉 AU variant runtime IIFE、保留 pet remount 后，
  七个 AU 脸型全部形成 `style/default`。角色预览因 fallback 仍可能显示一个新脸或传统脸，桌宠则
  可能闭眼、缺眼或整张空白，所以玩家观察到“侧边栏变了，桌宠没变”是合理的表象。恢复合法仪态后，
  八个桌宠画布均非空且哈希随脸型变化。结论：保留当前状态选择补丁，不新增第二条桌宠同步路径。
  同轮也纠正了验证边界：0810 basehead 报告中仍有合法路径的 `eyes.png` / `mouth-smile.png`
  ImageErrors；它们不是 basehead 错误、未形成可见 reporter，但不能再概括成“零图片缓存错误”。

- **修复 AU 源输入与产物门禁把 CRLF HTML 误判为 Passage 漂移**：当前汉化 Release 的 APK
  `index.html` 使用 CRLF，而四段精确上下文常量使用 LF；旧实现直接按原始字节/字符串计数，导致
  真实内容完全一致时仍报 `legacy_switch_contexts=[0,0,0]` 并拒绝构建，独立 AU 产物审计也会
  对成功构建的同一 APK 二次误报。构建门禁和审计器现在只在**比较副本**中把 CRLF/CR 规范为 LF，
  原 HTML 不写回、不改字节，随后仍要求三处切脸上下文各恰好 1 次、迁移上下文恰好 1 次、旧预
  汉化补丁为 0。新增构建门禁与 APK 审计两项 CRLF 回归；非 UTF-8 前后缀无损和真实漂移
  fail-closed 测试继续通过。

- （无代码改动，仅记录真机验证结论）**AU-F 真机验证：另两个补丁在 4.1.14 上运行时生效**。
  用 CI run `31296592461` 产出的 AU-F APK（132345566 字节，正式签名证书
  `b21cd15b…829ece6`）以 `adb install -r` 覆盖安装到 0808 版本之上：
  - **桌宠重挂正常**：连续四次导航（Start → Orphanage Intro → Start → Bedroom，全部经
    `Story.has()` 确认存在）每次都自动恢复为 1 子节点、**17587/17588 个不透明像素**，
    与 0808 基线一致（对应带穿着的宏路径，而非 16316 的裸模退化）。说明 4.1.14 新注册在
    `:storyready` 上的怀孕监听器没有干扰重挂订阅。
  - **AU 脸型补丁生效**：`setup.faceVariantOptions` 含全部八种注册脸型，每种暴露真实变体名，
    而不是无效的 style/default 组合。
  - **存档通路可用**：走游戏自己的 IndexedDB 层完成 存档 → 读档 往返，
    `idb.saveState` 返回 true、`getSaveDetails` 列出已写槽位、`idb.loadState` 完成，零抛错。
  - **后续状态**：上述 2026-08-09 结论保留为中间回归证据。2026-08-10 已完整退役 basehead
    补丁，并从当前源代码构建新的 AU-F 本地测试签名候选；该候选通过产物审计、冷首开、八脸真实
    点击与 Start → Start2 桌宠重挂，当前准确状态为 `runtime-smoke-passed`。
  - **未能验证的部分（如实记录）**：原定"加载已有 0808 存档"这一项**没有素材**——
    这台设备的 `degrees-of-lewdity` 存档库 `saves` / `details` 两个 store 计数都是 0，
    即 0808 那次安装从未存过档（配置类数据恢复正常，可确认不是恢复失败）。
    因此长期存档的迁移表现仍未测试。4.1.14 新增的 kaiju 遮罩在 0.5.10.12 上是死代码：
    构建产物中字面量 `kaiju costume` 出现 0 次、APK 内无任何 kaiju 图片资源，无法触发。

### Added

- **全 passage 自动扫描 + 关键功能流断言（Engine A，2026-10-04）**：新增
  `tools/passage_sweep.py` 与 `tools/sweep_flow_assertions.py`，把 2026-06
  `docs/TESTING_DECISION_SUMMARY.md` 的"不建议实施全自动化"结论变为落地流程：
  对构建产物"每个 passage 真实渲染一遍 + 关键功能流真断言 + 基线对比只报新增回归"。
  - **首跑实测（0.5.11.9-XFox-1.0.0a 1004 构建）**：15,627/15,627 passage 全部渲染，
    `ok` 15,619 / `fixture_insufficient` 8 / `hard_fail` 0 / `soft_fail` 0；
    `landed == requested` 15,627/15,627；p50 80ms、p90 202ms；单页长跑 28 分钟无中断。
    8 条 `fixture_insufficient`（`TimeTest` + 7 条 `Skyscraper *`）均为新游戏夹具
    缺深层状态，非游戏缺陷。
  - **判定分层 + 基线**：`ok` / `soft_fail` / `hard_fail` / `fixture_insufficient`
    四档；首跑封基线，之后只报新增回归（含"夹具缺口恶化为真 bug"的严重度升级）。
  - **关键流断言**：mods / saveload / ce-panel / au-face（8 脸型桌宠画布非空且像素互异）
    / morelove；非 AU 产物如实返回 `not_applicable`，不假通过。
  - **验证**：`310 passed`（含新增 `tests/test_passage_sweep.py` 19 条）；
    使用说明、判定规则与已知限制见 `docs/AUTOMATED_PASSAGE_SWEEP.md`。
  - **边界**：夹具只有新游戏深度；不检查视觉正确性；Engine B（MuMu 真机 CDP 门禁）
    仍待建。

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

- **修复 AU 换脸后桌宠与角色预览表现不一致、桌宠闭眼或空白，并迁移已保存的非法组合**：
  DoL 0.5.10.12 约定每个脸型的首个仪态代码值必须是 `default`，角色创建、镜子和作弊页三个
  交互入口在切换脸型后都把 `$facevariant` 硬设为 `default`。AU model 脸型实际注册值则是
  “大眼鼠鼠”“猫猫脸”“Q萌一号”等真实图片目录名，没有非传统脸型的 `default` 目录；因此只点
  脸型会形成无效的 `facestyle/default` 组合。框架仍会刷新角色预览和桌宠，但两条渲染路径的
  fallback 不同：预览可能看似已经换脸，桌宠则可能显示另一张退化脸、闭眼或空白，直到玩家再点
  一个仪态。AU 三码现在复用 Maplebirch 已有的
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
