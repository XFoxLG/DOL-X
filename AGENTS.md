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

**DO** run tests locally:
```bash
python -m pytest tests/ -v
```

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

**Last Updated**: 2026-06-15 (Mod 更新：maplebirchExpansion 代替 LongerCombat，Cheat Extended V1.19，Maplebirch v4.1.7)
