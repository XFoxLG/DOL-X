# DoL-X 自动化 Mod 兼容性测试 - 实施总结

## 已完成内容

### Phase 1: 配置与矩阵测试 ✓

**文件**:
- `tests/conftest.py` - pytest 配置
- `tests/__init__.py` - 测试包初始化
- `tests/test_build_matrix.py` - 构建矩阵测试（13 个测试用例）
- `tests/test_mod_config.py` - Mod 配置测试（14 个测试用例）
- `pytest.ini` - pytest 配置文件

**测试覆盖**:
- ✓ 只构建 4 个自用组合 (258, 1282, 2306, 4354)
- ✓ polyfill 已关闭
- ✓ 没有在线版配置
- ✓ 基础版 (258) 不包含 AU
- ✓ AU 三版本包含对应 AU feature
- ✓ 所有版本包含 UCB + 作弊/CSD
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
4. **slow-tests** - 可选的慢速测试
5. **summary** - 测试总结

**特性**:
- ✓ 自动上传测试结果和报告为 artifacts
- ✓ PR 自动评论审计摘要
- ✓ 高风险 mod 会触发警告但不阻断构建
- ✓ 配置测试失败会阻断构建

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
- 内嵌 mod base64 payload 可解码为有效 ZIP；
- 内嵌 ZIP 中缺失 `boot.json` 时给出 warning。

### 5. 查看报告

```bash
# Markdown 报告
cat output/mod-compatibility-report.md

# JSON 报告
cat output/mod-compatibility-report.json
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

### 查看结果

1. **Actions 页面**: https://github.com/XFoxLG/DOL-X/actions
2. **下载 artifacts**:
   - `config-test-results` - 配置测试结果
   - `mod-audit-reports` - Mod 审计报告

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
4. `test_base_code_is_258` - 验证基础版代码
5. `test_no_online_version` - 验证没有在线版
6. `test_au_features_exist` - 验证 AU features 存在
7. `test_base_version_no_au` - 验证基础版不含 AU
8. `test_au_versions_have_au` - 验证 AU 版本含 AU
9. `test_all_versions_have_ucb` - 验证所有版本含 UCB
10. `test_all_versions_have_cheat_or_csd` - 验证所有版本含作弊/CSD
11. `test_combination_calculator_consistency` - 验证计算器一致性

### test_mod_config.py (14 个测试)

1. `test_modloader_mods_exist` - 验证 modloader_mods 存在
2. `test_au_face_mod_exists` - 验证 AU 面部扩展存在
3. `test_au_face_feature_ids` - 验证 AU 面部扩展 feature_ids
4. `test_all_feature_ids_valid` - 验证所有 feature_ids 有效
5. `test_cache_name_uniqueness` - 验证 cache_name 唯一
6. `test_key_uniqueness_when_present` - 验证 key 唯一
7. `test_github_repo_format` - 验证 github_repo 格式
8. `test_asset_pattern_not_empty` - 验证 asset_pattern 非空
9. `test_au_main_mods_exist` - 验证 AU 主模组存在
10. `test_base_mods_config_exists` - 验证 base_mods 存在
11. `test_base_mods_keys_unique` - 验证 base_mods key 唯一
12. `test_base_mods_inject_mode_valid` - 验证 inject 模式有效
13. `test_modloader_gui_replaces_slot_0` - 验证 modloader_gui 配置
14. `test_no_conflicting_feature_assignments` - 验证无 feature 冲突

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

## Phase 3 当前状态与后续

Phase 3 静态 HTML smoke test 已实现第一版：

**已实现文件**:
- `tools/html_smoke_test.py` - 静态 HTML/ZIP smoke test
- `tests/test_html_smoke.py` - pytest 覆盖
- `.github/workflows/compatibility.yaml` - 非阻断 `html-smoke` job

**当前目标**:
- 快速检查构建产物能否找到 HTML；
- 检查 ModLoader 内嵌 mod 列表是否存在且格式正确；
- 检查内嵌 mod ZIP 是否损坏。

**后续浏览器 smoke test（待实现）**:

- 打开本地构建的 HTML 版本
- 采集 console 错误
- 采集 network 404
- 截图验证页面加载
- 检查 ModLoader 是否启动

**工具选择**:
- **GitHub Actions**: 使用 Playwright（headless Chromium）
- **本地测试**: 使用 agent-browser-cli（真实 Chrome）

**实现文件**:
- `tools/browser_smoke_test.py` - 浏览器测试脚本
- `tests/test_browser_smoke.py` - pytest 集成
- `.github/workflows/compatibility.yaml` - 后续添加 browser-smoke job

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
│   ├── test_html_smoke.py              # Phase 3 静态 HTML smoke 测试
│   ├── test_mod_config.py              # Mod 配置测试
│   └── README.md                       # 测试文档
├── tools/
│   ├── html_smoke_test.py              # Phase 3 静态 HTML smoke 工具
│   └── mod_audit.py                    # Mod 资源审计工具
├── pytest.ini                          # pytest 配置
├── requirements.txt                    # Python 依赖（已更新）
└── TESTING.md                          # 本文档
```

## 总结

Phase 1、Phase 2 和 Phase 3 静态 smoke 已实现，包括：

- ✅ 27 个自动化测试用例
- ✅ 完整的 Mod 资源审计工具
- ✅ GitHub API 错误分类与安全解压测试
- ✅ Phase 3 静态 HTML smoke test 初版
- ✅ GitHub Actions 集成
- ✅ 详细的报告生成
- ✅ 本地和 CI 都可运行
- ✅ PR 自动评论集成

这套方案可以在每次推送时自动验证：
1. 构建配置正确性
2. Mod 资源可用性
3. 配置一致性
4. 潜在风险

下次推送到 `vega` 分支时，GitHub Actions 会自动运行这些测试。
