# AU Model Diagnostic Matrix - 2026-06-28

This document records the current AU model investigation for DOL-X. It separates AU model packages from AU Face expansion and keeps each manual APK test tied to a build artifact.

## Current Build Artifact

Latest known successful `Build` workflow before this diagnosis:

| Field | Value |
|-------|-------|
| GitHub Actions run | `28115478539` |
| Workflow | `Build` |
| Branch | `vega` |
| Title | `fix: remove v4.x compat patch causing maplebirch is not defined error` |
| Status | success |
| Artifacts | `dol-builds-apk`, `dol-builds-zip`, `dol-builds-apk-sample` |

Important: the user-provided ModLoader log that still contains `BunnyTransformation` and `DOL-X Expansion v4.x Compat Patch` is not a clean baseline for current config. Current config disables BunnyTransformation and removed the v4.x compat patch in the later successful build.

## AU Release Layout

`AOKIUTAGE/UTAGEsDOL3.0` uses GitHub releases as a package store for multiple AU-related packages. Treat release tags and asset names as package identity.

| Release tag | Meaning | DOL-X default use |
|-------------|---------|-------------------|
| `mod` | AU model and imgpack packages | Yes, model assets only |
| `facemod` | AU facial expansion | No, disabled |
| `hairmod` | AU hairplus package | No, release title says it is not adapted for newer versions |
| `psd` | Art source files | No |

The `mod` release provides two installation methods:

| Method | What it does | DOL-X decision |
|--------|--------------|----------------|
| `*.model_*.zip` | ModLoader direct model mod | Current default, upstream-aligned |
| `*.imgpack_*.zip` | Imagepack overwrite package | Not default; only test on an isolated branch if model mode cannot be made stable |

## Version Pins

DOL-X now pins exact AU model release assets instead of broad substring patterns.

| Feature | Asset | Version | Status |
|---------|-------|---------|--------|
| `au-f` | `AUfemale.model_v0.8.7.zip` | v0.8.7 | Diagnostic rollback; testing whether v0.9.3 introduced the sidebar sprite regression |
| `au-m` | `AUmale.model_v0.4.2.zip` | v0.4.2 | Needs retest with latest build |
| `au-a` | `AUandrogynous.model_v0.1.1.zip` | v0.1.1 | Needs retest with latest build |
| `au_face` | `AUsDoL.facial.expansion.mod.zip` | v1.2.8 | Disabled |

## Diagnostic Matrix

| Case | Build code | Purpose | Current evidence | Next action |
|------|------------|---------|------------------|-------------|
| Base no-AU | `7315712` | Control group for sidebar rendering | User reports base package has no sidebar sprite issue | Retest after exact AU pins land, only as sanity check |
| AU-F rollback | `7316736` | Test whether AU-F v0.9.3 introduced the sidebar issue | v0.9.3 showed hair/face layers misplaced in sidebar; current config pins `AUfemale.model_v0.8.7.zip` | Retest latest build and compare with v0.9.3 evidence |
| AU-M current | `7317760` | Check whether issue is AU-F-specific | Old AU-M logs cannot be reused because they came from older builds | Retest latest build |
| AU-A current | `7319808` | Check third AU model package | No current evidence | Retest latest build |
| AU-F without NeoUI | TBD diagnostic build | Isolate NeoUI sidebar CSS interaction | Not tested | Build only if AU-F current still fails |
| AU-F without NPC avatar mods | TBD diagnostic build | Isolate Mae's Picvary / NPC Avatars sidebar interaction | Not tested | Build only if AU-F current still fails |
| AU-F v0.9.3 | previous build evidence | Known-problem comparison point | User reproduced sidebar sprite issue with `【AUfemale】model {v:0.9.3}` | Restore only if v0.8.7 shows same issue and CSS/mod isolation becomes next priority |

## Working Hypotheses

1. AU Face is not the current cause if `facemod` is absent from the ModLoader list and `au_face.enabled = false` remains true.
2. The issue may be in AU model rendering itself, because the base no-AU package is normal and AU-F model v0.9.3 reproduces the sidebar sprite issue.
3. The issue may also be a model plus UI interaction, especially with `NeoUI-Patch`, `BeautySelectorAddon`, `Mae's Picvary NPC`, or `NPC Avatars Mod`.
4. Do not switch to `imgpack` by default before isolation. `imgpack` changes the imagepack layer and has higher conflict risk with UCB and other imagepack rules.

## Manual Test Evidence Requirements

Every AU test result must include:

1. GitHub Actions run ID.
2. APK artifact name and build code.
3. APK filename, if available.
4. ModLoader loaded mod list lines for AU, NeoUI, Mae's Picvary, NPC Avatars, BunnyTransformation, and Lyra.
5. Screenshot of sidebar open and sidebar collapsed.
6. Whether combat can start without runtime errors.

## Upstream Comparison Notes

Upstream `DoL-Lyra/Lyra` also uses the AU `model` release assets, not the `imgpack` method, for AU feature builds. Therefore the first comparison target is not install method, but DOL-X-specific extra mods and CSS/layout interactions.

| Area | Upstream Lyra | DOL-X diagnostic implication |
|------|---------------|------------------------------|
| AU install method | `*.model_*.zip` ModLoader package | Same method; do not switch to `imgpack` as the first fix |
| AU Face expansion | Separate `facemod` package | Disabled in DOL-X; do not treat AU Face as part of AU-F/M/A model packages |
| Extra UI mods | Smaller/default upstream stack | Test DOL-X-only UI interactions first: NeoUI, Mae's Picvary, NPC Social Icon / NPC avatar mods, BeautySelectorAddon |
| Imagepack stack | Upstream recommended sets differ | Keep UCB comparison in scope, but AU model/sidebar rendering is the immediate symptom |

If upstream AU model builds render normally, the likely difference is DOL-X's combined mod stack rather than the AU release package identity.
