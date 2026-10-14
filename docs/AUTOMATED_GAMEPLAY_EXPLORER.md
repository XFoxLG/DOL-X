# 自动玩家与源码驱动探索器

这份文档说明 `tools/exploration_agent.py` 及其配套模块的证据边界。它不是替代现有的 passage / scenario / combat / environment 扫描，而是给这些静态和辅助测试补上“普通玩家能不能从 `Start` 自然走到这里”的证据。

## 证据轨道

- `natural`：只通过 Chromium 的真实 UI 控件推进。探索器不调用 `Engine.play`、时间注入、变量注入或 debug event。自然轨道的失败可以解释为玩家路径上的产品风险。
- `natural_prefix` + `continuation=checkpoint_restore`：前缀来自真实 UI，后续从本地 checkpoint 恢复。它不能和全程自然轨道混同。
- `assisted`：debug event、深层 fixture、环境注入或源码前驱链进入的场景。它证明“源码定义的功能在合法前置状态下可运行”，不证明普通玩家自然可达。

## 运行方式

```powershell
python tools/exploration_agent.py output/DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.zip `
  --out .local/exploration-smoke/natural-001 `
  --max-steps 50 --seed 1719 `
  --expect-version 0.5.11.9 `
  --tag v0.5.11.9-1.0.0a-0915 `
  --mods-lock config/mods.lock.json `
  --build-toml config/build.toml `
  --source-index .local/source-index/current.json `
  --source-commit <exact-commit>
```

运行开始时生成 `target-manifest.json`，读取 ZIP SHA-256、版本、Mod lock digest、source index digest、source commit 和 runner revision。这些字段缺一会让 release gate 无法绑定报告身份；基本 artifact identity 不完整时报告只能是 `infrastructure_fail`。

## 当前覆盖

2026-10-13 的 `v0.5.11.9-1.0.0a-0915` AU-F 真实包有两代证据：**shim 之前**的 `c5ca5b68…`
载体，以及 2026-10-14 在 **shim 之后**的 `96939f3f…` 载体上重跑的 shim 证据。

shim 之前的载体（`package_sha256=c5ca5b68…`，source index `417247f3…`）：

- `natural-014`：seed 1719，30 步，`complete`，0 个运行时失败，27 个唯一 coarse state；路径覆盖 `Start → Start2 → Character Creation → Orphanage Intro → Bedroom → Domus Street → Tutorial`。
- `assisted-full-0915-merged`：14,662 / 14,662 个静态目标 `ok`，无重复目标、无跨分片重复。它们使用 fixture restore + `Engine.play`，只证明“源码目标在合法夹具下可渲染”，不证明玩家自然可达。
- runtime Mod inventory：39 个 embedded payload、37 个 runtime-only passage、4 个 playable passage 全部尝试 `ok`、9 个 Mod 按钮隔离调用无异常、1 个受限 Mod 记为 `opaque_runtime_only`。
- 贴图位置探针（2026-10-13 新增）：`tools/sprite_layout_probe.py` 对 0915 AU-F 记录 8 个脸型样本、56 个唯一贴图资产、576 条带目标矩形的绘制记录、8/8 样本桌宠 canvas 有像素；同一构建两次独立运行的 56 个资产位置与 8 个 canvas 网格指纹零漂移（10 个天气动画层按已知设计排除）。

shim 之后的载体（`package_sha256=96939f3f…`、source index `4aa3fd5c…`、commit `aa475808…`）：

- `natural-shim`：seed 1719，30 步，`complete`，`stop_reason=budget_exhausted`，30/30 `ok`、0 失败、27 个唯一 coarse state，首次覆盖 `Orphanage Intro`(9) / `Tutorial`(19) / `Bedroom` / `Domus Street`。
- `assisted-shim`：`--limit 40`，40/40 `ok`，`assistance=[source_edge,fixture_restore,engine_play]`。这是身份闭环用的 smoke，**不是**全量覆盖。
- **release gate 实测（2026-10-14）**：29 个条件里 **27 true / 2 false**，`completion_claim=none`。两条阻塞都是真实缺口：
  1. `assisted_static_targets_covered`——shim 载体只跑了 40 个 assisted ok 目标，分母 14,772；
  2. `query_regression_passed`——query 集 24 passed / 0 failed / **2 pending**（`au-pet-remount-survives-reload`、`dayloop-time-advance-full-day`）。

  其余全部 true：identity 完整且一致、`target_sha256_matches`、`source_index_digest_matches`、source commit 与索引一致、mod inventory、static surface、mod passage sweep、Android gate，以及 Plan v5 新增的 6 条（符号化可达性、故事图审计、遍历统计、query 回归、AU 契约、框架契约）。
- **身份漂移警告**：旧的自然/辅助证据绑定 `c5ca5b68…`（shim 前）与旧索引 `417247f3…`；把它们和新载体混用会被 gate 判 `identity_consistent=False`。这是 fail-closed 设计生效，不是工具 bug。

这些数字只代表当前 seed、预算与被验证的载体，不是全游戏覆盖率证明；没有 Android 证据、没有全量 assisted 覆盖或仍有未归因 `hard_fail` 时，报告只能写“当前档位探索完成”。

## 符号化可达性实测（2026-10-14）

`tools/static_reachability_solver.py` 在真实 0915 索引上（15,627 passage、72,567 静态边、894 动态边）跑通了有见证与无见证两类结果：

- `--start Start2 --target "Orphanage Intro" --target "Bird Hunt Estate Scout 6" --target "Estate Stone Aphrodisiac Resist" --target "Farmland Manors Rescue" --bound 20 --shortest` → `verdict=reachable`，4/4 目标各给出 1 / 15 / 14 / 14 跳的见证（每跳带 passage、kind、HTML 行号）。
- `--start Start --target Start2` → `unknown_dynamic_edges`。原因是 `Start` 是年龄门，正文里只有 6 条非导航 JS 边（jQuery class 切换 + `localStorage.setItem("verifiedAge", true)`），"Enter" 按钮由页面脚本而非 passage body 驱动，所以静态图里没有 `Start → Start2` 边。`story_graph_audit` 的 `statically_reachable_from_entry=1` 是同一事实的独立印证；**符号化入口应当写 `Start2`**，写 `Start` 只能得到 fail-closed 的 `unknown_dynamic_edges`。
- `--start Start2 --target "Estate Manor"` → `unknown_dynamic_edges`（bound 30 与 120 都一样）。真实原因是该 passage **零入边**（任何 kind 都没有），属于 `defined_without_inbound`；但当前实现的判负门槛是"全图动态边为 0"，而全图永远有动态边，所以它只能给出保守的非结论。这是**已知的工具边界**，不是产品缺陷：要拿到 crisp 的"零入边"结论请看 `story_graph_audit`，不要改判 `unknown_dynamic_edges` 为"不可达"。

## 状态、动作与指纹

每次快照包含：

- 当前 passage；
- SugarCube `State.marshalForSave()`；
- 当前 `State.variables`；
- localStorage / sessionStorage 摘要；
- Mod 注册表摘要；
- 可见交互控件；
- console error / pageerror / requestfailed。

DOM 语义指纹包含 `id`、`name`、`href`、`role`、`text`、`semantic_id`、`scope`、`overlay`、`pointer_blocked`、`disabled`、`checked` 和 `value`，不包含动态 action index。被遮挡控件会从候选池移除，避免点到底层被 modal 覆盖的按钮。

动作去重使用 `passage + semantic_id`，不是全局控件 ID。这样同一控件可以在新 passage 或新状态下再次执行，但不会在同一 passage 内反复点击同一个单选框。

## 贴图位置探针

像素计数只能回答"画布上有东西"，不能回答"哪个贴图画在了哪里"。`tools/sprite_layout_probe.py` 补上这一半：

- 在游戏启动前注入 `CanvasRenderingContext2D.drawImage` 记录器，逐条记录源资产、源裁剪矩形（9 参数形态）、目标矩形和所属 canvas；
- 每个采样点（启用桌宠、逐个 AU 脸型）先清空记录、触发一次真实重绘，再按资产聚合：绘制次数、最后一次目标矩形，以及归一化到 0..1 的几何（x/y/w/h/中心点）；
- 对 `#maplebirch-character-pet` 额外计算 8×8 不透明像素分布 + 包围盒 + 质心，作为整层指纹；
- 同时记录 HTTP >= 400 与中止请求；`legacy_blush_tear_naming` 标记已知的 `blush1`/`tear3` 旧命名 404（AU 内层载荷请求旧名，资源是 `blush-1`/`tears-1`，游戏用 fallback 链继续）；
- 支持基线：`--update-baseline` 记录，`--baseline <file>` 回放比对；缺失贴图、超出容差（默认 1% 画布）的位移、网格漂移都判 `layout_drift`，新增贴图只记为 `new` 不算漂移；
- `img/misc/sky/`、`img/misc/weather/` 等已知动画背景层默认从位移判定排除并单独列在 `ignored_moved`，`--strict-layout` 可强制参与判定。

```powershell
python tools/sprite_layout_probe.py output\<产物>.zip `
  --out .local/sweep/sprite-layout\<name> --update-baseline
python tools/sprite_layout_probe.py output\<产物>.zip `
  --out .local/sweep/sprite-layout\<name>-repeat `
  --baseline .local/sweep/sprite-layout\<name>\sprite-layout-baseline.json
```

实测（0915 AU-F，同一构建跑两次）：`drift=False`，`missing=0`、`moved=0`、`new=0`、`grid_drift=0`，`ignored_moved=10`（全部是天气动画层）。边界：它确认"资产被绘制、位置与基线一致、像素分布一致"，不替代人工视觉评审，也读不到离屏 canvas 内部逐层合成（三层以上先合成再整体 blit 的管线只记到 canvas 级）。

探针在 boot 后和全部采样后各记一次 AU 模块标记，并写入 `lazy_note`：AU 载荷经 ModLoader 惰性加载路径注册，宏与渲染管线在 boot 后即可用，而 `SE Widgets` / `AU_facial_expansion` / `Widgets Mirror` 这些 twee 标记只有在会话真正打开 mod/AU UI 后才出现。`tools/mod_passage_inventory.py` 在它的 mod 按钮交互轮次后能看到这些标记；纯换脸采样的会话看不到，属于惰性注册的正常表现，不是缺陷。

## 辅助轨道

`tools/assisted_explorer.py` 从 source index 的静态边构造目标清单，过滤不在 runtime/static passage 集合里的错误表达式，然后逐条执行：

```powershell
python tools/assisted_explorer.py <zip-or-html> `
  --source-index .local/source-index/current.json `
  --fixture .local/fixtures/ci-base.json `
  --out .local/sweep/assisted-001 `
  --limit 30 `
  --expect-version <game-version> `
  --tag <target-tag> `
  --mods-lock config/mods.lock.json `
  --build-toml config/build.toml `
  --source-commit <exact-commit>
```

每条结果固定写 `evidence_track=assisted`、`assistance=["source_edge","fixture_restore","engine_play"]` 和精确源码位置。动态边不会因为静态解析不到目标而判 bug，只保留 `dynamic_edges` 计数，等自然/运行时探索发现。

长 passage 底部控件在采集前会执行真实的 `End` 滚动。滚动只影响视口，不注入导航。

全量 assisted 运行可以分片：`--shard-index N --shard-count K` 会先按目标名排序，再取 `targets[N::K]`。这样多个 job 可以拼出完整静态目标清单，报告里的 `shard.index/count` 能核对归属。

长分片会逐目标增量落盘；中断后的报告保留 `status=running` 和已完成目标，不会把 partial 证据写成 `complete`。重启同一个分片时加 `--resume`，runner 会校验 target manifest、source index digest 和 shard 归属，只复用匹配的已有结果，然后继续跑剩余目标。

## Checkpoint

checkpoint 保存 `State.marshalForSave()`、storage、Mod registry 和 fingerprint。恢复前会先走一次真实启动 UI，等 Mod registry 稳定，再恢复 state 和 storage。

2026-10-12 的结论：中间回合 checkpoint 还不能声明 exact roundtrip。`Tutorial` 这类带战斗副作用的 passage 在 `Engine.show()` 重渲染时会改变 `$combat`、NPC 状态和其他变量，恢复后 exact fingerprint 不一致。当前实现会 fail-closed 写 `infrastructure_fail`，不会把它伪装成自然轨道或通过。失败现在会输出 `drift_attribution`，列出 variables、DOM、combat、history、PRNG、storage 和 mod registry 中实际改变的组件；这是归因证据，不是“产品 bug”判定。这个问题必须在源码/引擎层继续归因后，才能把 checkpoint 回放作为发布证据。

## 战斗重新归因（Phase 0）

战斗扫描的判定在 2026-10-13 做了三处修正：

1. `terminal_landing_marker()` / `route_landing_marker()` 通过 `_executable_source()` 先剔除 Twee 注释和 `<<if false>>` 不可达分支，再检查组内终局宏；被注释或永假分支里的 `<<endcombat>>` 不再被算作终局落地。
2. `classify_entry_errors()` 不再用 `FIXTURE_MARKERS` 做模式匹配降级。渲染错误只有命中 `DECLARED_FIXTURE_GAPS` 这张已复核表（anchor widget/passage + 缺失字段 + 源码行号 + 归因理由）才降为 `fixture_insufficient`；其余一律 `hard_fail`。普通 `ReferenceError`、未注册宏和产品代码异常不会再被静默吸收。
3. landing passage 报告 `has no usable links` 时，`annotate_landing_links()` 会扫描该 passage 全部 `[[...]]` 出口目标；若所有目标都不在 story map 里，detail 记录每个缺失 passage。Estate Manor 分支因此从模糊的“无链接”变成具体断链证据。

对 CI 运行 `37967037983`（4 分片、786 行、HTML `8482754427…`）的 33 条 flagged 结果离线重新归因，产物在本机 `.local/sweep/combat-reattr-37967037983-offline/`：

| 旧判定 | 新判定 | 行数 | 说明 |
|---|---|---|---|
| `fixture_insufficient` | `fixture_insufficient` | 28 | 命中已复核缺口表（NPC 生成链 / 区域初始化状态） |
| `fixture_insufficient` | `soft_fail` | 3 | 战斗活跃但动作控件未渲染；证据不足以定性 |
| `hard_fail` | `hard_fail` | 2 | 见下 |

两行仍然 `hard_fail` 的失败都已落成可复核证据：

- `maninit:-:Estate Manor Approach Fight`：`Estate Manor Approach Finish` 三个出口（`Estate Manor Intro Entrance` ×2、`Estate Manor Approach Defeat` ×1）在 story map 里都不存在。`base/base.zip` 的 vanilla 0.5.11.9 构建有完全相同的引用/定义不对称，这是**上游断链缺陷**，不是整合或夹具问题。判定保持 `hard_fail`，detail 列出全部缺失 passage；修复后的 E2E 重跑（`.local/sweep/combat-reattr-estate-dp-probe2/`）已稳定输出该断链注解。
- `maninit:-:DP Test`：debug 场景在 `Molestation Ejaculation` 的 `<<ejaculation>>` 渲染中断（`$NPCList[_nn].penisdesc` 未生成时未防御读取 `penisdesc.includes`），CI 与本地重跑混合样本 2 fail / 2 pass，呈间歇性。由于这是 debug 入口自己的不完整生成链，归因记为 `debug-scenario fixture gap (intermittent)`；机器判定保守保持 `hard_fail`，不算产品通过，也不升级为产品缺陷。

本地用 `base-1004-fix8`（782 键）复跑 72 键时的 65 个 `hard_fail` 是**夹具漂移**产物（CI 使用 849 键的 `ci-base`），只用于提取缺口清单和源码证据，不作为发布口径；发布口径以上面的 CI 运行重分类为准。

## 失败重放与缩减

自然失败默认会保存原始 trace；加 `--shrink-failures` 后，runner 会从新的真实 `Start` 重放候选 trace，再按失败语义做 binary deletion。重放必须命中同一个 `verdict` 和 `semantic_id` 才会被判定为复现。缩减结果单独写入 `minimized-trace.jsonl`，原始 trace 不会被覆盖。重放证据固定为 `natural_prefix + semantic_trace_replay`，不能冒充首次自然探索。

`exploration_summary` 会单独列出未归因 `hard_fail`。只要这个列表不为空，报告就只能当作探索证据，不能当作发布门禁。

`sweep.yaml` 现在有 `nightly` 档位：三个固定 seed 各跑 120 步自然探索，打开 `--shrink-failures`，再做 200 目标的 assisted smoke，最后把未归因 `hard_fail` 数量作为失败条件。

`tools/exploration_gate.py` 把这些报告合成一层 fail-closed gate：核对 target identity、跨报告 identity drift、所有 run 是否 complete、未归因 `hard_fail` 是否为 0，并接收 Mod runtime inventory 和 Android summary。`--release` 还要求报告里已有 `source_commit`、`mods_lock_sha256` 和 `source_index_sha256`，并且传入的 source index 文件 SHA-256 与 manifest 一致、source index 自身的 source commit 与报告 source commit 一致。`--target` 和 `--mods-lock` 会让 gate 重新计算实际文件 SHA-256；release 模式必须传入这两个文件并匹配 manifest，非 release 的 assisted-full-coverage gate 只要提供了文件，也会在 digest 漂移时 fail-closed。Mod inventory payload 数与 manifest 一致、无错误、无静态 passage 遗漏、无未分类 mod passage、按钮隔离调用无异常，Android semantic replay 全 matched。release 还会用 source index 计算唯一的静态目标数，并要求 assisted shard 的 unique ok targets 覆盖全部静态目标、没有跨分片重复；2026-10-14 起还要求 android summary 的 `apk_sha256` 与 target manifest 的 `target.apk_sha256` 逐字节一致（`android_apk_sha256_matches`，任一侧缺失即 false）。这些条件缺一时 `completion_claim` 永远是 `none`。

`--assisted-full-coverage` 是独立于 Android release gate 的全量静态覆盖门禁。它允许只验收“14,662 个静态目标是否被 assisted shard 去重后全部 ok”，不要求 Android；full tier workflow 用 8 个 shard 跑这条路径，最后单独生成 `assisted-gate`。

`--mod-passage-sweep` 把 runtime-only Mod passage 的真实 sweep 结果接入 gate。release 和有 Mod inventory 的 evidence gate 都要求 inventory 里的 playable runtime-only passage 被实际尝试、completeness 通过、无 hard_fail、无重复结果。

2026-10-13（Plan v5）之后，`--release` 还接收 6 份外部方法证据，缺一份即 fail-closed：`--symbolic-reachability`（`static_reachability_solver`，非 `solver_unavailable`）、`--story-graph-audit`（full mode、两类 unclassified 为空）、`--traversal-stats`（natural 轨道有真实动作分母）、`--query-regression`（`release_blocking` 为空）、`--au-contract`（AU 行 schema 正确、无 errors、框架导出 ≥1、变体目录 shim marker = 1）、`--framework-contract`（`verdict == consistent`）。daily/nightly 不传这些参数时条件为 `null`，只产报告。

**APK 身份绑定（2026-10-14 已落地）**：此前 `android_gate_ready` 只读 summary 的 `verdict` / `cdp_connected` / `totals`，**不比对 APK SHA-256 与 target manifest**——2026-10-14 的 release 链里这条是 `true`，但它绑的是 2026-09-30 构建的 APK（`56dd6491…`），不是 shim 载体（ZIP `96939f3f…`）。现已收紧：`tools/target_manifest.py` 的 `--apk` 会把 APK 的 SHA-256 写入 `target.apk_sha256`（可选字段，缺失不报错，保持向后兼容）；release 档新增条件 `android_apk_sha256_matches`，要求 manifest、android summary、本机文件三方摘要逐字节一致，任一侧缺失或不等即 fail-closed，`android_gate_ready` 同步收紧，daily/nightly 不受影响。回归测试覆盖匹配 / 任一侧缺失 / 不相符 / 非 release 全四种配对态。历史结论不变：0915 那次绿灯不能读成“shim 载体已过真机门禁”，shim 载体必须重新走一遍绑定后的门禁。

## Android

Android 回放只能使用 semantic action trace：`semantic_id`、`kind`、`role`、`text_hash`、`expected_passage`。桌面 CSS selector 和 XPath 不进入 Android plan。匹配只允许 semantic id、identity 和 text hash；匹配成功后，可以执行 Android WebView 运行时刚分配的临时 `[data-dolx-action-index]`，但它只是执行句柄，不能当作跨设备定位器或计划输入。

`tools/android_replay.py execute` 会连接已运行 app 的 WebView CDP，采集 Android-side candidates，逐条匹配 semantic action，再输出 matched / ambiguous / unmapped / action_failed、截图、pageerror/console/network 观察、Android/WebView 版本和 logcat 摘要。没有设备或 CDP target 时结果是 `infrastructure_fail`，不能当作回放通过。

冷启动会把操作系统的 `Start` passage 与 ModLoader 的启动画面重叠：ModLoader 在 SugarCube 装载剧情之前就能提供可交互控件。因此 readiness 除了要求 candidate 存在，还要求 `SugarCube.State.passage` 已经等于计划的首个 passage（计划里取 `expected_passage`，bootstrap 步骤回退到 semantic id 前缀）。始终等不到该 passage 时结果是 `infrastructure_fail`，不会把被启动过程掩盖的步骤写成产品级 `unmapped`。

每次回放都要先用设备侧身份确认被测对象：安装 APK 后 `adb pull` 回 `base.apk` 并核对 SHA-256 与本地 artifact 一致，再把该 digest 写入 summary。

Android 报告必须区分 clean install、自然新游戏回放、保留存档回放和辅助存档进入深层场景；`--profile-mode clean_install|natural_new_game|preserved_save|assisted_save` 会把实际使用的档位写进 summary，缺省时不猜档位。清空设备数据只允许用于明确的 disposable profile；`execute` 默认不执行 `pm clear`。

计划与档位必须一致：`Start` 在验证前显示年龄确认复选框，验证后显示游戏模式选择，两者的 semantic id 完全不同。从“已通过验证”档位抓取的 trace 只能在同状态档位上回放；在 clean profile 上硬跑会得到全量 `unmapped` 的 `failed`，这是档位不匹配的证据，不是产品缺陷。`android-plan-natural-014-with-start.json` 就属于这类旧变体，发布证据固定使用从 clean profile 自然起步的完整 trace。

## 报告边界

完整报告按 target identity、coverage、failures、evidence archive 分层。没有 Android 门禁、没有全量 assisted 覆盖、或仍有未归因 `hard_fail` 时，只能写“当前档位探索完成”，不能写“全流程测试完成”。
