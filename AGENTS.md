---
project: DOL-X
type: Integration Package
language: Python 3.12+
build: GitHub Actions
upstream: DoL-Lyra/Lyra
status: Active Development
updated: 2026-06-18
---

# AGENTS.md

Context for AI coding agents working on DOL-X. Treat this file as the project-level README for agents: it should contain the practical setup, validation, constraints, and decision records needed to work safely without cluttering human-facing README files.

---

## Project Overview

**DOL-X** is a self-use integration of Degrees of Lewdity, based on upstream [DoL-Lyra](https://github.com/DoL-Lyra/Lyra).

- **Repository**: https://github.com/XFoxLG/DOL-X
- **Upstream**: https://github.com/DoL-Lyra/Lyra
- **Language**: Python 3.12+
- **Build System**: Custom (lyra/build.py)

### What DOL-X Does

Provides 4 build configurations (build_codes):
- 499968: UCB + more_love + cheat + custom_hair + mae_picvary + expansion
- 500992: AU-F + UCB + more_love + cheat + custom_hair + mae_picvary + expansion
- 502016: AU-M + UCB + more_love + cheat + custom_hair + mae_picvary + expansion
- 504064: AU-A + UCB + more_love + cheat + custom_hair + mae_picvary + expansion

### What DOL-X Does NOT Do

- Public releases (self-use only)
- Reverse engineering of encrypted mods (use publicly available only)
- Local full builds (delegate to GitHub Actions)

### Environment Constraints

**CRITICAL: DO NOT attempt full builds locally**

Local environment (Windows 10, no WSL) is partially provisioned:
- `bash` may not be on PATH in the Cursor agent shell; invoke `C:\Program Files\Git\bin\bash.exe` directly when bash is required
- `unrar` is not installed in the agent environment
- Large mod downloads and signed build steps still belong on GitHub Actions

**Local capabilities** (✅):
- `pytest tests/ -v` (unit/config tests)
- `curl -I <url>` (verify mod URLs)
- `python main.py matrix` (list combinations)
- Git operations (`status`, `diff`, `gh run list`)
- GitHub API checks with `gh api` when `GITHUB_TOKEN` is present

**Must use GitHub Actions** (❌):
- Full builds (`python main.py build --codes <code>`)
- APK signing
- Imagepack extraction
- Production artifact generation

**Automation Shell**: Prefer Git Bash for scripted tasks. If the agent shell is PowerShell and `bash` is missing from PATH, use the absolute Git Bash path. Avoid long or AMSI-sensitive automation in PowerShell.

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

## Critical Constraints

### Mod Version Locks

**2026-06-23 Update**: Rollback to v3.1.14 stable configuration

- **maplebirch**: v3.1.14 (rolled back from v4.1.8)
  - Reason: expansion v1.2.4 incompatible with v4.x
  - AU Face temporarily disabled (basehead.png path issue in v3.x)
- **cheat extended**: v1.17 (rolled back from v1.19)
  - Reason: v1.19 requires maplebirch v4.x
  - Provides complete Yanling system (Custom Yanling Set + Quick Yanling)
- **maplebirchExpansion**: v1.2.4
  - Fully compatible with v3.1.14
  - Provides longer combat, music player, sanity/spirituality features
- **AU Face expansion**: disabled
  - Reason: v3.x basehead.png path issue
  - Will be re-enabled after framework upgrade to v4.x

### Upgrade Path (Waiting)

**Trigger Conditions**:
1. maplebirchExpansion releases v1.2.5+ or version explicitly marked v4.x compatible
2. OR exceeds 3 months without update (2026-09-23) → re-evaluate

**Upgrade Plan** (when condition met):
1. maplebirch v3.1.14 → v4.1.8
2. cheatExtended v1.17 → v1.19
3. maplebirchExpansion v1.2.4 → v1.2.5+
4. Re-enable AU Face expansion
5. Run full test verification

**Monitoring**:
```bash
# Check for expansion updates
gh api repos/MaplebirchLeaf/SCML-DOL-maplebirchExpansion/releases/latest --jq '.tag_name'

# Check for framework updates
gh api repos/MaplebirchLeaf/SCML-DOL-maplebirchframework/releases/latest --jq '.tag_name'
```

### Cheat Extended UI (v1.17+)

**Entry points** (NOT a single "cheat panel"):
1. **Sidebar**: Quick actions (restore stats, teleport, yanling display)
2. **Options menu**: Main settings (attributes, combat, time control)
3. **In-game widgets**: Context features (wardrobe, enemy HP/AP, yanling editor)

**Yanling System Architecture**:
- **Custom Yanling Set** (Options → Cheat Extended → "Yanling Set" tab):
  - User-written SugarCube code (e.g., `<<set $money += 1000>>`)
  - Stored in `$cccheat[]` array
  - Executed manually through the Cheat Extended UI/sidebar; do not describe it as a page-refresh auto-run

- **Quick Yanling** (Options → Cheat Extended → "Quick Yanling" tab + sidebar display):
  - Pre-written cheat functions (e.g., "infinite oxygen", "daily auto-recovery")
  - One-click enable/disable, no coding required
  - Presets: status recovery, pepper spray, transformation traits, etc.

**Custom Spellbook**: Not part of the current build matrix; Cheat Extended Yanling Set replaces its practical use case for this project.

**Test checklist**: See `docs/MANUAL_TESTING_CHECKLIST.md`

---

## Build & Test

### Local Test

```bash
# Before committing: Run all tests
python -m pytest tests/ -v

# After editing config/build.toml: Verify mod URLs
pytest tests/test_mod_config.py -v

# After editing config/combinations.toml: Verify build matrix
pytest tests/test_build_matrix.py -v
```

### Pre-Commit Checklist

```bash
# 1. Run tests
python -m pytest tests/ -v

# 2. Check sensitive files
git status | grep -E "(AU_FACE|au_analysis|*_ANALYSIS)"

# 3. Commit
git add <files> && git commit -m "..." && git push origin vega
```

### CI Build (GitHub Actions)

```bash
gh run list --limit 3
gh run view <run-id> --log-failed
```

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

## Security & Sensitive Information

### ❌ Never Commit

- `AU_FACE_DEPENDENCY_ANALYSIS*.md` (reverse engineering)
- `au_analysis_result.json` (runtime analysis)
- `.env`, `credentials.json` (secrets)

### ✅ Safe to Commit

- `config/build.toml` (public mod URLs)
- `config/mods.lock.json` (version records)
- `docs/*.md` (documentation)
- Encrypted mods (`AU.mod.zip`, `AU_FACE.mod.zip`)

**Pattern check**: `.gitignore` already covers sensitive patterns

---

## Mod Matrix

Current build codes: 499968, 500992, 502016, 504064  
Formula: `base (499968) + AU variant (0/1024/2048/4096)`

**Critical rules**:
- ❌ NEVER add BESC (conflicts with UCB)
- ❌ NEVER upgrade maplebirch to v4.x (expansion incompatible)
- ✅ AU + UCB is safe (no path overlap)

**Why these choices?** See [MOD_MATRIX_RATIONALE.md](MOD_MATRIX_RATIONALE.md)

---

## Common Issues

| Error | Quick Fix |
|-------|-----------|
| Mod download 404 | `curl -I <url>` → update `config/build.toml` |
| Rate limit (403) | Already fixed (GITHUB_TOKEN in workflow) |
| Test fails after config change | `git diff config/` → update `tests/test_*.py` |

**Detailed steps**: See `docs/TROUBLESHOOTING.md`

---

## Upstream Sync

**Core principle**: Keep `lyra/` aligned with upstream, maintain `config/combinations.toml` independently.

```bash
# Check upstream updates
git fetch upstream && git log upstream/vega..vega --oneline

# Sync core files
git checkout upstream/vega -- lyra/build.py
git add lyra/ && git commit -m "sync: merge upstream changes"

# Test
python -m pytest tests/ -v
```

**Conflict resolution**:
- Config files (`config/combinations.toml`): Keep DOL-X (`git checkout --ours`)
- Core code (`lyra/`): Keep upstream (`git checkout --theirs`)

**Detailed checklist**: See `UPSTREAM_SYNC_CHECKLIST.md`

---

## Maintenance

### Weekly
- Check builds: `gh run list --limit 5`
- Verify mod URLs still work

### After Upstream Updates
- Fetch: `git fetch upstream`
- Check breaking changes: `git log upstream/vega..vega`
- Sync if needed + run tests

### Before Major Changes
- Backup: `git branch backup-$(date +%Y%m%d)`
- Document rationale in commit
- Test locally before push

---

**Last Updated**: 2026-06-23 (rollback to maplebirch v3.1.14 + cheat v1.17 stable config)
