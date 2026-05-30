#!/usr/bin/env python3
"""Build or describe isolated cheatExtended/maplebirch canary ZIP artifacts.

The default build matrix intentionally stays stable-only.  This helper creates
one explicit canary build code when runtime validation needs a real artifact
whose metadata actually contains cheatExtended/maplebirch.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.build import BuildResult, BuildTask, build_single
from lyra.config import ModCode
from lyra.config_loader import get_config_loader, load_build_config
from lyra.paths import BuildPaths
from lyra.utils import download_file, get_github_release_asset
from lyra.version import LyraVersion


CHECKLIST_PATH = Path("CHEAT_EXTENDED_MANUAL_TEST_CHECKLIST.md")
REPLACEMENT_PROFILE = "ucb-cheat-extended-maplebirch"
COMBINED_PROFILE = "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"

CANARY_CODES: dict[str, dict[str, int]] = {
    "stable-replacement": {
        "base": int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH | ModCode.UCB),
        "au-f": int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH | ModCode.UCB | ModCode.AU_FEMALE),
        "au-m": int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH | ModCode.UCB | ModCode.AU_MALE),
        "au-a": int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH | ModCode.UCB | ModCode.AU_ANDROGYNOUS),
    },
    "combined": {
        "base": int(
            ModCode.CHEAT_EXTENDED_MAPLEBIRCH
            | ModCode.CUSTOM_SPELLBOOK
            | ModCode.MORE_LOVE
            | ModCode.UCB
        ),
        "au-f": int(
            ModCode.CHEAT_EXTENDED_MAPLEBIRCH
            | ModCode.CUSTOM_SPELLBOOK
            | ModCode.MORE_LOVE
            | ModCode.UCB
            | ModCode.AU_FEMALE
        ),
        "au-m": int(
            ModCode.CHEAT_EXTENDED_MAPLEBIRCH
            | ModCode.CUSTOM_SPELLBOOK
            | ModCode.MORE_LOVE
            | ModCode.UCB
            | ModCode.AU_MALE
        ),
        "au-a": int(
            ModCode.CHEAT_EXTENDED_MAPLEBIRCH
            | ModCode.CUSTOM_SPELLBOOK
            | ModCode.MORE_LOVE
            | ModCode.UCB
            | ModCode.AU_ANDROGYNOUS
        ),
    },
}

MANUAL_RUNTIME_BLOCKERS: tuple[str, ...] = (
    "maplebirchFrameworks is not defined",
    "skinColourFullback / skinColourFallback reference error",
    "CE_options missing after mod initialization",
    "cheatExtended menu or basic controls unavailable",
    "duplicate legacy cheat/CSD/BJX/BCCM UI present",
    "save/reload/continue console errors",
)


@dataclass(frozen=True)
class CanaryPlan:
    """Description of one explicit canary artifact target."""

    flavor: str
    variant: str
    code: int
    pack_type: str
    smoke_profile: str
    expected_slug_tokens: list[str]
    forbidden_slug_tokens: list[str]
    manual_checklist: str
    manual_runtime_blockers: list[str]
    build_command: list[str]
    html_smoke_command: list[str]
    browser_smoke_command: list[str]


def _profile_for_flavor(flavor: str) -> str:
    if flavor == "stable-replacement":
        return REPLACEMENT_PROFILE
    if flavor == "combined":
        return COMBINED_PROFILE
    raise ValueError(f"unknown canary flavor: {flavor}")


def _expected_slug_tokens(flavor: str) -> list[str]:
    tokens = ["ucb", "cheat-extended", "maplebirch"]
    if flavor == "combined":
        tokens.extend(["more-love", "custom-spellbook"])
    return tokens


def _forbidden_slug_tokens(flavor: str) -> list[str]:
    if flavor == "stable-replacement":
        return ["more-love", "custom-spellbook"]
    return []


def _expected_applied_mods(flavor: str) -> list[str]:
    expected = ["UCB", "maplebirch", "cheatExtended"]
    if flavor == "combined":
        expected.extend(["更多恋人", "自定义魔法书"])
    return expected


def validate_canary_code(code: int, flavor: str) -> list[str]:
    """Return validation errors for a proposed cheatExtended canary code."""
    mod_code = ModCode(code)
    errors: list[str] = []

    if not mod_code & ModCode.CHEAT_EXTENDED_MAPLEBIRCH:
        errors.append("canary code must include cheat_extended_maplebirch")
    if not mod_code & ModCode.UCB:
        errors.append("canary code must include UCB")
    if mod_code & ModCode.CHEAT:
        errors.append("canary code must not include legacy cheat/cheat_csd bit")
    if mod_code & ModCode.CSD:
        errors.append("canary code must not include legacy CSD bit")

    au_bits = [ModCode.AU_FEMALE, ModCode.AU_MALE, ModCode.AU_ANDROGYNOUS]
    enabled_au_bits = [bit for bit in au_bits if mod_code & bit]
    if len(enabled_au_bits) > 1:
        errors.append("canary code must not mix multiple AU variants")

    if flavor == "stable-replacement":
        if mod_code & ModCode.MORE_LOVE:
            errors.append("stable replacement canary must not include more_love")
        if mod_code & ModCode.CUSTOM_SPELLBOOK:
            errors.append("stable replacement canary must not include custom_spellbook")
    elif flavor == "combined":
        if not mod_code & ModCode.MORE_LOVE:
            errors.append("combined canary must include more_love")
        if not mod_code & ModCode.CUSTOM_SPELLBOOK:
            errors.append("combined canary must include custom_spellbook")
    else:
        errors.append(f"unknown canary flavor: {flavor}")

    return errors


def make_canary_plan(flavor: str, variant: str, pack_type: str = "zip") -> CanaryPlan:
    """Create a validated build/smoke plan for one canary artifact."""
    try:
        code = CANARY_CODES[flavor][variant]
    except KeyError as exc:
        raise ValueError(f"unknown canary target: {flavor}/{variant}") from exc

    errors = validate_canary_code(code, flavor)
    if errors:
        raise ValueError("invalid canary code: " + "; ".join(errors))

    profile = _profile_for_flavor(flavor)
    artifact_placeholder = f"output/<DoL-*{code}*-or-slugged-canary>.{pack_type}"
    return CanaryPlan(
        flavor=flavor,
        variant=variant,
        code=code,
        pack_type=pack_type,
        smoke_profile=profile,
        expected_slug_tokens=_expected_slug_tokens(flavor),
        forbidden_slug_tokens=_forbidden_slug_tokens(flavor),
        manual_checklist=str(CHECKLIST_PATH),
        manual_runtime_blockers=list(MANUAL_RUNTIME_BLOCKERS),
        build_command=[
            "python",
            "tools/cheat_extended_canary.py",
            "--flavor",
            flavor,
            "--variant",
            variant,
            "--ensure-payloads",
            "--build",
        ],
        html_smoke_command=[
            "python",
            "tools/html_smoke_test.py",
            artifact_placeholder,
            "--output",
            f"output/html-smoke-cheat-canary-{flavor}-{variant}.json",
        ],
        browser_smoke_command=[
            "python",
            "tools/browser_smoke_test.py",
            artifact_placeholder,
            "--profile",
            profile,
            "--output-dir",
            f"output/browser-smoke-cheat-canary-{flavor}-{variant}",
        ],
    )


def _modloader_mod_matches_plan(mod_config, plan: CanaryPlan) -> bool:
    """Return whether a configured modloader mod should be present in this canary."""
    config_loader = get_config_loader()
    mod_code = ModCode(plan.code)
    for feature_id in mod_config.required_feature_ids:
        feature = config_loader.get_feature_by_id(feature_id)
        if feature and mod_code & feature.bit:
            return True
    return False


def ensure_canary_payloads(plan: CanaryPlan, workspace: Path) -> list[dict[str, object]]:
    """Download/cache modloader payloads required by one canary plan.

    The normal warmup step only downloads payloads needed by the default stable
    matrix.  Canary builds are intentionally outside that matrix, so CI can call
    this helper before `--build` to seed the exact cache files build_single uses.
    """
    paths = BuildPaths(workspace=workspace)
    paths.ensure_dirs()
    build_config = load_build_config()
    payloads: list[dict[str, object]] = []
    errors: list[str] = []

    for mod_config in build_config.modloader_mods:
        if not mod_config.enabled or not _modloader_mod_matches_plan(mod_config, plan):
            continue

        dest_path = paths.get_mod_cache_path(mod_config.cache_name)
        display_name = mod_config.name or mod_config.key or mod_config.asset_pattern
        if dest_path.exists() and dest_path.stat().st_size > 0:
            payloads.append(
                {
                    "name": display_name,
                    "cache_name": mod_config.cache_name,
                    "path": str(dest_path),
                    "cached": True,
                    "size_bytes": dest_path.stat().st_size,
                }
            )
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if mod_config.download_url:
                download_file(mod_config.download_url, dest_path, quiet=True)
                source = mod_config.download_url
            else:
                asset = get_github_release_asset(
                    mod_config.github_repo,
                    mod_config.asset_pattern,
                    tag=mod_config.release_tag,
                )
                if asset is None:
                    errors.append(f"{display_name}: no matching release asset")
                    continue
                download_file(asset.url, dest_path, quiet=True)
                source = asset.url
        except Exception as exc:  # pragma: no cover - network failure details vary
            errors.append(f"{display_name}: {exc}")
            continue

        if not dest_path.exists() or dest_path.stat().st_size == 0:
            errors.append(f"{display_name}: empty cache file at {dest_path}")
            continue

        payloads.append(
            {
                "name": display_name,
                "cache_name": mod_config.cache_name,
                "path": str(dest_path),
                "cached": False,
                "size_bytes": dest_path.stat().st_size,
                "source": source,
            }
        )

    if errors:
        raise RuntimeError("failed to ensure canary payloads: " + "; ".join(errors))

    return payloads


def build_canary(plan: CanaryPlan, workspace: Path, tag: str | None = None):
    """Build one explicit canary ZIP/APK without consulting the default matrix."""
    version = LyraVersion.from_tag(tag) if tag else None
    paths = BuildPaths(workspace=workspace)
    paths.ensure_dirs()
    task = BuildTask(
        pack_type=plan.pack_type,
        mod_code=plan.code,
        version=version,
        paths=paths,
    )
    result = build_single(task)
    validation_errors = validate_canary_build_result(plan, result)
    if validation_errors:
        if result.output_path:
            with contextlib.suppress(OSError):
                Path(result.output_path).unlink()
        result.success = False
        result.error = "invalid canary artifact: " + "; ".join(validation_errors)
    return result


def validate_canary_build_result(plan: CanaryPlan, result: BuildResult) -> list[str]:
    """Validate that a successful build actually injected the canary payloads."""
    if not result.success:
        return []

    errors: list[str] = []
    missing_mods = [
        mod_name
        for mod_name in _expected_applied_mods(plan.flavor)
        if mod_name not in result.applied_mods
    ]
    if missing_mods:
        errors.append(
            "missing applied canary mods: "
            + ", ".join(missing_mods)
            + "; run prepare/download so maplebirch.mod.zip and cheat_extended.mod.zip are cached"
        )

    normalized_name = result.output_name.lower().replace("_", "-")
    for token in plan.expected_slug_tokens:
        if token not in normalized_name:
            errors.append(f"output name is missing expected token: {token}")
    for token in plan.forbidden_slug_tokens:
        if token in normalized_name:
            errors.append(f"output name contains forbidden token: {token}")

    return errors


def _write_payload(payload: dict, output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or describe one isolated cheatExtended/maplebirch canary artifact"
    )
    parser.add_argument("--flavor", choices=sorted(CANARY_CODES), default="stable-replacement")
    parser.add_argument("--variant", choices=("base", "au-f", "au-m", "au-a"), default="base")
    parser.add_argument("--pack-type", choices=("zip", "apk"), default="zip")
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--tag", help="Optional Lyra version tag for artifact naming")
    parser.add_argument(
        "--ensure-payloads",
        action="store_true",
        help="Download/cache modloader payloads required by the selected canary",
    )
    parser.add_argument("--build", action="store_true", help="Actually build the canary artifact")
    parser.add_argument("--output", type=Path, help="Optional JSON plan/result path")
    args = parser.parse_args()

    plan = make_canary_plan(args.flavor, args.variant, args.pack_type)
    payload: dict = {
        "plan": asdict(plan),
        "manual_gate_required": True,
        "default_matrix_mutated": False,
    }

    if args.ensure_payloads:
        try:
            payload["payload_cache"] = ensure_canary_payloads(plan, args.workspace)
        except Exception as exc:
            payload["payload_cache_error"] = str(exc)
            _write_payload(payload, args.output)
            return 1

    if args.build:
        result = build_canary(plan, args.workspace, args.tag)
        payload["build_result"] = result.to_dict()
        _write_payload(payload, args.output)
        return 0 if result.success else 1

    _write_payload(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
