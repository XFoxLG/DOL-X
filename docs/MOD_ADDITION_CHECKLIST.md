# Mod Addition Checklist

Complete guide for adding new mods to DOL-X.

---

## Phase 1: Pre-Addition Checks

### 1.1 Source Verification
- [ ] Mod source is trustworthy (official GitHub repo)
- [ ] Mod has clear license (compatible with project)
- [ ] Mod has stable releases with version numbers
- [ ] Mod author is responsive to issues

### 1.2 Compatibility Check
- [ ] Mod works with current DOL version
- [ ] Mod uses ModLoader API (has `boot.json`)
- [ ] No known conflicts with existing mods
- [ ] Dependencies are available and compatible

### 1.3 Impact Assessment
- [ ] Understand what the mod changes (gameplay, UI, content)
- [ ] Evaluate if it fits project goals
- [ ] Consider user demand (GitHub issues, community requests)
- [ ] Assess maintenance burden (update frequency, complexity)

---

## Phase 2: Configuration Addition

### 2.1 Use Add Mod Helper

Run the automated helper:

```bash
python tools/add_mod.py <key> "<name>" <github_repo> <asset_pattern> \
  --release-tag <tag> \
  --dry-run  # Test first
```

**Example**:
```bash
python tools/add_mod.py beauty_selector "Beauty Selector Addon" \
  "user/Beauty-Selector-Addon" \
  "BeautySelectorAddon.mod.zip" \
  --release-tag "v1.0.0" \
  --dry-run
```

### 2.2 Manual Verification

Check generated entries in:

**config/build.toml**:
```toml
[[modloader_mods]]
key = "beauty_selector"
name = "Beauty Selector Addon"
enabled = true
feature_id = "beauty_selector"
github_repo = "user/Beauty-Selector-Addon"
asset_pattern = "BeautySelectorAddon.mod.zip"
release_tag = "v1.0.0"
```

**config/features.toml**:
```toml
[[features]]
id = "beauty_selector"
name = "Beauty Selector Addon"
bit = 65536  # Auto-assigned
required = false
```

### 2.3 Add to Combinations (Optional)

If mod should be in default builds, update `config/combinations.toml`:

```toml
# Add new build code: base_code (24834) + new_feature_bit (65536) = 90370
build_codes = ["24834", "25858", "26882", "28930", "90370"]
```

### 2.4 Add Profile (Optional)

If mod needs a dedicated profile, update `config/profiles.toml`:

```toml
[[profiles]]
id = "with-beauty-selector"
name = "整合包 + Beauty Selector"
description = "标准整合包 + Beauty Selector Addon"
build_code = 90370
```

---

## Phase 3: Automated Testing

### 3.1 Run Validation Pipeline

```bash
python tools/validate_mod_addition.py <mod_key> <test_code>
```

**Expected output**:
```
→ Building test artifact (code 90370)...
✓ Building test artifact passed
→ Running HTML smoke test...
✓ HTML smoke test passed
→ Running browser smoke test...
✓ Browser smoke test passed
→ Running functional tests...
✓ Functional tests passed
```

### 3.2 Check Test Results

- [ ] Build completes without errors
- [ ] HTML smoke: payload extracted and valid
- [ ] Browser smoke: reaches Orphanage Intro, no console errors
- [ ] Functional tests: cheat menu, stat modification, save/load work

### 3.3 Review Test Logs

Check output files in `output/`:
- `*-html-smoke.json`
- `*-browser-smoke/browser-smoke-report.json`
- `*-functional.json`

---

## Phase 4: Manual Testing

### 4.1 Build and Extract

```bash
python tools/build.py --codes <test_code>
```

Extract ZIP and open in browser.

### 4.2 Mod-Specific Tests

- [ ] Mod loads without errors (check console)
- [ ] Mod UI appears and is accessible
- [ ] Mod features work as expected
- [ ] No conflicts with other mods
- [ ] Performance is acceptable

### 4.3 Edge Cases

- [ ] Test with AU variants (if applicable)
- [ ] Test save/load with mod active
- [ ] Test mod disable/enable (if supported)
- [ ] Test with different passages/scenarios

### 4.4 APK Testing (Optional)

If mod should work on Android:

```bash
python tools/build.py --codes <test_code> --pack-type apk
# Install and test on device/emulator
```

---

## Phase 5: Documentation

### 5.1 Update README

Add mod to feature list in `README.md`:

```markdown
## Features

- ...existing features...
- **Beauty Selector Addon** (v1.0.0): Customizable beauty traits selector
```

### 5.2 Update PROFILE_USAGE.md

If added new profile:

```markdown
| Profile ID | Build Code | Description |
|------------|------------|-------------|
| with-beauty-selector | 90370 | 整合包 + Beauty Selector |
```

### 5.3 Document Known Issues

If mod has known issues, add to `docs/KNOWN_ISSUES.md`:

```markdown
### Beauty Selector Addon

- **Issue**: May conflict with AU-A variant
- **Workaround**: Use with AU-F/M only
- **Status**: Reported upstream
```

### 5.4 Update CHANGELOG (Optional)

```markdown
## [Unreleased]

### Added
- Beauty Selector Addon v1.0.0 integration
```

---

## Phase 6: Pull Request

### 6.1 Create PR

```bash
git checkout -b feature/add-beauty-selector
git add config/build.toml config/features.toml config/profiles.toml
git commit -m "feat: add Beauty Selector Addon integration"
git push origin feature/add-beauty-selector
```

### 6.2 PR Description Template

```markdown
## Summary

Adds [Mod Name] v[version] integration.

## Motivation

[Why this mod? User demand? Essential feature?]

## Changes

- Added mod configuration to config/build.toml
- Added feature definition (bit: XXXXX)
- [Optional] Added profile "profile-id"
- [Optional] Updated default build codes

## Testing

- [x] Automated tests pass
- [x] Manual testing complete
- [x] Works with AU variants
- [x] No conflicts with existing mods

## Screenshots

[Optional: screenshots of mod in action]

## Checklist

- [x] All checklist items completed
- [x] Documentation updated
- [x] Tests added/updated
- [x] No breaking changes
```

### 6.3 Wait for CI

GitHub Actions will run:
- HTML smoke tests
- Browser smoke tests
- Functional tests

Fix any failures before merging.

---

## Phase 7: Merge and Release

### 7.1 Review and Merge

- [ ] Code review approved
- [ ] All tests passing
- [ ] Documentation complete
- [ ] No conflicts with main branch

### 7.2 Post-Merge

- [ ] Verify mod in next release build
- [ ] Monitor for user-reported issues
- [ ] Update mod version when upstream releases

---

## Rollback Plan

If mod causes issues after merge:

### Quick Disable

Set `enabled = false` in `config/build.toml`:

```toml
[[modloader_mods]]
key = "problematic_mod"
enabled = false  # Disable without removing
```

### Complete Removal

```bash
# Remove from config/build.toml
# Remove from config/features.toml
# Remove from config/combinations.toml (if added)
# Remove from config/profiles.toml (if added)

git commit -m "revert: remove problematic mod"
```

---

## Tips and Best Practices

### Feature Bit Management
- Use `tools/add_mod.py` for automatic bit assignment
- Document bit assignments in comments
- Never reuse bits (even after removal)

### Testing Strategy
- Always test with base configuration first
- Then test with AU variants
- Test both ZIP and APK if mod should work on Android
- Test with multiple save files

### Upstream Relationship
- Link to upstream repo in mod description
- Report bugs upstream, not in DOL-X
- Keep local patches to minimum
- Document any local modifications

### Maintenance
- Subscribe to upstream release notifications
- Update mod versions regularly
- Test updates before merging
- Keep compatibility matrix up to date

---

## Common Issues

### Issue: Feature bit conflict
**Solution**: Run `tools/add_mod.py` again, it will suggest next available bit

### Issue: Mod not loading
**Solution**: Check `boot.json` format, verify download URL

### Issue: Conflicts with existing mod
**Solution**: Add `conflicts_with` in `config/features.toml`

### Issue: APK build fails
**Solution**: Check if mod uses web-only APIs, may need APK compatibility patch

---

## References

- [ModLoader API Documentation](https://github.com/DoL-Lyra/sugarcube-2-ModLoader)
- [DOL-X Architecture](docs/)
- [Testing Guide](docs/TESTING.md)
