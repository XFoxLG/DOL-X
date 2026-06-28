# Changelog

All notable changes to DOL-X will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Current enabled mod set documented** (2026-06-28):
  - `guide_to_me` v1.1.0 - 控制NPC嘴部
  - `neoui_patch` V1.1.0 - NeoUI Patch (侧边栏动画优化)
  - `npc_social_icon` v1.4.1 - NPC社交栏头像
- **AU model diagnosis**: pinned AU model assets to exact release files and added `docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md`
- **Build version tracking**: commit hash in APK filename (e.g., `-e0b1a4b`)
- **BUILD_MANIFEST.json**: Complete build traceability for each build_code
- **tools/quick_check.py**: Local validation tool (< 2 min)
- **tools/download_latest_build.py**: Test management automation
- **Test checklist system**: Auto-generated TEST_CHECKLIST.md
- **MCP memory integration**: Test strategy and known issues storage

### Changed

- **Build codes updated**: current stable matrix excludes BunnyTransformation after combat crash
  - Base: 7315712
  - AU-F: 7316736
  - AU-M: 7317760
  - AU-A: 7319808
- **BunnyTransformation disabled**: v0.3.1β caused 16 TweeReplacer errors and combat crashes in current DoL 0.5.8.10 stack
- **AU-F temporary rollback**: pinned AU-F to `AUfemale.model_v0.8.7.zip` to test whether v0.9.3 introduced the sidebar sprite regression
- **APK naming**: Now includes commit hash for version tracking

### Documentation

- Added CHANGELOG.md
- Added docs/TESTING_GUIDE.md
- Updated docs/AGENTS.md with test management section

## [v3.1.14-stable] - 2026-06-23

### Changed

- **Rolled back to maplebirch v3.1.14** (from v4.1.8)
- **Rolled back to cheat extended v1.17** (from v1.19)
- **Disabled AU Face expansion** (enabled=false in build.toml)

### Reason

- **expansion v1.2.4 incompatible with maplebirch v4.x**
  - Multiple runtime errors in game
  - AU Face has basehead.png path issue on v3.x (fixed in v4.1.7)
  - Will upgrade when expansion v1.2.5+ releases with native v4.x support

### Fixed

- Stabilized build stack with proven compatible versions
- Prevented mod version conflicts

## [v4.1.8-experimental] - 2026-06-23

### Changed

- Upgraded to maplebirch v4.1.8
- Upgraded to cheat extended v1.19

### Reverted

- Rolled back due to expansion compatibility issues
- See v3.1.14-stable for details

---

## Version History Notes

### Mod Version Strategy

DOL-X uses a **conservative version locking strategy**:

1. **Lock tested versions** in `config/mods.lock.json`
2. **Only upgrade when**:
   - Upstream game version updates
   - Critical bug fixes
   - New features with verified compatibility
3. **Test before upgrade**:
   - Manual testing on MuMu emulator
   - CI automated smoke tests
   - Community feedback review

### Build Code Calculation

Build codes are calculated from feature bits in `config/features.toml`:

```
base_code = sum(required_features.bit)
AU variants = base_code + AU_bit

Example (current):
- base: 7315712 (UCB + more_love + cheat + custom_hair + mae_picvary + expansion + guide_to_me + neoui_patch + npc_social_icon)
- AU-M: 7317760 (base + 2048)
```

### Upstream Sync Policy

DOL-X syncs with upstream Lyra selectively:

- ✅ **Sync**: Core build system, game version updates, localization updates
- ❌ **No sync**: Mod matrix decisions (DOL-X decides independently)
- 📋 **Review**: Documentation and workflow improvements

See `UPSTREAM_SYNC_CHECKLIST.md` for sync procedures.
