# DOL-X 自动化测试套件（Engine A 总说明）

**创建**: 2026-10-04（全 passage 扫描）／**扩写**: 2026-10-05（剧情·战斗·环境 第二期）
**适用版本**: 0.5.11.9-XFox 1.0.0a 及之后
**相关工具**: `tools/passage_sweep.py`、`tools/scenario_sweep.py`、`tools/combat_sweep.py`、
`tools/env_matrix.py`、`tools/fixture_ladder.py`、`tools/save_safety_guard.py`、
`tools/report_sanitize.py`、`tools/sweep_flow_assertions.py`
**相关测试**: `tests/test_passage_sweep.py`、`tests/test_scenario_sweep.py`、
`tests/test_combat_sweep.py`、`tests/test_env_matrix.py`、`tests/test_fixture_ladder.py`、
`tests/test_save_safety_guard.py`、`tests/test_report_sanitize.py`

> 本文是 Engine A 测试套件的总说明。§1-§2 是设计理由，§3 起是第二期新增的
> 三轴（剧情/战斗/环境）、夹具阶梯、两层跑分与 CI 工作流；passage 轴原有的
> 实测数据保留在 §8。

---

## 0. 一句话

用本地 headless Chromium 打开我们自己构建的 HTML，把**全部 15,627 个 passage**
逐个真实渲染一遍，用分层判定 + 基线对比，只报"新增的"渲染回归；
再补 5 条关键功能流的真断言。一条命令跑完，全部运行时注入，
不碰构建配置、不可能泄漏进发行包。

---

## 1. 为什么推翻 2026-06 的"6-9 个月"结论

2026-06 的评估（见 `TESTING_DECISION_SUMMARY.md` 原文）把"全自动化"默认成了：
手写 200-500 条端到端用例 + 断言每个条件分支。2026-10-04 的实测推翻了它的成本模型：

- 条件分支共 92,146 个（`<<if>>` 68,153 + `<<elseif>>` 23,993），逐组合断言数学上不可行；
- 但"每个 passage 都真实渲染一次"完全可行：实测中位数 **72ms**（300 抽样）/
  **80ms**（全量），15,627 条约 28 分钟跑完；
- 关键洞察：passage 渲染本身就会执行它内部的宏、widget、`<<set>>` 和变量读取，
  "渲染过"已经覆盖了"这段代码能不能跑"的主要部分。

于是目标收敛为：**全部 passage 真实渲染 + 关键功能流断言 + 只报新增回归的基线机制。**

---

## 2. 两个引擎

| 引擎 | 载体 | 用途 | 状态 |
| --- | --- | --- | --- |
| **A（快）** | 本地 headless Chromium 打开构建产物 HTML | 全量扫描、日常回归、发版前 | 已实现 |
| **B（法官）** | MuMu 模拟器里的 APK，走 CDP | 发版门禁 | 计划中 |

Engine A 的全部注入都发生在运行时：`add_init_script` 安装错误采集器 +
`:passagedisplay` 钩子 + 内存中的 fixture。**不改构建配置、不改产物文件**，
所以不可能把测试代码带进发行版。

---

## 3. 快速开始

```powershell
# 前置：Python 3.11+、pytest、playwright；本机有 Chrome/Edge（自动回退 channel）
$env:PYTHONIOENCODING='utf-8'

# 1) 抽样冒烟（推荐先跑）
python tools\passage_sweep.py "workspace/prepare_package/zip/Degrees of Lewdity.html" `
  --sample 300 --out .local/sweep/out-smoke

# 2) 全量扫描 + 封存基线
python tools\passage_sweep.py "workspace/prepare_package/zip/Degrees of Lewdity.html" `
  --out .local/sweep/full --save-baseline

# 3) 之后每次构建：与基线对比，只看新增回归
python tools\passage_sweep.py "workspace/prepare_package/zip/Degrees of Lewdity.html" `
  --out .local/sweep/run --baseline .local/sweep/full/passage-sweep-baseline.json

# 4) 关键功能流断言（mods / saveload / ce-panel / au-face / morelove）
python tools\sweep_flow_assertions.py "output\DoL-0.5.11.9-XFox-1.0.0a-au-f-1003.zip" `
  --flow all --out .local/sweep/flows
```

参数：`--limit` `--sample` `--seed` `--timeout-ms` `--headful` `--baseline`
`--save-baseline` `--bootstrap-settle-ms`。zip 会被解包到临时目录再跑（退出时自动清理）。

---

## 4. 判定分层（五档，所有轴统一）

| verdict | 含义 | 处理方式 |
| --- | --- | --- |
| `ok` | 渲染完成、有 passage DOM、有文本 | 记入基线；之后变非 ok 即回归 |
| `soft_fail` | 渲染了但超时未完成 / 空内容 | 观察项；稳定复现可封为新基线 |
| `hard_fail` | 未捕获异常 / 引擎抛错 / 没有 passage 节点 | 真问题，需要人看 |
| `fixture_insufficient` | 报错属于"前置状态不足"（is not defined / cannot read properties…） | **不算 bug**：这条 passage 需要更深的存档状态 |
| `not_applicable` | 该检查在此产物/环境不适用（如非 AU 产物跑 au-face） | 如实记录原因，不算通过也不算失败 |

夹具（fixture）来源：真实点过启动门后的新游戏快照（约 780 个变量、118KB JSON），
每条 passage 渲染前用 `structuredClone` 还原，保证互不污染、可重复
（同一个 `--seed` 结果一致）。

为什么"进不去的 passage"不算 bug：DoL 有大量 passage 只在特定剧情/战斗/遭遇状态
下才可达；用新游戏快照强行 `Engine.play` 进去时，报"读不到某状态"属于夹具边界，
不是游戏坏了。这些条目会稳定留在基线里，不会淹没新回归。

### 4.1 测试轴总览（第二期）

| 轴 | 工具 | 规模 | 日常档 | 发版档 |
| --- | --- | --- | --- | --- |
| passage 渲染 | `tools/passage_sweep.py` | 全量 15,627 条 | 300 抽样 | 全量 + 夹具/上下文 |
| 剧情场景 | `tools/scenario_sweep.py` | 363 行 = 331 可点击 + 32 分隔标题 | 全部 | 全部 + 基线封存 |
| 日循环 | `tools/scenario_sweep.py --suite dayloop` | 1 条真实游玩流程 | 跑 | 跑 |
| 战斗 | `tools/combat_sweep.py` | 原型矩阵 ~25-30 × 4 路径 + 4 控制模式；全量入口 1,570 | 原型矩阵 | `--tier initiators` |
| 环境 | `tools/env_matrix.py` | 环境敏感 passage × 8 上下文；全量 × 4 上下文 | daily | full |
| 关键功能流 | `tools/sweep_flow_assertions.py` | 5 条流（mods/saveload/ce-panel/au-face/morelove） | 跑 | 跑 |

### 4.2 两层跑分（时间预算）

| 档位 | 覆盖面 | 时间预算 | 载体 |
| --- | --- | --- | --- |
| **日常档** | 300 passage 抽样 + 331 场景 + 日循环 + 战斗原型矩阵 + 4 控制模式 + 环境日常档 + 5 条功能流 | ≤ 60 分钟 | 本机 |
| **发版档** | 全量 passage + 363 场景 + 1,570 战斗入口 + 环境全矩阵 | 本地 3-4 小时 | 本机 |
| **CI 档** | `full` 与 `combat-full` 两次手动触发，各 < 3.5 小时（单 job 上限 210 分钟） | GitHub Actions |

发版门槛：三轴 0 `hard_fail` 且无新增回归；战斗 `fixture_insufficient` 列表与基线一致或更少；
日循环为 `ok` 或如实的 `not_applicable`。

### 4.3 夹具阶梯与存档安全

`tools/fixture_ladder.py` 提供 `capture`（合成快照）/ `from-save`（导入可丢弃的 `.save`，
真实存档必须 `--allow-real`）/ `sanitize`（剥离姓名、路径）/ `verify`（格式与必需键校验）/
`list`（打印清单）。夹具统一放 `.local/fixtures/`（gitignore，永不入库），
`index.json` 记录来源、日期、游戏版本、字节数与 sha256。

当前本地夹具：

| 文件 | 键数 | 字节 | 说明 |
| --- | --- | --- | --- |
| `base-1004.json` | 780 | 211,352 | 2026-10-04 合成基线（file sha256 `7d2406b9…`） |
| `base-1004-fix8.json` | 782 | 174,170 | §8.2 的 fix8 合并版（file sha256 `d59e8b8d…`，payload sha256 `249d05e4…`） |
| `selftest-roundtrip.json` | 780 | 207,880 | `from-save` 回环自测产物（已脱敏） |

`tools/save_safety_guard.py` 对仓库做 fail-closed 检查：跟踪文件里出现 `*.save`、
`.local/` 之外的夹具载荷、LZString 存档块或本机绝对路径（仓库根目录、用户目录的
具体前缀）即失败；本地实测扫描 162 个仓库文件全部通过，另有 16 条 pytest 覆盖守卫逻辑
（含"故意放一个假 `*.save` 必须失败"的取证测试）。

### 4.4 各轴用法（第二期）

```powershell
$FIX = ".local/fixtures/base-1004-fix8.json"
$HTML = "workspace/prepare_package/zip/Degrees of Lewdity.html"

# 剧情场景（331 个可点击行）+ 日循环
python tools\scenario_sweep.py $HTML --fixture $FIX --suite scenarios --out .local/sweep/scenarios
python tools\scenario_sweep.py $HTML --fixture $FIX --suite dayloop   --out .local/sweep/dayloop

# 战斗：日常原型矩阵（含 4 控制模式）/ 发版全量入口（可 --resume）
python tools\combat_sweep.py $HTML --fixture $FIX --tier archetypes  --out .local/sweep/combat
python tools\combat_sweep.py $HTML --fixture $FIX --tier initiators --resume --out .local/sweep/combat-full

# 环境矩阵：先 dry-plan 看展开数字，再真跑
python tools\env_matrix.py --target $HTML --tier daily --dry-plan
python tools\env_matrix.py --target $HTML --fixture $FIX --tier daily --out .local/sweep/env-daily
python tools\env_matrix.py --target $HTML --fixture $FIX --tier full  --out .local/sweep/env-full
```

要点：

- 场景清单运行时读 `setup.debugMenu.eventList`，与静态 HTML 交叉核对，生成
  `.local/sweep/scenario-manifest.json`；游戏更新导致增删时报告差异而不是静默跳过。
- 战斗自动驱动在 `#listContainer` 选 `input.macro-radiobutton` → Enter 确认 → 比对状态增量；
  连续 3 回合无状态变化记 `soft_fail`（卡死）；4 种控制模式（Radio / Radio(c) / Lists / List(w)）
  各打 ≥3 回合的真实 DOM 操作测试。
- 环境 daily 的 8 个上下文：春晨晴 / 夏午雷暴 / 秋昏雨 / 冬夜雪 / 万圣节夜 / 圣诞晨 / 血月夜 /
  上课日；full 的 4 个：白天晴 / 夜雨 / 冬雪 / 血月夜。用游戏自己的
  `Time.timeTravel` / `Weather.set` / `Weather.setTemperature` / `V.halloween` / `V.christmas` /
  `V.moonstate` 注入，**读回校验后才开跑**；读回不一致按设计记 `hard_fail`，绝不带错误环境继续。
- passage 轴第二期新增 `--fixture` / `--fixture-patch` / `--context` / `--only-file` 四个参数，
  基线在有夹具/上下文时按 `{fixture}__{context}` 分组封存副本（`.local/sweep/baselines/`）。

### 4.5 报告脱敏（离开本机前）

`tools/report_sanitize.py` 把仓库/家目录路径替换为 `<repo>` / `<home>`、其它绝对路径替换为
`<abs-path>`、LZString/长 base64 替换为 `<redacted-save>`、大夹具 dump 替换为
`{"__redacted__": true, "keys": N}`；`--check` 模式在仍发现脏数据时 exit 1。
CI 在"脱敏 → 复核"两步之后才上传 Artifact。

---

## 5. 基线对比

`diff_against_baseline()` 输出四类：

- `regressions`：verdict 变差（ok→非 ok，或 `fixture_insufficient`→`hard_fail` 这类严重度升级）
- `fixed`：变好（非 ok→ok）
- `changed`：非 ok 之间的降级（如 `hard_fail`→`soft_fail`），列出但不当作回归
- `unseen_in_baseline`：基线里没有的新 passage

---

## 6. 关键功能流断言（Engine A）

`sweep_flow_assertions.py --flow all` 当前 5 条流（对 AU-F 1003 产物实测 5/5 通过）：

| flow | 断言 | 实测（0.5.11.9-XFox-1.0.0a AU-F 1003） |
| --- | --- | --- |
| `mods` | maplebirch / cheat extended / longer-combat / yanling 四个 mod 运行时都在 | pass（39 个内嵌 mod） |
| `saveload` | 存档写入→改动→读回，passage + 5 个变量一致 | pass（槽位 7，`window.loadSave` 读回） |
| `ce-panel` | 打开 CE 面板：`CEiconClicked()` → `#customOverlay[data-overlay=CEcheatMenu]` 可见 | pass |
| `au-face` | 8 种 AU 脸型逐个切换后桌宠 canvas 非空且像素数互异 | pass：基线 17588px、Twinkle 17626px、spread 38px |
| `morelove` | More Love 食物偏好入口渲染成功 | pass（`Food Preference`，text_len=81） |

非 AU 产物跑 `au-face` 会如实返回 `not_applicable`（不是假通过）。

---

## 7. 已知限制（诚实清单）

1. **夹具只有新游戏深度**：需要深层存档状态的 passage 会落在 `fixture_insufficient`。
   后续可以做"夹具强化"（用玩到中期的真实存档做快照），当前版本先保证"能跑、能对比"。
2. **异步错误归因**：passage A 触发的延迟异常可能记到 passage B 的窗口；
   极端情况有 ±1 条噪声，基线对比可抑制影响。
3. **Engine A ≠ 真机**：headless Chrome 与 Android WebView 的差异（触摸、性能、字体）
   由 Engine B 覆盖。
4. **不检查视觉正确性**：只检查"渲染成功 + 有文本 + 关键流像素/入口断言"。
5. **单页长跑**：全量在一个页面里跑完；SugarCube 的 `Config.history.maxStates=5`
   已限制历史内存。注意内存压力会拖慢尾段：本机 16 GB 上同时开着浏览器/模拟器时，
   尾段速度一度从 ~20 条/s 掉到 ~7 条/s（整轮 28 分钟，未中断）。跑全量前先关掉
   其它吃内存的程序，扫描更稳。
6. 报告里 `console.error` 会被记录但不单独判失败（很多是游戏自带的天气/画布噪声）。
7. **日循环尚未走满一天**：当前 DOM 点击序列走到"出门"就停，时间只推进 0.03h，
   已被如实标记为 `soft_fail`；把"上学→放学→回家→睡觉"接上属于后续工作。
8. **环境矩阵的节日上下文**：`timeTravel` 不会触发游戏的跨日钩子，所以万圣节/圣诞
   是显式设置对应标志位（等价于"当天自然到达"的状态），并在读回校验里验证；
   血月是硬校验，上游若改名/去掉 bloodMoon orbital 会整条 `hard_fail` 而不是静默降级。
9. **战斗入口清单与备忘值差 19 条**：实测 `.local/sweep/combat-initiators.json` 为
   1,570，第二期调研备忘为 1,603；以实测清单为准，已知 5 个 `maninit` 原型因 base
   夹具缺 NPC bedsheet 数据落在 `fixture_insufficient`。
10. **环境矩阵口径比调研更宽**：daily 的"环境敏感 passage"实测 1,378（备忘 886），
   差 +492 来自 time_clock / day_state 的更宽口径，原因记录在代码注释与报告 meta 里。
11. **场景增量快照只到两层**：`widgets produced no observable state delta`（82/331）里
    有一部分是"改了嵌套对象内部字段、快照看不到"（如 `worn.under_upper.integrity`），
    不是没生效；这类行稳定停在 `soft_fail`，升级为 `hard_fail` 时基线 diff 仍会报回归。
12. **debug 菜单自身的缺陷按 `soft_fail` 上报**：0.5.11.9 的
    `<<parasiteProgressDay>>`（Pregnancy Progress Day/Week 两行）只定义了同名 JS 函数、
    没有注册宏；工具用 `upstream debug-menu defect (unregistered macro)` 如实标注，
    既不隐瞒也不当作渲染失败。

---

## 8. 实测数据（2026-10-04，0.5.11.9-XFox-1.0.0a 1004 构建）

- 冒烟：40/40 ok；
- 300 抽样：**300/300 ok、0 异常**；每 passage p50 72ms、p90 177ms、max 411ms；
- 全量 15,627：**15,619 ok + 8 fixture_insufficient，0 hard_fail、0 soft_fail**（§8.1）；
- 关键流：5/5（见 §6）。

### 8.1 全量结果（2026-10-04 首跑，已封基线）

- 命令：`python tools\passage_sweep.py "workspace/prepare_package/zip/Degrees of Lewdity.html" --timeout-ms 8000 --out .local/sweep/full-1004 --save-baseline`
- 对象：0.5.11.9-XFox-1.0.0a 1004 构建的 `Degrees of Lewdity.html`（82,267,118 B）
- 结果：**swept 15,627 / 15,627**；`landed == requested` 也是 **15,627/15,627**
  （无重定向、无静默回退）；`fatal_error` 为空。
- verdict 分布：`ok` **15,619** / `soft_fail` 0 / `hard_fail` 0 / `fixture_insufficient` **8**。
- 8 条 fixture_insufficient 全部可归因于"新游戏夹具缺深层状态"，不是游戏缺陷：
  - `TimeTest`（1 条）：读不到时间事件定义的 `name`；
  - `Skyscraper *`（7 条：Ruin / Fire / Party 6 / Ascend / Fall / Foundation / Structure）：
    读不到高楼剧情的 `progress` 状态；文本本身已渲染（text_len 91–828）。
- 耗时：p50 **80ms**、p90 **202ms**、p99 439ms、max 2,698ms；
  整轮墙钟 **约 28 分钟**（19:46:49 → 20:15:03，单页长跑，中途无重启）。
- 12 条 passage 附带了 console 噪声（`ImageLoaderHook ... imgList.length === 0`、
  天气/降水/雾 effect 绘制报错、`CanvasModel Example`），按设计不判失败，不影响 verdict。
- 基线文件：`.local/sweep/full-1004/passage-sweep-baseline.json`（本地，不入库）。
  之后每次构建只对比新增回归：
  `python tools\passage_sweep.py "workspace/prepare_package/zip/Degrees of Lewdity.html" --out .local\sweep\run --baseline .local\sweep\full-1004\passage-sweep-baseline.json`

### 8.2 fix8：8 条历史 `fixture_insufficient` 已用夹具补丁修到 `ok`（2026-10-05）

8 条 = `TimeTest` + `Skyscraper {Ruin, Fire, Party 6, Ascend, Fall, Foundation, Structure}`。
根因从真实报错栈定位（不是猜测）：

- `TimeTest`：`$timeDistortion` 未定义 → undefined 算术 → `Time.set()` 内
  `new DateTime(V.startDate + time)` 得到 NaN，读 `.name` 崩溃；
- 7 条 `Skyscraper *`：美术 `condition` 读 `V.avery_tower.progress`，而新游戏夹具里
  还没有这个对象（游戏自己的初始化是 `$avery_tower to {}` + `progress 0`）。

补丁 `.local/patches/patch-fix8-0511.json`：

```json
{
  "timeDistortion": 0,
  "timeStamp": 0,
  "avery_tower": {"progress": 0, "effects": [], "stage": 0, "intro": 0}
}
```

实测（同一份 82MB 真实载荷、`--only-file` 指定这 8 条）：

- 用 `--fixture base-1004.json --fixture-patch patch-fix8-0511.json`：`verdicts={'ok': 8}`；
- 用合并后的 `--fixture base-1004-fix8.json`（不带 patch）：`verdicts={'ok': 8}`。

### 8.3 剧情场景与日循环（2026-10-05）

- manifest：**363 行 = 331 可点击 + 32 分隔标题**，与静态 HTML 交叉核对一致；
- `--limit 12` 冒烟：12/12 `ok`；
- 全量 331 行（2026-10-05 修复后）：`ok=239 / soft_fail=82 / hard_fail=0 /
  fixture_insufficient=9 / not_applicable=1`；静态交叉核对报 1 条索引漂移
  （`Events#96`：静态 `Livestock Job Pig Rape` vs 运行时 `Forest Boar Rape`，
  计数一致、按索引比对时的错位），已如实写进报告；
- 修复前的 18 条 `hard_fail` 全部定位并归类：9 条"写未定义状态"→ 扩展
  `FIXTURE_MARKERS` 后归 `fixture_insufficient`；1 条年号范围写错（DoL 用虚构历法，
  游戏内年份是 361）→ 修检查；6 条 debug 作弊故意越界（`$awareness -= 200`、
  `Damage Chastity` 等）→ 改为"该行自己写入的越界值"备注；2 条上游 debug 菜单宏缺失
  （`<<parasiteProgressDay>>`）→ `soft_fail` 并标注 `upstream debug-menu defect`；
- dayloop（修掉早期假通过之后）如实结果：`ok=3`（起床/洗漱/出门）、`not_applicable=6`、
  fallback 0、stalled 0，存档往返 PASS；时间只推进 0.03h → 如实判 `soft_fail`
  （"走一天"的水龙头还没接上，没有被伪装成通过）。

### 8.4 战斗（2026-10-05）

- 4 种控制模式（Radio / Radio(c) / Lists / List(w)）真机全 PASS：逐回合 `enemyhealth` 下降、
  默认模式自动还原；
- 静态清单 `.local/sweep/combat-initiators.json`：`total=1570`
  （第二期方案里的备忘值 1,603 与之差 19 条，按实测清单为准，drift 已记录）；
- 已知限制：base 夹具缺 NPC bedsheet 数据，5 个 `maninit` 原型目前落在
  `fixture_insufficient`（不算 bug，基线记录在案）。
- **入口选择修复（同日第二轮）**：原型矩阵最初把 `beastNEWinit` 无 starter 的行
  （如 `Farmland Pigs` / `Wolf Bear` / `Widgets Maze`）当成"可玩"入口，实机全部
  `not_applicable`（只生成怪物，战斗在后续 passage 才开）。修复：
  `find_combat_link_target` 支持 wiki 链接 + `<<link [[...]]>>` widget 链接、
  最多 2 跳（`max_depth=2`）找到带战斗 starter 的落点；`choose_entry` 按
  "link_depth → starters → flags" 重新排序（`beast-pig/cat/fox/lizard/hawk/bear/boar/snake`
  共 8 个原型由此改为真实战斗入口，6/28 规格解析为真实战斗）；
  并修复两处状态泄漏（矩阵逐 job 前与控制模式跑前强制 restore）+ 一处
  `mode_entry is None` 时仍调 `run_control_modes` 的分支错误。
- **修复后全量原型矩阵实测**（`.local/sweep/combat-archetypes-final/`，28 规格 →
  104 jobs，5:15-5:45，约 30 分钟）：
  `ok=28 / soft_fail=14 / hard_fail=0 / fixture_insufficient=46 / not_applicable=16`，
  4 控制模式 `mode:ok`；`ok` 覆盖 dog/horse/lizard/cow/snake/stalk/plant 共 7 个
  原型（全部 4 路径），`not_applicable` 收敛到 cat/fox/wraith/possession 4 个
  （widget 库行与无真实战斗入口的行，如实记录），修复前是 12 个原型 48 条。
- `fixture_insufficient` 汇总：human/named 4 原型（NPC bedsheet 数据缺失）+
  beast 4 原型（wolf/pig/hawk/bear/boar，静态行无 link 落点）+ special 4 原型
  （tentacle/swarm/vore/hypno，action widget 渲染不出），全部为夹具/入口数据
  问题，不是游戏 bug。

### 8.5 环境矩阵（2026-10-05）

- `--tier daily --dry-plan`（真实产物）：`passages=15627 env_sensitive=1378 contexts=8 executions=11024`；
  口径命中：time_clock 943 / weather 481 / day_state 435 / holiday 270 / season 116 …；
  与第二期备忘的"886 条"差 +492，原因（更宽的时间/日夜口径）已写进代码注释与
  `meta.env_sensitive_rule.drift_note`，没有为了凑数收窄；
- `--tier full --dry-plan`：`15627 passages × 4 contexts = 62508 executions`；
- 小样本真机：`--tier daily --limit 8` → 8/8 `ok`；`--limit 32 --seed 5` 覆盖全部 8 个
  上下文，8 个上下文 `verified=True`、`reads_failed=0`，32/32 `ok`。
- **daily 全量真机**（`.local/sweep/daily-acceptance/env-daily/`，1:03-1:27，
  约 24 分钟）：11,024 执行 → `ok=11016 / soft_fail=0 / hard_fail=0 /
  fixture_insufficient=0 / not_applicable=8`；8 个上下文全部 `verified=True`、
  `reads_failed=0`。

### 8.6 单测

`python -m pytest -q`：**510 passed**（原 310 + 第二期新增 + 战斗入口修复
第二轮 +6；含 scenario 68、combat 49、env_matrix 27、fixture_ladder 20、
save_safety_guard 16、report_sanitize 11、passage_sweep 28 等）。

---

## 8.7 CI 手动工作流

`.github/workflows/sweep.yaml`，仅 `workflow_dispatch`，输入 `tier`：

| tier | 内容 |
| --- | --- |
| `daily` | 300 passage 抽样 + 全部场景 + 日循环 + 战斗原型矩阵 + 环境日常档 |
| `full` | 全量 passage + 全部场景 + 环境全矩阵 |
| `combat-full` | 全部战斗入口逐条打到终局 |
| `env-full` | 环境全矩阵单独重跑 |

流程：`checkout` → pytest → `prepare` 产出 HTML → **现场 capture 合成夹具** →
按档位跑工具 → `report_sanitize` 脱敏并 `--check` 复核 → 上传 Artifact。
单 job `timeout-minutes: 210`，`concurrency` 与 Build 分开排队；
**真实存档与个人路径永不进入 CI**。发版验收 = `full` + `combat-full` 两次手动触发。

---

## 9. 一键复现清单（发版前）

```powershell
$env:PYTHONIOENCODING='utf-8'
$FIX  = ".local\fixtures\base-1004-fix8.json"
$HTML = "workspace\prepare_package\zip\Degrees of Lewdity.html"

python tools\quick_check.py                                   # 网络/依赖 13/13
python -m pytest -q                                           # 全量单元测试（504）
python tools\save_safety_guard.py                             # 仓库存档安全守卫
python tools\au_artifact_check.py output\*.zip                # AU 产物审计

# 日常档五轴
python tools\passage_sweep.py $HTML --fixture $FIX --sample 300 --out .local\sweep\out-smoke
python tools\scenario_sweep.py $HTML --fixture $FIX --suite all --out .local\sweep\scenarios
python tools\combat_sweep.py $HTML --fixture $FIX --tier archetypes --out .local\sweep\combat
python tools\env_matrix.py --target $HTML --fixture $FIX --tier daily --out .local\sweep\env-daily
python tools\sweep_flow_assertions.py output\DoL-...-au-f-1003.zip --flow all --out .local\sweep\flows

# 发版级：全量扫描 + 与上一份基线对比
python tools\passage_sweep.py $HTML --out .local\sweep\full --baseline .local\sweep\full-1004\passage-sweep-baseline.json

# 报告离开本机前先脱敏
python tools\report_sanitize.py .local\sweep
python tools\report_sanitize.py --check .local\sweep
```

---

## 10. 产物目录

每个 `--out` 目录里至少一对 `*-report.json` / `*.md`（工具名可能是 `passage-sweep.*`、
`scenario-*`、`combat-*`、`env-*`、`flow-assertions.*`），内含逐条结果
（verdict / reason / 耗时 / 缺失变量 / 上下文）与五档计数：

- passage：`passage-sweep.json`（机器可读全量结果）+ `passage-sweep.md`（人读报告）；
- 场景/日循环：`scenario-sweep.json` + `scenario-manifest.json`（清单跨会话复现）；
- 战斗：`combat-sweep.json` + `combat-initiators.json`（入口清单，`--resume` 依据）；
- 环境：`env-<tier>-report.json` + `env-<tier>-report.md`（含 8/4 个上下文的读回状态）；
- `--save-baseline` 时另写一份基线到 `.local/sweep/baselines/`（passage 轴按
  `{fixture}__{context}` 分组）；功能流断言目录里是 `flow-assertions.json` / `.md`。

所有报告在离开本机前必须过 `tools/report_sanitize.py`。
