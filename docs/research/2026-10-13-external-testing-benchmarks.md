# 外部测试方案调研档案（2026-10-13）

> Plan v5（外部测试方案融合 + AU 契约验证防线）第 1 项交付物。
> 用途：记录我们参考过的外部测试体系、每条结论的核验方式、以及与我们预期不符的负结论。
> 纪律：本文所有“结论”必须能在本机按第 5 节的命令复核；“未能核实”的条目单独列出，禁止当作结论使用。

## 0. 一句话总览

DOL-X 的测试路线不是自创：SugarCube 官方只提供调试态的 Test Mode；上游 DoL（Vrelnir）用 shell / Python lint 脚本加人工测试；DoL Plus 有一小套 Playwright 端到端测试但 CI 不执行它；真正把测试跑进 CI 的是同类游戏 Corruption of Champions 的社区 mod（ant/JUnit）；ChoiceScript 官方自带 Quicktest / Randomtest；学术侧 DendryScope 用 ASP（answer set programming，符号逻辑求解）在有限步数内搜索可玩轨迹。

## 1. 总览表

| # | 外部来源 | 采纳的成熟组件 | 落地形态（本项目工具） | 核验 |
|---|---|---|---|---|
| 1 | SugarCube v2 官方文档 | Test Mode（`tweego -t/--test`） | 仅用于 assisted tier 的宏错误 smoke，不做遍历 | 已核实 |
| 2 | Goctionni/SugarValidator | `<<>>` 配平与条件嵌套校验 | `tools/sugarcube_validator.py`（同族重写） | 已核实 |
| 3 | aucchen/SugarCube 随机玩家 gist | Selenium 随机点击 + 读 `SugarCube.State.active.variables` | `tools/exploration_agent.py`（自然轨道） | 已核实 |
| 4 | ChoiceScript Quicktest/Randomtest | 枚举每个选项/if 两侧 + 固定次数随机游走 + hit count | `config/exploration-queries.toml` + 固定 seed 随机探索 | 已核实 |
| 5 | DendryScope（AIIDE 2023） | ASP 有界 playtrace 与 query | `tools/static_reachability_solver.py`（clingo） | 已核实 |
| 6 | Vrelnir 上游脚本 | `sanityCheck.sh`（41 项）／`devTools/check.py`／`devTools/macro_check.py` | `tools/sugarcube_validator.py` lint 清单 | 已核实（原文位置见 2.6） |
| 7 | DoL Plus（Frostberg） | Playwright 端到端测试（7 个 spec）+ 资产存在性检查 | 与我们的 `passage_sweep` / 关键旅程同构 | 已核实（修正了旧说法，见 3.1） |
| 8 | DoL-Lyra/Lyra、ModLoader CI | 只有构建与发布，无测试 | 说明我们的 CI 增量是真实缺口 | 已核实 |
| 9 | i18nMod `test/` | 仅数据/序列化校验 | 不需要借鉴 | 已核实 |
| 10 | Ice-Bound（FDG 2014） | 组合式内容必须有可量化度量 | `tools/traversal_statistics.py` | 已核实 |
| 11 | CoC 社区 mod（Kitteh6660 系） | `ant` + JUnit 单元测试跑进 CI | 同类游戏对照先例 | 已核实 |
| 12 | SyntheticPlayer.js（esthers） | 故事图完整性审计 | `tools/story_graph_audit.py` | **未能核实**（见 4.1） |
| 13 | PlotEx | 可达性当回归单元测试 | `config/exploration-queries.toml` | **未能核实**（见 4.2） |
| 14 | CoT（用户提到的友情链接游戏） | — | — | **未能定位**（见 4.3） |

## 2. 逐条记录

### 2.1 SugarCube v2 官方 Test Mode

- 来源：<https://www.motoslave.net/sugarcube/2/docs>（Test Mode 章节）、<https://www.motoslave.net/tweego/docs>（`-t`、`--test`）
- 复核：抓取上述两页，检索 “Enabling Test Mode” 与 “`--test`”。
- 结论：官方 Test Mode 是**调试界面**（变量监视、任意历史跳转，SugarCube ≥ 2.23.0），不是自动化测试框架；Tweego 提供 `-t/--test` 编译开关。
- 负结论：SugarCube 官方**没有**提供自动遍历、随机玩家或断言 API。官方文档同时提醒调试视图会引入额外 DOM，可能破坏部分嵌套标记与选择器——这也是我们只把 Test Mode 用在 assisted smoke、不用于自然轨道判定的原因。

### 2.2 SugarValidator（社区静态校验器）

- 来源：<https://github.com/Goctionni/SugarValidator>
- 复核：抓取仓库 README；文中含浏览器拖拽、npm 包、CLI（`sugarvalidator`）、Node 脚本四种用法。
- 结论：检查 `<<` / `>>` 配平与 `<<if>>` / `<<elseif>>` / `<</if>>` 结构；作者注明“大多数 SugarCube 游戏发布时都会带几个这类错误”。
- 采纳：`tools/sugarcube_validator.py` 与其同族（我们不直接依赖 Node 包，保持 Python 单栈）。

### 2.3 SugarCube 随机玩家示例（gist）

- 来源：<https://gist.github.com/aucchen/808ebf87a8ebd7d6ecb2d4753eff9ba5>（“automated random tester for twine-sugarcube”）
- 复核：抓取 gist 文本；核心循环为 `driver.find_elements(By.XPATH, '//a[@class="link-internal"]')` → `random.choice` → `click()`，完成后 `return JSON.stringify(window.SugarCube.State.active.variables, null, 2)` 落盘 transcript。
- 结论：社区长期存在的“随机玩家”实践形态 = 真实点击可见链接 + 读取 `SugarCube.State.active.variables` 做证据。
- 采纳与差异：我们的 `natural` 轨道采用同样的“真实点击 + 读状态”，但加了语义动作 ID、状态指纹去重、失败缩减与 checkpoint 恢复；gist 版本没有去重、没有断言、没有失败重放。

### 2.4 ChoiceScript Quicktest / Randomtest（对照引擎）

- 来源：<https://www.choiceofgames.com/make-your-own-games/testing-choicescript-games-automatically>、<https://choicescriptdev.fandom.com/wiki/Automatically_testing_your_game>
- 复核：抓取两页正文；Quicktest 逐个测试每个 `#option` 与每个 `if` 的两侧（“作弊”式跳过已测行）；Randomtest 默认随机游玩 10,000 次并输出每个代码行的 hit count 报告。
- 结论：官方明确“两种测试互补，且都不能替代人工测试”；Quicktest 会产生“假 bug”（风格问题）。
- 采纳：Quicktest 的思路对应我们的 query 回归集（把可达性断言当回归单元）；Randomtest 的 hit count 对应遍历统计；官方“不能替代人工测试”的立场支持我们在报告里保留 `fixture_insufficient` / `source_gap` 等非通过分区。

### 2.5 DendryScope（ASP 符号化可达性）

- 来源：<https://jazztap.github.io/dendry-paper/2023_AIIDE_Dendryscope_Camera_Ready.pdf>（AIIDE 2023 论文）
- 复核：抓取论文正文；摘要与正文写明“用现代 ASP 系统实现 playtesting 策略”，适用条件是状态变量取值有限、感兴趣轨迹长度可界定、状态更新规则可以用符号逻辑表达；工具接受 Dendry 语言写成的 QBN。
- 结论：这正是 `tools/static_reachability_solver.py` 的方法论来源——有界（bounded）而不是全知；论文同样把“有限步”作为前提。
- 采纳与差异：我们用 `clingo` 编码 `time(0..N)` 的单步推进，默认 bound=120；对无法证明的目标输出 `unreachable_within_bound`（附 `bound_is_not_proof=True`），绝不写成“不可达”。

### 2.6 Vrelnir 上游：`sanityCheck.sh` / `devTools/check.py` / `devTools/macro_check.py`

- 来源：官方仓库 <https://gitgud.io/Vrelnir/degrees-of-lewdity>（GitGud，非 GitHub）
- 复核（2026-10-13 实测，脚本见第 5 节）：
  - `sanityCheck.sh` 存在，长 10,112 字节，含 **41 条** `run_check`：TripleOpen、TripleClose、RunInConcat、MissingClosingAngleBracket(1/2)、MissingOpeningAngleBracket2、AccidentalAssignmentInIf、AccidentalAssignmentInElseIf、UseCssColors、MissingDollar(1/2)、MissingOpeningBracket(1/2)、MissingClosingBracket(1/2/3)、TooManyAngleBrackets(1/2)、SpellCheck、PregmodderCannotSpellReceive、ShouldBeSlaves、MissingPropertyAfterSlaves、DoubleSlash、ShouldBeElseIf、ElseForAnIf、EqualAndTo、DoubleEqualsInSet、BadCommand、DuplicateWords、ObsoleteMacro、DoubleArticle、VarSignMidWord、VarSignAtMacroStart、MissingSemicolonBeforeStatement(×2)、MissingSpaceInMacro、MissingColonInMacro、MismatchedPassTimes(1/2)、TypeofNotComparedToString。
  - `devTools/check.py` 存在（2,359 字节）：用正则 `<<(\/?) *(if|for|else|switch|case|replace|link)` 检查成对标签。
  - `devTools/macro_check.py` 存在（3,960 字节）：建立 widget（`<<widget>>`）、`Macro.add(...)`、`DefineMacroS(...)`、JS `function` 四类登记表，再用 `used_regex = <</?([\w\-_]+).*?>>` 对账，并有内置宏白名单（if/elseif/else/set/link/include/...）。
- 关键细节：`sanityCheck.sh` 依赖 `git grep`，必须在**源码 git 仓库内**运行（脚本开头检测 `.git`，否则直接 exit 0 并提示 “skipping sanity checks”）——这解释了为什么在我们的构建仓库里搜不到“可运行入口”，它属于上游源码树。
- DoL Plus 的同名文件与上游**逐字节相同**（`plus == sc` 为 True，同为 41 checks）。
- 采纳映射（我们的 lint ↔ 上游检查名）：

  | 我们的 lint | 上游对应 |
  |---|---|
  | `suspect_assignment_in_condition` | AccidentalAssignmentInIf / ElseIf |
  | `double_equals_in_set` | DoubleEqualsInSet |
  | `deprecated_macro` | ObsoleteMacro |
  | `pass_time_mismatch` | MismatchedPassTimes / MismatchedPassTimes2 |
  | `unbalanced_html_tag` / Twee 配平 | TripleOpen / TripleClose / Missing…Bracket 系列、`devTools/check.py` |
  | `unregistered_macro` | `devTools/macro_check.py` 的登记表对账 |
  | `single_use_variable` | （上游没有直接对应项，来自 `check.py` 语义扩展） |

- 尚未迁移：`SpellCheck`、`UseCssColors`、`BadCommand`、`TypeofNotComparedToString` 等文本类检查（低成本，可在后续版本补）。

### 2.7 DoL Plus（Frostberg）的 Playwright 端到端测试

- 来源：<https://gitgud.io/Frostberg/degrees-of-lewdity-plus>
- 复核（实测 API）：
  - 仓库根目录含 `playwright.config.ts`：`testDir: "./tests"`，`headless: true`，单 project `chromium`。
  - `tests/` 含 7 个文件：`cafe.spec.ts`、`dancestudio.spec.ts`、`docks.spec.ts`、`feats.spec.ts`、`time.spec.ts`、`wear-prop-images.spec.ts`、`helpers.ts`。
  - `tests/helpers.ts`：用 `file://` 直接打开本地 `Degrees of Lewdity.html`，导出 `waitForPassage`（等待 SugarCube 渲染完成）、`getVar`、`wikifyEval`、`assertNoErrors` 等工具函数。
  - `tests/feats.spec.ts`：通过 `page.addInitScript` 预置 `localStorage`（`verifiedAge`、`dolFeats`）后进游戏断言——与我们 fixture 注入同思路。
  - `tests/wear-prop-images.spec.ts`：扫描 twee 源码里的 `<<wearProp "名称" ...>>` 字面量，与 `game/` 图集文件名对账——即**资产存在性检查**（对应 Plan 里“贴图位置/缺失贴图”的关注点）。
  - `.gitlab-ci.yml`：stages 只有 `compilation` 与 `upload`；全文 `playwright` 出现 **0** 次，`npm test` 0 次，`sanityCheck` 0 次（`compile` 出现 19 次）。
- 结论：DoL Plus **有**真正的端到端测试代码，但**没有**在 CI 中运行；CI 只负责编译和上传产物。这既证明“同生态存在可借鉴的 Playwright 方案”，也证明“把测试纳入门禁”在生态里仍是空白。

### 2.8 DoL-Lyra/Lyra 与 ModLoader 的 CI

- 来源：<https://github.com/DoL-Lyra/Lyra>、<https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader>
- 复核（GitHub API 实测）：
  - Lyra `.github/workflows/` = `build.yaml`、`deploy.yaml`、`trigger.yaml`；`build.yaml` 内 `pytest` 出现 0 次。仓库自述为“基于汉化仓库制作的自动化打包仓库，使用 Github Actions 提供多种 Mod 组合”。
  - ModLoader `.github/workflows/` = `Build-InsertTools-Docker.yml`、`Build-ModLoader-Package.yml`（均为构建/打包）。
- 结论：两者 CI 只有构建，无运行时测试——支持我们“测试必须自己建模”的判断。

### 2.9 i18nMod 的 `test/`

- 来源：<https://github.com/Lyoko-Jeremie/Degrees-of-Lewdity_Mod_i18nMod>
- 复核：仓库根含 `test/`，其中只有 `jsonTest.ts` 与 `tsconfig.json`；`jsonTest.ts` 引入 `jszip` / `fs` / `lodash`，是数据/打包序列化校验脚本。
- 结论：这是数据校验，不是游戏运行时测试。Plan 原文判断成立。

### 2.10 Ice-Bound（组合式内容的度量）

- 来源：<http://www.fdg2014.org/papers/fdg2014_paper_23.pdf>（FDG 2014）
- 复核：抓取论文；文中讨论组合式（sockets/lights）叙事必须“high-level metrics and tools”，并给出一个 build 的组合数（约 30–70）等量化讨论。
- 结论：组合爆炸场景里，没有量化度量就无法判断“内容是否写完”；我们对应产物是 `tools/traversal_statistics.py`（按 evidence track 分开的访问率/边覆盖）与报告的 `budget_exhausted` / `frontier_exhausted` 停止条件。

### 2.11 CoC（Corruption of Champions）社区 mod 的单元测试（同类游戏对照）

- 来源：<https://github.com/BelshazzarII/Corruption-of-Champions-Mod>（Kitteh6660 系 fork）
- 复核：README 含 “Testing” 一节：`ant test`、`ant test-single -Dtestclass=classes.Items.MutationsTest`、`ant release` 可跳过测试（原文标注 “not recommended”）；仓库含 `test/` 目录、`build.xml`、`sonar-project.properties`。
- 结论：同类成人文本游戏存在**真正跑在构建流程里的单元测试**先例——说明“这类项目只能靠手测”不成立；也说明我们的方向（把判定与归因做成可回归资产）在生态内有可比对象。

### 2.12 DoL Plus 的 `.gitlab/` 目录（对 Plan 旧说法的修正）

- 复核：仓库根含 `.gitlab/`（GitLab 元数据，如 issue/CI 模板）**同时**含 `tests/`、`playwright.config.ts`、`sanityCheck.sh`。
- 修正：此前记录的“DoL Plus evidence 是 GitLab metadata”若指的是“该仓库只有 GitLab 元数据、没有测试”，**不准确**；准确表述见 2.7。此项属于调研纠错，必须在后续报告中沿用修正版。

## 3. 与 Plan v5 原文的偏差与修正

1. **DoL Plus**：原文“evidence 是 GitLab metadata” → 修正为“有 Playwright 测试（7 spec，含资产存在性检查），但 CI 不运行它们”。
2. **上游 lint 原文位置**：`sanityCheck.sh` / `check.py` / `macro_check.py` 均存在于官方 GitGud 仓库（`game/` 同级与 `devTools/` 下）；此前“本仓库未找到原文”只是因为它们在**上游源码树**，不在 DOL-X 构建仓库。
3. **sanityCheck.sh 依赖 `git grep`**：不能直接拿独立 HTML 或打包产物运行；迁移到 Python 时按清单语义重写是正确路径（我们已这样做）。
4. **SugarCube Test Mode 的定位**：官方文档明确它只影响调试视图且可能破坏嵌套标记——因此它不能作为自然轨道的判定依据，只能做 assisted smoke。

## 4. 未能核实项（禁止当作结论）

### 4.1 SyntheticPlayer.js（esthers）

- 已尝试：GitHub 仓库搜索 `SyntheticPlayer` → `total_count = 0`；多轮网页检索无命中。
- 状态：**未能核实**。`tools/story_graph_audit.py` 的方法是独立重写（networkx 有向图：死胡同/自环/不可达/未定义目标），不依赖该来源；若后续能找到原始出处，需回填 URL 并复核方法是否等价。

### 4.2 PlotEx

- 已尝试：Tavily/Exa 多轮检索（“PlotEx twine / interactive fiction / regression”）无命中；GitHub 仓库搜索 `PlotEx story` → 0。
- 状态：**未能核实**。`config/exploration-queries.toml` 的“可达性当回归单元”思想来自 ChoiceScript 对照与工程直觉（见 2.4），不是因为 PlotEx。

### 4.3 CoT（用户提到的友情链接游戏）

- 已尝试：DoL 官方 wiki “Useful Links” 页面检索 `CoT` → 0 命中；Vrelnir 博客首页检索 `CoT` / `Corruption` → 0 命中。
- 状态：**缩写未能定位**（可能是其它游戏的简称或圈内叫法）。若用户能给出 CoT 的完整名称或链接，再补一条同类测试体系对照。

## 5. 可复核命令清单

以下命令均为 2026-10-13 实际执行过的核验路径（PowerShell + Python 3.12；GitHub API 直连，其它走本机代理）：

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7890'; $env:HTTPS_PROXY='http://127.0.0.1:7890'
$env:NO_PROXY='api.github.com,127.0.0.1,localhost'; $env:no_proxy='api.github.com,127.0.0.1,localhost'

# 1) 上游 DoL：sanityCheck.sh 的 41 条检查名 + devTools 清单
python -c "import json,re,urllib.request; u='https://gitgud.io/api/v4/projects/Vrelnir%2Fdegrees-of-lewdity/repository/files/sanityCheck.sh/raw?ref=master'; t=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'dolx'}),timeout=40).read().decode(); print(len(t)); print(re.findall(r\"run_check '([^']+)'\", t))"

# 2) DoL Plus：测试目录 / Playwright 配置 / CI 是否跑测试
#    （tree API：tests/、playwright.config.ts、.gitlab-ci.yml；对 .gitlab-ci.yml 计数 playwright/npm test/sanityCheck）

# 3) Lyra 与 ModLoader 的 workflows 清单
python -c "import json,urllib.request; h={'User-Agent':'dolx','Accept':'application/vnd.github+json'}; [print(r, [i['name'] for i in json.loads(urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/%s/contents/.github/workflows'%r,headers=h),timeout=30).read())]) for r in ('DoL-Lyra/Lyra','Lyoko-Jeremie/sugarcube-2-ModLoader')]"

# 4) i18nMod 的 test/ 内容
#    GET https://api.github.com/repos/Lyoko-Jeremie/Degrees-of-Lewdity_Mod_i18nMod/contents/test

# 5) 网页侧（浏览器/检索）：SugarCube 文档、SugarValidator、随机玩家 gist、ChoiceScript、DendryScope、Ice-Bound、CoC mod README
```

> 维护约定：本文件只记录“外部世界的事实”。DOL-X 自己工具的验收状态写在 `docs/AUTOMATED_GAMEPLAY_EXPLORER.md` 与 `docs/CURRENT_PROJECT_STATE.md`；两边冲突时以工具报告与测试为准，并回改本文件。
