# 自动化全 passage 扫描（Engine A）

**创建**: 2026-10-04
**适用版本**: 0.5.11.9-XFox 1.0.0a 及之后
**相关工具**: `tools/passage_sweep.py`、`tools/sweep_flow_assertions.py`
**相关测试**: `tests/test_passage_sweep.py`

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

## 4. 判定分层（报告里的 4 个 verdict）

| verdict | 含义 | 处理方式 |
| --- | --- | --- |
| `ok` | 渲染完成、有 passage DOM、有文本 | 记入基线；之后变非 ok 即回归 |
| `soft_fail` | 渲染了但超时未完成 / 空内容 | 观察项；稳定复现可封为新基线 |
| `hard_fail` | 未捕获异常 / 引擎抛错 / 没有 passage 节点 | 真问题，需要人看 |
| `fixture_insufficient` | 报错属于"前置状态不足"（is not defined / cannot read properties…） | **不算 bug**：这条 passage 需要更深的存档状态 |

夹具（fixture）来源：真实点过启动门后的新游戏快照（约 780 个变量、118KB JSON），
每条 passage 渲染前用 `structuredClone` 还原，保证互不污染、可重复
（同一个 `--seed` 结果一致）。

为什么"进不去的 passage"不算 bug：DoL 有大量 passage 只在特定剧情/战斗/遭遇状态
下才可达；用新游戏快照强行 `Engine.play` 进去时，报"读不到某状态"属于夹具边界，
不是游戏坏了。这些条目会稳定留在基线里，不会淹没新回归。

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

---

## 9. 一键复现清单（发版前）

```powershell
$env:PYTHONIOENCODING='utf-8'
python tools\quick_check.py                                   # 网络/依赖 13/13
python -m pytest -q                                           # 全量单元测试
python tools\au_artifact_check.py output\*.zip                # AU 产物审计
python tools\passage_sweep.py "workspace\prepare_package\zip\Degrees of Lewdity.html" --sample 300 --out .local\sweep\out-smoke
python tools\sweep_flow_assertions.py output\DoL-...-au-f-1003.zip --flow all --out .local\sweep\flows
# 发版级：全量扫描 + 与上一份基线对比
python tools\passage_sweep.py "workspace\prepare_package\zip\Degrees of Lewdity.html" --out .local\sweep\full --baseline .local\sweep\full-1004\passage-sweep-baseline.json
```

---

## 10. 产物目录

`--out` 目录里：

- `passage-sweep.json`：机器可读全量结果（每条 passage 的 verdict / errors / text_len / 耗时 / 落点）
- `passage-sweep.md`：人读报告（verdict 计数 + 明细 + 基线对比）
- `passage-sweep-baseline.json`：`--save-baseline` 时封存的基线

功能流断言目录里：`flow-assertions.json` / `flow-assertions.md`，含每条流的证据 JSON。
