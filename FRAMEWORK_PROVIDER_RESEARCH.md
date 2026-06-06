# Framework provider source research

This document records the source-level comparison for `maplebirch`, `Simple
Frameworks`, and `cheatExtended` before any DOL-X build integration change.

## Scope and non-goals

- Keep the current DOL-X build matrix unchanged.
- Do not modify `config/build.toml` in this research step.
- Do not add `Simple Frameworks` to the current build config.
- Do not write a `Simple Frameworks -> maplebirch` shim from this evidence
  alone.
- Do not commit downloaded third-party source or release assets. The local
  inspection cache lives under ignored `workspace/framework-provider-research/`.

The goal is to verify registration names, dependency declarations, API surfaces,
and the real cheatExtended framework call sites so the next canary step is based
on source evidence instead of provider-name assumptions.

## Source manifest

GitHub API metadata and release lookups were rate-limited during collection, so
repository metadata is incomplete. Source archives and configured release assets
were still downloaded through codeload/direct asset URLs, and tag/head SHAs were
resolved with `git ls-remote`.

| Project | Repository | Ref/tag inspected | Commit SHA | Asset inspected | SHA256 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| maplebirch | `MaplebirchLeaf/SCML-DOL-maplebirchframework` | `maplebirch-release-v3.1.13` | `8a7c280b004befd05615627d80844a6661a54983` | `maplebirch-0.5.8.10-v3.1.13.mod.zip` | source: `499bebdb540670c6be894225697580ba5cbb0c90526ed05defff4b2897c79e7f`; asset: `593e1795f1affa9760924eb613f63a9e6dbe587cc82948a0da0ef5c8825fd1a7` | Current DOL-X configured provider asset. |
| Simple Frameworks | `emicoto/SCMLSimpleFramework` | `main` | `34dc915697ecda77e9ef3b70b83d689d4d116a39` | none resolved | source: `bfbe2995abc2a9a3695585404f27daaa186ed4df23b399ed261e81a1f2b67aa3` | Source-only inspection because release asset lookup was rate-limited / unresolved. |
| cheatExtended | `chris81605/Degrees-of-Lewdity_Cheat_Extended` | `V1.18(Dev20260325)` | `6e92c7e90b0a726c5a1c785de52c59b1fb04baea` | `cheat_extended.mod.zip` | source: `a301632d8b049c9763319a2bb85d10833f0558c93270de83647edd93f6bbdaaf`; asset: `4572ed9f18efbb0f08f951fe815a617e1843f0fa2197fcee1bb9ed2b969430bd` | Current cheatExtended candidate asset. |

## ModLoader registration names

| Provider/mod | `boot.json` name | Version | Relevant dependency declarations | Name/alias findings |
| --- | --- | --- | --- | --- |
| maplebirch | `maplebirch` | `3.1.13` | Depends on ModLoader, ModLoaderGui, ModSubUiAngularJs, ConflictChecker, BeautySelectorAddon, ReplacePatcher, TweeReplacer, GameVersion. | Its `boot.json` includes `alias: ["Simple Frameworks"]`, but the canonical provider name remains `maplebirch`. |
| Simple Frameworks | `Simple Frameworks` | `2.0.5` | Depends on TweeReplacer and ReplacePatcher. Example bundled dependents declare `Simple Frameworks`. | Distinct canonical provider name. Its source checks mods that depend on `Simple Frameworks`. |
| cheatExtended | `cheat extended` | `1.18(Dev260325)` | Depends on ModLoader, ImageLoaderHook, TweeReplacer, ReplacePatcher, SweetAlert2Mod, GameVersion. | Does not declare either framework in `dependenceInfo`; instead it detects providers at runtime with `window.modUtils.getMod(...)`. |

Important consequence: `maplebirch` and `Simple Frameworks` are not the same
provider just because maplebirch advertises an alias. The source shows distinct
canonical names and distinct framework globals/API branches.

## Framework API comparison

### maplebirch

Observed source/API indicators:

- Canonical ModLoader name: `maplebirch`.
- Runtime/global API used by cheatExtended: `maplebirchFrameworks`.
- Registration API used by cheatExtended: `maplebirchFrameworks.addto(...)`.
- Source contains compatibility-oriented files such as `src/SFcompat.ts` and
  type declarations in `dist/maplebirch.d.ts`.
- Source/assets reference framework services beyond simple menu-slot
  registration, including `TimeEvent`-related APIs and IDB/indexedDB-related
  services.

### Simple Frameworks

Observed source/API indicators:

- Canonical ModLoader name: `Simple Frameworks`.
- Runtime/global API used by cheatExtended: `simpleFrameworks`.
- Registration API used by cheatExtended: `simpleFrameworks.addto(...)`.
- Source exposes `TimeEvent` and `TimeHandle` on `window`.
- Source contains manager logic that scans loaded mods for dependencies on
  `Simple Frameworks`.

### Compatibility status

Both frameworks provide an `addto(...)` style API and both expose or document
time-event functionality, but the researched source does not prove complete
semantic equivalence. The slot names used by cheatExtended are also different
between providers, which means name-only aliasing is not equivalent to proving
the runtime APIs are interchangeable.

## cheatExtended framework dependency trace

cheatExtended's `boot.json` does not list `maplebirch` or `Simple Frameworks`
as required dependencies. The framework choice is decided by runtime code.

Observed runtime detector behavior:

```js
window.modUtils.getMod('maplebirch')
window.modUtils.getMod('Simple Frameworks')
```

Observed maplebirch branch registrations:

```js
maplebirchFrameworks.addto('Cheats', 'cheat_extended')
maplebirchFrameworks.addto('MenuBig', 'CE_originalCheatButton')
maplebirchFrameworks.addto('Options', 'CE_options')
maplebirchFrameworks.addto('CaptionAfterDescription', 'CEstatebox')
maplebirchFrameworks.addto('HintMobile', 'CE_sideBarIcon')
```

Observed Simple Frameworks branch registrations:

```js
simpleFrameworks.addto('ModCaptionAfterDescription', 'CEstatebox')
simpleFrameworks.addto('iModOptions', 'CE_options')
simpleFrameworks.addto('iModFooter', 'CE_CheatExtendedVersion')
```

Additional dependency findings:

- `CE_options` is defined as a SugarCube widget/slot id, not as a required
  `window.CE_options` global.
- `skinColourFallback` is present in the inspected cheatExtended source/asset
  replacement path. This scan did not find source evidence for
  `skinColourFullback`; keep the historical misspelling warning as a runtime
  blocker only if the generated artifact or browser console still shows it.
- cheatExtended README states it can use `Simple Framework` or
  `maplebirchframework`, but also warns that some behavior is temporarily
  maplebirch-limited and the Simple Framework path is untested / may not work
  as expected.

## Conflict classification

| Conflict area | Classification | Reason |
| --- | --- | --- |
| Provider identity | Real distinction | Canonical names are different: `maplebirch` vs `Simple Frameworks`. |
| maplebirch alias | Compatibility clue, not proof | `alias: ["Simple Frameworks"]` exists, but source-level semantic compatibility is not proven. |
| cheatExtended dependency model | Runtime optional-provider model | cheatExtended does not declare either provider in `boot.json`; it probes both at runtime. |
| Menu/slot registration | Provider-specific | cheatExtended uses different slot names for maplebirch and Simple Frameworks. |
| `CE_options` | Not a global blocker by itself | It is a widget/slot id registered through `addto(...)`. UI rendering is the meaningful check. |
| `skinColourFullback` vs `skinColourFallback` | Runtime evidence needed | Source/asset scan found `skinColourFallback`; do not assume the misspelling remains unless built artifacts or console logs reproduce it. |
| Simple Framework integration | Future mutually exclusive provider | Adding it now would widen the matrix and make failures harder to diagnose. |

## Recommendation for the next DOL-X mod track

Continue with a **maplebirch-only canary track**, but do **not** implement a
`Simple Frameworks -> maplebirch` alias shim from this research alone.

Rationale:

1. The current DOL-X candidate already carries maplebirch evidence, and
   cheatExtended has an explicit maplebirch runtime branch using
   `window.modUtils.getMod('maplebirch')` plus `maplebirchFrameworks.addto(...)`.
2. Simple Frameworks is a distinct provider with its own canonical name,
   `simpleFrameworks` API, dependency scanner, and slot names.
3. maplebirch's `Simple Frameworks` alias is useful evidence, but it is not a
   sufficient compatibility proof for a DOL-X shim.
4. Introducing Simple Frameworks now would create a second provider path and
   obscure whether failures are cheatExtended replacement issues, framework
   provider issues, or load-order issues.

Practical next step after this research:

- Keep stable/default build codes unchanged.
- Keep Simple Frameworks out of the current B1/B2 gate.
- Re-run the maplebirch canary without adding a name shim first, and collect the
  exact runtime trace around `framework_detector.js` / `CERegist.js`.
- If the only remaining blocker is still a `getMod('Simple Frameworks')` lookup
  after the explicit `getMod('maplebirch')` branch should have succeeded, fix the
  branch logic or load order directly in the canary path before considering any
  alias-based compatibility workaround.
- Only consider an alias shim after runtime evidence proves that cheatExtended
  will bind to `maplebirchFrameworks`, not accidentally enter the
  `simpleFrameworks` branch against a non-identical provider.
