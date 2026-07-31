# Lyra Upstream 同步指南

保持与上游 DoL-Lyra 同步，获取游戏和汉化更新。

---

## DOL-X 同步策略

### 同步触发条件（仅满足以下条件时同步）

1. **游戏版本更新**（主要触发条件）
   - DoL 基础游戏发布新版本（如 v0.5.8.11）
   - 包含重要 bug 修复或新功能

2. **汉化包重大更新**
   - 新游戏版本对应的汉化包发布
   - 重要翻译修正

3. **构建系统重大改进**
   - 上游 Lyra 构建系统有重大优化
   - 影响 DOL-X 的核心功能

### 不同步的情况

- ❌ 上游 mod 矩阵调整（DOL-X 独立决策）
- ❌ 上游文档更新（除非影响构建流程）
- ❌ 上游实验性功能（candidate/canary builds）
- ❌ 频繁的小修小补（累积到游戏版本更新时一起同步）

### 同步延迟策略

**延迟上游更新的好处**：
- 等待 mod 作者发布兼容版本
- 观察社区是否发现严重 bug
- 减少频繁同步导致的配置冲突
- 降低维护负担

**建议延迟时间**：
- 游戏新版本发布后等待 1-2 周
- 确认 maplebirch、Cheat Extended 等关键 mod 已发布兼容版本
- 检查社区反馈，确认无严重问题

---

## 设置 Upstream Remote

上游构建仓库是 `DoL-Lyra/Lyra`，不是 `sakarie9/DoL-Lyra`（后者是早期分发，已不作为构建上游）。

```bash
# 添加上游仓库
git remote add upstream https://github.com/DoL-Lyra/Lyra.git

# 验证
git remote -v
```

---

## 手动同步流程

### 1. 获取上游更新

```bash
git fetch upstream
```

### 2. 查看更新内容

```bash
# 查看有哪些新 commit
git log HEAD..upstream/vega --oneline

# 查看文件变更
git diff HEAD..upstream/vega --stat
```

### 3. 合并更新

```bash
# 切换到本地主分支
git checkout vega

# 合并（不自动 commit）
git merge upstream/vega --no-commit --no-ff
```

### 4. 解决冲突（如果有）

常见冲突文件：
- `config/build.toml`（mod 配置）
- `config/combinations.toml`（build codes）
- `config/features.toml`（feature定义）

解决策略：
- **保留本地**: mod 相关配置
- **接受上游**: 游戏版本、汉化更新
- **合并**: 文档更新

```bash
# 查看冲突文件
git status

# 手动编辑冲突文件
# 选择保留哪部分

# 标记为已解决
git add <conflicted-file>
```

### 5. 提交合并

```bash
git commit -m "chore: sync with upstream Lyra $(date +%Y-%m-%d)"
```

### 6. 测试

```bash
# 构建测试
python tools/build.py --codes 24834

# 运行测试
python tools/html_smoke_test.py output/*.zip
python tools/browser_smoke_test.py output/*.zip
```

---

## 自动化同步（GitHub Actions）

创建 `.github/workflows/upstream-sync.yml`:

```yaml
name: Upstream Sync

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: Setup Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      
      - name: Add Upstream
        run: git remote add upstream https://github.com/DoL-Lyra/Lyra.git
      
      - name: Fetch Upstream
        run: git fetch upstream
      
      - name: Check for Updates
        id: check
        run: |
          BEHIND=$(git rev-list --count HEAD..upstream/vega)
          echo "commits_behind=$BEHIND" >> $GITHUB_OUTPUT
          if [ "$BEHIND" -gt 0 ]; then
            echo "has_updates=true" >> $GITHUB_OUTPUT
          else
            echo "has_updates=false" >> $GITHUB_OUTPUT
          fi
      
      - name: Create Sync PR
        if: steps.check.outputs.has_updates == 'true'
        uses: peter-evans/create-pull-request@v5
        with:
          branch: upstream-sync-${{ github.run_number }}
          title: "chore: sync with upstream Lyra"
          body: |
            自动同步上游更新。
            
            落后 upstream/vega: ${{ steps.check.outputs.commits_behind }} commits
            
            **请手动检查**：
            - [ ] 解决冲突（如果有）
            - [ ] 测试构建
            - [ ] 验证游戏版本
            - [ ] 验证汉化更新
```

---

## 冲突解决策略

### config/build.toml

**保留本地**：
- `[[modloader_mods]]` 自定义 mod
- mod 特定配置

**接受上游**：
- 游戏版本号
- Lyra 版本号

```toml
# 本地
[[modloader_mods]]
key = "custom_mod"  # 保留

# 上游
game_version = "0.5.8.11"  # 接受
```

### config/combinations.toml

**保留本地完全控制**：
```toml
build_codes = ["33024", "33792", "34816", "36864"]  # 本地决定
```

### 文档

**合并策略**：
- 上游修复 → 接受
- 本地添加 → 保留
- 两者都改 → 手动合并

---

## 同步频率建议

- **自动检查**: 每周（GitHub Actions）
- **手动同步**: 每月或当上游有重大更新
- **紧急同步**: 游戏重大 bug 修复时

---

## 回滚

如果同步后出现问题：

```bash
# 查看合并前的状态
git reflog

# 回滚到合并前
git reset --hard HEAD@{1}

# 或创建 revert commit
git revert -m 1 HEAD
```

---

## 参考

- 上游构建仓库: https://github.com/DoL-Lyra/Lyra
- 游戏本体: https://github.com/Vrelnir/Degrees-of-Lewdity
- 汉化仓库: https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization
- 当前差异摘要: [UPSTREAM_DIFF_SUMMARY.md](../UPSTREAM_DIFF_SUMMARY.md)
- 上游友好策略: [UPSTREAM_FRIENDLY_STRATEGY.md](../UPSTREAM_FRIENDLY_STRATEGY.md)
- 当前事实入口: [CURRENT_PROJECT_STATE.md](CURRENT_PROJECT_STATE.md)
