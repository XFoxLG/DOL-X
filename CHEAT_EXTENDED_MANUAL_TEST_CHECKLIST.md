# cheatExtended maplebirch manual test checklist

`experiment/cheat-extended-maplebirch` remains a held experiment. Do not merge it
to `vega` until the runtime blockers below are manually cleared.

## Current blockers

- Browser/runtime error: `maplebirchFrameworks is not defined`.
- Missing or misspelled skin fallback reference: `skinColourFullback` vs `skinColourFallback`.
- `CE_options` insertion is not confirmed at runtime.
- cheatExtended is a replacement candidate for the legacy cheat stack, not an
  additive mod to mix with `cheat`, `csd`, `bjx_word_unlock`,
  `bjx_portable_word`, or `bccm`.

## Branch and feature-bit rules

- Keep the test branch isolated from `vega` until all checks pass.
- If testing together with the current more-love/custom-spellbook candidate:
  - `more_love = 8192`
  - `custom_spellbook = 16384`
  - `cheat_extended_maplebirch = 32768`
- If testing cheatExtended alone on stable `vega`, use only the dedicated
  `cheat_extended_maplebirch = 32768` bit.
- Load the framework before `cheat_extended.mod.zip`.
- Enable exactly one framework:
  - `MaplebirchLeaf/SCML-DOL-maplebirchframework`, or
  - `emicoto/SCMLSimpleFramework`.

## Static checks before launching the game

- Run the focused config tests:

  ```bash
  python -m pytest tests/test_mod_config.py tests/test_build_matrix.py -v --tb=short
  ```

- Run the advisory audit when GitHub API rate limits are not blocking:

  ```bash
  python tools/cheat_extended_audit.py --output-dir output
  ```

- Confirm the generated build code does not include `cheat_csd` when
  cheatExtended is enabled as a replacement.
- Confirm old legacy cheat-stack entries are disabled or removed in the
  candidate branch.

## Runtime smoke test

Open the built HTML/APK and check the browser console from first load through a
new game start.

- No `maplebirchFrameworks is not defined` error.
- No `skinColourFullback` or `skinColourFallback` reference error.
- `CE_options` exists after mod initialization.
- cheatExtended menu opens and basic stat/money/time controls work.
- Enemy/combat state display works well enough to replace CSD.
- Yanling-related functions are present if replacing BJX word mods.
- No duplicate old cheat menu, CSD panel, BCCM panel, or BJX menu remains.
- Save, reload, and continue work without console errors.

## Compatibility smoke test matrix

Test at least one base build and one AU build.

- Stable-only replacement candidate:
  - base: `33024` (`32768 + 256`)
  - AU-F: `34048`
  - AU-M: `35072`
  - AU-A: `37120`
- If testing after more-love/custom-spellbook are accepted:
  - base: `57600` (`32768 + 16384 + 8192 + 256`)
  - AU-F: `58624`
  - AU-M: `59648`
  - AU-A: `61696`

## Merge gate

Only consider merging after all of these are true:

- Full mod audit passes without `rate_limited`, `api_error`, or `asset_missing`.
- Config tests pass.
- At least one ZIP artifact builds and passes `tools/html_smoke_test.py`.
- At least one browser/manual runtime session clears the blocker list above.
- The legacy cheat stack is not mixed with cheatExtended in the final config.
