# Changelog

All notable changes to DOL-X will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Removed

- **CI build artifacts pruned** (2026-07-01): GitHub Actions artifact storage had
  grown to 573 artifacts / ~89 GB and exceeded quota. Deleted all but the newest
  3 build runs (9 artifacts total: apk + zip + apk-sample each), freeing ~86.5 GB.
  Remaining: 2.55 GB across runs `28461618104` (2026-06-30), `28390261132` and
  `28354033076` (2026-06-29). Deletion is irreversible but these are historical CI
  outputs reproducible from source; the newest run kept is the one used for the
  sidebar comparison.

### Fixed

- **Build artifact naming collision** (2026-06-30): `ModCode.get_suffix()` did not
  recognize the newer mod bits (`guide_to_me`, `bunny_transformation`,
  `neoui_patch`, `npc_social_icon`), so AU-F without NeoUI (`5219584`) and AU-F
  with NeoUI (`7316736`) produced identical APK filenames and overwrote each
  other in `output/`. The APK artifact therefore shipped only 4 APKs instead of
  5, and the surviving AU-F APK could not be identified for sidebar comparison.
  Registered the 4 missing bits with distinct filename suffixes and added
  `test_build_codes_have_unique_output_suffixes` to prevent future collisions.
  Verified on CI run `28461618104`: APK artifact restored to 5 files / 588 MB
  (was 4 files / 458 MB), with two distinct AU-F builds (with/without
  `neoui-patch` in the filename). Commit `0197f79`.

### Added

- **D.O.L.I integrated** (2026-07-01): `ArsNativa/Degrees-of-Lewdity-Intelligence`
  pinned to `v0.2.3` (asset `DOLI.mod.zip`). LLM-driven AI dialogue / combat-text
  enhancement running in ReAct mode against an OpenAI-compatible backend. It is a
  maplebirch plugin (`boot.json` requires ModLoader `^2.0.0` + maplebirch `^3.1.0`,
  both satisfied by the current 2.101.1 + 3.1.14 stack, so no version-lock change).
  Added as a required mod (feature bit `8388608`, `depends_on = cheat_extended_maplebirch`),
  so it ships in all 5 builds. Build codes shifted accordingly:
  base `5218560`→`13607168`, AU-F `5219584`→`13608192`, AU-F+NeoUI `7316736`→`15705344`,
  AU-M `5220608`→`13609216`, AU-A `5222656`→`13611264`. The build system never embeds
  an API key; players supply their own in-game, and the mod loads inert when unset.
  License CC BY-NC-SA 4.0. First CI build must be watched once to confirm it coexists
  with the NeoUI overlay / maplebirch stack.
- **Current enabled mod set documented** (2026-06-29):
  - `guide_to_me` v1.1.0 - 控制NPC嘴部
  - `npc_social_icon` v1.4.1 - NPC社交栏头像
- **AU model diagnosis**: pinned AU model assets to exact release files and added `docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md`
- **Build version tracking**: commit hash in APK filename (e.g., `-e0b1a4b`)
- **BUILD_MANIFEST.json**: Complete build traceability for each build_code
- **tools/quick_check.py**: Local validation tool (< 2 min)
- **tools/download_latest_build.py**: Test management automation
- **Test checklist system**: Auto-generated TEST_CHECKLIST.md
- **MCP memory integration**: Test strategy and known issues storage

### Changed

- **Build codes updated**: current matrix is 5 builds — base + 3 AU variants,
  plus an AU-F + NeoUI compare build for sidebar isolation. Values below reflect
  the D.O.L.I integration (all shifted by `+8388608`; see the Added entry above)
  - Base: 13607168
  - AU-F (no NeoUI): 13608192
  - AU-F + NeoUI (compare): 15705344
  - AU-M: 13609216
  - AU-A: 13611264
- **BunnyTransformation disabled**: v0.3.1β caused 16 TweeReplacer errors and combat crashes in current DoL 0.5.8.10 stack
- **NeoUI Patch cleared and kept as permanent opt-in** (updated 2026-06-30): NeoUI was
  originally the leading suspect for AU sidebar sprite misplacement and isolated to a
  single compare build. Side-by-side testing on CI run `28461618104` (builds `5219584`
  without NeoUI vs `7316736` with NeoUI, identical game/mod versions) reversed that:
  sprites render correctly in both, so NeoUI is not the cause. Its overlay sidebar that
  covers story text is by design, not a bug; the user judged it usable. Both AU-F builds
  (with/without NeoUI) are kept permanently for user choice. Root cause of the original
  misplacement is attributed (strongest inference, not proven) to the earlier maplebirch
  v4.x stack + `expansion_v4_compat.js` shim removed in commit `d3bcd47`, not NeoUI.
- **AU-F restored to upstream-aligned asset**: pinned AU-F to `AUfemale.model_v0.9.3.zip`
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
- base: 5218560 (UCB + more_love + cheat + custom_hair + mae_picvary + expansion + guide_to_me + npc_social_icon)
- AU-M: 5220608 (base + 2048)
```

### Upstream Sync Policy

DOL-X syncs with upstream Lyra selectively:

- ✅ **Sync**: Core build system, game version updates, localization updates
- ❌ **No sync**: Mod matrix decisions (DOL-X decides independently)
- 📋 **Review**: Documentation and workflow improvements

See `UPSTREAM_SYNC_CHECKLIST.md` for sync procedures.
