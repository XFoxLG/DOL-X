# 会话状态 2026-06-29

本文档记录 2026-06-29 会话的诊断结论与决策,供后续会话(或上下文压缩后)快速恢复。

## 一句话现状

项目主干健康(中文/图片已验证可玩)。当前唯一活跃问题是 **AU-F 侧边栏立绘错位**,诊断方向已从"AU 版本"转向 **NeoUI-Patch 覆盖式侧边栏**。

## 本会话的关键修正(推翻此前归因)

### 1. AU 版本基本被排除为错位主因
- 上游 Lyra 用**无版本号**模式拉 AU,实际取到的就是 `AUfemale.model_v0.9.3`(AOKIUTAGE 的 `mod` tag 下 AUfemale 最新即 v0.9.3,无更高版本)。
- **同一个 v0.9.3,上游侧边栏正常、DOL-X 错位** → 错位与 AU 版本无关。
- 之前从 v0.9.3 回滚到 v0.8.7 的诊断假设不成立。

### 2. NeoUI-Patch 成头号嫌疑
- 它故意改 `#story { margin-left }` 做**覆盖式抽屉侧边栏**,会遮挡内容。
- [docs/COMMUNITY_MOD_RESEARCH_2026.md](COMMUNITY_MOD_RESEARCH_2026.md) 记载:NeoUI 最初因"覆盖式布局遮挡内容"被**拒绝/禁用**,2026-06-24 又改为"观察阶段启用"。
- 用户报告的"开始菜单遮挡东西"正是当初拒绝它的原因。

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

## 当前执行状态

**关掉 NeoUI + AU-F 回 v0.9.3** 已进入配置落实阶段。当前目标是出一组对比包验证侧边栏,而不是继续回滚 AU 版本。

当前配置口径:
- `config/build.toml`: AU-F 使用 `AUfemale.model_v0.9.3.zip`; `neoui_patch` 为 `enabled = false`; `au_face` 仍为 `enabled = false`。
- `config/features.toml`: `neoui_patch` 为 `skip = true`; `bunny_transformation` 仍为 `skip = true`。
- `config/combinations.toml`: 当前 build codes 为 `5218560` / `5219584` / `5220608` / `5222656`,已移除 `2097152`(NeoUI Patch) 与 `1048576`(BunnyTransformation)。

下一步验证口径(沿用既定规则):侧边栏展开 + 收起两张截图,与现有 v0.9.3 + NeoUI 启用证据对比;确认新包不含 BunnyTransformation / NeoUI Patch / au_face / Expansion v4.x Compat Patch。

## 本地验证结果

- `python -m pytest tests/test_build_matrix.py -v`: 15/15 通过。
- `python main.py matrix`: 输出 `["5218560", "5219584", "5220608", "5222656"]`。
- `python tools/quick_check.py`: 通过。8/8 enabled mod URLs 可访问;检测到 `guide_to_me` / `npc_social_icon` 启用,`bunny_transformation` / `neoui_patch` 禁用。
- `ReadLints`: 本次触及的 Python 文件无 IDE 诊断。

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
