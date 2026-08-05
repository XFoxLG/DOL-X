# DOL-X 快速参考

常用构建、测试和发版命令。当前事实总入口见
[`docs/CURRENT_PROJECT_STATE.md`](docs/CURRENT_PROJECT_STATE.md)。

**最后更新**：2026-08-05

**当前稳定版本**：`v0.5.10.12-1.0.8a-0804`

**CI Python**：3.12

> 构建码以 `config/combinations.toml` 为准，命令参数以 `python main.py <命令> --help` 为准。

---

## 环境准备

```bash
python --version
python -m pip install -r requirements.txt
python tools/check_environment.py
```

CI 固定使用 Python 3.12；本地也建议使用同一版本。仓库没有 `pyproject.toml`，依赖记录在
`requirements.txt`。

---

## 构建码

| 构建码 | 产物 | 说明 |
|--------|------|------|
| `15704320` | base | 基础版，不含 AU 体型模型与 AU 改脸 |
| `15705344` | AU-F | AU 女性模型 + AU 改脸 |
| `15706368` | AU-M | AU 男性模型 + AU 改脸 |
| `15708416` | AU-A | AU 双性模型 + AU 改脸 |

AU Face 不占独立 bit；任一 AU 体型命中时自动注入，base 明确不注入。

### 当前必选 bit

```text
32768    cheat_extended_maplebirch
65536    custom_hair
131072   mae_picvary
262144   maplebirch_expansion（当前由 LongerCombat + YanlingCheatCollection 承担）
524288   guide_to_me
2097152  neoui_patch
4194304  npc_social_icon
8388608  doli
```

当前四码还都包含 `ucb`（256）与 `more_love`（8192）。`bunny_transformation`（1048576）因已知
不兼容而禁用；BESC、Hikari、Goose、Susato、WAX、KR/BJ 特写不属于当前公开矩阵。

---

## 常用构建命令

```bash
# 查看配置中的四个公开构建码
python main.py matrix

# 准备当前稳定版本的游戏与 mod 资源
python main.py prepare --tag v0.5.10.12-1.0.8a-0804 --workspace . -v

# 预热四码共用资源
python main.py warmup --codes 15704320,15705344,15706368,15708416 --workspace . -v

# 构建单一码（默认同时生成 ZIP 和 APK）
python main.py build --codes 15704320 --workspace . --jobs 2 -v

# 构建全四码并写入构建清单
python main.py build --tag v0.5.10.12-1.0.8a-0804 \
  --codes 15704320,15705344,15706368,15708416 \
  --workspace . --jobs 2 --manifest output/build-manifest.json -v

# 只构建一种格式
python main.py build zip --codes 15704320 --workspace . -v
python main.py build apk --codes 15704320 --workspace . -v
```

`--codes` 支持逗号分隔，也支持多个参数。CI 使用逗号分隔字符串；不要使用不存在的 `--profile`
参数。

---

## 测试与产物检查

```bash
# 与公开 CI 相同的测试入口
python -m pytest tests -q

# 只跑构建矩阵与公开分发边界
python -m pytest tests/test_build_matrix.py tests/test_public_distribution_boundary.py -q

# HTML 静态烟雾测试（参数可以是 ZIP、HTML 或目录）
python tools/html_smoke_test.py output --output output/html-smoke-report.json

# 浏览器烟雾测试（一次传一个 ZIP、解包目录或 HTML）
python tools/browser_smoke_test.py output/<artifact>.zip --output-dir output/browser-smoke

# Mod 资源审计
python tools/mod_audit.py --output-dir output/audit

# AU ZIP 产物审计
python tools/au_artifact_check.py output --output output/au-artifact-report.json

# 检查上游 mod 更新
python tools/check_mod_updates.py --output output/mod-updates.json --include-prerelease
```

本机全量会额外发现 `.gitignore` 排除的私有 MuMu 诊断测试，因此本机计数可能高于公开 CI；不要把
本机计数写成 CI 覆盖。

---

## GitHub Actions 分档

- 推送 `vega`：构建 base + AU-F。
- 手动运行 `build_tier=release`：在不打 tag 的前提下干跑全四码，release job 必须跳过。
- 推送普通发版 tag：构建全四码并创建 Release。
- 镜像 tag（`*-mirror-*`）被 workflow 排除。

发版前必须先创建 `docs/release-notes/<tag>.md`。Release job 会把它作为玩家向正文；文件缺失时
fail-closed，不允许发布空白正文。

---

## 发版顺序

```bash
# 1. 本地测试
python -m pytest tests -q

# 2. 推送 vega，等待分支 CI 成功
# 3. 手动运行 build_tier=release，等待全四码 dry run 成功
# 4. 确认 CHANGELOG、README、CURRENT_PROJECT_STATE、mods.lock 和 release-notes 已同步
# 5. 创建并推送 annotated tag（把 <tag> 替换成实际版本）
git tag -a <tag> -m "<tag>"
git push origin <tag>

# 6. 核对 Release、Latest 指针、8 件资产与正文
# https://github.com/XFoxLG/DOL-X/actions
# https://github.com/XFoxLG/DOL-X/releases/latest
```

不要在门禁失败时强行打 tag。Release 正文的写法与必填结构见
[`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md)。

---

## 配置文件

| 文件 | 用途 |
|------|------|
| `config/build.toml` | 游戏身份、APK、图片包和 ModLoader mod 下载配置 |
| `config/combinations.toml` | 当前四个构建码 |
| `config/features.toml` | feature bit、依赖、冲突与禁用状态 |
| `config/mods.lock.json` | 已核验版本、SHA-256、验证状态与备注 |
| `.github/workflows/build.yaml` | 分支/发版构建与发布门禁 |

---

## 常见问题

### APK 与 ZIP 怎么选？

`.apk` 用于安卓安装，`.zip` 用于浏览器版。安卓应用名是 `DoL XFox`，包名是
`com.vrelnir.dol.xfox`，可与原版/汉化版共存；存档请通过游戏内导出/导入功能迁移。

### UCB 和 AU 是否冲突？

当前公开矩阵已同时构建 UCB 与三个 AU 体型。UCB 主要覆盖战斗图片，AU 主要覆盖体型和面部；
产物级检查已接入 CI。兼容性边界见
[`docs/MOD_COMPATIBILITY_MATRIX.md`](docs/MOD_COMPATIBILITY_MATRIX.md)。

### D.O.L.I 为什么没有直接可用的 AI？

D.O.L.I 需要玩家在游戏内自行填写 OpenAI 兼容 API key；整合包不会内置或上传任何密钥。

### 云存档为什么连不上？

框架没有提供公共云存档服务器，需要自行部署服务端。本地存档和导出存档不受影响。

---

## 进一步阅读

- [README](README.md)
- [当前项目状态](docs/CURRENT_PROJECT_STATE.md)
- [更新日志](CHANGELOG.md)
- [文档写作规范](docs/DOCUMENTATION_GUIDE.md)
- [测试指南](docs/TESTING_GUIDE.md)
- [Mod 兼容矩阵](docs/MOD_COMPATIBILITY_MATRIX.md)
- [构建文档](BUILD.md)
