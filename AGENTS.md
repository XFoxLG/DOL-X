---
project: DOL-X
type: Integration Package
language: Python 3.12+
build: GitHub Actions
upstream: DoL-Lyra/Lyra
status: Active Development
updated: 2026-06-15
---

# AGENTS.md

Context for AI coding agents working on DOL-X.

---

## Project Overview

**DOL-X** is a self-use integration of Degrees of Lewdity, based on upstream [DoL-Lyra](https://github.com/DoL-Lyra/Lyra).

- **Repository**: https://github.com/XFoxLG/DOL-X
- **Upstream**: https://github.com/DoL-Lyra/Lyra
- **Language**: Python 3.12+
- **Build System**: Custom (lyra/build.py)

### What DOL-X Does

Provides 4 build configurations (build_codes):
- 57600: UCB + more_love + spellbook + cheat
- 58624: AU-F + UCB + more_love + spellbook + cheat
- 59648: AU-M + UCB + more_love + spellbook + cheat
- 61696: AU-A + UCB + more_love + spellbook + cheat

### What DOL-X Does NOT Do

- Public releases (self-use only)
- Reverse engineering of encrypted mods (use publicly available only)
- Local full builds (delegate to GitHub Actions)

---

## Quick Reference

### Most Common Tasks

1. **Fix failing tests**:
   ```bash
   pytest tests/test_build_matrix.py -v
   ```

2. **Update mod download link**:
   - Edit `config/build.toml`
   - Verify URL with `curl -I <URL>`
   - Run tests: `pytest tests/test_mod_config.py`

3. **Check GitHub Actions build**:
   ```bash
   gh run list --limit 3
   gh run view <run-id> --log-failed
   ```

4. **Run all tests before committing**:
   ```bash
   python -m pytest tests/ -v
   ```

---

## Build Commands

### Test (run locally)

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_build_matrix.py -v

# Run specific test
python -m pytest tests/test_build_matrix.py::TestBuildMatrix::test_all_versions_have_ucb -v
```

**Always run tests before committing.**

### Build (run on GitHub Actions)

```bash
# List available combinations
python main.py matrix

# Build specific codes (locally, if needed)
python main.py build --codes 57600

# Prepare environment
python main.py prepare --tag v0.5.8.10

# Warmup cache
python main.py warmup
```

**For production builds, push to GitHub and download artifacts from Actions.**

---

## Code Guidelines

### File Structure

- `lyra/` - Core build system (sync from upstream)
- `config/` - Build configuration
  - `build.toml` - Imagepack/mod definitions (sync from upstream)
  - `features.toml` - Feature definitions (partially upstream)
  - `combinations.toml` - **DOL-X mod matrix (independent)**
  - `mods.lock.json` - Dependency versions (independent)
- `docs/` - Internal documentation
- `tests/` - Test suites
- `tools/` - Utility scripts

### Editing Rules

**Sync from upstream** (keep aligned):
- `lyra/` core code
- `config/build.toml` imagepack/mod data definitions
- `config/features.toml` feature definitions (except DOL-X additions)

**DOL-X maintains independently**:
- `config/combinations.toml` build_codes
- `config/mods.lock.json` versions
- `docs/`, `tools/`, tests

**Before editing**:
1. Check if file syncs from upstream
2. If yes, consider impact on future merges
3. Prefer extending over modifying

### Commit Messages

Follow Conventional Commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `test`, `chore`, `sync`

Example:
```
fix: remove BESC from build_codes to avoid UCB conflict

- Update config/combinations.toml: remove bit 1
- Update config/features.toml: set BESC skip=true
- Update tests to match new matrix

Reason: UCB overwrites BESC combat images (applied last).
Upstream also does not recommend BESC+UCB (code=259).
```

---

## Recent Fixes

### 2026-06-16: Stable Configuration (maplebirch v3.1.14 + cheat v1.17 + expansion v1.2.4)

**Problem**:
- maplebirchExpansion v1.2.4 incompatible with maplebirch v4.x (R.use API breaking change)
- Cheat Extended v1.19 requires maplebirch ≥3.2.5 (but v3.2.x doesn't exist, needs v4.x)
- Cheat Extended v1.18 release deleted by author (only tag remains)
- Need stable configuration with all features working

**Investigation**:
- Checked cheat extended Git history: v1.18 tags exist but releases deleted
- v1.18(Dev20260325) and v1.18(Dev) tags point to commit 22faf42 (2026-02-07)
- Author removed v1.18 releases when publishing v1.19
- v1.17(dev) release still available and stable

**Solution (Stable Downgrade Path)**:
1. **maplebirch**: v4.1.7 → v3.1.14
   - v3.1.14 is latest v3.x, supports maplebirchExpansion v1.2.4
   - Maintains all core framework features
   
2. **cheat extended**: v1.19 → v1.17
   - v1.17 is last stable release with maplebirch v3.x compatibility
   - Core features intact (NPC control, time control, stat editing)
   - Missing v1.19 additions: farm helper, achievement unlocker, combat skills
   
3. **maplebirchExpansion**: v1.2.4 (enabled)
   - Provides: music player, sanity/spirituality attributes, longer combat, custom tattoos
   - Fully compatible with maplebirch v3.1.14

**Build Configuration**:
- Updated `config/build.toml`: maplebirch v3.1.14, cheat v1.17
- Updated `config/combinations.toml`: restore 262144 bit (maplebirch_expansion)
- Build codes: 516352 (base), 517376 (AU-F), 518400 (AU-M), 520448 (AU-A)
- GitHub Actions build: 27610025173 (SUCCESS, 3m31s)

**Known Limitations**:
- AU face expansion image positioning issue (needs v4.1.7 fix)
- Cheat v1.19 features unavailable (farm helper, achievement unlocker)
- Temporary until maplebirchExpansion releases v4.x compatible version

**Future Upgrade Path**:
When maplebirchExpansion supports v4.x:
1. Upgrade maplebirch v3.1.14 → v4.1.7
2. Upgrade cheat extended v1.17 → v1.19
3. Update maplebirchExpansion to v4.x compatible version
4. Fix AU face expansion positioning
5. Unlock all v1.19 features

**Lessons Learned**:
- Always check if release exists, not just tags: `curl -I <download_url>`
- Use `gh api repos/{owner}/{repo}/releases` to list available releases
- Document version constraints in `mods.lock.json` for future reference
- Keep fallback versions when upstream deletes releases

### Cheat Extended v1.17+ UI Design (2026-06-17 调研)

**Context**: 用户反馈"点击侧边栏作弊扩展按钮没有弹出界面"

**调研结论**: ✅ **这是v1.17+的正式设计特性，非bug**

**UI架构变更** (v1.16及以前 → v1.17+):
- **旧版设计** (推测): 集中式面板 - 点击按钮打开统一作弊设置界面
- **新版设计** (v1.17+): 分散式原生集成 - 功能分布在多个入口

**v1.17更新说明** (官方README):
```
嘗試重新設計側邊欄相關按鈕顯示方式，避免相關UI太過佔空間
```

**正确使用方式**:

1. **侧边栏** (快捷功能触发器):
   - 一键状态恢复 + PC高潮
   - 言靈实时显示 (三代言靈系统)
   - 空间节点传送 (孤儿院卧室、伊甸家、随身衣柜)

2. **游戏选项菜单 (Options)** (主要设置入口):
   - 属性控制面板
   - 战斗设置 (伤害加倍/疼痛衰减)
   - 时间控制
   - 商业功能配置

3. **场景内Widget** (情境功能):
   - 孤儿院卧室 → 随身衣柜
   - 战斗场景 → 敌人HP/AP显示
   - 言靈编辑界面

**设计理念**:
- **原生集成**: 功能融入游戏原有UI，而非独立外挂面板
- **情境触发**: 功能在需要的场景自动显示
- **快捷优先**: 高频操作放在侧边栏一键触发

**证据来源**:
- 官方README (chris81605/Degrees-of-Lewdity_Cheat_Extended)
- v1.17 Release Notes明确记载UI重构
- 功能列表按"功能点"组织，无"打开主面板"说明

**测试更新**: 见 `docs/MANUAL_TESTING_CHECKLIST.md` 更新的测试清单

### 2026-06-15: maplebirch Framework Downgrade (v4.1.7 → v3.1.13)

**Problem**:
- maplebirchExpansion v1.2.4 incompatible with maplebirch v4.1.7
- Error: `R.use is not a function` in `dist/maplebirch.js`
- Game settings interface broken, expansion features unavailable

**Root Cause**:
- maplebirch v4.1.7 (2026-06-14) removed/changed `R.use` API
- maplebirchExpansion v1.2.4 (2026-03-11) still uses old API
- Expansion released before framework v4.x breaking changes

**Solution**:
- Downgraded maplebirch to v3.1.13 (last stable v3.x)
- Updated [`config/build.toml`](config/build.toml): changed release_tag and download_url
- Updated [`config/mods.lock.json`](config/mods.lock.json): documented downgrade reason
- v3.1.13 confirmed compatible with expansion v1.2.4

**Trade-offs**:
- Lost v4.1.7 features: time travel UI optimization, NPC transformation improvements
- Kept expansion features: longer combat, music player, tattoos, sanity/spirituality attributes
- **Will upgrade to v4.x when maplebirchExpansion v1.2.5+ is released with compatibility**

**AU Face Expansion "Duplicate Loading"**:
- NOT a bug - normal ModLoader encrypted mod workflow
- v1.1.0 (Local) = encrypted container → decrypts to v1.2.8 (SideLoadLazy)
- Game only uses v1.2.8 (decrypted version)
- Mod Manager shows both for transparency (decryption process)

---

## Testing Instructions

### Before Committing

```bash
# 1. Run tests
python -m pytest tests/ -v

# 2. Check for untracked sensitive files
git status | grep -E "(AU_FACE|au_analysis|*_ANALYSIS)"

# 3. Stage changes
git add <files>

# 4. Commit
git commit -m "..."

# 5. Push
git push origin vega
```

### After GitHub Actions Build

1. Visit https://github.com/XFoxLG/DOL-X/actions
2. Download artifacts from latest run
3. Test locally if needed

---

## Security & Sensitive Information

### Never Upload

- Reverse engineering docs (e.g., `AU_FACE_DEPENDENCY_ANALYSIS_FINAL.md`)
- Runtime analysis (e.g., `au_analysis_result.json`)
- Credentials, keys, personal info

### Safe to Include

- Public mod download links (GitHub Releases)
- Official documentation references (DoL-Lyra Hub)
- Encrypted mods for self-use (AU, AU Face)

**.gitignore already covers most patterns.** Always check `git status` before committing.

---

## Environment Constraints

### Local Build Limitations

**DO NOT** run full builds locally. Local environment lacks:
- Java (APK signing)
- unrar (imagepack extraction)
- Stable network (large downloads)

**Local Environment**:
- **OS**: Windows 10 (No WSL, No Linux subsystem)
- **Shell**: Git Bash (default for automation, configured in `.vscode/settings.json`)
- **Python**: 3.12+ (for tests and utilities only)
- **Build Target**: GitHub Actions (all production builds)

**What CAN be done locally**:
```bash
# Run tests
python -m pytest tests/ -v

# Check mod URLs
curl -I <download_url>

# Git operations
git status
git diff
gh run list

# Python utilities
python main.py matrix  # List build combinations
```

**What CANNOT be done locally**:
- Full builds (missing Java, unrar)
- APK signing (requires Java + keystore)
- Imagepack extraction (requires unrar)
- Large file downloads (network instability)

### Cursor Agent Shell Environment

**Default shell**: Git Bash (configured in `.vscode/settings.json`)
- PowerShell 5.1 有 AMSI 崩溃问题
- 所有自动化命令使用 Git Bash 执行

### PowerShell AMSI Issue (Legacy)

If Shell commands fail with `AccessViolationException`:
- Cursor Agent Shell tool used PowerShell 5.1 by default (now fixed)
- AMSI (Anti-Malware Scan Interface) crashes on complex scripts
- **Solution**: Now using Git Bash for all automation

---

## Recent Fixes (2026-06-15)

### Mod Download Links Updated

所有 modloader mods 下载链接已验证并更新：

1. **cheat_extended**: V1.18 → V1.19
   - 原因：V1.18(Dev20260325) 已从 GitHub 删除
   - 新 URL: `https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended/releases/download/V1.19/cheat_extended.mod.zip`
   
2. **maplebirch**: v3.1.13 → v4.1.7
   - 新 tag: `maplebirch-release-v4.1.7`
   - 新 asset: `maplebirch-0.5.8.10-v4.1.7.mod.zip`
   
3. **Custom Hair**: CustomHair-1.0 → CustomHair tag
   - 原因：release tag 变更
   - 修复 `config/build.toml` 中的 release_tag

4. **Mae's Picvary**: 1.3.2 → DOL tag
   - 原因：asset pattern 变更
   - 新 asset_pattern: `maespicvary-DOL-.*\.mod\.zip`

5. **maplebirch扩展包**: v1.2.4 (官方框架扩展)
   - 替代独立的 LongerCombat mod（避免版本冲突）
   - 内置功能：更长遭遇战、作弊集、音乐播放器、定制纹身
   - 核心属性扩展：理智、灵性，新增恐惧/侵蚀状态
   - 完美兼容 maplebirch v4.1.7

### GitHub Actions Rate Limit Fixed

添加 `GITHUB_TOKEN` 环境变量到 build job：
- 匿名访问：60次/小时
- 认证访问：5000次/小时

配置位置：`.github/workflows/build.yaml`

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### BESC Removed from Build Matrix

- `config/features.toml`: BESC `skip=true`
- `config/combinations.toml`: 移除 bit 1 (所有 build_codes 减 1)
- 理由：UCB 最后应用，会覆盖 BESC 战斗图片

**更新后的 build_codes**:
- 57600 (原 57601): UCB + more_love + spellbook + cheat
- 58624 (原 58625): AU-F + UCB + more_love + spellbook + cheat
- 59648 (原 59649): AU-M + UCB + more_love + spellbook + cheat
- 61696 (原 61697): AU-A + UCB + more_love + spellbook + cheat

---

## Upstream Sync Strategy

### When Syncing Core Files

```bash
# 1. Check upstream updates
git fetch upstream
git log upstream/vega..vega --oneline

# 2. Compare differences
git diff upstream/vega...vega -- lyra/

# 3. Selective sync (core system)
git checkout upstream/vega -- lyra/build.py
git add lyra/build.py
git commit -m "sync: merge upstream build.py changes"

# 4. Run tests
python -m pytest tests/ -v

# 5. Push
git push origin vega
```

### Conflict Resolution

- Config files (`config/build.toml`, `config/combinations.toml`): Keep DOL-X version (`git checkout --ours`)
- Core code (`lyra/`): Keep upstream version (`git checkout --theirs`)
- Other conflicts: Manual merge

---

## Key Decisions

### Why UCB instead of BESC?

- UCB applied last → overwrites BESC combat images
- Upstream doesn't recommend BESC+UCB (code=259)
- UCB-only avoids redundant downloads

**Config**: `features.toml` has `skip=true` for BESC, `combinations.toml` excludes bit 1.

**Documentation**: See `MOD_MATRIX_RATIONALE.md` for detailed reasoning.

### Why UCB + AU?

- UCB: combat scenes (`img/sex/`, `img/combat/`)
- AU: body types (`img/body/`) + faces (`img/face/`)
- **No path overlap** → compatible

Verified in `docs/UCB_COMPATIBILITY_REPORT.md`.

### Why cheatExtended + maplebirch?

Replaces upstream's cheat+CSD with more feature-rich cheatExtended using maplebirch framework.

---

## Documentation

- [`README.md`](README.md) - Project intro (for humans)
- [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md) - Command cheat sheet
- [`MOD_MATRIX_RATIONALE.md`](MOD_MATRIX_RATIONALE.md) - Mod decision rationale
- [`docs/INDEX.md`](docs/INDEX.md) - Documentation navigator
- [`docs/UCB_COMPATIBILITY_REPORT.md`](docs/UCB_COMPATIBILITY_REPORT.md) - UCB compatibility verification
- [`.local/`](.local/) - Temporary analysis (gitignored)

---

## Common Tasks

### Add a New Mod

1. Edit `config/build.toml` (if modloader mod)
2. Update `config/combinations.toml` (if changing build_codes)
3. Run `pytest tests/test_mod_config.py -v`
4. Build test: `python main.py build --codes <new_code>`
5. Commit with clear rationale

### Update from Upstream

1. `git fetch upstream`
2. Cherry-pick or merge: `git cherry-pick <hash>` or `git merge upstream/vega`
3. Resolve conflicts (keep DOL-X identity & mod matrix)
4. Run `pytest tests/ -v`
5. Push: `git push origin vega`

### Fix Test Failures

1. Read error message carefully
2. Check if config changed: `git diff config/`
3. Run specific test: `pytest tests/test_<name>.py -v -s`
4. Fix issue
5. Verify: `pytest tests/ -v`

### Troubleshooting Build Failures

**Scenario 1: Mod download 404 error**
```bash
# 1. Verify URL manually
curl -I <mod_url>

# 2. Check GitHub releases
gh release list --repo <owner/repo>

# 3. Update config/build.toml with correct URL
# 4. Run tests
pytest tests/test_mod_config.py -v
```

**Scenario 2: GitHub Actions rate limit**
```
Error: 403 rate limit exceeded
```
**Fix**: Already fixed - `GITHUB_TOKEN` added to workflow.

**Scenario 3: Test failures after config change**
```bash
# 1. Check what changed
git diff config/

# 2. Update test expectations
# Edit tests/test_build_matrix.py

# 3. Verify
pytest tests/test_build_matrix.py -v
```

---

## Maintenance Checklist

### Weekly

- [ ] Check GitHub Actions builds: `gh run list --limit 5`
- [ ] Review open issues/PRs upstream
- [ ] Verify mod download links still work

### After Upstream Updates

- [ ] Fetch upstream: `git fetch upstream`
- [ ] Check for breaking changes: `git log upstream/vega..vega`
- [ ] Sync core files if needed
- [ ] Run full test suite: `pytest tests/ -v`

### Before Major Changes

- [ ] Create backup branch: `git branch backup-$(date +%Y%m%d)`
- [ ] Document rationale in commit message
- [ ] Run tests locally before pushing
- [ ] Monitor GitHub Actions after push

---

**Last Updated**: 2026-06-16 (稳定配置：maplebirch v3.1.14 + cheat v1.17 + expansion v1.2.4)
