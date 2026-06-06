# Upstream sync checklist

Use this checklist when syncing `vega` with upstream `DoL-Lyra/Lyra`.

DOL-X is the current XFox self-use integration project and release line.
`DoL-Lyra/Lyra` is the direct upstream for build and packaging flow reuse, so
the sync direction is `DoL-Lyra/Lyra -> DOL-X`.  The goal of an upstream sync is
to keep DOL-X current with build-system and packaging improvements while
preserving DOL-X-specific identity, build matrix, and candidate/rollback mod
boundaries.

## Before sync

- Confirm current branch is `vega` and working tree changes are intentional.
- Review upstream changes for build-system edits before resolving conflicts.
- Keep self-use identity limited to `config/build.toml` unless a generic hook is needed.
- Keep DOL-X-only mod decisions in config, candidate gates, or docs; do not
  turn XFox self-use integrations into assumed upstream defaults during sync.
- Do not merge experiment branches during an upstream sync unless that is the explicit goal.

## During sync

- Preserve generic upstream behavior in core modules.
- Prefer config-driven differences for:
  - output artifact identity (`XFox`),
  - APK display name,
  - APK package name,
  - enabled mod combinations.
- Preserve the DOL-X stable matrix unless the sync explicitly includes a
  separate matrix migration decision.
- Re-check `.github/workflows/deploy.yaml`; the legacy online deploy is intentionally disabled for this fork.
- Re-check `.github/workflows/compatibility.yaml`; workflow-run checkouts must use the build run head SHA for experiment branches.

## After sync

- Run fast tests:

  ```bash
  python -m pytest tests/ -v --tb=short
  ```

- For network/resource validation, run with a GitHub token to avoid false rate-limit failures:

  ```bash
  python tools/mod_audit.py --output-dir output --no-cache
  python tools/cheat_extended_audit.py --output-dir output
  ```

- For built ZIP artifacts, run the Phase 3 static smoke test:

  ```bash
  python tools/html_smoke_test.py output --output output/html-smoke-report.json
  ```

- Verify output filenames use `DoL-<dol>-XFox-<chs>-...` and not `Lyra`.
- Verify required base mods fail fast instead of producing incomplete green builds.
- Verify DOL-X documentation still distinguishes DOL-X as the current project,
  `DoL-Lyra/Lyra` as the direct upstream, and greenfield work as a separate
  disposable spike rather than the current release line.
