# DoL-X 自动化 Mod 兼容性测试 - 实施总结

## 已完成内容

### Phase 1: 配置与矩阵测试 ✓

**文件**:
- `tests/conftest.py` - pytest 配置
- `tests/__init__.py` - 测试包初始化
- `tests/test_build_matrix.py` - 构建矩阵测试（13 个测试用例）
- `tests/test_mod_config.py` - Mod 配置测试（22 个测试用例）
- `pytest.ini` - pytest 配置文件

**测试覆盖**:
- ✓ 只构建 4 个稳定自用组合 (24834, 25858, 26882, 28930)
- ✓ polyfill 已关闭
- ✓ 没有在线版配置
- ✓ 基础版 (24834) 不包含 AU
- ✓ AU 三版本包含对应 AU feature
- ✓ 所有版本包含 UCB + more-love + custom-spellbook + 项目本地旧 cheat/CSD 栈
- ✓ 默认版本不包含 cheatExtended/maplebirch 实验 feature
- ✓ AU 面部扩展配置正确
- ✓ feature_ids 有效性
- ✓ cache_name 唯一性
- ✓ github_repo 格式正确
- ✓ base_mods 配置正确

### Phase 2: Mod 资源审计 ✓

**文件**:
- `tools/mod_audit.py` - Mod 资源审计工具（完整实现）
- `config/mods.lock.json` - Mod 锁文件模板

**功能**:
- ✓ 下载所有 modloader_mods 和 base_mods
- ✓ 验证 GitHub release asset 可访问性
- ✓ 计算 SHA256 校验和
- ✓ 检查 ZIP 文件完整性
- ✓ 验证 Mod 结构（boot.json, .js 文件）
- ✓ 风险等级评估（low/medium/high）
- ✓ 生成 JSON 和 Markdown 报告
- ✓ 下载缓存支持
- ✓ GitHub API 错误分类，rate limit 不再误报为 asset 删除

**输出**:
- `output/mod-compatibility-report.json` - 结构化报告
- `output/mod-compatibility-report.md` - 人类可读报告
- `output/cache/` - 下载缓存

### GitHub Actions 集成 ✓

**文件**:
- `.github/workflows/compatibility.yaml` - 兼容性测试 workflow

**触发条件**:
- 每次推送到 `vega` 分支
- Pull Request 到 `vega` 分支
- 手动触发（可选运行慢速测试）

**Jobs**:
1. **config-tests** - 运行配置与矩阵测试
2. **mod-audit** - 运行 Mod 资源审计
3. **html-smoke** - Phase 3 静态 HTML smoke test（非阻断）
4. **browser-smoke** - Phase 4 浏览器运行 smoke test（report-only，非阻断）
5. **slow-tests** - 可选的慢速测试
6. **summary** - 测试总结

**特性**:
- ✓ 自动上传测试结果和报告为 artifacts
- ✓ PR 自动评论审计摘要
- ✓ 高风险 mod 会触发警告但不阻断构建
- ✓ 配置测试失败会阻断构建
- ✓ Phase 4 浏览器 smoke 只在 Compatibility Tests 中临时安装 Playwright，不污染主 Build 依赖

### 依赖和配置 ✓

**更新的文件**:
- `requirements.txt` - 添加 pytest 和 pytest-cov
- `pytest.ini` - pytest 配置
- `tests/README.md` - 测试使用文档

## 本地使用

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行配置测试

```bash
# 运行所有非 slow 测试（与 CI 配置测试一致）
python -m pytest tests/ -v --tb=short -m "not slow"

# 只运行构建矩阵和 mod 配置测试
python -m pytest tests/test_build_matrix.py tests/test_mod_config.py -v

# 只运行构建矩阵测试
python -m pytest tests/test_build_matrix.py -v

# 只运行 mod 配置测试
python -m pytest tests/test_mod_config.py -v

# 运行所有测试（包括标记的测试）
python -m pytest tests/ -v
```

### 3. 运行 Mod 资源审计

```bash
# 基本用法
python tools/mod_audit.py

# 指定输出目录
python tools/mod_audit.py --output-dir output

# 禁用缓存（每次重新下载）
python tools/mod_audit.py --no-cache
```

### 4. 运行 Phase 3 静态 HTML smoke test

```bash
# 检查单个构建 ZIP、HTML，或递归检查目录内的 ZIP/HTML
python tools/html_smoke_test.py output --output output/html-smoke-report.json
```

该 smoke test 是 Phase 3 的第一步，当前不启动浏览器，主要验证：

- 构建产物中存在 HTML；
- HTML 内存在 `window.modDataValueZipList`；
- 列表是有效 JSON 数组；
- 内嵌 mod base64 payload 可解码；
- 可识别 ZIP payload 的 `boot.json` 元数据；
- 内嵌 ZIP 中缺失 `boot.json` 时给出 warning；
- 可解码但不是 ZIP 的 payload 作为 warning/诊断保留，交由 Phase 4 浏览器 smoke 继续验证。

### 5. 运行 Phase 4 浏览器 smoke test（可选）

Phase 4 使用 Playwright/Chromium 打开构建后的 HTML，捕获真实浏览器运行时证据。Playwright 不放入主构建依赖，CI 的 `browser-smoke` job 会临时安装；本地需要手动安装：

```bash
python -m pip install playwright
python -m playwright install chromium
```

检查单个构建 ZIP、已解压目录或 HTML：

```bash
python tools/browser_smoke_test.py output --output-dir output/browser-smoke --report-only
```

CI 的 `dol-builds-zip-sample` 用于快速验证基础运行路径：Build workflow 会优先选择不含 `-au-` 的基础 ZIP；如果当前构建没有基础 ZIP，才回退到排序后的第一个 ZIP。AU-F/AU-M/AU-A 变体仍会上传到完整 `dol-builds-zip` artifact，建议在基础包 browser boot / game-ready 稳定后再单独测试或扩展为后续矩阵。

默认 profile 为稳定主线 `ucb-more-love-custom-spellbook`。检查 cheatExtended/maplebirch 实验分支产物时，显式加 `--profile ucb-more-love-custom-spellbook-cheat-extended-maplebirch`；Actions 会根据 `workflow_run.head_branch` 自动选择对应 profile。报告会记录 `package_identity.package_slug`、`workflow_head_branch`、`expected_profile_for_branch`、`branch_profile_match`、`profile_slug_match` 和 `forbidden_slug_tokens_present`，用于区分 `vega` 主线 CI artifact 与手动/实验包，避免把主线报告和实验运行日志混看。

Phase 4 现在按分层 smoke 记录结果：

- **Phase 4A / Browser boot**：通过本地 HTTP server 打开 HTML，处理 Custom Spellbook prompt 密码，观察 ModLoader 内嵌 mod 元数据，并捕获 `console.error`、`pageerror`、failed request 和 HTTP 4xx/5xx；
- **Phase 4A.5 / Startup interaction replay**：在导航和 Game Ready 检查之间，按无痕浏览器手动验证出的启动流程最多尝试 45 步：自动填写 Custom-Spellbook SweetAlert 密码 `DOL-Custom-Spellbook-Mod`，处理 OK/确定确认框，勾选年龄确认 `我确定我已年满十八岁` 并点击 `进入游戏`，勾选秋枫白桦/Mod 框架说明 `我已阅读并理解上述说明` 并点击 `我已知晓`。每一步的 action、按钮文本、consent label、前后 passage 和最终 passage 会写入 `startup_interactions`；浏览器原生 alert/prompt/confirm 会自动接受，并把 type/message/accepted/password_supplied 写入 `startup_interactions.browser_dialogs`，其中 `ev.preventDefault is not a function` 等文本仍按 high-risk 运行时错误分类；
- **Phase 4B / Game Ready**：检查 `window.jQuery`、`window.SugarCube`、`SugarCube.State`、`SugarCube.Engine`、`SugarCube.Story`、当前 passage、正文长度、loading-like 状态和可交互元素数量；
- **Phase 4C / Enter Game**：在 runtime ready 后，用通用按钮/链接文本（Start、New Game、Continue、开始、继续等）最多尝试 5 步进入首个可玩场景，记录 `passage_before`、`passage_after`、点击步骤和进入过程中新增的 high-risk 错误；
- **Phase 4D / Mod profile probes**：检查 profile 要求的 mod 名称、warning global、可选 UI selector 点击，以及 `ReferenceError`、`TypeError`、`Error [tw-user-script-*]`、`maplebirchFrameworks is not defined`、`ev.preventDefault is not a function`、`skinColourFullback`/`skincolourtext` 等高风险运行时错误；
- **Phase 4E / Package identity**：检查分支、profile、package slug 是否一致。`vega` 应对应 `ucb-more-love-custom-spellbook`，且 slug 不应包含 `cheat-extended`/`maplebirch`；`experiment/cheat-extended-maplebirch` 应对应实验 profile。分支/profile 错配或主线 profile 下出现实验 slug token 会作为 high-risk finding 写入报告；
- **Phase 4F / Static asset audit**：对打包目录做轻量资源审计，记录 `static_asset_audit.face_dir_exists`、`face_png_count`、`blush_png_count` 和 `required_face_assets`。当前会重点检查 `img/face/default/default/blush1.png`，用于自动复核 AU/BeautySelector 触发的 `Failed to load image ... for layer blush` 类问题；
- **Phase 4G / Blocker diagnostics**：记录浏览器原生 dialog、popup/new page，以及可见的页面内 modal/blocker（如 `dialog[open]`、SweetAlert2、`[role="dialog"]`、`.modal`、`.overlay`）。在 Game Ready 检查前，会安全尝试点击常见确认按钮（OK、Confirm、Continue、Close、确定、继续、关闭等）最多 3 次，并把点击前后 blocker 样本、popup 样本和 dismissal 结果写入报告；
- 当目标目录内同时存在多个已解压 HTML 包或多个 ZIP 包时，Phase 4 会优先选择非 AU 基础包；AU 变体建议在基础包 boot/game-ready 通过后再单独跑一次实验 profile；
- 本地 HTTP server 会在包内缺失 `/modList.json` 时返回空 JSON 数组 `[]`。这是为了模拟“没有远程附加 mod 列表”的正常状态，避免 ModLoader 把 404 HTML 当 JSON 解析并产生测试环境噪音；如果包内实际存在 `modList.json`，仍会按真实文件提供；
- `success=true` 的含义是：没有 high-risk finding、browser boot 成功，并且已经确认 `enter_game.success=true` 或页面状态足够接近可玩场景。只有 browser boot 成功但 `game_ready.ready=false` / `enter_game.success=false` 时，即使 high-risk 数量为 0，也会保持 `success=false` 和 `report_only_with_findings`；
- 图片层错误会被单独归类：`Failed to load image ... for layer ...` 记为 `image_layer_load_failed`，`img/face/...` 的 HTTP 4xx、`ERR_FILE_NOT_FOUND`、`ERR_FAILED`、`failed` 或 `not found` 记为 `face_image_asset_missing`；
- `modList.json`、`usettings.js`、More Love 可选依赖、Custom-Spellbook 外部资源缺失等仍作为已知非致命/待定位告警记录。

输出：

- `output/browser-smoke/browser-smoke-report.json`
- `output/browser-smoke/browser-smoke-summary.json`
- `output/browser-smoke/browser-smoke-report.md`
- `output/browser-smoke/console.log`
- `output/browser-smoke/network-failures.json`
- `output/browser-smoke/browser-smoke-final.png`

`browser-smoke-summary.json` 是面向 CI 和快速人工复核的精简摘要，包含 `success`、`report_only`、`browser_boot`、`startup_interactions`、`game_ready`、`enter_game`、`blockers`、`package_identity`、`static_asset_audit`、`screenshot`、issue 计数和前 5 个 high-risk finding。`startup_interactions` 会汇总启动交互步数、点击次数、是否填写密码、接受 consent 数量、最终 passage、启动 gate 状态、浏览器原生 dialog 样本和前 20 个步骤摘要；`blockers` 会汇总页面内 modal 数量/样本、popup 数量/样本、以及是否自动点击过确认按钮。`browser-smoke-report.md` 是首选人工阅读入口；开头会显示 package slug、branch/profile match、profile/package slug match、截图路径、启动交互、blocker 诊断和静态资产审计摘要。

初期建议始终使用 `--report-only`。在该模式下，GitHub Actions job 成功只表示浏览器测试完成并生成报告；如果报告中 `success=false`、`issue_counts.high` 大于 0、`game_ready.ready=false`，或 `enter_game.success=false`，仍代表存在运行时风险或需要人工复核。等 browser boot / game ready / enter game 在主线和实验分支上连续稳定后，再考虑移除 `--report-only` 并升级为严格门禁。

### 6. 查看报告

```bash
# Markdown 报告
cat output/mod-compatibility-report.md

# JSON 报告
cat output/mod-compatibility-report.json

# Phase 4 浏览器 smoke 报告
cat output/browser-smoke/browser-smoke-report.md

# Phase 4 精简摘要
cat output/browser-smoke/browser-smoke-summary.json
```

## GitHub Actions 使用

### 自动触发

每次推送到 `vega` 分支时自动运行：

```bash
git add .
git commit -m "test: update mod config"
git push origin vega
```

### 手动触发

1. 访问 https://github.com/XFoxLG/DOL-X/actions
2. 选择 "Compatibility Tests" workflow
3. 点击 "Run workflow"
4. 可选：勾选 "运行慢速测试"

### Baseline Candidate Gate 手动触发（Phase 1A + B1 + B2 Android 自动运行时）

1. 访问 https://github.com/XFoxLG/DOL-X/actions
2. 选择 "Baseline Candidate Gate" workflow
3. 点击 "Run workflow"
4. 选择目标分支/SHA 后运行

该 workflow 是手动 release-candidate evidence gate，不是快速 PR CI；它不会修改默认构建矩阵，也不会进入普通 PR/push 路径。B2 运行时验证是全自动的 GitHub-hosted Android emulator / Android WebView CDP smoke，不需要也不包含人工手机测试。

接受为候选门禁 green evidence 需要同时满足：

- `baseline-candidate-config.json` 成功，且 `default_matrix_mutated=false`；
- `baseline-candidate-zip-build.json` 和 `baseline-candidate-apk-build.json` 中 `base`、`au-f`、`au-m`、`au-a` 四个候选均成功；
- `baseline-candidate-zip-audit.json` 和 `baseline-candidate-apk-audit.json` 均成功；
- `baseline-candidate-zip-browser-summary.json` 中四个候选 ZIP browser smoke 均成功；
- `baseline-candidate-apk-debug-derivation.json` 中四个 release-derived smoke-debug APK 均成功，且 `webview_debug_hook_applied=true`；
- `baseline-candidate-apk-equivalence.json` 中 release/debug HTML、payload sha、payload names、required payloads 均匹配；
- `baseline-candidate-apk-cdp-smoke.json` 中 blocking 层的 `base` smoke-debug APK emulator/WebView CDP smoke 成功，且 `runtime_scope.platform="Android emulator"`、`webview_cdp=true`、`manual_phone_testing=false`、`harmonyos_covered=false`；
- `baseline-candidate-apk-cdp-smoke.json` 按 `signal_layers` 拆分 `base_apk_readiness`、`au_apk_runtime_readiness`、`cdp_adapter_health`、`emulator_health`。其中 `au-f`、`au-m`、`au-a` 是 strict diagnostic：失败会记录到 `diagnostic_errors` 并令 `diagnostic_success=false` / `full_candidate_gate_ready=false`，但在 runtime instability 修复前不阻塞候选门禁 green evidence；
- artifacts 包含 `baseline-candidate-zip-artifacts`、`baseline-candidate-apk-artifacts`、`baseline-candidate-apk-debug-artifacts`、`baseline-candidate-apk-cdp-smoke-reports`、`baseline-candidate-gate-reports`。

候选门禁 green evidence 要求 static/B1/ZIP browser 与 blocking `base` APK CDP 均通过；AU APK CDP diagnostic 失败不应让候选门禁本身失败。只有当上述 ZIP、APK static、B1 debug/equivalence 与 `base`、`au-f`、`au-m`、`au-a` 四个 APK CDP runtime 全部通过时，`baseline-candidate-phase1a-summary.json` 才会提升为 `gate_level=full_candidate_gate` 且 `counts_for_phase2_promotion=true`。即便如此，也仍然不得直接迁移默认矩阵；Phase 2 仍要求两个同一 head SHA 的 full candidate gate green。

B2 覆盖范围仅限 Android emulator + Android WebView。该 gate 不声明 Huawei/Honor/HarmonyOS 5 兼容性，也不覆盖 HarmonyOS NEXT；不得把该 workflow 的 green 解释为人工真机或 Huawei/HarmonyOS 认证通过。

### 查看结果

1. **Actions 页面**: https://github.com/XFoxLG/DOL-X/actions
2. **下载 artifacts**:
   - `config-test-results` - 配置测试结果
   - `mod-audit-reports` - Mod 审计报告
   - `html-smoke-report` - Phase 3 静态 HTML smoke 报告
   - `browser-smoke-report` - Phase 4 浏览器运行 smoke 报告（保留 3 天）

`browser-smoke-report` artifact 中优先查看：

1. `browser-smoke-report.md` - 人工阅读的完整摘要、high-risk、warning 和 observations；
2. `browser-smoke-summary.json` - 快速判断 `success`、`report_only`、`browser_boot`、`game_ready`、`enter_game` 和 issue 计数；
3. `console.log` / `network-failures.json` - 深入定位浏览器 console 与网络问题。

注意：当前 Phase 4 是 report-only。Actions 成功不等于运行时无错误；请以 `browser-smoke-summary.json` 中的 `success` 和 `issue_counts.high` 为准。

### PR 集成

当创建 Pull Request 时：
- 自动运行兼容性测试
- 自动在 PR 中评论审计摘要
- 配置测试失败会阻止合并
- Mod 审计高风险会显示警告

## 测试用例详情

### test_build_matrix.py (13 个测试)

1. `test_build_codes_count` - 验证只构建 4 个组合
2. `test_build_codes_values` - 验证组合代码正确
3. `test_polyfill_disabled` - 验证 polyfill 关闭
4. `test_base_code_is_24834` - 验证基础版代码
5. `test_no_online_version` - 验证没有在线版
6. `test_au_features_exist` - 验证 AU features 存在
7. `test_base_version_no_au` - 验证基础版不含 AU
8. `test_au_versions_have_au` - 验证 AU 版本含 AU
9. `test_all_versions_have_ucb` - 验证所有版本含 UCB
10. `test_all_versions_have_cheat_or_csd` - 验证所有版本含作弊/CSD
11. `test_all_versions_have_more_love_and_custom_spellbook` - 验证所有默认版本包含稳定主线 mod
12. `test_default_versions_exclude_cheat_extended_maplebirch` - 验证默认构建排除实验 feature
13. `test_combination_calculator_consistency` - 验证计算器一致性

### test_mod_config.py (22 个测试)

1. `test_modloader_mods_exist` - 验证 modloader_mods 存在
2. `test_au_face_mod_exists` - 验证 AU 面部扩展存在
3. `test_au_face_feature_ids` - 验证 AU 面部扩展 feature_ids
4. `test_all_feature_ids_valid` - 验证所有 feature_ids 有效
5. `test_cache_name_uniqueness` - 验证 cache_name 唯一
6. `test_key_uniqueness_when_present` - 验证 key 唯一
7. `test_github_repo_format` - 验证 github_repo 格式
8. `test_asset_pattern_not_empty` - 验证 asset_pattern 非空
9. `test_modloader_mods_have_download_source` - 验证 modloader mod 有下载来源
10. `test_modloader_enabled_flags_are_boolean` - 验证启用标记类型
11. `test_cheat_extension_mods_exist` - 验证 cheatExtended 相关配置存在
12. `test_love_and_spellbook_mods_exist` - 验证主线 more-love / custom-spellbook 配置存在
13. `test_au_main_mods_exist` - 验证 AU 主模组存在
14. `test_base_mods_config_exists` - 验证 base_mods 存在
15. `test_base_mods_keys_unique` - 验证 base_mods key 唯一
16. `test_base_mods_inject_mode_valid` - 验证 inject 模式有效
17. `test_stable_base_mods_are_required` - 验证稳定主线 base mod 必需
18. `test_modloader_gui_replaces_slot_0` - 验证 modloader_gui 配置
19. `test_no_conflicting_feature_assignments` - 验证无 feature 冲突
20. `test_cheat_extended_replacement_not_mixed_with_legacy_stack` - 验证 cheatExtended 替代栈不与项目本地旧 cheat/CSD 栈混装
21. `test_cheat_extended_framework_choice_is_exclusive` - 验证 cheatExtended 框架选择互斥
22. `test_cheat_extended_uses_dedicated_feature_when_configured` - 验证 cheatExtended 使用独立实验 feature

## 风险检测能力

| 问题类型 | 检测方式 | 自动化能力 |
|---------|---------|-----------|
| 构建组合错误 | 配置测试 | ✓ 能自动阻断 |
| polyfill 回归 | 配置测试 | ✓ 能自动阻断 |
| Mod key 冲突 | 配置测试 | ✓ 能自动阻断 |
| 基础版误注入 AU | 配置测试 | ✓ 能自动阻断 |
| Release asset 消失 | Mod 审计 | ✓ 能自动阻断 |
| 下载失败 | Mod 审计 | ✓ 能自动阻断 |
| ZIP 损坏 | Mod 审计 | ✓ 能自动阻断 |
| Hash 变化 | Mod 审计 + lock 文件 | ⚡ 可检测变化 |
| 依赖缺失 | Mod 审计 | ⚡ 可检测结构 |
| HTML 内嵌 mod ZIP 损坏 | Phase 3 HTML smoke | ⚡ 非阻断报告 |
| HTML 内嵌非 ZIP payload | Phase 3 HTML smoke | ⚡ 作为 warning 诊断，交由浏览器验证 |
| 游戏 runtime 未加载/卡 loading | Phase 4 Game Ready | ⚡ report-only，后续可升级门禁 |
| 无法确认进入可玩场景 | Phase 4 Enter Game | ⚡ report-only，需要人工复核 |
| 浏览器运行时错误 | Phase 4 browser smoke | ⚡ report-only，后续可升级门禁 |
| UI 入口函数缺失 | Phase 4 mod profile | ⚡ report-only，后续可升级门禁 |

## Phase 3 当前状态与后续

Phase 3 静态 HTML smoke test 已实现第一版：

**已实现文件**:
- `tools/html_smoke_test.py` - 静态 HTML/ZIP smoke test
- `tests/test_html_smoke.py` - pytest 覆盖
- `.github/workflows/compatibility.yaml` - 非阻断 `html-smoke` job

**当前目标**:
- 快速检查构建产物能否找到 HTML；
- 检查 ModLoader 内嵌 mod 列表是否存在且格式正确；
- 检查内嵌 mod ZIP 是否损坏；
- 对 maplebirch/modpack 这类可解码但非 ZIP 的 payload 给出 warning，而不是误判为构建失败。

## Phase 4 当前状态：浏览器运行 smoke test（report-only）

Phase 4 已作为 `browser-smoke` job 接入 `.github/workflows/compatibility.yaml`，当前为 report-only、非阻断模式。

**已实现文件**:
- `tools/browser_smoke_test.py` - Playwright/Chromium 浏览器运行 smoke 工具
- `tests/test_browser_smoke.py` - 嵌入 mod 元数据提取、错误分类、summary 分层输出测试
- `.github/workflows/compatibility.yaml` - 非阻断 `browser-smoke` job

**当前目标**:
- 通过本地 HTTP server 打开构建产物，避免 `file://` CORS 误报；
- 自动处理 Custom Spellbook prompt 密码并记录 dialogs；
- 采集 `console.error`、`pageerror`、failed network requests 和 HTTP 4xx/5xx；
- 输出完整 JSON、精简 summary JSON、Markdown、console 和 network failure artifacts；
- 记录 `browser_boot`、`game_ready`、`enter_game` 三层结果，至少确认 HTML、ModLoader、SugarCube 能启动，并尽量自动进入首个可玩场景；
- 使用 profile 检查当前主线或实验分支必需 mod 与 Custom-Spellbook 入口。

**已知高风险模式**:
- `spellBookMobileClicked is not defined`
- `ev.preventDefault is not a function`
- `maplebirchFrameworks is not defined`
- `Failed to load image ... for layer ...`
- `img/face/...` 的 HTTP 4xx、`ERR_FILE_NOT_FOUND`、`ERR_FAILED`、`failed` 或 `not found`
- `skinColourFullback` / `skincolourtext` 相关缺失
- 分支/profile/package slug 身份错配，例如 `vega` 主线 profile 下出现 `cheat-extended` 或 `maplebirch` slug token
- `Error [tw-user-script-*]`
- `ReferenceError` / `TypeError` / `Uncaught`

**已知降级/允许模式**:
- `modList.json` 外部 mod list 失败：报告，不阻断；
- `usettings.js not active, this is normal`：允许；
- More Love 可选依赖 `Remy Love Mod`、`NPC Avatars Mod`、`NPC Avatars Mod (SF)`：optional warning；
- `style.css`、`img/misc/banner.png`：Custom-Spellbook 外部资源缺失，先报告，后续定位后再决定是否升为失败。

**严格门禁切换条件**:
1. 主线 `ucb-more-love-custom-spellbook` 构建稳定满足 `browser_boot.navigation_ok=true`、`game_ready.ready=true`。
2. 主线构建能稳定 `enter_game.success=true`，或已证明无法完全自动化且有明确人工复核流程。
3. 当前构建不再出现 `spellBookMobileClicked is not defined`、`ev.preventDefault is not a function` 等 high-risk runtime error。
4. Custom-Spellbook 侧边栏入口可点击且不产生新的 `pageerror`。
5. `style.css` / `banner.png` 已修复或明确记录为安全 allowlist。
6. GitHub Actions 连续多次生成稳定报告后，再移除 `--report-only`。

## 新增 mod 的 Phase 4 profile 策略

为了保持上游友好和低冲突，新增 mod 时优先扩展 `tools/browser_smoke_test.py` 中的 profile，而不是改 Lyra 核心构建流程。

- **内容型 mod**：检查 mod 名称被观察到，首屏/卧室无 fatal runtime error。
- **UI/功能型 mod**：增加必要全局函数、按钮 selector、点击后无新 pageerror 的检查。
- **框架型 mod**：检查框架 API、依赖 mod 识别、设置入口是否存在。
- **替代型作弊栈**：必须单独实验分支验证，不与旧 `Cheat` / `CSD` / BJX / BCCM 混装后直接合主线。

## 文件清单

```
DOL-X/
├── .github/
│   └── workflows/
│       └── compatibility.yaml          # GitHub Actions workflow
├── config/
│   └── mods.lock.json                  # Mod 锁文件模板
├── tests/
│   ├── __init__.py                     # 测试包初始化
│   ├── conftest.py                     # pytest 配置
│   ├── test_build_matrix.py            # 构建矩阵测试
│   ├── test_au_face_compat.py          # AU face nested blush alias 测试
│   ├── test_browser_smoke.py           # Phase 4 浏览器 smoke helper 测试
│   ├── test_cheat_extended_audit.py    # cheatExtended 替代性审计测试
│   ├── test_html_smoke.py              # Phase 3 静态 HTML smoke 测试
│   ├── test_mod_config.py              # Mod 配置测试
│   └── README.md                       # 测试文档
├── tools/
│   ├── browser_smoke_test.py           # Phase 4 浏览器运行 smoke 工具
│   ├── html_smoke_test.py              # Phase 3 静态 HTML smoke 工具
│   └── mod_audit.py                    # Mod 资源审计工具
├── pytest.ini                          # pytest 配置
├── requirements.txt                    # Python 依赖（已更新）
└── TESTING.md                          # 本文档
```

## 总结

Phase 1、Phase 2、Phase 3 静态 smoke 和 Phase 4 浏览器 smoke 初版已实现，包括：

- ✅ 配置、HTML smoke 和 browser smoke helper 自动化测试
- ✅ 完整的 Mod 资源审计工具
- ✅ GitHub API 错误分类与安全解压测试
- ✅ Phase 3 静态 HTML smoke test 初版
- ✅ Phase 4 浏览器运行 smoke test（report-only，非阻断）
- ✅ GitHub Actions 集成
- ✅ 详细的报告生成
- ✅ 本地和 CI 都可运行
- ✅ PR 自动评论集成

这套方案可以在每次推送时自动验证：
1. 构建配置正确性
2. Mod 资源可用性
3. 配置一致性
4. HTML 内嵌 mod ZIP 完整性
5. 浏览器运行时风险

下次推送到 `vega` 分支时，GitHub Actions 会自动运行这些测试。
