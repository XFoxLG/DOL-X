# Mod 更新回滚指南

本文档提供 Mod 更新失败后的回滚操作指南。

## 概述

当 Mod 更新导致构建失败或运行时兼容性问题时，需要回滚到上一个稳定版本。

## 回滚场景与方案

### 场景 1：构建阶段失败

**症状：**
- `python lyra.py build` 失败
- 下载 Mod asset 失败（404 / 网络错误）
- ZIP 解压失败
- ModLoader 加载失败

**排查步骤：**

1. 查看构建日志定位失败的 Mod：

```bash
python lyra.py build | tee build.log
```

2. 检查 Mod 资源审计报告：

```bash
python tools/mod_audit.py
cat output/mod-compatibility-report.md
```

3. 检查 Mod 更新报告（如果是更新触发的）：

```bash
cat output/mod-updates.json | jq '.updates[] | select(.mod_key == "maplebirch")'
```

**回滚操作：**

1. 查看 `config/mods.lock.json` 中的上次测试版本：

```json
{
  "mods": {
    "maplebirch": {
      "release_tag": "maplebirch-release-v3.1.14",
      "last_tested_version": "v3.1.14",
      "notes": [...]
    }
  }
}
```

2. 恢复 `config/build.toml` 中的版本号：

```toml
[[modloader_mods]]
key = "maplebirch"
github_repo = "MaplebirchLeaf/SCML-DOL-maplebirchframework"
release_tag = "maplebirch-release-v3.1.14"  # 回退到此版本
```

3. 清理缓存并重新构建：

```bash
# 清理失败的 Mod 缓存
rm -rf workspace/cache/maplebirch*

# 重新构建
python lyra.py build --combo 24834
```

4. 提交回滚 commit：

```bash
git add config/build.toml
git commit -m "revert: 回滚 maplebirch 到 v3.1.14

原因：v4.x 与 maplebirchExpansion v1.2.4 不兼容
等待 expansion 发布 v4.x 兼容版本
"
```

### 场景 2：运行时兼容性问题

**症状：**
- APK 安装成功，但游戏启动失败
- ModLoader 报错（Console 中看到）
- 游戏功能异常（如侧边栏渲染错误、保存加载失败）

**排查步骤：**

1. 查看 `config/mods.lock.json` 的 `notes` 字段，检查已知兼容性问题：

```json
{
  "maplebirch_expansion": {
    "notes": [
      "不兼容 maplebirch v4.x（R.use API 变更）",
      "等待作者发布 v4.x 兼容版本"
    ]
  }
}
```

2. 检查 Mod 依赖关系：

```bash
# 查看 maplebirch 相关的所有 mod
grep -A 5 "maplebirch" config/build.toml
```

**回滚操作：**

与场景 1 相同，但需要额外：

1. 在 `config/mods.lock.json` 中记录问题：

```json
{
  "mods": {
    "maplebirch": {
      "notes": [
        "2026-06-18: v4.1.7 导致侧边栏渲染错误",
        "回滚到 v3.1.14",
        "相关 Issue: #123"
      ]
    }
  }
}
```

2. 在 GitHub Issue 中记录问题（供未来参考）。

### 场景 3：依赖链回滚

**症状：**
- 更新了 Mod A，但 Mod B 依赖旧版本的 Mod A

**示例：** maplebirch v3 → v4 导致 maplebirch_expansion 和 cheat_extended 不兼容

**回滚操作：**

1. 识别依赖链（从 `mods.lock.json` 的 `notes` 或上游文档）：

```
maplebirch v4.x
  ↓ (requires)
maplebirch_expansion v1.2.5+  (未发布)
cheat_extended v1.19+          (依赖新 API)
```

2. 回滚所有相关 Mod 到兼容组合：

```toml
[[modloader_mods]]
key = "maplebirch"
release_tag = "maplebirch-release-v3.1.14"

[[modloader_mods]]
key = "maplebirch_expansion"
release_tag = "release-v1.2.4"

[[modloader_mods]]
key = "cheat_extended"
release_tag = "V1.17(dev)"
```

3. 更新 `mods.lock.json` 记录稳定组合。

## 预防措施

### 1. 更新前检查风险

使用增强的 Mod 更新检查工具：

```bash
python tools/check_mod_updates.py --summary
```

输出会包含风险等级和已知问题：

```
🔴 maplebirch: v3.1.14 → v4.1.7
   ⚠️ Major version change: 3.x → 4.x
   ⚠️ Known issue: 不兼容 maplebirch v4.x（R.use API 变更）
```

### 2. 使用 mods.lock.json

在更新前确保 `mods.lock.json` 记录了当前稳定版本：

```bash
# 记录当前版本为 last_tested_version
# 手动编辑 config/mods.lock.json
```

### 3. 分阶段更新

对于高风险更新（Major 版本变化），分步验证：

```bash
# 1. 只更新单个 Mod
# 2. 本地构建测试
python lyra.py build --combo 24834

# 3. 安装 APK 手动测试
# 4. 确认无问题后再更新依赖的其他 Mod
```

### 4. 利用 Git 分支

```bash
# 在独立分支测试更新
git checkout -b test/maplebirch-v4
# 编辑 build.toml
git commit -m "test: 尝试更新 maplebirch 到 v4.1.7"

# 测试失败则直接删除分支
git checkout vega
git branch -D test/maplebirch-v4
```

## 自动化脚本（未来扩展）

当前回滚操作是手动的。未来可以实现：

```bash
# 自动回滚脚本（未实现）
python tools/rollback_mod_version.py --mod=maplebirch --to=v3.1.14

# 功能：
# 1. 自动读取 mods.lock.json 的 last_tested_version
# 2. 修改 build.toml
# 3. 清理缓存
# 4. 生成 Git commit
```

## 邮件通知配置（可选）

如果配置了邮件通知，更新检测会自动发送邮件。需要在 GitHub Secrets 配置：

```yaml
# Repository Settings > Secrets and variables > Actions

MAIL_USERNAME: your-email@gmail.com
MAIL_PASSWORD: your-app-password  # 使用 App Password，不是账户密码
MAIL_TO: recipient@example.com
```

**注意：** 如果不配置邮件 secrets，workflow 会跳过邮件步骤（`continue-on-error: true`），不影响其他功能。

## 故障排查

### Q: 回滚后仍然失败

**A:** 可能是缓存问题，尝试：

```bash
# 清理所有 Mod 缓存
rm -rf workspace/cache/*

# 清理 workspace
rm -rf workspace/extract workspace/temp

# 重新构建
python lyra.py build --clean --combo 24834
```

### Q: 不确定应该回滚到哪个版本

**A:** 查看 Git 历史：

```bash
# 查看最近的稳定构建
git log --oneline --grep="build\|mod" --all

# 查看特定文件的历史
git log -p config/build.toml -- "maplebirch"
```

### Q: 多个 Mod 同时更新后失败

**A:** 二分法定位问题 Mod：

```bash
# 先回滚一半
# 测试构建
# 根据结果继续二分，直到找到问题 Mod
```

## 相关文档

- [Mod 添加清单](MOD_ADDITION_CHECKLIST.md) - 添加新 Mod 的流程
- [Mod 兼容性测试](../TESTING.md) - 自动化测试
- [ModLoader 故障排查](MODLOADER_TROUBLESHOOTING.md)
- [构建系统文档](../QUICK_REFERENCE.md)
