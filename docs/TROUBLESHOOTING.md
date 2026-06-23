# Troubleshooting Guide

Common build and configuration issues for DOL-X.

---

## Mod Download Failures

### Symptom: 404 Not Found

```
Error: Failed to download mod from https://github.com/.../releases/download/.../mod.zip
HTTP Status: 404
```

**Diagnosis**:
```bash
# Verify URL
curl -I https://github.com/.../releases/download/.../mod.zip

# If 404, check available releases
gh api repos/{owner}/{repo}/releases | jq '.[].tag_name'
```

**Fix**:
1. Find correct release tag
2. Update `config/build.toml` with correct `release_tag` and `download_url`
3. Run tests: `pytest tests/test_mod_config.py -v`

**Example**:
```toml
# Before (broken)
release_tag = "v1.18"
download_url = "https://github.com/author/mod/releases/download/v1.18/mod.zip"

# After (fixed)
release_tag = "v1.19"
download_url = "https://github.com/author/mod/releases/download/v1.19/mod.zip"
```

---

## GitHub Actions Rate Limit

### Symptom: 403 Rate Limit Exceeded

```
Error: API rate limit exceeded for anonymous requests
```

**Cause**: GitHub limits anonymous API calls to 60/hour

**Fix**: Already implemented - `GITHUB_TOKEN` added to workflow

**Verify**:
```yaml
# .github/workflows/build.yaml
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}  # ✅ This line must exist
```

---

## Test Failures After Config Change

### Symptom: Build Matrix Mismatch

```
AssertionError: Expected build_code 57601, got 57600
```

**Diagnosis**:
```bash
# Check what changed
git diff config/

# Review current matrix
python main.py matrix
```

**Fix**:
1. Update test expectations in `tests/test_build_matrix.py`
2. Verify: `pytest tests/test_build_matrix.py -v`

**Example**:
```python
# If you removed BESC (bit 1), update expected codes:
# Before
assert 57601 in build_codes

# After
assert 57600 in build_codes
```

---

## Local Build Attempts

### Symptom: Missing Dependencies

```
Error: unrar: command not found
Error: jarsigner: command not found
```

**Cause**: Local environment (Windows 10) lacks required tools

**Fix**: **Do NOT attempt to fix locally**

Instead:
1. Push to GitHub: `git push origin vega`
2. Download artifacts from Actions: `gh run list --limit 3`

**Why**:
- APK signing requires Java runtime
- Imagepack extraction requires unrar binary
- Large mod downloads may timeout on home network

---

## Mod Compatibility Issues

### Symptom: maplebirch API Error

```
Error: R.use is not a function
Source: maplebirchExpansion v1.2.4
```

**Cause**: maplebirch v4.x removed `R.use` API

**Fix**: Downgrade to v3.1.14 (see `config/build.toml`)

**Current stable config**:
- maplebirch: v3.1.14
- cheat extended: v1.17
- maplebirchExpansion: v1.2.4

**Upgrade path**: Wait for expansion v1.2.5+ (v4.x compatible)

---

## Test Environment Issues

### Symptom: PowerShell AMSI Crash

```
AccessViolationException in System.Management.Automation.dll
```

**Cause**: AMSI (Anti-Malware Scan Interface) crashes on complex scripts

**Fix**: Use Git Bash instead

**Verify**:
```json
// .vscode/settings.json
{
  "terminal.integrated.defaultProfile.windows": "Git Bash"
}
```

---

## Quick Diagnostic Commands

```bash
# Check build matrix
python main.py matrix

# Verify mod URLs
for url in $(grep download_url config/build.toml | cut -d'"' -f2); do
  echo "Checking $url"
  curl -I "$url" | head -1
done

# Run all tests
python -m pytest tests/ -v

# Check GitHub Actions status
gh run list --limit 5

# View failed job logs
gh run view <run-id> --log-failed
```

---

## Getting Help

1. **Check existing documentation**:
   - `AGENTS.md` - Agent instructions
   - `.local/CHANGELOG.md` - Historical decisions
   - `MOD_MATRIX_RATIONALE.md` - Mod combination rules

2. **Search GitHub Issues**:
   - Upstream: https://github.com/DoL-Lyra/Lyra/issues
   - Mod repos: Check individual mod repositories

3. **Verify assumptions**:
   - Read mod documentation (README.md)
   - Check upstream changelog
   - Review test output carefully

---

**Last Updated**: 2026-06-17
