# 会话状态 2026-06-29

本文档记录 2026-06-29 会话的诊断结论与决策,供后续会话(或上下文压缩后)快速恢复。

## 一句话现状

项目主干健康(中文/图片已验证可玩)。**AU-F 侧边栏立绘错位问题已不复现,诊断收尾**:在干净的 v3.1.14 栈对比包中,无论 NeoUI 开不开,立绘都正常。原"NeoUI 是头号嫌疑"假设**已作废**,根因指向更早已被移除的 v4.x 强行兼容补丁 + maplebirch v4.x 栈(见 commit `d3bcd47`)。当前无活跃阻断问题。

> **2026-06-30 诊断收尾**:用 CI run `28461618104` 的两个 AU-F 包(文件名以 `neoui-patch` 区分)做了侧边栏实测,结论反转——
>
> 1. **立绘错位两个包都不复现**。无 NeoUI(`5219584`)和含 NeoUI(`7316736`)的立绘渲染都正常。NeoUI 被**洗清**:它不是立绘错位的原因。
> 2. **NeoUI 的"覆盖式遮挡正文"是其设计本意,不是 bug**。用户判定"能用就用",两个 AU-F 包**永久并存**供选择,配置不动。
> 3. **根因结论(证据最强推断,非铁证)**:最初出错位时栈是 maplebirch **v4.x + `patches/expansion_v4_compat.js` 强行兼容 shim**,该 shim 导致 `maplebirch is not defined`(commit `d3bcd47` 删除它的理由)。回滚到 v3.1.14 稳定栈 + 删 shim + 干净重装重建 BeautySelector 缓存(日志里那段 77 秒 `Cache file to IndexDB ...10...80`),三者叠加后错位消失。**不是这轮 mod/游戏更新修好的**(两个对比包游戏版本 `0.5.10.12`、所有 mod 版本完全一致)。
> 4. **无法 100% 证明** v4 shim 是错位的唯一单独成因——手上没有当时崩溃状态的包可做 A/B。但当前干净栈下问题确认不复现。
>
> 之前的产物文件名碰撞 bug 已在 commit `0197f79` 修复并由本 run 验证(APK 恢复 5 个 / 588 MB),正是它让这次干净对比成为可能。

## 本会话的关键修正(推翻此前归因)

### 1. AU 版本基本被排除为错位主因
- 上游 Lyra 用**无版本号**模式拉 AU,实际取到的就是 `AUfemale.model_v0.9.3`(AOKIUTAGE 的 `mod` tag 下 AUfemale 最新即 v0.9.3,无更高版本)。
- **同一个 v0.9.3,上游侧边栏正常、DOL-X 错位** → 错位与 AU 版本无关。
- 之前从 v0.9.3 回滚到 v0.8.7 的诊断假设不成立。

### 2. ~~NeoUI-Patch 成头号嫌疑~~（2026-06-30 已作废）
> **此假设已被实测推翻**,保留原文仅作推理留痕。对比包证明 NeoUI 开/关立绘都正常,它不是错位原因。它改 `#story { margin-left }` 做的覆盖式抽屉侧边栏遮挡正文是**设计本意**,用户判定"能用就用"。详见顶部 6-30 诊断收尾。
- ~~它故意改 `#story { margin-left }` 做**覆盖式抽屉侧边栏**,会遮挡内容。~~
- ~~[docs/COMMUNITY_MOD_RESEARCH_2026.md](COMMUNITY_MOD_RESEARCH_2026.md) 记载:NeoUI 最初因"覆盖式布局遮挡内容"被**拒绝/禁用**,2026-06-24 又改为"观察阶段启用"。~~
- ~~用户报告的"开始菜单遮挡东西"正是当初拒绝它的原因。~~

### 3. au_face 确认是禁用的
- `config/build.toml` 中 `au_face` 为 `enabled = false`,Mod 管理器列表也无面部扩展。
- 此前"maplebirch + au_face 叠加致错位"是**错误归因**,已纠正。
- 规则重申:不要假设每个 AU 侧边栏错误都是 au_face 引起。

### 4. git "完整同步"是空操作
- `git fetch upstream` 后:DOL-X vega 与 upstream/vega = **161 ahead, 0 behind**。
- 上游最新 tag `v0.5.10.12-1.0.8a-0628` 与 `upstream/vega` 同一 commit,且已在 DOL-X 历史内。
- `git merge upstream/vega` 会直接 "Already up to date"。两边产物差异只来自 config(AU 版本钉死、maplebirch 栈、au_face shim),而这些正是同步时**保留本地、不被覆盖**的部分。

### 5. 两个"问题"实为澄清
- **染发店缺十六进制输入框**:不是 bug。需先点"自定义染发"选项才出现输入框。
- **战斗崩溃**:元凶是 BunnyTransformation(16 个 TweeReplacer 错误 + `Cannot use 'in' operator to search for 'wings' in undefined`),已在 config 禁用,待不含它的新包运行时确认。

## 社区工具调研:早已完成(此前反复失忆)

数据源 `degreesoflewditycn.miraheze.org/wiki/模组列表#模组相关工具` 已调研,结论在 4 份文档:
- [COMMUNITY_TOOLS_RESEARCH_2026-06-24.md](COMMUNITY_TOOLS_RESEARCH_2026-06-24.md)
- [COMMUNITY_TOOLS_COMPARISON.md](COMMUNITY_TOOLS_COMPARISON.md)
- [COMMUNITY_TOOLS.md](COMMUNITY_TOOLS.md)
- [COMMUNITY_MOD_RESEARCH_2026.md](COMMUNITY_MOD_RESEARCH_2026.md)

核心结论:社区工具多为用户端 GUI / mod 开发用,无法直接接入 DOL-X 的 Python 构建系统。值得动手但未做的两件:
1. 借鉴 `NumberSir/DOL-Mod-Created-Helper` 的本地测试服务器(REMOTE_TEST,改完刷新即看,比每次出 APK 装 MuMu 快)。
2. `Lethivia/DoL-Commit2Mod`(把上游 commit 单独打成 mod 测试)。

## 当前执行状态（2026-06-30 诊断已收尾）

侧边栏对比验证**已完成**(见顶部 6-30 收尾)。立绘错位不复现,NeoUI 洗清,无活跃阻断问题。**配置保持现状不动**:两个 AU-F 包(带/不带 NeoUI)永久并存供用户选择。

当前配置口径(确认保留):
- `config/build.toml`: AU-F 使用 `AUfemale.model_v0.9.3.zip`; `neoui_patch` 为 `enabled = true`(下载/注入资格,实际由 feature bit 精确控制); `au_face` 仍为 `enabled = false`。
- `config/features.toml`: `neoui_patch` 为 `skip = false`(注释已更新为"诊断收尾、永久 opt-in、非病因"); `bunny_transformation` 仍为 `skip = true`。
- `config/combinations.toml`: build codes 为 `5218560` / `5219584` / `7316736` / `5220608` / `5222656`(共 5 个)。`7316736` = AU-F + NeoUI,与 `5219584`(AU-F 无 NeoUI)唯一差异为 NeoUI(bit 2097152)。`1048576`(BunnyTransformation)仍排除。

遗留待清理(非阻断,与侧边栏无关):两份日志均有 3 error / 2 warning,系版本漂移导致的补丁失配——`cheat extended v1.17` 的 `<<if $stall_amount gte ...>>`(Widgets Market)、`maplebirchEx v1.2.4` 的 `statChange.skill("beauty", ...)`(time.js)、1 个 CSS 替换失败,加 maplebirch zone 模块 Eden 正则 2 warning。说明 cheat v1.17 / maplebirchEx v1.2.4 对 `0.5.10.12` 有轻微脱节,可日后单独清理。

## 本地验证结果（2026-06-30 配置收尾后复跑）

- `python -m pytest tests/test_build_matrix.py -q`: 16/16 通过(含新增的产物后缀唯一性测试)。
- `python main.py matrix`: 输出 `["5218560", "5219584", "5220608", "5222656", "7316736"]`(共 5 个)。
- `python tools/quick_check.py`: 通过。9/9 enabled mod URLs 可访问;检测到 `guide_to_me` / `neoui_patch` / `npc_social_icon` 启用,`bunny_transformation` 禁用;`mods.lock.json` 与 `build.toml` 同步。
- 本次仅改动 `config/features.toml` 一行 neoui_patch 注释,结构未动,验证确认配置未被改坏。

## 记录分层与更改日志规范

本会话确认:Git 提交不能替代 changelog。DOL-X 后续按四层记录体系维护:

- `CHANGELOG.md`:只写用户、测试者或发布接收者真正会看到的 notable changes。格式基于 Keep a Changelog 1.1.0,版本语义参考 Semantic Versioning。Git commit hash、build code、artifact 名称可以作为追踪证据,但不能替代人类可读发布摘要。
- `docs/SESSION_STATUS_YYYY-MM-DD.md`:实时工作台。记录当前会话的证据、推理、已推翻假设、下一步、验证结果和提交卫生提醒。被 Cursor 自动压缩或换窗口打断时,优先读这里恢复。
- MCP memory:只写会改变未来行为的稳定判断、用户偏好、项目策略或反复出现的错误模式。不把临时猜测、未验证观察或一次性日志写入长期记忆。
- `AGENTS.md` / `.cursor/rules`:只保留短、稳定、WAF-safe 的仓库护栏。大段排障、命令、代码块、HTML/macro 片段、救援备份和敏感分析细节放到 docs 或本地 `.bak`,不要放入自动注入层。

当前 CHANGELOG 维护口径已同步为:
- 顶部说明链接到 Keep a Changelog 1.1.0。
- SemVer 链接到官方主页。
- 后续发布前把 `Unreleased` 中的项目整理为正式版本条目,必要时使用 yanked/superseded 口径,不要用 git log 直接生成发布说明。

## 提交卫生提醒

正常配置/测试/项目文档可以进入主线提交,但不要盲目 `git add .`。`.cursorignore.bak`、`AGENTS.md.bak` 属于本地 WAF 救援备份,不能进入正常提交。`AGENTS.md`、`docs/AGENTS_FULL.md`、`docs/WAF_TROUBLESHOOTING.md` 和本会话状态文档需要单独审查后再决定是否提交。

## 环境约束(不变)

- 本地能跑:pytest、git、`python main.py matrix`、curl。
- 本地不能:完整构建、APK 签名、imagepack 解压(缺 unrar)。完整构建走 GitHub Actions。
- Windows:bash 需用 `C:\Program Files\Git\bin\bash.exe`。
