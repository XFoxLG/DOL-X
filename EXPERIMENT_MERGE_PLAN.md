# Experiment branch merge plan

This project keeps self-use changes isolated on `experiment/**` until they are proven safe on top of `vega`.

## Merge order

1. `experiment/more-love`
   - Lowest-risk candidate to review first.
   - Rebase or merge from current `vega`, run config tests, mod audit, and one ZIP/APK build sample before considering merge.
2. `experiment/custom-spellbook`
   - Review after `more-love` so feature-bit and load-order conflicts are easier to isolate.
   - If both branches are kept, assign a distinct feature bit instead of reusing the experiment-only `8192` bit.
3. `experiment/cheat-extended-maplebirch`
   - Do not merge to `vega` yet.
   - Treat maplebirch as a shared framework candidate, not only as a
     cheatExtended dependency: keep AU+maplebirch framework-support evidence
     separate from cheatExtended replacement evidence so failures stay
     diagnosable.
   - Rollback evidence: maplebirch `v3.1.14` still reproduced the historical
     `maplebirchFrameworks is not defined` blocker; `v3.1.13` restored
     `maplebirchFrameworks` as an object and reached a playable SugarCube state.
   - Current canary blocker after `v3.1.13`: cheatExtended reaches a
     `window.modUtils.getMod('Simple Frameworks')` lookup even though the
     maplebirch branch should be available; ModLoader reports
     `ModOrderContainer getByNameOne() cannot find name. [Simple Frameworks, ModOrderContainer]`.
   - `CE_options` is currently traced as a SugarCube widget/slot id registered
     through `addto(...)`, not as a required `window.CE_options` global. Do not
     add a global initializer unless a later trace finds real global reads.
   - Source research is recorded in `FRAMEWORK_PROVIDER_RESEARCH.md`.
     maplebirch and Simple Frameworks are distinct providers; the maplebirch
     `Simple Frameworks` alias is a compatibility clue, not enough proof for a
     DOL-X shim.
   - Next fix direction is to re-run the maplebirch-only canary without adding
     a name shim, then trace `framework_detector.js` / `CERegist.js` to confirm
     why the explicit `getMod('maplebirch')` branch did not short-circuit. Fix
     branch logic or load order first; only revisit an alias workaround after
     runtime evidence proves it binds to `maplebirchFrameworks` rather than the
     distinct `simpleFrameworks` path.
   - Browser smoke now records canary-only runtime probes for
     `maplebirchFrameworks`, `CE_options`, `SCMLSimpleFramework`,
     `window.modUtils.getMod('maplebirch')`, and
     `window.modUtils.getMod('Simple Frameworks')`.  Use
     `tools/canary_payload_introspect.py` to correlate those probes with HTML
     smoke and ModLoader order before choosing any fix.
   - Minimal fix order for this canary is: correct load order first, patch the
     cheatExtended canary branch logic second, and consider an alias workaround
     only if runtime evidence proves it still binds to `maplebirchFrameworks`
     rather than the separate `simpleFrameworks` path.
   - Validation gate for the next concrete fix: build one stable-replacement
     canary (`33024`), run one HTML smoke, run one browser smoke with profile
     `ucb-cheat-extended-maplebirch`, then run canary payload introspection.
     Passing evidence must show no old cheat/CSD mix, default build codes
     unchanged, `getMod('maplebirch')` available before cheatExtended uses the
     framework, and no `Simple Frameworks` lookup blocker during startup.
   - After that gate passes, the only next decision is whether to continue the
     replacement-candidate gate for cheatExtended/maplebirch or to keep the
     project-local legacy cheat/CSD stack as the active stable stack and retain
     cheatExtended as a held experiment.
   - Replacement candidate codes are prepared as no-legacy-cheat evidence only:
     base `57600`, AU-F `58624`, AU-M `59648`, AU-A `61696`.  They exclude the
     project-local stable `cheat_csd` bit while retaining local rollback
     entries.
   - Simple Frameworks remains a future mutually exclusive provider. Do not add
     it to this round's B1/B2 gate and do not require both providers to pass
     before evaluating maplebirch evidence.
   - Historical non-framework blocker: missing or misspelled skin fallback
     reference `skinColourFullback` vs `skinColourFallback`. The current source
     scan found `skinColourFallback`, so keep this as a runtime check rather
     than assuming the misspelling remains.

## Feature bits if branches are combined

- `more_love`: `8192`
- `custom_spellbook`: `16384`
- `cheat_extended_maplebirch`: `32768`

## Per-experiment gate

- Confirm upstream branch freshness against `vega`.
- Run fast tests: `python -m pytest tests/ -v --tb=short`.
- Run mod audit with `GITHUB_TOKEN` when network checks are needed.
- Build at least one representative ZIP and APK artifact.
- Run `tools/html_smoke_test.py` against built ZIP artifacts.
- Keep XFox-only naming/config in `config/build.toml`; avoid hardcoding self-use behavior into generic build code.
