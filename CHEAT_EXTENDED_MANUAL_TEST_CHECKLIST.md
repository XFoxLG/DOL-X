# cheatExtended maplebirch manual test checklist

`experiment/cheat-extended-maplebirch` remains a held experiment. Do not merge it
to `vega` until the runtime blockers below are manually cleared.

## Current blockers

- Historical browser/runtime blocker: `maplebirchFrameworks is not defined`.
  maplebirch `v3.1.14` still reproduced it; `v3.1.13` restored
  `maplebirchFrameworks` as an object and reached a playable SugarCube state.
- Current `v3.1.13` framework blocker: cheatExtended reaches a
  `window.modUtils.getMod('Simple Frameworks')` lookup even though the
  maplebirch branch should be available; ModLoader reports
  `ModOrderContainer getByNameOne() cannot find name. [Simple Frameworks, ModOrderContainer]`.
- Historical skin fallback warning: `skinColourFullback` vs
  `skinColourFallback`. The source research found `skinColourFallback`, so keep
  this as a runtime check rather than assuming the misspelling remains.
- `CE_options` is traced as a SugarCube widget/slot id registered through
  `addto(...)`, not as a required `window.CE_options` global. Do not treat
  `window.CE_options === undefined` by itself as a blocker; verify the CE
  options widget/slot renders in the options UI instead.
- cheatExtended is a replacement candidate for the project-local legacy
  cheat/CSD stack, not an additive mod to mix with `cheat`, `csd`,
  `bjx_word_unlock`, `bjx_portable_word`, or `bccm`.
- maplebirch is a shared framework candidate.  Keep AU+maplebirch
  framework-support evidence separate from cheatExtended replacement evidence;
  a failure in one path should not hide the other path's diagnosis.

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
- Source research is recorded in `FRAMEWORK_PROVIDER_RESEARCH.md`. maplebirch
  and Simple Frameworks are distinct providers; the maplebirch
  `Simple Frameworks` alias is a compatibility clue, not enough proof for a
  DOL-X shim.
- Current canary fix direction is to re-run the maplebirch-only path without a
  name shim, then trace `framework_detector.js` / `CERegist.js` to confirm why
  the explicit `getMod('maplebirch')` branch did not short-circuit. Fix branch
  logic or load order before revisiting any alias workaround.
- Browser smoke now records the canary runtime probe set:
  `maplebirchFrameworks`, `CE_options`, `SCMLSimpleFramework`,
  `window.modUtils.getMod('maplebirch')`, and
  `window.modUtils.getMod('Simple Frameworks')`.  Correlate those probes with
  HTML smoke and ModLoader order through `tools/canary_payload_introspect.py`.
- Minimal fix order is load order first, cheatExtended canary branch logic
  second, and an alias workaround only after runtime evidence proves it still
  binds to `maplebirchFrameworks` instead of the distinct `simpleFrameworks`
  path.
- Simple Frameworks is reserved as a future mutually exclusive provider.  It is
  not part of this round's B1/B2 gate and should not block maplebirch evidence.

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
- Confirm project-local legacy cheat/CSD entries are not active in replacement
  candidate artifacts.  Keep those local rollback config entries available
  until the Phase 2 migration decision is explicit.

## Runtime smoke test

Open the built HTML/APK and check the browser console from first load through a
new game start.

- No `maplebirchFrameworks is not defined` error.
- No `ModOrderContainer getByNameOne() cannot find name. [Simple Frameworks, ModOrderContainer]`
  error after the maplebirch branch/load-order fix is applied.
- No `skinColourFullback` or `skinColourFallback` reference error.
- The CE options widget/slot appears in the options UI; do not require a
  `window.CE_options` global.
- cheatExtended menu opens and basic stat/money/time controls work.
- Enemy/combat state display works well enough to replace CSD.
- Yanling-related functions are present if replacing BJX word mods.
- No duplicate old cheat menu, CSD panel, BCCM panel, or BJX menu remains.
- Save, reload, and continue work without console errors.

For blocker validation, run only one canary stable-replacement build (`33024`) +
HTML smoke + browser smoke with profile `ucb-cheat-extended-maplebirch` + canary
payload introspection after a concrete runtime fix. Passing evidence must show:

- Default/stable build codes remain unchanged.
- The artifact does not mix cheatExtended with the project-local legacy
  cheat/CSD stack.
- `getMod('maplebirch')` is available before cheatExtended uses the framework.
- The `Simple Frameworks` lookup blocker is gone without adding Simple
  Frameworks to the build.

If the same blocker remains, record the evidence and stop rather than repeating
the smoke loop.

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

The current baseline candidate gate still records maplebirch provider evidence
separately from these no-legacy replacement codes.  Do not treat the presence
of prepared replacement codes as a default matrix migration.

## Merge gate

Only consider merging after all of these are true:

- Full mod audit passes without `rate_limited`, `api_error`, or `asset_missing`.
- Config tests pass.
- At least one ZIP artifact builds and passes `tools/html_smoke_test.py`.
- At least one browser/manual runtime session clears the blocker list above.
- The project-local legacy cheat/CSD stack is not mixed with cheatExtended in the final config.

After the canary gate passes, choose only between continuing the
cheatExtended/maplebirch replacement-candidate gate or keeping the
project-local legacy cheat/CSD stack as the active stable stack while retaining
cheatExtended as a held experiment.
