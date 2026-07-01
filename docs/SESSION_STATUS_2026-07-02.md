# 会话状态 2026-07-02

承接 2026-07-01 会话。上一份 `SESSION_STATUS_2026-07-01.md` 把 D.O.L.I 停在"集成前调研"阶段,本会话把它真正落地、验证、提交并推送到远程。本文档记录本会话的操作、决策与当前状态,供后续会话(或上下文压缩后)快速恢复。

## 一句话现状

D.O.L.I 已完成集成并推送到 `origin/vega`,构建矩阵从 5218560 系列迁移到 13607168 系列,工作区干净,本地与远程完全同步。无活跃阻断问题。

## 本会话完成的事

### 1. D.O.L.I 集成落地(已提交并推送)

把上一会话调研好的方案真正写进配置,提交为 `e201211`(`feat(mod): integrate D.O.L.I v0.2.3 into build matrix`),涉及 9 个文件:

- `lyra/config.py`:新增 `DOLI = 8388608` 枚举 + `get_suffix()` 里加 `doli` 分支(文件名追加 "doli")。
- `config/features.toml`:新增 `[[features]] id="doli"` 块,bit 8388608,required=true,depends_on=["cheat_extended_maplebirch"](它是 maplebirch 插件)。
- `config/combinations.toml`:更新 build_codes、base_code=13607168、recommended、注释。
- `config/build.toml`:新增 `[[modloader_mods]] key="doli"` 块,download_url 钉死到 release v0.2.3 的 DOLI.mod.zip。
- `config/mods.lock.json`:新增 doli 锁定条目(仓库、asset pattern、release_tag v0.2.3、许可证 CC BY-NC-SA 4.0、maplebirch 插件说明、API key 由玩家自填的红线)。
- `tests/test_build_matrix.py`:更新 3 个受影响的硬编码测试到新 code 值。
- `.gitignore`:配合调整。

### 2. Build code 迁移(全部 +8388608)

D.O.L.I 作为 required 且进全部 5 个构建,每个 build code 加上它的 bit 8388608:

- base: 5218560 → 13607168
- AU-F(无 NeoUI): 5219584 → 13608192
- AU-F + NeoUI(对比): 7316736 → 15705344
- AU-M: 5220608 → 13609216
- AU-A: 5222656 → 13611264

`python main.py matrix` 已确认输出这 5 个新 code。

### 3. AGENTS.md 退役 + WAF 文档(已提交并推送)

本会话又一次遇到 BYOK / Cloudflare 403。按已固化四次的策略,不再纠结文件内容干净与否,直接让根目录 `AGENTS.md` 退出自动注入。提交为 `55a4cf0`(`docs: retire auto-injected AGENTS.md, add WAF-safe context docs`),涉及 4 个文件:

- 删除根目录 `AGENTS.md`(完整指引已保底在 `docs/AGENTS_FULL.md`)。
- 新增 `docs/AGENTS_FULL.md`(363 行,完整项目指引的非自动注入参考版)。
- 新增 `docs/WAF_TROUBLESHOOTING.md`(57 行排障手册)。
- 更新 `docs/SESSION_STATUS_2026-06-29.md`(补入加固策略)。

固化结论(与记忆节点 `waf-byok-403-guide` 一致):DOL-X 默认不保留会被自动注入的根目录 `AGENTS.md`。上下文恢复只依赖 MCP 记忆 + `.cursor/rules/session-recovery.mdc`(纯散文,可继续自动注入)+ `docs/SESSION_STATUS`。`AGENTS.md.bak` / `.bak1` / `.cursorignore.bak` 是本地救火备份,不提交。

### 4. CHANGELOG 口径统一(本会话新改)

CHANGELOG 的 `### Added` 段(D.O.L.I 条目)已在 `e201211` 里写了新 code,但 `### Changed` 段的旧 build code 清单仍是 5218560 系列,两段自相矛盾。本会话把 `### Changed` 那段更新为 13607168 系列并标注"见上方 Added 条目",消除矛盾。此改动待随下次收尾提交。

## 提交与推送记录

推送到 `origin/vega`,范围 `91cc0f4..55a4cf0`,两个提交:

- `e201211` — D.O.L.I v0.2.3 集成进构建矩阵
- `55a4cf0` — 退役自动注入的 AGENTS.md + WAF 安全文档

推送前审阅结论:13 个文件全是配置/测试/文档,敏感文件扫描零命中(`.bak`/`.env`/secret/token/key 均未被追踪),`AGENTS.md.bak1` 等本地备份确认未追踪,干净快进推送无冲突。`git status -sb` 显示 `## vega...origin/vega`(完全同步)。

## 本会话的过程教训(诚实记录)

- 上一会话结尾我小结说"三个文档已暂存",但重新核对时 `git diff --cached` 是空的,实际未暂存成功。已纠正并重新暂存。教训:小结里的状态声明也要以 `git` 实查为准,不能凭记忆。
- PowerShell 不支持 bash heredoc,`git commit -m "$(cat <<'EOF'...)"` 直接解析失败。改用把提交信息写进临时文件、`git commit -F` 的方式解决,临时文件已清理。后续在本机构造多行提交信息一律走 `-F 文件`,不用 heredoc。

## 待办 / 下一步

- **首次 D.O.L.I CI 构建必须盯一次加载日志**:确认它与 NeoUI 的 overlay、maplebirch 栈共存不打架。这是集成后唯一未验证的点。
- CHANGELOG 的 `### Changed` 口径修正 + 本 SESSION_STATUS 待随收尾提交(如已提交则忽略)。
- 美化包冲突(inuno/犬野等)仍暂缓,后续单独规划。

## 当前配置口径(D.O.L.I 集成后)

- `config/combinations.toml`:build codes 13607168 / 13608192 / 15705344 / 13609216 / 13611264(5 个),base_code=13607168。
- `config/features.toml`:新增 doli(8388608,required,depends_on cheat_extended_maplebirch);neoui_patch enabled;bunny_transformation skip=true;au_face enabled=false。
- `config/build.toml`:AU-F = `AUfemale.model_v0.9.3.zip`;doli 钉死 v0.2.3 DOLI.mod.zip。
- 版本锁不变:maplebirch v3.1.14、cheat extended v1.17。

## 已知噪声(接受现状,承接 07-01)

两份加载日志的 3 error / 2 warning(cheat v1.17 的 Widgets Market、maplebirchEx v1.2.4 的 time.js beauty、1 个 CSS、maplebirch zone 的 Eden 正则 2 warning)是版本轻微漂移导致的补丁失配,不阻断,接受现状。

## 环境约束(不变)

- 本地能跑:pytest、git、`python main.py matrix`、curl、gh。
- 本地不能:完整构建、APK 签名、imagepack 解压(缺 unrar)。完整构建走 GitHub Actions。
- Windows:bash 需用 `C:\Program Files\Git\bin\bash.exe`;PowerShell 不支持 heredoc,多行提交信息走 `git commit -F 文件`。
