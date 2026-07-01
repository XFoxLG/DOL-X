# 会话状态 2026-07-01

承接 2026-06-30 会话。本文档记录 2026-07-01 会话的操作、决策与待办,供后续会话(或上下文压缩后)快速恢复。上一份 `SESSION_STATUS_2026-06-29.md` 的诊断结论仍然有效,未被推翻。

## 一句话现状

侧边栏诊断已收尾(见 6-29 文档),无活跃阻断问题。本会话做了三件运维/规划工作:再次确认 WAF 由 `AGENTS.md` 触发并保持精简版、清理超额的 CI artifact、完成 D.O.L.I 集成前调研。BunnyTransformation 正式放弃。美化包冲突问题本轮不处理。

## 本会话完成的事

### 1. WAF / AGENTS.md(再次证实,非新结论)

用户又遇到 BYOK / Cloudflare 403,把根目录 `AGENTS.md`(3778 字节的较大版本)改名成 `AGENTS.md.bak`、换上精简版(2087 字节)后立即恢复。这是对既有记忆节点 `core://dol-x-project-info/waf-byok-403-guide` 的**第三次实证**:自动注入的 `AGENTS.md` 越大越容易命中 WAF,精简纯散文版安全。

- 当前被 git 跟踪的 `AGENTS.md` = 2087 字节干净散文版,由 agent 接管维护,内容不再手动改动。
- `AGENTS.md.bak`(3778)、`.cursorignore.bak`(900)带 `!!`,已被忽略,是本地救火备份,**不提交**。
- 教训(已隐含在启动协议):遇到 403 先读 WAF 记忆节点再行动,不要凭上下文抢答归因。

### 1b. WAF 第四次复现(2026-07-01 晚,策略固化)

同一会话稍晚,用户再次遇到 403,这次把 2087 字节的**精简纯散文版** `AGENTS.md` 改名成 `AGENTS.md.bak1` 才恢复。这是关键升级证据:

- **精简纯散文版也会触发**,不是"内容脏"的问题。`AGENTS.md.bak1` 经确认是纯散文,无命令/代码/管道/宏。
- 真正机制:该第三方中转对"根目录自动注入 AGENTS.md 这一行为本身"敏感,累计评分顶阈值,内容干净与否都可能中招。逐字洗内容治标不治本。
- **固化策略**:DOL-X 默认**不依赖根目录 `AGENTS.md` 自动注入**。上下文恢复主要靠 MCP 记忆 + `docs/SESSION_STATUS`。`AGENTS.md.bak1` 与之前的 `AGENTS.md.bak` 一样是本地救火备份,**不提交**。
- 遇到 403 别再纠结"文件写得够不够干净",直接让它退出自动注入(改名)即可,这是已验证四次的有效动作。
- 记忆节点 `waf-byok-403-guide` 已同步这条第四次复现结论。

### 2. CI artifact 清理(不可逆,已执行并核实)

GitHub Actions artifact 存储涨到 **573 个 / ~89 GB**,超配额。经用户确认"保留最新 3 次构建",执行删除:

- 删除 564 个,**释放 ~86.5 GB**。
- 剩余 9 个 / 2.55 GB:run `28461618104`(6-30)、`28390261132`、`28354033076`(6-29),每个 run 含 apk + zip + apk-sample。
- 保留的最新 run 正是侧边栏对比用的那次。
- 已在 CHANGELOG `Unreleased > Removed` 记录。

### 3. D.O.L.I 集成前调研(尚未集成)

`ArsNativa/Degrees-of-Lewdity-Intelligence` —— 用 LLM 给 DoL 加 AI 对话 + 战斗文本增强的 agent mod,ReAct 模式,可配 OpenAI 兼容后端。许可证 **CC BY-NC-SA 4.0**。

关键事实(取自其 README.zh / boot.json / .gitmodules):
- **本身是 maplebirch 插件**:`boot.json` 的 `addonPlugin` 要求 maplebirch `^3.1.0`,依赖 ModLoader `^2.0.0`。当前 DOL-X maplebirch 3.1.14 + ModLoader 2.101.1 **全部满足**,无需改版本锁。
- 挂载面小:往 maplebirch Options 挂一个 `doliMaplebirchOptionsEntry` 入口 + `twee/widgets.twee` + 一个 `patches/overlay-replace.json`。
- 集成方式**与 GuideToMe/NeoUI 相同**:下载器加一条、加一个 mod-code feature bit(参考 commit `0197f79` 补 `ModCode` 枚举的做法)、matrix/combinations 加组合。属多文件配置改动。
- 版本:最新 release `v0.2.3`(2026-03-28);仓库 HEAD 的 boot.json 仍写 0.2.2(tag 领先 main,正常)。集成应拉 release 的 `DOLI.mod.zip`,不自建。

集成时需注意的所有情况:
- 0.2.x 早期阶段,README 明说"更多功能开发中",预期不稳定 → 按保守版本锁策略**钉死到 v0.2.3**,不跟 latest 漂。
- LLM 需玩家自行在游戏内填 API key;**构建系统绝不嵌 key**(符合不提交密钥红线)。未配后端时 mod 仍能加载,只是 AI 功能不工作。
- 它动 overlay 补丁,NeoUI 也动 overlay/侧栏,都走 maplebirch/ModLoader,大概率共存,但**首次加入必须盯一次加载日志**确认不打架。

**下一步(待用户点头再动手)**:按上述 pattern 改 `config/` 下载器 + feature bit + combinations + mods.lock,锁 v0.2.3,本地 `python main.py matrix` / `pytest` / `quick_check.py` 验证,再出 CI 包实测加载日志。

## 本会话的决策

- **BunnyTransformation 正式放弃**:此前因 16 个 TweeReplacer 错误 + 战斗崩溃已在 config 禁用(`bunny_transformation` skip=true)。本会话确认**不再投入维护/自行更新**,长期保持禁用。年久失修,自行维护成本不划算。
- **美化包冲突(inuno/犬野等)本轮不处理**:已知会与 AU 美化冲突,留待后续单独规划。
- **已知噪声接受**:两份加载日志的 3 error / 2 warning(cheat v1.17 的 Widgets Market、maplebirchEx v1.2.4 的 time.js beauty、1 个 CSS、maplebirch zone 的 Eden 正则 2 warning)是版本轻微漂移导致的补丁失配,不阻断,接受现状,日后单独清理。

## 当前配置口径(未改动,承接 6-29)

- `config/build.toml`:AU-F = `AUfemale.model_v0.9.3.zip`;`neoui_patch` enabled=true;`au_face` enabled=false。
- `config/features.toml`:`neoui_patch` skip=false;`bunny_transformation` skip=true。
- `config/combinations.toml`:build codes `5218560` / `5219584` / `7316736` / `5220608` / `5222656`(5 个)。

本会话未改动任何 `config/`。改动仅限:`AGENTS.md`(精简版,已由用户换好)、`CHANGELOG.md`(加 artifact 清理 Removed 条目 + 修正 NeoUI 归因表述)、本 SESSION_STATUS 新建。

## 提交卫生提醒(承接并强化)

- 不要 `git add .`。
- `AGENTS.md.bak`、`.cursorignore.bak`:本地 WAF 救火备份,**不提交**。
- `AGENTS.md` 精简化属"平台注入策略修复",可单独提交,但需确认是纯散文、无命令/代码/宏。
- `CHANGELOG.md`、本 SESSION_STATUS:可提交。
- `docs/AGENTS_FULL.md`:若含命令/代码/宏,只作非自动注入参考,提交前确认无密钥/逆向/敏感路径。
- 之前遗留的 `docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md` 的 CRLF 噪声改动仍属换行符层面,不必单独提交。

## 环境约束(不变)

- 本地能跑:pytest、git、`python main.py matrix`、curl、gh。
- 本地不能:完整构建、APK 签名、imagepack 解压(缺 unrar)。完整构建走 GitHub Actions。
- Windows:bash 需用 `C:\Program Files\Git\bin\bash.exe`。
