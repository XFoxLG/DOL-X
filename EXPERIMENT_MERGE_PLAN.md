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
   - Current blockers: `maplebirchFrameworks is not defined`, missing `skinColourFullback`, and unconfirmed `CE_options` insertion.

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
