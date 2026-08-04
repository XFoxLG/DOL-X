# DOL-X 自动化测试

跟踪的测试覆盖构建矩阵、公开构建分档、供应链锁定、兼容补丁与产物 smoke。

## 本地运行

```bash
pip install -r requirements.txt

# 全量
python -m pytest tests -q

# 跳过 slow 标记
python -m pytest tests -v --tb=short -m "not slow"

# 单个模块
python -m pytest tests/test_build_matrix.py -v
```

配置改动后的最快检查：

```bash
python tools/quick_check.py
```

## 测试覆盖

### 构建矩阵与公开分档

- `test_build_matrix.py`：四个构建码 `15704320 / 15705344 / 15706368 / 15708416`
  与 feature 图自洽；polyfill 关闭；base 不含 AU；三个 AU 码各含对应体型；
  短后缀互不重复以防产物覆盖。
- `test_public_distribution_boundary.py`：分支档构建 base + AU-F，tag 档构建
  全部四码；warmup 与 build 引用同一组解析后的构建码。
- `test_warmup_explicit_codes.py`：显式构建码只预热所需 feature，且每个
  imagepack 只匹配自己的 URL。
- `test_identity.py`、`test_project_boundaries.py`：XFox 身份与项目边界。

### 供应链与配置

- `test_mod_config.py`：mod 条目、`feature_ids` 有效性、`cache_name` 唯一性。
- `test_mod_audit.py`：资源审计报告生成。
- `test_mod_update_checker.py`：带前缀 tag 的版本提取；同一 Pre-release tag 下
  asset digest 漂移可被发现；tag 与 digest 均未变时判定为最新。

### 兼容补丁

- `test_compatibility_registry.py`：兼容面登记表。
- `test_more_love_drag_patch.py`：More Love 拖拽事件防御性改写。
- `test_doli_float_icon_patch.py`：D.O.L.I 悬浮图标路径改写。
- `test_au_face_compat.py`：AU Face 资源别名。

### 安全与 fail-closed

- `test_archive_extraction.py`：路径穿越与符号链接防护。
- `test_prepare_fail_fast.py`：必需 base mod 缺失时中止而非静默产出。

### 产物 smoke

- `test_html_smoke.py`：构建 ZIP 内存在 HTML；`window.modDataValueZipList`
  可解析；内嵌 base64 payload 可解码且通过 ZIP 完整性检查。
- `test_browser_smoke.py`、`test_apk_emulator_smoke.py`：公开仓库中的浏览器与通用模拟器
  smoke helper。
- `test_mumu_apk_smoke.py`：本机 MuMu 私有诊断测试，和依赖的本地工具一起由 `.gitignore`
  排除，不进入 commit 或 GitHub Actions；本地全量 pytest 的计数会因此比 CI 多 15 项。
- `test_embedded_mod_source_scan.py`：内嵌 mod 来源扫描。

## 相关工具

```bash
# 资源审计
python tools/mod_audit.py --output-dir output

# 静态 HTML smoke
python tools/html_smoke_test.py output --output output/html-smoke-report.json

# 更新检查
python tools/check_mod_updates.py --output output/mod-updates.json
```

## GitHub Actions

- `build.yaml`：推送到 `vega` 或打 tag 时构建。分支推送产出 base + AU-F，
  tag 发版产出全部四码，并上传 ZIP/APK artifact；tag 构建额外创建 Release。
- `mod-update-check.yml`：每周检查上游 mod 更新，结果写入 Step Summary 与
  `mod-update-report` artifact。仓库 Issues 已关闭，不创建 Issue。

结果查看：https://github.com/XFoxLG/DOL-X/actions
