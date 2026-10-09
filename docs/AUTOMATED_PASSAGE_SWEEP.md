# DOL-X 自动化测试套件（Engine A 总说明）

**创建**: 2026-10-04（全 passage 扫描）／**扩写**: 2026-10-05（剧情·战斗·环境 第二期）
**适用版本**: 0.5.11.9-XFox 1.0.0a 及之后
**相关工具**: `tools/passage_sweep.py`、`tools/scenario_sweep.py`、`tools/combat_sweep.py`、
`tools/env_matrix.py`、`tools/fixture_ladder.py`、`tools/save_safety_guard.py`、
`tools/report_sanitize.py`、`tools/sweep_flow_assertions.py`、`tools/sweep_ledger.py`、
`tools/sweep_summary.py`
**相关测试**: `tests/test_passage_sweep.py`、`tests/test_scenario_sweep.py`、
`tests/test_combat_sweep.py`、`tests/test_env_matrix.py`、`tests/test_fixture_ladder.py`、
`tests/test_save_safety_guard.py`、`tests/test_report_sanitize.py`、`tests/test_sweep_ledger.py`、
`tests/test_sweep_summary.py`、`tests/test_sweep_workflow.py`

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
| **CI 档** | 手动 `workflow_dispatch`：`daily` 单 job；`full` = 4 passage 分片 + 场景 + 8 环境分片 + 汇总；`combat-full` / `env-full` = 8 分片 + 汇总（每 job 上限 210 分钟） | GitHub Actions |

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
- 云端分片（第二期收尾）：四套 sweep 工具都支持 `--shard-index/--shard-count`，报告带
  身份台账（`tools/sweep_ledger.py`）与 `completeness` 块；战斗 `--resume` 从台账合并
  历史结果（旧版只记完成键的检查点被显式拒绝），环境每会话重建浏览器并可从崩溃恢复；
  `tools/sweep_summary.py` 对全部分片做 fail-closed 汇总（缺片/重复/身份漂移退出码 1）。

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
- dayloop（2026-10-09 收口）：真实 UI 走完起床、洗漱、早餐、出门、上学、上课、
  放学、回家、睡觉；`ok=9 / fallback=22 / stalled=2 / not_applicable=0`，
  时间推进 **16.20h**、地点切换 70 次、存档往返 PASS、`hard_errors=0`。
  两条 `stalled` 是脚本化 Tutorial 战斗中"动作已点但 passage/时钟未动"的记录，
  后续导航仍真实完成 Tutorial，不把它们伪装成步骤完成。

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
- **前置保真六根因（2026-10-07）**：连续槽位覆盖、link-body 起始 flag、链与 flag
  同分支、后继 passage/widget 的 `<<personN>>` 闭包、具名行改用上游真实链、
  `generateRole` 等槽位宏识别（0-based 槽）——逐条证据与影响面见 §8.11。

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

`python -m pytest -q`：**597 passed**（原 310 + 第二期新增 + 战斗入口修复
第二轮 +6 + 云端分片设施 +33 + 战斗前置链 3 + 载体身份守卫 6 + 工作流契约 2 +
战斗前置保真 +6（§8.11 的具名行 / `generateRole` / `<<clearnpc>>` 边界回归）：
`sweep_ledger` 16、`sweep_summary` 6、
`target_package_check` 6、`sweep_workflow` 6 与 combat/env 测试扩写；
含 scenario 68、combat 95、env_matrix 27+、fixture_ladder 20、
save_safety_guard 16、report_sanitize 11、passage_sweep 28 等）。

---

## 8.7 CI 手动工作流

`.github/workflows/sweep.yaml`，仅 `workflow_dispatch`，输入 `tier`：

| tier | 内容 | 分片 |
| --- | --- | --- |
| `daily` | 300 passage 抽样 + 全部场景 + 日循环 + 战斗原型矩阵 + 环境日常档 | 单 job |
| `full` | 全量 passage + 全部场景 + 环境全矩阵 | passage ×4 + 场景 ×1 + 环境 ×8，另加汇总 |
| `combat-full` | 全部战斗入口逐条打到终局 | 战斗 ×8，另加汇总 |
| `env-full` | 环境全矩阵单独重跑 | 环境 ×8，另加汇总 |

云端四阶段结构：

1. **prepare**（≤120 分钟）：`checkout` → pytest → `prepare --tag <锁定 tag>` →
   `warmup --codes <构建码>` → `build zip --codes <构建码>` 产出**真实整合包** →
   `tools/target_package_check.py` fail-closed 身份核验（`StartConfig.version` +
   期望 Mod 名单 + 最少 payload 数）→ 用该产物**现场 capture 合成夹具** →
   把已核验的构建 ZIP、mods 清单与夹具作为 Artifact 上传，全部分片共享同一份产物。
   工作流输入：`tier` / `tag`（默认 `v0.5.11.9-1.0.0a-0915`）/ `code`（默认 base
   `15704320`）/ `expect_mods`。
2. **分片执行**（每分片 `timeout-minutes: 210`、`fail-fast: false`、`max-parallel: 4`）：
   每个分片下载同一份 HTML/夹具，以 `--shard-index/--shard-count` 运行并写身份台账
   （`tools/sweep_ledger.py`：`html_sha256`/夹具摘要/测试器版本/计划摘要 + 原子检查点；
   旧版只有完成键的检查点显式拒绝）与 `completeness` 块；环境分片每 500 条重建浏览器、
   崩溃最多重启 2 次，基础设施中断与用例结果分开记录。
3. **白名单导出**：每个分片先把报告按白名单复制到独立 `sweep-reports/` 目录，再
   `report_sanitize.py` 脱敏并 `--check` 复核，缺报告即失败；原始夹具与真实存档
   不进上传目录。
4. **summary**（≤30 分钟）：`tools/sweep_summary.py` 汇总全部 `sweep-*` Artifact，
   核对预期分片数、逐份 completeness、键重复/缺失与 `html_sha256`/`fixture_digest`
   身份一致性，任何异常退出码 1；缺分片、重复结果、身份漂移都不能封存为完整基线。

`concurrency` 与 Build 分开排队；**真实存档与个人路径永不进入 CI**。
发版验收 = `full` + `combat-full` 两次手动触发；分片数只影响调度，不改变覆盖范围。

### 8.8 载体身份：目标整合包 vs prepare 空壳（2026-10-06 → 2026-10-07）

2026-10-06 的云端 daily（run 37500965698）暴露了"全绿报告测的不是目标产品"这一类
静默缺陷，两个根因都在 prepare 阶段：

1. 工作流调用 `main.py prepare` **没有传 `--tag`** → 下载上游最新汉化 Release，
   当时构建出来的是 **0.5.12.13**，而不是仓库锁定的 0.5.11.9；
2. 只上传了 prepare 产出的 HTML → 分片手里既没有 `img/`（天气画布 `drawImage`
   全红，战斗原型矩阵 104/104 hard_fail，全部是基础设施伪失败），也**没有 DOL-X
   的 mod 栈**——prepare HTML 内嵌 24 个 payload（ModLoader 基础件 + ModI18N），
   而真正 build 出的整合包内嵌 37 个 payload（maplebirch / cheat extended /
   More Love / CustomHair / longer-combat / yanling / DOLI …）。

因此从 2026-10-07 起：

- 工作流在 prepare 内完成 `prepare --tag` → `warmup --codes` → `build zip --codes`，
  只上传**已核验的构建产物**；每个浏览器分片在跑测试前重跑
  `tools/target_package_check.py <zip> --expect "<名单>" --expect-version <版本> --min-mods 30`，
  版本或 Mod 缺失立即失败（fail-closed，不再产出误导性报告）；
- 四个 sweep 工具都原生接受 `.zip`（内部解包到临时目录，HTML 与 `img/` 同级），
  本地复现与 CI 使用同一份载体；
- 判定口径不变，但**§8.1–§8.5 的历史数字全部是在 prepare 空壳载体（无 mod）上测得的**，
  它们只代表"基础游戏 + 汉化"的覆盖基线；针对整合包（含 mod 栈）的基线需要在
  `output/DoL-*-base-*.zip` 上重新封存，不得把两类数字混用。

本地验证证据（2026-10-07）：

```powershell
# 真实整合包：版本与 mod 名单通过
python tools\target_package_check.py "output\DoL-0.5.11.9-XFox-1.0.0a-base-1003.zip" `
  --expect "maplebirch,cheat extended,More Love Interests Mod" --expect-version 0.5.11.9 --min-mods 30
# -> ok version=0.5.11.9 mods=37

# prepare 空壳：同样命令必须失败（守卫有效）
python tools\target_package_check.py "workspace\prepare_package\zip\Degrees of Lewdity.html" `
  --expect "maplebirch" --min-mods 30      # -> exit 1（24 < 30 且缺少 maplebirch）

# 载体冒烟：整合包（含 mod、img 同级）跑 passage 抽样
python tools\passage_sweep.py "output\DoL-0.5.11.9-XFox-1.0.0a-base-1003.zip" `
  --fixture .local\fixtures\base-1004-fix8.json --sample 20 --out .local\sweep\carrier-smoke-1007
# -> verdicts={'ok': 20}
```

### 8.9 CI 引导预算：整合包 60 步不够（2026-10-07，run 37513170382）

同一轮云端 daily 里，`prepare` 全绿（真实整合包构建 + 身份核验 + 现场 capture
夹具都成功），但 `daily` 分片四轴全部拿不到结果，报
`bootstrap did not reach gameplay; last passage='Start' after 60 steps`。

根因不是载体：**同一 runner 上 `fixture_ladder capture` 用 90 步引导成功抓住了
732 键夹具，而 passage_sweep / env_matrix 只给 60 步**。整合包要等 30+ 个 mod
（ModLoader / maplebirch 通知弹窗、汉化包）加载完才离开 `Start`，CI 冷启动比
本机慢得多；本机 4 步就能进入 gameplay，所以本地冒烟看不出来。

修复（2026-10-07）：

- `tools/passage_sweep._reach_gameplay` 默认预算统一为 **240 步**（900 ms/步），
  并新增**早停**：连续 40 步没有任何可点击动作立即退出，把步数、动作轨迹与
  耗时写进 `bootstrap` 报告，而不是白等满预算；
- `sweep_flow_assertions._session`（所有分片工具的公共会话）与
  `env_matrix` 同步使用该预算，五个工具不再各写各的步数。

**第二轮（2026-10-07，run 37532832848）：240 步仍然不够。** 四轴全部在引导阶段失败，
报 `bootstrap did not reach gameplay; last passage='Start' after 240 steps`，
最后 4 个动作全是 `dismiss_modal`（点击成功 → 早停永远不触发，预算被烧干）。
同一 run 的 `prepare` 里 `fixture_ladder capture` 用**同样的** `_reach_gameplay`
（同样失败）之后继续 snapshot，却拿到了 732 键夹具——说明包本身没问题，
是共享 runner 上 37 个 mod 的冷启动**真的慢**：capture 从启动到成功一共 250 s，
而 240 步预算约 240 s，正好差一口气。

修复（第二轮）：

- 预算改为 **1,000 步（约 15 分钟）**，并新增 **12 分钟墙钟硬上限**
  （`STARTUP_DEADLINE_S`），用 `time.monotonic()` 计量；真正卡死的引导仍有界失败；
- `deadline_hit` / `elapsed_ms` 写进 boot 报告，`sweep_flow_assertions._boot_failed`
  的报错文本带上这两项，方便下次直接区分"慢"和"卡死"；
- 单测覆盖：passage 离开 Start 立即返回、无动作早停、**重复 modal 点击不算早停**
  （正是本次 CI 的场景）、墙钟 deadline 生效（`tests/test_passage_sweep.py`）。

### 8.10 战斗"无控件"是游戏机制，不是夹具缺陷（2026-10-07）

针对 20 条 hard_fail 归因（`a394e99` 修复生成前置链）后剩余 11 soft_fail + 3
fixture_insufficient 的逐条现场取证，推翻了两条旧判定：

1. **"no action controls in #listContainer" 是 DoL 的"无力"状态**。实测
   `Office Security Molest`：双臂 `bound`、`pain=100.5`、`willpowerpain=0`，
   `#listContainer` 里只剩"手臂阵痛"文本，游戏给出的唯一出路是点击过场
   "继续"链接（`Man combat suffocated` 的窒息两段式同理，第二段还有
   1.5 s × N 的淡入动画后才出现 `#next`）。旧驱动在第一条无控件回合就判
   soft_fail，等于把"玩家只能挨着等剧情推进"误判成测试失败。
   修复：`drive_combat` 在无控件时调用 `_advance_passage`（优先 `#next`，
   其次"继续/Next"文案链接，最多 8 次轮询以等出淡入链接），照常推进回合；
   只有连继续链接都没有时才保留 soft_fail，并在 detail 里写明尝试次数。
2. **终局判定被终局 passage 的状态重置骗过**。兽交 `Finish` 会把
   `$enemyarousal` 重置（如 573.66 → 26.66），旧判定只读最终状态因此报
   "unknown"；而 `<<endcombat>>` 的过场（`… Finish` / `… Escape` /
   `… Orgasm`）本身就是游戏自己的终局信号。修复：`classify_outcome` 同时看
   **最后一个战斗活跃回合**的快照与落点 passage 源码里的 `<<endcombat>>`，
   新增 `end` / `end_player_orgasm` 两个如实的终局结论；原型矩阵的 win 路径
   仍强制要求 `win`（`end*` 依旧记 soft_fail），不放松口径。

定向复跑 20 条（`.local/sweep/combat-hardfail-attr-1007c/`）与逐条证据见
§8.4 的后续小节。

### 8.11 战斗前置保真：槽位、分支与具名 NPC（2026-10-07）

41 条与 `<<personN>>` 有关的战斗入口逐轮复跑后，把"合成前置不像上游真实路径"这一类问题
收敛到六个根因。全部只在测试器侧修（`tools/combat_sweep.py`），不改游戏数据、不改
`config/`、不进发行包。

| 复跑目录 | 行数 | ok | soft_fail | hard_fail | fixture_insufficient | 控制模式 |
| --- | --- | --- | --- | --- | --- | --- |
| `combat-personn-1007e` | 41 | 30 | 0 | 1 | 10 | — |
| `combat-personn-1007f` | 41 | 38 | 0 | 1 | 2 | — |
| `combat-personn-1007g` | 41 | 39 | 0 | 1 | 1 | mode:ok 4 |
| `combat-personn-1007h` | 81 | 72 | 0 | **0** | 9 | mode:ok 4 |
| `combat-personn-1007i` | 119 | **110** | 2 | **0** | 7 | mode:ok 4 |

1007h 的 81 行 = 41 条回归集 + 30 条"改用真实前驱链"的行 + 12 条具名行抽样。
1007i 的 119 行 = 1007h 的 81 行 + 20 条静态抽样 + 18 条前驱改链行，用 v3 最终代码跑
完整回归：`Island Fight` / `Island Trap Fight` 两条如实记 `soft_fail`
（`$combat` 结束时敌人还活着：`enemyhealth≈320/295`、`enemyarousal≈45`，win 路径没有击杀证据），
7 条 `fixture_insufficient` 全部是落点场景状态不足（见下表）。

1. **链必须连续覆盖槽 1..N（根因 A）**。旧逻辑只看 `max(slot) >= need`，单条
   `<<generate2>>` 被当成合法前置，槽 0 仍是夹具空壳；`combatinit` 把空壳标 `active` 后
   `leftgrabnew` 读 `$NPCList[undefined].penis` 抛错（Courtyard Crush / Docks /
   Home Intervene / Soup Kitchen / Street Collar / Rent First Robin 等）。`_maninit_slot_range`
   + `_maninit_run_covers` 现在要求生成串**连续覆盖 1..need** 且含递增 `$enemyno` 的宏，
   纯 `<<npc "Name" 3>>` 串不算（它写槽但不递增）。
2. **场景起始 flag 只写在 link body 里（根因 B）**。
   `<<link [[Fight them both|Courtyard Crush Fight]]>><<set $fightstart to 1>><</link>>`
   的 flag 不在 passage 正文，只重放生成链会让 `maninit` 被 `<<if $fightstart is 1>>` 跳过
   （`$combat`/`$enemynomax` 停在 0）。`LINK_BODY_RE` + `LINK_BODY_ALLOWED_MACROS` 白名单
   重放这些 flag，并**排除 `<<endevent>>`**（它会清掉刚生成的 NPC）。
3. **链与 flag 必须来自同一分支（根因 C）**。`Widgets Street` 的夜分支
   （`beastNEWinit 1 dog` + `generate2/3`，`$phase 1`）与昼分支（`generate1/2`，`$phase 2`）
   并存时，1007f 混用两边，`Street Collar Molestation` 的 phase-1 路径执行
   `saveNPC 0` → `clearsinglenpc 2`，把夹具空壳克隆进槽 1 后崩溃。`_maninit_slot_chain`
   改为遍历每个 link 出现位置**各自的邻近窗口**，链与该 link 的 flag 取自同一候选；
   1007g 起 Street Collar 转 ok。
4. **后继 passage / widget 的 `<<personN>>` 闭包（根因 D）**。`Balloon Sex` 入口正文没有
   任何 person 引用，落点 `Balloon Sex Finish` 渲染的 `<<balloonRobinHelped>>` widget 内却
   调用 `<<person2>>`。新增 `build_widget_index`（从 passage store 抽 `<<widget "name">>`
   正文）+ `person_reference_closure`（入口正文 + 最多 8 个直接后继 + widget 深度 2）。
   同时修正 `personselect` 索引映射：widget 自述 "calls are 0-5 corresponding to NPCs 1-6"，
   `<<personselect 3>>` 读 `$NPCList[3]`，旧代码却映射成 `$NPCList[2]`。
5. **具名行不再豁免闭包（根因 E）**。`Underground Robin Stage Molestation` 正文只
   `<<set $enemyno to 1>>`，但落点 `… Finish` 的**两个分支**都渲染 `<<person2>>`。
   1007e / 1007f 的两次"通过"是假通过：`errors` 为空、落点其实什么都没渲染，靠上一个用例
   残留的 `NPCList[1]` 撑住；1007g 残留消失后暴露 `Undefined NPC in personselect 1`
   （`missing: NPCList[1]`）。修复：闭包对**所有** maninit 行生效，且在"场景需要多于
   `$enemyno` 的槽位"时**优先采用上游自己的前驱生成链**——该行的真实路径是
   `Underground Robin Stage Intro` 的 `<<generate1>><<generate2>>`（Robin 在台上，不在
   `$NPCList` 里）；只有找不到真实链时才回退 `<<npc "Name">><<generate2..N>>` 保留具名 NPC。
   1007h 实测该行 ok（敌血打到负值）。静态影响面：闭包对所有 maninit 行生效后，1,570 行中
   220 行变化（30 行改用真实前驱链、190 行补足槽位），全部是"更接近上游 / 多造空位"方向。
6. **槽位宏识别补全（根因 F）**。`Widgets NPC Generation` 有 121 个 widget，旧正则只认识
   `generateN` / `generatePolice N` / `generateBEAST N` / `beastNEWinit N` / `npc Name N`。
   2026-10-07 逐个体检后补全：
   - `<<generateRole N …>>` 的 `N` 是 **0-based 槽**（widget 自述 "Slot one would be 0"，
     内部调用 `generateNPC N+1`）；`<<generateRole 1 0 "x">>` 单独出现**不算**覆盖槽 0。
   - 数字粘在名字里的变体（`<<generatecf1>>`、`<<generatey3>>`、`<<generatep2>>`、
     `<<generatePlant1>>`、`<<generateym3>>` …）与首参形式
     （`<<generatePolice/Temple/Demon/Security/Sailor/Confessor/Cultist/Doctor/SweaterWearer/NPC N …>>`）
     一律 1-based 槽——它们最终都调用 `generateNPC N`，而 `generateNPC` 内部就是
     `_n = N - 1` 且 `$enemyno += 1`。
   - `<<generatel>>` 动态取 `$enemyno + 1`：只计 `$enemyno` 递增，不证明具体槽位。
   - `<<clearnpc>>`（含带参形式）作为**链边界**：任何链都不得跨过它，且它本身不被重放
     （每个用例前都恢复夹具，没有陈旧槽要清）。
   影响面：v2 → v3 有 155 行改用真实链或更贴合的链（96 行 `debug-menu → predecessor`、
   41 行 `predecessor → predecessor`、18 行 `title-npc → predecessor`）。例：`Bailey Sheet
   Fight` 由兜底的 `Farm Road Widgets` 链改为上游真实链
   `<<generateRole 0 0 "thug">>…<<generateRole 3 0 "thug">>`。
7. `tools/passage_sweep.py` 里还有一处遗留的 `_reach_gameplay(..., steps=60)`（第 754 行）
   未随其余工具改用 `STARTUP_STEPS`（240），同批修掉——它是 §8.9 引导预算修复的漏网。

**fixture_insufficient 台账（1007h 的 9 条，全部是落点场景状态不足，不是 NPC 槽位问题）**：

| 入口 | 落点报错 | 缺失场景状态 |
| --- | --- | --- |
| `Bailey Sheet Fight` / `Farm Assault Fight Bailey` | `<<set>>: … (setting 'bindings')` | `$pubfame.bailey` |
| `Farm Assault Alex Fight` / `Farm Assault Tower Bailey Fight` | `… (reading 'teams')` | 农场突袭状态（`teams`） |
| `Farm Assault Alex Fight Bailey` | `… (setting 'bindings')` | 同上（多 NPC 分支） |
| `Underground Robin Escape Fight` | `… (reading 'water')` | 地下逃亡状态（`water`） |
| `Underground Robin Hunt Molestation` | `… (reading 'robin')` | `<<undergroundRobinTopic>>` 需要的 Robin 状态 |
| `Hospital Keycard Seduce Sex` | `… (reading 'status')` | 医院钥匙卡剧情状态（1007e 起既有） |
| `Bird Hunt Tent Steal Group Fight` | `<<flight_hunt_return>>: … (reading 'duo')` | 猎鸟剧情状态（1007e 起既有） |

这 9 条里 7 条是 1007h 新纳入的前驱改链行：此前根本没被扫到，现在如实记
`fixture_insufficient`（落点缺场景状态），不再表现为假通过。`missing` 字段对 TypeError
形状不做猜测（只保留报错宏与落点 passage），补齐方式（`--fixture-patch` 或改用游戏自身
初始化 widget）列入台账待办。

**验证**：`pytest` **597 passed**（combat 轴 95 条，含 6 条本轮新增的回归测试：
具名行改用真实链、具名行闭包补槽、`generateRole` 0-based、glued 变体、
`<<clearnpc>>` 边界、`generateRole` 链重放）。

### 8.12 战斗覆盖台账（静态，2026-10-07）

`tools/combat_ledger.py` 把 1,570 条 initiator 逐条落成**带源码依据的分类台账**，
不再只有"跑没跑过"这一个状态。纯静态、无浏览器，输入是产物 HTML（可附一次跑分报告
做 runtime join），输出 `combat-ledger.json` + `combat-ledger.md`：

```powershell
python tools/combat_ledger.py "workspace\prepare_package\zip\Degrees of Lewdity.html" `
  --report .local\sweep\full-1006-combat\combat-sweep.json `
  --fixture .local\fixtures\base-1004.json `
  --out .local\sweep\combat-ledger-1007
```

当前 0.5.11.9 产物的分类（1,570 行）：

| entry shape | 行数 | 含义 |
| --- | --- | --- |
| `entry` | 916 | 该 passage 自己带 combat starter 宏 |
| `sexual_encounter` | 384 | `$sexstart` + `consensual` + `<<actionsman>>` + `_combatend` 的共识性场景；复用战斗渲染器但没有敌人失败目标 |
| `entry_via_link` | 127 | 自己只生成，靠 passage 内链接进战斗 |
| `widget_definition` | 73 | 宏调用落在 `<<widget>>` 定义体内（扫描口径内的"库函数"，不是入口） |
| `helper_only` | 69 | 没有 starter / 链接；由别处调用的生成宏 |
| `unresolved` | **1** | 静态推不出任何前驱（`Beast Parade` 的动态 `$beasttype`） |

同一份数据还给了 derivation 维度（前驱链从哪来）：`upstream_predecessor` 470、
`synthetic_generator` 392、`named_npc_plus_generator` 173、`beast_token` 247、
`named_beast_npc` 26、`self_generation` 20、`not_needed` 212（wraith/swarm/stalk/plant
这类本来就不依赖 `$NPCList` 手部状态，之前被笼统记成"无前驱"）、`unresolved` 30。

**"未覆盖"清单**（30 条 unresolved derivation）单列一节，每条都带：

- `derive_precursor` 的原始 reason；
- 入口/前驱里保存兽类 NPC 的变量（如 `Docks Watch Dog` → `$dock_dog` @ `Docks Watch`）；
- 是否渲染 `$beasttype`；
- **候选 token（标记为未验证）**：沿上游链接图最多 4 跳找到的 `<<beastNEWinit X>>`，
  记 depth / 来源 passage / 是正文还是被调 widget。

这 30 条 = 29 条 token-less `<<beastCombatInit>>`（读 `$beasttype`，真正的来源往往在
几跳之前）+ 1 条动态兽潮。台账**不把候选当事实**：`verified: false`，也绝不据此生成
夹具（深度 3-4 跳的 token 可能是错的，例如 `Bird Tower Mating Ritual Sex` 的候选 fox
与实际场次不符）。候选只作为下一步真机实验的输入。

`--fail-on-unresolved` 是给 CI 的门：unresolved 非空即退出 1，默认关闭
（当前有 1 条已知动态入口，不隐藏、也不假装通过）。
`combat-shards` 工作流已加 "Build static coverage ledger" 步骤（`if: always()`，
`HTML_PATH` 缺失时明确跳过而不是产出假报告），台账随其他报告一并脱敏上传。

### 8.13 深层前驱 fallback：3-4 跳与父 widget 链（2026-10-07 第二轮）

§8.12 的候选清单不能只停在"未验证"：`candidate-probe-1007.json` 用 5 条真机 A/B 检验了
"把候选链重放一遍"是否真的能救活这些入口（同一夹具，只差一段 precursor 注入）：

| 入口 | 无前驱 | 候选链重放 |
| --- | --- | --- |
| `Docks Watch Dog` | `leftActionInit` DOM 错误 | `<<beastNEWinit 1 dog>>` → ok，20 回合胜利 |
| `Pound Deviant Sex` | 同上 | dog → ok，21 回合胜利 |
| `Wolf Patrol Sex` | 同上 | wolf → ok，19 回合胜利 |
| `Street Collar Dog 2` | 同上 | dog → ok，25 回合胜利 |
| `Forest Wolf Molestation Resist` | `soft_fail` | fox → 仍 `soft_fail`（候选与实际不符） |

4/5 成立。据此把这套搜索从台账的"只给候选"升级成 sweep 的**低置信前驱 fallback**：

- `combat_sweep.PRECURSOR_SCHEMA` 升到 `combat-precursor-v2`；浅搜索（`max_depth=2`）
  失败后调 `deep_beast_precursors`（BFS 最多 4 跳，每个父节点先自身 body chain、再看它
  调用的 widget 里有没有 `beastNEWinit` 链），命中则 `basis` 记
  `deep-predecessor:<source>:<body|widget:name>:depth<N>`，并写 `confidence: low` 与
  `token`。反例（Forest Wolf）说明这个标记不是形式主义：低置信就是低置信。
- `combat_ledger` 新增 `deep_predecessor` 分类与 "Deep (low-confidence) derivations"
  一节；`candidate_precursors` 直接复用 sweep 的搜索函数，台账与运行时候选集永远一致。
- 台账复跑（同产物、同 1006 报告 join）：`unresolved` 30 → 14，新增 `deep` 16，
  shape 与 drift（19）不变。16 条包含探针全部 5 行；`Forest Wolf` 的 fox 仍是反例，
  会以 `soft_fail` 留在报告里而不是被"修成通过"。
- 新增单测 6 条（浅搜索深度边界、widget 链、wraith 跳过、provenance/limit、台账分类
  与 MD 渲染）；`pytest` 626 passed。

**本机复跑（2026-10-07，16 条 deep 行 `--only-keys`，报告 `.local/sweep/combat-deep-1007j/`）**：

| 结果 | 行数 | 说明 |
| --- | --- | --- |
| `ok` | 10 | 9 条由 `fixture_insufficient` 翻正，1 条（`Street Monster 2`）保持 ok；胜判据是敌方 arousal 到顶 |
| `fixture_insufficient` | 5 | 战斗已能打到终局，卡在 **Finish 后置 passage**：`<<setTowerTemp>>`（Bird Tower ×2）、`<<pound_status>>`（Pound ×2）、`<<person1>>`（Prison Spire）——失败面从"进不去战斗"推进到"退出时缺状态" |
| `soft_fail` | 1 | `Forest Wolf Molestation Resist`（fox 候选与实际不符，path=win 但无敌人失败证据），保留反例 |
| `hard_fail` | 0 | — |

对比 1006 基线：这 16 条当时是 15 条 `fixture_insufficient`（"combat active but
#listContainer never rendered"）+ 1 条 ok。本次启动只花 3 步（1000 步预算远未触及），
4 种控制模式全 ok，`outcome_counts = win 13 / end 1 / unknown 2`。

**第三轮（同日）：区域引导把剩余 5 条也推进到 `ok`（`combat-deep-1007k/l/m`）**

上表的 5 条 `fixture_insufficient` 全部死在战斗*之后*的出口 passage——入口战斗已经能打到终局：

| 失败点 | 读到的状态 | 游戏自己的初始化 |
| --- | --- | --- |
| `<<setTowerTemp>>`（Bird Tower ×2） | `$bird.upgrades.shelter` | `<<bird_init>>` |
| `<<pound_status>>`（Pound ×2） | `$pound.status` | `<<pound_init>>` |
| `<<prison_attention>>` + `<<person1>>`（Prison Spire） | `$prison.*`、slot 0 | `<<prison_init>>` + `$prison_intro=1` + 预置 `anxious_guard` 存档 |

`derive_precursor` 现在在命中 `^Bird` / `^Pound` / `^Prison` 的行前面重放对应初始化，
basis 追加 `|area-bootstrap:<widget>`（没有野兽链时不加，避免假前驱）。Prison 那条要特别处理：
`generate_anxious_guard` 的 `$prison_intro isnot 1` 分支把 guard 写进 **slot 1**，而所有调用方
打印的是 `person1`（slot 0）——只有 `$prison_intro=1` 的 `loadNPC` 路径能对上，所以引导里
同时设 `$prison_intro=1` 并按监狱流程把 slot 0 的 anxious guard 存进 `$per_npc`。

16 条 deep 行最后**一次跑完**（`combat-deep-1007m`）：`ok` **15** / `soft_fail` 1（Forest Wolf
反例）/ `hard_fail` 0 / `fixture_insufficient` 0；4 种控制模式全 ok，启动 3 步。
对比 1006 基线的 15 条 `fixture_insufficient` + 1 条 ok，这一档收口。

顺带：把 Bird 模式放宽到 `^Bird` 后，Bird Hunt 系列的 `<<flight_hunt_return>>`（读
`$bird.hunts.duo`）也一起修复——`combat-bird-1007n` 3/3 ok（2 条 Bird Tower + 1 条
Bird Hunt Tent Steal Group Fight）。

**第四轮（同日）：status-bootstrap 收口事件链中段入口（`combat-status-1007p`）**

`combat-personn-1007i` 剩下的 6 条 `fixture_insufficient` 有同一个形状：行本身是**事件链中段**
的战斗入口，Finish 读的是父事件已经建好的状态，而不是某片区域的一次性初始化：

| 入口 | 倒在这里 | 游戏自己的初始化 | basis tag |
| --- | --- | --- | --- |
| `Bailey Sheet Fight` | Finish 写 `$pubfame.bailey.fight` | `$pubfame` {seen,tasksDone} @ Pub Fame Intro + accept 流程建 `$pubfame[task]` | `status-bootstrap:pubfame-bailey` |
| `Farm Assault` | `<<farm_assault_init>>` 读 `$farm.kennel` | Farm Assault Start 自身 `<<set $bus to "yard">><<farm_assault_init>>` | `status-bootstrap:farm_assault_init` |
| `Hospital Keycard` | Finish 读 `$pubfame.status` | 同上 pubfame accept 流程 | `status-bootstrap:pubfame-hospital` |
| `Island Wood` | Finish 做 `$island.wood += 3` 后走 `island_explore_end` | `<<island_init>>`（种 `$island`，含 wood） | `status-bootstrap:island_init` |
| `Street Car` | Finish 用 `$bus.toUpperFirst()` + `$location` 拼离场目标 | 事件从 alley 街道遭遇触发 | `status-bootstrap:street-bus` |
| `Temple Confess Sydney` | `statusCheck('Sydney')` 只在 `C.npc.Sydney.init=1` 时跑 | 游戏自己的 cheat 场景就是 `<<set C.npc.X.init to 1>>` + `$sydneySeen` [] | `status-bootstrap:sydney-init` |

和第三轮的区域引导同一个原则：**只补 Finish 真正会读的字段**，每条 evidence 注明它在游戏自身
哪个 widget / 事件里被初始化；`basis` 追加 `|status-bootstrap:<name>` 保持可审计。

**本机复跑（`combat-status-1007p`，6 条 status 行 + 1 条模式载体）**：

| 结果 | 行数 | 说明 |
| --- | --- | --- |
| `ok` | 6 | 1007i 的 6 条 `fixture_insufficient` 全部翻正 |
| `soft_fail` | 1 | `Bailey Sheet Fight`：`$combat` 结束后没有"敌人失败"证据（path=win），实际走进了 `Rent Intro`——这是该事件的失败结局分支，属预期走向而非缺陷 |
| `fixture_insufficient` / `hard_fail` | 0 | — |

4 种控制模式的载体从 Bailey 换成 `Docks Watch Dog` 后 4/4 ok（Bailey 作为子集载体连挂 4 个是
载体选择问题，不是模式缺陷）。

**CI 冷启动预算修复（run 37536425118 归因）**

同日 daily 档在云端失败，根因不是游戏卡死：`bootstrap did not reach gameplay; last
passage='Start' after 789 steps`——789 次点击几乎全是 `dismiss_modal`，撞上 720s deadline；
而 prepare 同产物在另一 runner 的 capture 花了 12m27s。这是贴边预算，不是真死循环。修复：

- `STARTUP_STEPS` 1000 → 1500、`STARTUP_DEADLINE_S` 720 → 1140（19 分钟）；
- 新增**重复点击断路器**：同一个 dismiss 目标（按 120 字符文本样本做 key）重复
  `STARTUP_REPEAT_SKIP_AFTER=25` 次后加入 `skipKeys` 传给浏览器侧，后续步骤不再点它，
  改用其它控件 / 页面兜底——真死循环不再静默吃掉整个预算；
- action trail 每条记录 `root` / `sample` / `repeat`，`info` 增加 `skip_keys`，
  失败可直接归因。

新增单测 6 条（战斗 2 条 + passage 4 条，含重复 dismiss 假页的 skip 时序），另有 3 处旧断言
随实现更新。`pytest` **636 passed**。

**补充证据（同日）**：修复前派出的 combat-full run 37542211811（head `05b3b95`）头 4 个分片
全部以同一形态失败——`bootstrap stopped on startup passage 'Start' after 788 steps
(deadline_hit=True)`，四份报告的 `verdict_counts` 全 0、`completeness` 197/197 缺失。即这批
失败是冷启动预算问题而非战斗缺陷；修复后的新 run 需重跑，旧报告的作战结论一概不采信。

**第五轮（同日）：剧情项分类 + 深度摘要与赋值前置检查（`scenario-1007t/u`）**

1006 剧情报告里 331 行有 82 条 `soft_fail`，其中 **80 条是同一句话**：
"widgets produced no observable state delta"。浅层摘要（`__dolxSummary`）只取一层、数组/对象
前 8 个成员，所以 `<<learn_recipe_all>>`、`<<undress>>`、`<<updateMuseumAntiques>>` 这类写入
嵌套状态的操作看起来"什么都没做"。三件事一起改：

1. **行分类**（`classify_interaction`，报告新增 `interaction` 字段与 "row interactions" 一节）：

   | 类别 | 判据（来自游戏源码/运行时） | 行数 |
   | --- | --- | --- |
   | `state` 状态操作 | 目标是函数（本构建 212 个动态目标全部是 `stayOnPassageFn` = `() => V.passage`）且解析结果等于 `V.passage` | 212 |
   | `scene` 场景跳转 | 目标是字面 passage，点击后真正导航 | 94 |
   | `display` 展示项 | widget 源全为空白（`Wardrobe` / `Foodstuff Prop Debug` / `CanvasModel Sample` / `NNPC Parade` 等纯渲染页） | 24 |

   判据静态可验证：`debug-menu.js` 里 `const stayOnPassageFn = function () { return V.passage; };`，
   且菜单区域内 `stayOnPassageFn` 的引用数（212）等于动态目标数。
2. **深度摘要 + 定向差异**：新增 `__dolxDeepSnapshot`（遍历全变量树：节点预算 15 万、深度 12、
   循环保护）与 `__dolxDeepDelta`；浅层 delta 为空时自动做深度对比，报告新增 `deep_delta`
   （最多 40 条路径级 before/after）。`<<learn_recipe_all>>` 等 5 行由"无 delta"变成 40 条
   嵌套变化。
3. **赋值前置检查**：`__dolxAssignChecks` 解析 `<<set $path to <literal>>` 与
   `+= / -= / *= / /=`（数值运算用深度快照里的 before 值算期望），逐条比对最终值；无法静态
   判定的 RHS（`random(...)`、`V.x`）与 function widget（`String(fn)` 是源码不是 SugarCube，
   曾造成 `Main#25` 假阳性，已修并留单测）显式记 `checked: false`，绝不冒充验证。报告新增
   `assignment_checks` / `assignment_summary`；检查失败 → `soft_fail`（例如 `$sea` 期望 0 实得 3）。

**判定语义**："有没有 delta"不再直接决定失败：没观测到增量时按类别记 note，行仍是 `ok`
（报告新增 "ok rows with notes" 一节，本次 80 条全部可见）；失败只来自真实证据——赋值检查
失败、invariant 电池、渲染/落点错误。

**本机全量复跑（同一产物、同一夹具，与 1006 基线 diff）**：

| 结果 | 1006 | 1007u | 变化 |
| --- | --- | --- | --- |
| `ok` | 239 | 319 | +80 |
| `soft_fail` | 82 | 2 | -80，仅剩 2 条上游 `<<parasiteProgressDay>>` 未注册宏缺陷（原样保留） |
| `hard_fail` | 0 | 0 | — |
| `fixture_insufficient` | 9 | 9 | 不变（`Events 40 / 103-110`，野兽生成前驱） |
| `not_applicable` | 1 | 1 | 不变（目标为空的重放行） |

`baseline_diff`：**new_regressions 0 / fixed 80**。新增单测 6 条（分类四分支、赋值汇总、
function widget 不可静态检查、失败赋值 → soft_fail），`pytest` **642 passed**。

**第六轮（同日）：Maplebirch 欢迎框 checkbox-gated 死循环（run 37544629870 / 37544640529 / 37546495918）**

三个云端 run 全部红在同一形态：`bootstrap did not reach gameplay; last passage='Start'
after 1245-1252 steps (deadline_hit=True)`，action trail 清一色
`{"action": "click_startup_control", "clicked": true, "text": "I Understand"}`。根因不是慢：
maplebirch 4.1.14 的框架欢迎框是 `<<dialog>>` + `<<checkbox '_maplebirchNoticeVerify'>>`
（渲染成真实 `input#checkbox--maplebirchnoticeverify`）+ `<<button "I Understand">>`，
按钮体的 `<<if _maplebirchNoticeVerify>>` 不成立时**只关不掉对话框**。旧逻辑三处缺口叠加：
英文勾选说明 `I have read and understood the notice above` 不在 `STARTUP_CONSENT_LABELS`
里（无法走勾选分支）、重复断路器只覆盖 `dismiss_modal/sweetalert`（页面级 confirm 不算
重复）、`skipKeys` 只比对容器文本（对无 root 的页面级点击无效），于是"点击成功"的假进度
吃满 19 分钟预算。此前本机没复现（中文标签分支命中情况与冷启动速度都和 runner 不同），
所以只能从 CI 报告与 mod 源码取证，不能拿本机冒烟当对照。

修复（全部在测试器侧，不碰发行包）：

- `browser_smoke_test._startup_interaction_script` 新增 `accept_framework_notice` 分支：
  见到 `checkbox--maplebirchnoticeverify` 先勾选再点确认按钮，`checkbox_checked` 记进 trail；
- 新增通用 `ensureGateCheckboxes`：任何 confirm 候选点击前，自动勾选最近的门控容器内
  未勾选 checkbox（同类"先勾选后确认"的 mod 门一并覆盖）；`skipTextHit` 让 `skipKeys`
  同时按候选按钮文本匹配（含 `all_candidates_skipped` 归因）；
- `STARTUP_CONSENT_LABELS` 补英文/中文两条 maplebirch 勾选说明；`passage_sweep`
  的重复 key 扩到 `click_startup_control` / `accept_consent_gate` /
  `accept_framework_notice`，页面级确认按 `button_text` 而非整页文本做 key。

证据：真实产物（base-1003，37 mod，同锁定栈）本机 bootstrap **4 步**到 `Orphanage Intro`
（`.local/sweep/bootcheck/`，trail = 年龄门 → `accept_framework_notice` 勾选后点击 →
`(1) 开始游戏！` → `(1) 继续`）；新增 2 条真实 DOM 测试（Chromium 驱动
`_startup_interaction_script`：Maplebirch 表单一次点掉、skipKeys 生效后不再点击）与 3 条
passage_sweep 单测；`pytest` **647 passed**。云端复跑仍按 daily → combat-full 顺序验证。

**第七轮（同日）：mod passage 盘点 + `--allow-runtime-only`（本机 base-1003 / au-f-1003）**

先纠正一个口径：静态 `extract_passages` 只解析 HTML 文件里的 `<tw-passagedata>`，在锁定栈上
是 15,627 条 **vanilla** passage。37 个内嵌 mod 的 twee 是 `window.modDataValueZipList` 的
base64 payload，ModLoader 只在运行时把它们合并进 DOM 与 `SugarCube.Story`——所以此前所有
"15,627 全通过"的报告**没有覆盖任何 mod passage**。

补的门是 `tools/mod_passage_inventory.py`：启动一次真实载体，取运行时 DOM passage
（base 15,663 / au-f 15,664）、`SugarCube.Story.lookup('passages')`（15,219，widget 定义的
passage 不进 Story）与 `Macro.has`，再按 payload 里的 `:: Name`、`<<widget "name">>` 反查
来源 mod，产出 JSON + MD（工作流里命名为 `*-report.json/md` 以进入脱敏白名单）。

实测（au-f-1003，同一锁定栈）：

| 口径 | 数量 | 说明 |
| --- | --- | --- |
| 静态文件 passage | 15,627 | 只有 vanilla |
| 运行时 DOM passage | 15,664 | +37 条 mod 合并 |
| 运行时独有 = mod passage | 37 | `CE_*` / CustomHair / More Love / DOLI / NPC Avatars / Yanling / longer-combat / npcpic … |
| 其中可游玩 passage | 4 | `CE_Wardrobe`、`CustomDyeHair`、`CustomHairPassage`、`Food Preference` |
| 其中 widget 定义 | 33 | 声明 34 个 widget 宏，启动快照已注册 32（`swich_teleportation` / `swich_yanling` 懒注册） |
| 加密（不透明）mod | 1 | `【AUsDoL】facial expansion 1.1.0`：`.zip.crypt/.salt/.nonce` |

让 mod passage 真正进入扫描的开关是 `passage_sweep --only-file <清单> --allow-runtime-only`：
静态解析不到的名单按"运行时独有"保留（不当作漂移丢弃）。本机对 au-f-1003 跑这 4 条 =
**4/4 ok**（`CE_Wardrobe` 423 字/37 链接、`CustomHairPassage` 632 字/4 链接、`CustomDyeHair`、
`Food Preference`），并将结果写进 `only_file.runtime_only` 供归因。daily 云端档已接入这条
链路：先盘点、再扫可游玩 mod passage，清单为空视为覆盖回归（`::error::`）。

**加密 mod 的边界**：静态侧只能识别"这是密文"（payload 内层是 `.crypt/.salt/.nonce`），
内层 passage / widget **读不到**；按 `UPSTREAM_FRIENDLY_STRATEGY.md`「避免解密、拆包重分发」
与 `docs/AU_MODS_INTEGRATION.md` 的既定边界，不做白盒解密。可测路径只剩黑盒运行时：
Engine A 的 `au-face` 流（八脸型 + 桌宠 canvas 像素）与 Engine B MuMu 真机
（`tools/mumu_apk_smoke.py`）——这条与本轮 mod 盘点并列，不互相替代。

### 8.12 combat-full 首轮 26 条 hard_fail 的归因与收口（2026-10-09）

run `37899995638`（head `a2e324f`）前 4 个 combat 分片完成后，共暴露 26 条
`hard_fail`。这批结果不封存为通过基线，只作为归因输入；逐条映射后分成三类：

| 根因 | 行数 | 典型现场 | 修复 |
| --- | ---: | --- | --- |
| Finish / 出口 passage 读父事件状态 | 15 | `Mansion Return * Fight Finish` 读 `$avery_passage`；`Dog Park Escape` / `Lake Underwater Tentacles Finish` 读 `$bus`；`Estate Manor Approach Finish` 读 `$estate.chaos` | 新增 11 条 status-bootstrap，只补源码真正读取的字段，basis 追加 `status-bootstrap:<name>` |
| `personselect` 读未初始化 NPC 槽 | 6 | `Chalets Work End Refuse`、`Street Collar Dog`、`Trash Compare Combat Loss` 报 `Undefined NPC in personselect N` | `person_reference_max` 识别 raw index 与 `random(0, N)`；闭包沿入口 → Finish → widget 推导最大槽位 |
| widget 库 / SugarCube chrome 被当成可玩入口 | 5 | `Moor Widgets`、`Clothing Shop v2 Widgets` 直接 `Engine.play` 后报段落不存在或无链接 | `resolve_widget_entry` 只接受普通 caller passage；无真实 caller 的行如实记 `not_applicable` |

另有两个测试器细节一并修复：`derive_precursor` 对自带 combat starter 的行
（如 tentacle）允许附加状态引导；`Brothel Show` 按游戏源码初始化完整
`$brothelshowdata`（含 `counts`），不再只写 `{}` 后访问 `.counts.pig`。

最终代码对 26 条原 hard_fail 全量定向复跑（`.local/sweep/combat-fix-1009f/`，
同一 1004 产物 + 合成夹具，回合上限 160）：

| verdict | 行数 | 说明 |
| --- | ---: | --- |
| `ok` | 15 | 状态引导 / 槽位闭包后到达可确认终局 |
| `not_applicable` | 10 | widget host 无真实 caller，或直接渲染后 `$combat` 保持 0（扫描命中但不是战斗入口） |
| `hard_fail` | 1 | `Estate Manor Approach Fight` |
| `soft_fail` / `fixture_insufficient` | 0 | — |

唯一剩余 hard_fail 的源码证据：`Estate Manor Approach Finish` 的两个胜利分支都链接到
`Estate Manor Intro Entrance`，但当前 0.5.11.9 产物中没有这个 passage，因此落点
“没有可用链接”。这是上游断链，不是 DOL-X 集成或夹具问题；测试器不创建假出口，
保留 hard_fail 与源码证据，等上游修复后再复跑。

本轮新增/更新 25 条战斗单测，`pytest` **725 passed**。随后又修复一个终局判定细节：
`Brothel Show Machine` 的实际血量是 `$machineHealth`（20 → -1），旧逻辑只看
`$enemyhealth`，把已到达终局的机器战误报为无失败证据。现在终局与动态回合上限都会识别
`enemyhealth` / `machineHealth` / `tentacleHealth` / `swarmActive`，并优先采用最近
回合里真正下降的血量字段；新增 4 条回归测试后 `pytest` **729 passed**。旧 run 的后
4 个分片仍按原代码继续执行，其结论只用于保留原始报告；修复后的 combat-full 需要在
新 head 上重跑。

对旧 run 全 8 片的 `soft_fail` 复核又发现三个测试器问题，均有真实样本复现：

1. **动态回合上限把“剩余血量所需回合”当成新总上限**。`Livestock Return Horse Rape`
   在第 80 回合只剩 7.14 HP，旧公式因此判断“不需要扩展”并截断；正确语义是
   `当前上限 + ceil(剩余血量 / 中位伤害) + 5`，硬顶 160。修复后同一样本在扩展上限内
   到达 `enemyhealth=-5.71`，verdict `ok`。
2. **无控件续进只数 3 次，不区分“状态在推进”与“只换 passage”**。`Abduction` 与
   `Adult Shop Clerk Angel Molestation` 在只剩 Next 时，`enemyarousal` 每次续进都在
   上升；旧驱动 3 次后停止。现在续进会记录 HP/arousal 证据，只有连续 3 次**有意义
   状态**不变才停止，纯 passage 来回切换仍会被 bounded。两个真实样本修复后均以
   arousal 达到上限结束，verdict `ok`。
3. **384 条共识性场景被误当成胜利战斗**。这些 passage 同时具备
   `$sexstart` / `consensual` / `<<actionsman>>` / `_combatend` 源码标记，复用战斗
   渲染器但没有敌人失败目标；旧 run 中 349 条因此成为 `soft_fail`。现在运行时如实
   记 `not_applicable`，静态台账新增 `sexual_encounter` shape，保留源码依据，不把它们
   算进战斗胜利矩阵。

上述修复后 `pytest` **734 passed**。这些结论来自旧报告归因与本地定向复现，最终
combat-full 仍必须在新 head 上完整重跑。

---

## 9. 一键复现清单（发版前）

```powershell
$env:PYTHONIOENCODING='utf-8'
$FIX = ".local\fixtures\base-1004-fix8.json"
# 载体必须是 build 出来的整合包（含 mod 栈与 img/），不是 prepare 的 HTML 空壳：
$PKG = "output\DoL-0.5.11.9-XFox-1.0.0a-base-1004.zip"

python tools\quick_check.py                                   # 网络/依赖 13/13
python -m pytest -q                                           # 全量单元测试
python tools\save_safety_guard.py                             # 仓库存档安全守卫
python tools\au_artifact_check.py output\*.zip                # AU 产物审计
python tools\target_package_check.py $PKG --expect "maplebirch,cheat extended,More Love Interests Mod" `
  --expect-version 0.5.11.9 --min-mods 30                     # 载体身份 fail-closed

# 日常档五轴
python tools\passage_sweep.py $PKG --fixture $FIX --sample 300 --out .local\sweep\out-smoke
python tools\scenario_sweep.py $PKG --fixture $FIX --suite all --out .local\sweep\scenarios
python tools\combat_sweep.py $PKG --fixture $FIX --tier archetypes --out .local\sweep\combat
python tools\env_matrix.py --target $PKG --fixture $FIX --tier daily --out .local\sweep\env-daily
python tools\sweep_flow_assertions.py output\DoL-...-au-f-1003.zip --flow all --out .local\sweep\flows

# 发版级：全量扫描 + 与上一份基线对比
python tools\passage_sweep.py $PKG --out .local\sweep\full --baseline .local\sweep\full-1004\passage-sweep-baseline.json

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
- 战斗：`combat-sweep.json` + `combat-initiators.json`（入口清单）+
  `combat-sweep-ledger.json`（身份台账与逐条结果，`--resume` 依据）；
- 环境：`env-<tier>-report.json` + `env-<tier>-report.md`（含 8/4 个上下文的读回状态）；
- 环境台账：`env-sweep-ledger.json`（身份 + 逐条结果 + 原子检查点）；分片汇总写在
  `sweep-summary/sweep-summary.json` / `.md`（缺片/重复/身份漂移时报错）；
- `--save-baseline` 时另写一份基线到 `.local/sweep/baselines/`（passage 轴按
  `{fixture}__{context}` 分组）；功能流断言目录里是 `flow-assertions.json` / `.md`。

所有报告在离开本机前必须过 `tools/report_sanitize.py`。
