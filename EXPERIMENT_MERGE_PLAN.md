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
   - Rollback evidence: maplebirch `v3.1.14` still reproduced the historical
     `maplebirchFrameworks is not defined` blocker; `v3.1.13` restored
     `maplebirchFrameworks` as an object and reached a playable SugarCube state.
   - Current canary blocker after `v3.1.13`: cheatExtended calls
     `window.modUtils.getMod('Simple Frameworks')`, but ModLoader reports
     `ModOrderContainer getByNameOne() cannot find name. [Simple Frameworks, ModOrderContainer]`.
   - `CE_options` is currently traced as a SugarCube widget/slot id registered
     through `addto(...)`, not as a required `window.CE_options` global. Do not
     add a global initializer unless a later trace finds real global reads.
   - Next fix direction is a canary-only alias shim so `Simple Frameworks`
     resolves to the already loaded `maplebirch` module; keep stable/default
     build codes unchanged.
   - Remaining non-framework blocker: missing or misspelled skin fallback
     reference `skinColourFullback` vs `skinColourFallback`.

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
