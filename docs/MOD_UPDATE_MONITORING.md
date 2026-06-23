# Mod 更新监控系统使用指南

## 功能概览

自动化的 Mod 更新检查系统，包含：

- ✅ 每周自动检查所有启用的 Mod 更新
- ✅ GitHub Release changelog 自动提取
- ✅ 基于 semver 和 mods.lock.json 的风险评估
- ✅ Pre-release 版本监控支持
- ✅ GitHub Issue 自动创建/更新
- ✅ 邮件通知（可选）
- ✅ Rate limit 保护（使用 GITHUB_TOKEN）

## 本地使用

### 基础检查

```bash
# 检查所有启用的 mod
python tools/check_mod_updates.py --summary

# 输出到文件
python tools/check_mod_updates.py --output output/mod-updates.json

# 包含 pre-release 版本
python tools/check_mod_updates.py --include-prerelease --summary
```

### 输出示例

```
=== Summary ===
Total mods checked: 9
Updates available: 2
Errors: 0

Mods with updates:
  🟡 maplebirch: maplebirch-release-v3.1.14 → v3.2.0
    https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchframework/releases/tag/v3.2.0
    ⚠️  Minor version change: 1 → 2

  🔴 maplebirch扩展包: release-v1.2.4 → v1.3.0
    https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchExpansion/releases/tag/v1.3.0
    ⚠️  Major version change: 1.x → 2.x
    ⚠️  Known issue: 不兼容 maplebirch v4.x（R.use API 变更）
```

### 风险等级说明

| 等级 | 标识 | 含义 |
|------|------|------|
| Low | 🟢 | Patch 更新（如 v1.2.3 → v1.2.4），通常安全 |
| Medium | 🟡 | Minor 更新（如 v1.2.0 → v1.3.0）或 pre-release |
| High | 🔴 | Major 更新（如 v1.x → v2.x）或有已知兼容性问题 |
| Unknown | ⚪ | 无法解析版本号 |

## GitHub Actions 自动化

### 触发条件

- **定时运行**：每周日 UTC 00:00
- **手动触发**：在 Actions 页面点击 "Run workflow"

### 配置邮件通知（可选）

在 Repository Settings > Secrets and variables > Actions 中配置：

```yaml
MAIL_USERNAME: your-email@gmail.com
MAIL_PASSWORD: your-gmail-app-password
MAIL_TO: recipient@example.com
```

**注意：**
- Gmail 需要使用 [App Password](https://support.google.com/accounts/answer/185833)，不是账户密码
- 如果不配置这些 secrets，邮件步骤会自动跳过（不影响其他功能）

### Workflow 输出

**有更新时：**
1. 创建/更新 GitHub Issue（标签：`mod-update`, `automation`）
2. 上传 `mod-updates.json` 到 Artifacts（保留 30 天）
3. 发送邮件通知（如果配置）

**Issue 内容示例：**

```markdown
## 🔄 检测到 Mod 更新

**检测时间**: 2026-06-18T12:00:00Z
**更新数量**: 2 / 9

### 可用更新

#### 🟡 maplebirch

- **当前版本**: `maplebirch-release-v3.1.14`
- **最新版本**: `v3.2.0`
- **仓库**: MaplebirchLeaf/SCML-DOL-maplebirchframework
- **发布时间**: 2026-06-01T10:00:00Z
- **风险等级**: MEDIUM
- **风险提示**:
  - ⚠️ Minor version change: 1 → 2

<details>
<summary>📝 更新日志摘要</summary>

- Fix R.use path resolution bug
- Add sanity attribute extension
...

[查看完整日志](https://github.com/...)
</details>

### 📋 处理步骤

1. 查看上游 Release Notes 和风险提示
2. 评估依赖兼容性（参考 `config/mods.lock.json` notes）
3. 更新 `config/build.toml` 中的版本号
4. 运行 `python tools/mod_audit.py` 验证
5. 本地测试构建
6. 提交更新并更新 `mods.lock.json`

若更新失败，参考 [回滚指南](docs/MOD_UPDATE_ROLLBACK.md)
```

## JSON 输出格式

```json
{
  "timestamp": "2026-06-18T12:00:00Z",
  "total_checked": 9,
  "updates_available": 2,
  "errors_count": 0,
  "has_updates": true,
  "updates": [
    {
      "mod_key": "maplebirch",
      "mod_name": "maplebirch Framework",
      "repo": "MaplebirchLeaf/SCML-DOL-maplebirchframework",
      "current": "maplebirch-release-v3.1.14",
      "latest": "v3.2.0",
      "has_update": true,
      "url": "https://github.com/.../releases/tag/v3.2.0",
      "published_at": "2026-06-01T10:00:00Z",
      "is_prerelease": false,
      "changelog_summary": "- Fix R.use path resolution...",
      "changelog_url": "https://github.com/.../releases/tag/v3.2.0",
      "risk_level": "medium",
      "risk_notes": ["Minor version change: 1 → 2"],
      "status": "success"
    }
  ],
  "errors": [],
  "all_results": [...]
}
```

## 更新流程

### 1. 收到通知

通过 GitHub Issue 或邮件收到更新通知。

### 2. 评估风险

查看 Issue 中的风险提示：

- 🟢 Low：通常可以直接更新
- 🟡 Medium：检查 changelog，本地测试
- 🔴 High：**必须**查看 `mods.lock.json` 的 notes 和上游文档

### 3. 更新配置

编辑 `config/build.toml`：

```toml
[[modloader_mods]]
key = "maplebirch"
github_repo = "MaplebirchLeaf/SCML-DOL-maplebirchframework"
release_tag = "v3.2.0"  # 更新此处
```

### 4. 验证

```bash
# 验证 mod 资源可访问性
python tools/mod_audit.py

# 本地构建测试
python lyra.py build --combo 24834
```

### 5. 更新 mods.lock.json

记录测试结果：

```json
{
  "mods": {
    "maplebirch": {
      "release_tag": "v3.2.0",
      "last_tested_version": "v3.2.0",
      "last_tested_date": "2026-06-18",
      "notes": [
        "v3.2.0 测试通过",
        "兼容 DoL v0.5.8.10"
      ]
    }
  }
}
```

### 6. 提交

```bash
git add config/build.toml config/mods.lock.json
git commit -m "chore: 更新 maplebirch 到 v3.2.0"
```

## 故障排查

### Rate Limit 错误

**症状：** `403 Client Error: rate limit exceeded`

**解决：**
1. 本地测试时设置 `GITHUB_TOKEN` 环境变量
2. GitHub Actions 会自动使用 `secrets.GITHUB_TOKEN`

```bash
# Windows PowerShell
$env:GITHUB_TOKEN="ghp_your_token_here"
python tools/check_mod_updates.py --summary

# Linux/Mac
export GITHUB_TOKEN="ghp_your_token_here"
python tools/check_mod_updates.py --summary
```

### 编码错误

**症状：** `'gbk' codec can't decode byte`

**解决：** 已修复，`mods.lock.json` 现在使用 UTF-8 编码读取。

### 更新失败回滚

参考 [docs/MOD_UPDATE_ROLLBACK.md](docs/MOD_UPDATE_ROLLBACK.md)

## 高级用法

### 监控特定 mod 的 pre-release

编辑 `config/build.toml`（未来功能，当前版本未实现 per-mod 配置）：

```toml
[[modloader_mods]]
key = "maplebirch"
track_prerelease = true  # 计划中的功能
```

当前使用全局参数：

```bash
python tools/check_mod_updates.py --include-prerelease --summary
```

### 集成到 CI/CD

在其他 workflow 中引用：

```yaml
- name: Check mod updates before build
  run: |
    python tools/check_mod_updates.py --output mod-status.json
    
    # 检查是否有高风险更新
    HIGH_RISK=$(jq '[.updates[] | select(.risk_level == "high")] | length' mod-status.json)
    if [ "$HIGH_RISK" -gt 0 ]; then
      echo "⚠️ 发现 $HIGH_RISK 个高风险更新，建议先更新再构建"
    fi
```

## 相关文档

- [MOD_UPDATE_ROLLBACK.md](docs/MOD_UPDATE_ROLLBACK.md) - 回滚指南
- [TESTING.md](TESTING.md) - Mod 兼容性测试
- [MOD_ADDITION_CHECKLIST.md](docs/MOD_ADDITION_CHECKLIST.md) - 添加新 Mod
