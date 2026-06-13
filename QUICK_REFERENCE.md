# DOL-X 快速参考

快速查找 DOL-X 常用命令、配置和故障排除方法。

---

## 常用命令

### 构建命令

```bash
# 查看所有可用组合
python main.py matrix

# 构建特定代码
python main.py build --codes 57600

# 构建 AU 变体
python main.py build --codes 58624,59648,61696

# 使用 profile 构建
python main.py build --profile standard

# 实验性 profile（cheatExtended）
python main.py build --profile cheat-extended-base

# 并行构建（4 个进程）
python main.py build --jobs 4

# 准备构建环境
python main.py prepare --tag v0.5.8.10

# 预热缓存
python main.py warmup
```

### 测试命令

```bash
# 运行所有配置测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_build_matrix.py -v

# 运行单个测试
pytest tests/test_build_matrix.py::TestBuildMatrix::test_all_versions_have_ucb -v

# HTML 烟雾测试
python tools/html_smoke_test.py output/*.zip

# 浏览器烟雾测试
python tools/browser_smoke_test.py output/*.zip --output output/smoke-report.json

# Mod 审计
python tools/mod_audit.py --output-dir output/audit
```

### 开发命令

```bash
# 检查环境
python tools/check_environment.py

# 检查 Mod 更新
python tools/check_mod_updates.py --output output/mod-updates.json

# Commit 转 Mod（待实现）
python main.py dev commit-to-mod <commit-hash>

# 热加载开发（待实现）
python tools/dev_server.py --watch mods/my_mod
```

### Git 命令

```bash
# 查看状态
git status

# 推送到自己的仓库
git push origin vega

# 拉取上游更新
git fetch upstream

# 查看上游差异
git log upstream/vega..vega --oneline

# 对比核心构建系统
git diff upstream/vega...vega -- lyra/

# 对比配置文件
git diff upstream/vega...vega -- config/

# 选择性同步单个提交
git cherry-pick <commit-hash>

# 合并上游分支
git merge upstream/vega

# 创建 Release（自动触发云端构建）
git tag v0.5.8.10-3.1.13-20260613
git push origin v0.5.8.10-3.1.13-20260613

# 查看构建状态
# https://github.com/XFoxLG/DOL-X/actions
```
```

---

## Build Codes 速查表

### 当前稳定组合

| Code | 组合 | 说明 |
|------|------|------|
| **57600** | UCB + more_love + custom_spellbook + cheatExtended+maplebirch | **基础版（推荐）** |
| **58624** | 上述 + AU-F | **AU 面部扩展** |
| **59648** | 上述 + AU-M | **AU 武术** |
| **61696** | 上述 + AU-A | **AU 小巷** |

### Build Code 计算

```
57600 = 256 (UCB) + 8192 (more_love) + 16384 (custom_spellbook) + 32768 (cheatExtended+maplebirch)

AU 变体：
58624 = 57600 + 1024 (AU-F)
59648 = 57600 + 2048 (AU-M)
61696 = 57600 + 4096 (AU-A)
```

---

## Feature Bits 参考

| Feature | Bit | 十六进制 | 说明 | 状态 |
|---------|-----|----------|------|------|
| BESC | 1 | 0x1 | 基础图片包 | ❌ **已禁用（skip=true）** |
| cheat_csd | 2 | 0x2 | 旧作弊模组 | ❌ 已废弃 |
| reserved | 4 | 0x4 | 保留位 | ⚠️ 跳过 |
| BJ特写 | 8 | 0x8 | BJ特写 | ⚠️ 跳过 |
| KR特写 | 16 | 0x10 | KR特写 | ⚠️ 跳过 |
| HIKARI | 32 | 0x20 | Hikari 图片包 | ⚠️ 依赖 BESC |
| WAX | 64 | 0x40 | Wax 图片包 | ⚠️ 跳过 |
| SUSATO | 128 | 0x80 | Susato 图片包 | ⚠️ 跳过 |
| **UCB** | **256** | **0x100** | **UCB 战斗美化** | **✅ 启用** |
| GOOSE | 512 | 0x200 | Goose 图片包 | ⚠️ 冲突 |
| **AU-F** | **1024** | **0x400** | **AU Face 面部扩展** | **✅ 启用** |
| **AU-M** | **2048** | **0x800** | **AU 武术** | **✅ 启用** |
| **AU-A** | **4096** | **0x1000** | **AU 小巷** | **✅ 启用** |
| **more_love** | **8192** | **0x2000** | **更多恋人** | **✅ 启用** |
| **custom_spellbook** | **16384** | **0x4000** | **自定义魔法书** | **✅ 启用** |
| **cheat_extended_maplebirch** | **32768** | **0x8000** | **作弊扩展+秋枫白桦框架** | **✅ 启用** |

---

## 配置文件位置

### 核心配置
- [`config/build.toml`](config/build.toml) - 构建系统配置（身份、路径、APK）
- [`config/combinations.toml`](config/combinations.toml) - **Mod 组合配置（build_codes）**
- [`config/features.toml`](config/features.toml) - **Feature 定义（bits）**
- [`config/profiles.toml`](config/profiles.toml) - 用户场景配置

### Mod 配置
- [`config/modloader/mods.toml`](config/modloader/mods.toml) - ModLoader mod 列表
- [`config/base_mods.toml`](config/base_mods.toml) - 基础 mod 配置

---

## 常见场景

### 场景 1: 构建新版本

```bash
# 1. 准备环境
python main.py prepare --tag v0.5.8.10

# 2. 预热缓存
python main.py warmup

# 3. 构建所有配置
python main.py build --jobs 4

# 4. 运行测试
pytest tests/ -v
python tools/browser_smoke_test.py output/*.zip

# 5. 检查输出
ls output/
# 预期：DoL-0.5.8.10-XFox-57601-*.zip 等 4 个文件
```

### 场景 2: 添加新 Mod

```bash
# 1. 编辑 config/modloader/mods.toml
# 添加新 mod 配置

# 2. 更新 build_codes（如需要）
# 编辑 config/combinations.toml

# 3. 运行测试验证
pytest tests/test_mod_config.py -v

# 4. 构建验证
python main.py build --codes <new_code>

# 5. 浏览器测试
python tools/browser_smoke_test.py output/*.zip
```

### 场景 3: 测试上游新功能

```bash
# 1. 查看上游最新提交
git fetch upstream
git log upstream/vega --oneline --max-count=10

# 2. 转换为 mod（待实现）
python main.py dev commit-to-mod <commit-hash>

# 3. 构建测试
python main.py build --profile experimental

# 4. 验证功能
python tools/browser_smoke_test.py output/*.zip
```

### 场景 4: 同步上游改进

```bash
# 1. 拉取上游更新
git fetch upstream

# 2. 查看差异
git diff upstream/vega...vega -- lyra/
git log upstream/vega..vega --oneline

# 3. 选择性合并
git cherry-pick <commit-hash>
# 或
git merge upstream/vega

# 4. 解决冲突（保留 DOL-X 的身份和 Mod 矩阵）
git diff --name-only --diff-filter=U
# 编辑冲突文件

# 5. 提交并推送
git commit
git push origin vega

# 6. 运行测试验证
pytest tests/ -v
```

---

## 故障排除

### PowerShell AMSI 错误

**症状**: 运行 Python 或 Git 命令时出现 `AccessViolationException` 或 AMSI 相关错误

**解决方案**:
```bash
# 方法 1: 切换到 Git Bash（推荐）
# 1. 打开 Git Bash
# 2. cd /e/game/repo/DOL-X
# 3. 重新运行命令

# 方法 2: 使用环境检测脚本
python tools/check_environment.py

# 方法 3: 在 Git Bash 中验证环境
echo $MSYSTEM  # 应输出 MINGW64 或类似
```

### 测试失败

**症状**: `pytest` 测试失败

**排查步骤**:
```bash
# 1. 检查工作区状态
git status

# 2. 查看未提交的更改
git diff

# 3. 暂存并重新测试
git stash
pytest tests/ -v

# 4. 恢复更改
git stash pop

# 5. 运行特定测试查看详细信息
pytest tests/test_build_matrix.py -v -s
```

### 构建失败

**症状**: `python main.py build` 失败

**排查步骤**:
```bash
# 1. 检查环境
python tools/check_environment.py

# 2. 重新准备环境
python main.py prepare --tag v0.5.8.10

# 3. 清理缓存
rm -rf workspace/cache/*
rm -rf workspace/temp/*

# 4. 重新预热
python main.py warmup

# 5. 重试构建
python main.py build --codes 57601 --jobs 1

# 6. 检查日志
# 查看错误信息，通常在输出末尾
```

### Mod 加载失败

**症状**: 浏览器测试显示 mod 加载错误

**排查步骤**:
```bash
# 1. 运行 HTML 烟雾测试
python tools/html_smoke_test.py output/*.zip

# 2. 检查 boot.json
unzip -p output/*.zip ModLoader/boot.json | python -m json.tool

# 3. 检查 mod 依赖
python tools/mod_audit.py

# 4. 查看详细浏览器日志
python tools/browser_smoke_test.py output/*.zip --verbose
```

### Git 冲突

**症状**: `git merge` 或 `git cherry-pick` 出现冲突

**解决步骤**:
```bash
# 1. 查看冲突文件
git status
git diff --name-only --diff-filter=U

# 2. 对于配置文件冲突（保留 DOL-X 版本）
git checkout --ours config/build.toml
git checkout --ours config/combinations.toml

# 3. 对于核心代码冲突（保留上游版本）
git checkout --theirs lyra/build.py

# 4. 手动编辑其他冲突
code <conflicted-file>

# 5. 标记为已解决
git add <resolved-file>

# 6. 继续操作
git merge --continue
# 或
git cherry-pick --continue
```

---

## 环境变量

### 可选配置

```bash
# 设置并行构建进程数
export DOL_BUILD_JOBS=4

# 设置工作目录
export DOL_WORKSPACE=/custom/path

# Playwright 无头模式
export PWDEBUG=0  # 0=headless, 1=headed

# Python 优化
export PYTHONOPTIMIZE=1
```

---

## 相关文档

- [完整构建文档](BUILD.md)
- [上游同步清单](UPSTREAM_SYNC_CHECKLIST.md)
- [上游友好策略](UPSTREAM_FRIENDLY_STRATEGY.md)
- [社区工具](docs/COMMUNITY_TOOLS.md)
- [测试指南](TESTING.md)

---

## Cheat Sheet 下载

打印或保存本文档以便离线参考：

```bash
# 生成 PDF（需要 pandoc）
pandoc QUICK_REFERENCE.md -o QUICK_REFERENCE.pdf

# 生成 HTML
pandoc QUICK_REFERENCE.md -o QUICK_REFERENCE.html
```

---

**最后更新**: 2026-06-13  
**维护者**: DOL-X 项目组

**反馈**: 如发现错误或需要补充内容，请在 GitHub Issues 中提出
