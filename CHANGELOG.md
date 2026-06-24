# Changelog

All notable changes to DOL-X will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **4 new mods integrated** (2026-06-24):
  - `guide_to_me` v1.1.0 - 控制NPC嘴部
  - `bunny_transformation` v0.3.1β - 变身兔兔
  - `neoui_patch` V1.1.0 - NeoUI Patch (侧边栏动画优化)
  - `npc_social_icon` v1.4.1 - NPC社交栏头像
- **Build version tracking**: commit hash in APK filename (e.g., `-e0b1a4b`)
- **BUILD_MANIFEST.json**: Complete build traceability for each build_code
- **tools/quick_check.py**: Local validation tool (< 2 min)
- **tools/download_latest_build.py**: Test management automation
- **Test checklist system**: Auto-generated TEST_CHECKLIST.md
- **MCP memory integration**: Test strategy and known issues storage

### Changed

- **Build codes updated**: 499968 → 8364288 series (4 new required mods)
  - Base: 8364288
  - AU-F: 8365312
  - AU-M: 8366336
  - AU-A: 8368384
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
- base: 8364288 (UCB + more_love + cheat + custom_hair + mae_picvary + expansion + 4_new_mods)
- AU-M: 8366336 (base + 2048)
```

### Upstream Sync Policy

DOL-X syncs with upstream Lyra selectively:

- ✅ **Sync**: Core build system, game version updates, localization updates
- ❌ **No sync**: Mod matrix decisions (DOL-X decides independently)
- 📋 **Review**: Documentation and workflow improvements

See `UPSTREAM_SYNC_CHECKLIST.md` for sync procedures.
