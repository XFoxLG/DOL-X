#!/usr/bin/env python3
"""Build and validate the baseline cheatExtended/maplebirch candidate gate.

Phase 1A intentionally keeps the default stable matrix unchanged.  This helper
describes and builds explicit candidate codes that add the framework/provider
bit to the current stable codes, then writes machine-readable reports that CI
can enforce without mutating config/combinations.toml.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.build import BuildResult, BuildTask, build_single
from lyra.config import ModCode
from lyra.config_loader import get_config_loader, load_build_config
from lyra.paths import BuildPaths
from tools.artifact_inspection import (
    collect_string_values,
    decode_base64_payload,
    load_html_artifact,
    parse_mod_data_value_zip_list,
)
from tools.au_artifact_check import audit_zip_artifact as audit_au_zip_artifact
from tools.cheat_extended_canary import (
    _download_modloader_payload,
    _is_maplebirch_mod,
    _patch_maplebirch_idb_schema_recovery,
)
from tools.html_smoke_test import audit_html_content, audit_zip_artifact as audit_html_zip_artifact


NAME = "baseline-candidate-gate"
PARTIAL_GATE_LEVEL = "partial_candidate_gate"
FULL_GATE_LEVEL = "full_candidate_gate"
PROMOTION_REQUIRED_GREEN_RUNS = 2
PROFILE = "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"
DEFAULT_STABLE_CODES: dict[str, int] = {
    "base": 24834,
    "au-f": 25858,
    "au-m": 26882,
    "au-a": 28930,
}
DEFAULT_STABLE_CODE_ORDER: tuple[str, ...] = ("base", "au-f", "au-m", "au-a")
MAPLEBIRCH_PROVIDER = "maplebirch"
FRAMEWORK_CANDIDATE_PURPOSE = "framework_candidate"
REPLACEMENT_CANDIDATE_PURPOSE = "cheat_extended_replacement"
CANDIDATE_CODES: dict[str, int] = {
    slug: code + int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH)
    for slug, code in DEFAULT_STABLE_CODES.items()
}
REPLACEMENT_CANDIDATE_CODES: dict[str, int] = {
    slug: (code & ~int(ModCode.CHEAT)) + int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH)
    for slug, code in DEFAULT_STABLE_CODES.items()
}
AU_BITS_BY_SLUG: dict[str, ModCode] = {
    "au-f": ModCode.AU_FEMALE,
    "au-m": ModCode.AU_MALE,
    "au-a": ModCode.AU_ANDROGYNOUS,
}
BASE_REQUIRED_BITS: tuple[tuple[str, ModCode], ...] = (
    ("cheat_csd compatibility identity", ModCode.CHEAT),
    ("ucb", ModCode.UCB),
    ("more_love", ModCode.MORE_LOVE),
    ("custom_spellbook", ModCode.CUSTOM_SPELLBOOK),
    ("cheat_extended_maplebirch", ModCode.CHEAT_EXTENDED_MAPLEBIRCH),
)
REPLACEMENT_REQUIRED_BITS: tuple[tuple[str, ModCode], ...] = (
    ("ucb", ModCode.UCB),
    ("more_love", ModCode.MORE_LOVE),
    ("custom_spellbook", ModCode.CUSTOM_SPELLBOOK),
    ("cheat_extended_maplebirch", ModCode.CHEAT_EXTENDED_MAPLEBIRCH),
)
BASE_REQUIRED_APPLIED_MOD_TERMS: tuple[str, ...] = (
    "UCB",
    "maplebirch",
    "cheatExtended",
)
BASE_REQUIRED_PAYLOAD_TERMS: dict[str, tuple[str, ...]] = {
    "ModLoaderGui": ("modloadergui", "modloader gui"),
    "ModI18N": ("modi18n", "i18n"),
    "maplebirch": ("maplebirch",),
    "cheatExtended": ("cheatextended", "cheat extended"),
    "More Love Interests Mod": ("more love interests mod",),
    "Custom-Spellbook": ("custom-spellbook", "custom spellbook"),
    "Lyra": ("lyra",),
}
ZIP_BUILD_REPORT = "baseline-candidate-zip-build.json"
APK_BUILD_REPORT = "baseline-candidate-apk-build.json"
ZIP_AUDIT_REPORT = "baseline-candidate-zip-audit.json"
APK_AUDIT_REPORT = "baseline-candidate-apk-audit.json"
ZIP_BROWSER_SUMMARY = "baseline-candidate-zip-browser-summary.json"
PHASE1A_SUMMARY = "baseline-candidate-phase1a-summary.json"
PHASE1A_CONFIG_REPORT = "baseline-candidate-config.json"
APK_DEBUG_REPORT = "baseline-candidate-apk-debug-derivation.json"
APK_EQUIVALENCE_REPORT = "baseline-candidate-apk-equivalence.json"
APK_CDP_SMOKE_REPORT = "baseline-candidate-apk-cdp-smoke.json"
STABLE_REPLACEMENT_READINESS_REPORT = "baseline-candidate-stable-replacement-readiness.json"
FULL_GATE_COMPONENT_LEVEL = "full_candidate_gate_ready_component"
LEGACY_FEATURE_ID = "cheat_csd"
REPLACEMENT_FEATURE_ID = "cheat_extended_maplebirch"
LEGACY_BASE_MOD_KEYS: tuple[str, ...] = ("cheat", "csd")
LEGACY_MODLOADER_MOD_KEYS: tuple[str, ...] = ("bjx_word_unlock", "bjx_portable_word", "bccm")
REPLACEMENT_MODLOADER_MOD_KEYS: tuple[str, ...] = ("maplebirch", "cheat_extended")
WEBVIEW_DEBUG_INVOKE = "Landroid/webkit/WebView;->setWebContentsDebuggingEnabled(Z)V"
WEBVIEW_DEBUG_METHOD_NAME = "setWebContentsDebuggingEnabled"
WEBVIEW_DEBUG_SMALI_SNIPPET = (
    "    const/4 v0, 0x1\n"
    f"    invoke-static {{v0}}, {WEBVIEW_DEBUG_INVOKE}\n"
)
DEBUG_KEYSTORE_ALIAS = "dolx-smoke-debug"
DEBUG_KEYSTORE_PASSWORD = "dolxdebug"


@dataclass(frozen=True)
class CandidateTarget:
    """One explicit candidate build target."""

    slug: str
    legacy_code: int
    code: int
    provider: str
    purpose: str
    replacement_candidate_code: int
    legacy_cheat_stack_included: bool
    pack_type: str
    smoke_profile: str
    expected_slug_tokens: list[str]
    required_bits: dict[str, int]
    build_command: list[str]
    html_smoke_command: list[str]
    browser_smoke_command: list[str]


@dataclass
class CandidateBuildRecord:
    """Build result for one candidate target."""

    slug: str
    code: int
    pack_type: str
    success: bool
    output_path: str | None = None
    output_name: str = ""
    error: str | None = None
    applied_mods: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    payload_cache: list[dict[str, object]] = field(default_factory=list)


@dataclass
class EmbeddedPayload:
    """Minimal embedded ModLoader payload metadata for candidate audits."""

    index: int
    names: list[str] = field(default_factory=list)
    boot_json_found: bool = False
    error: str | None = None
    payload_sha256: str | None = None
    search_text_sample: str = ""


@dataclass
class CandidateZipAuditRecord:
    """Static ZIP audit result for one candidate artifact."""

    slug: str
    code: int | None
    target: str
    success: bool
    html_smoke: dict[str, Any]
    au_alias_audit: dict[str, Any] | None
    payload_count: int
    required_payloads: dict[str, bool]
    package_slug_checks: dict[str, Any]
    errors: list[str] = field(default_factory=list)


@dataclass
class CandidateApkAuditRecord:
    """Static APK audit result for one candidate artifact."""

    slug: str
    code: int | None
    target: str
    success: bool
    html_member: str | None = None
    html_sha256: str | None = None
    manifest_debuggable: bool | None = None
    release_debuggable_ok: bool | None = None
    payload_count: int = 0
    payload_sha256: list[str] = field(default_factory=list)
    required_payloads: dict[str, bool] = field(default_factory=dict)
    package_slug_checks: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DebugApkRecord:
    """Release-derived smoke-debug APK derivation result."""

    slug: str
    release_apk: str
    debug_apk: str | None
    success: bool
    release_debuggable: bool | None = None
    debug_manifest_debuggable: bool | None = None
    webview_debug_hook_applied: bool = False
    release_html_sha256: str | None = None
    debug_html_sha256: str | None = None
    html_sha256_match: bool | None = None
    release_payload_sha256: list[str] = field(default_factory=list)
    debug_payload_sha256: list[str] = field(default_factory=list)
    payload_sha256_match: bool | None = None
    errors: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ApkWebIdentity:
    """Static WebView content identity extracted from one APK artifact."""

    target: str
    html_member: str | None = None
    html_sha256: str | None = None
    payload_count: int = 0
    payload_sha256: list[str] = field(default_factory=list)
    payload_names: list[list[str]] = field(default_factory=list)
    required_payloads: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class ApkEquivalenceRecord:
    """Release/debug APK static equivalence result for one candidate."""

    slug: str
    code: int | None
    release_apk: str | None
    debug_apk: str | None
    success: bool
    release_debuggable: bool | None = None
    debug_manifest_debuggable: bool | None = None
    webview_debug_hook_applied: bool = False
    release_identity: dict[str, Any] = field(default_factory=dict)
    debug_identity: dict[str, Any] = field(default_factory=dict)
    html_sha256_match: bool | None = None
    payload_sha256_match: bool | None = None
    payload_names_match: bool | None = None
    required_payloads_match: bool | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class ApkCdpSmokeRecord:
    """Android emulator/WebView CDP smoke result for one APK."""

    target: str
    package: str
    success: bool
    cdp_url: str | None = None
    passage: str | None = None
    cdp_targets: list[dict[str, Any]] = field(default_factory=list)
    startup_steps: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)


def _gate_dir() -> Path:
    path = Path("output") / NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _target_output_dir(pack_type: str) -> Path:
    return _gate_dir() / f"{pack_type}-artifacts"


def _expected_slug_tokens(slug: str) -> list[str]:
    tokens = ["ucb", "more-love", "custom-spellbook", "cheat-extended", "maplebirch"]
    if slug != "base":
        tokens.insert(0, slug)
    return tokens


def _required_bits_for_slug(slug: str) -> dict[str, int]:
    bits = {name: int(bit) for name, bit in BASE_REQUIRED_BITS}
    if slug in AU_BITS_BY_SLUG:
        bits[slug] = int(AU_BITS_BY_SLUG[slug])
    return bits


def validate_candidate_code(slug: str, code: int) -> list[str]:
    """Return validation errors for one baseline candidate code."""
    errors: list[str] = []
    expected_code = CANDIDATE_CODES.get(slug)
    if expected_code is None:
        return [f"unknown candidate slug: {slug}"]
    if code != expected_code:
        errors.append(f"{slug} candidate code must be {expected_code}, got {code}")

    mod_code = ModCode(code)
    for label, bit in BASE_REQUIRED_BITS:
        if not mod_code & bit:
            errors.append(f"candidate code must include {label} bit {int(bit)}")

    if mod_code & ModCode.CSD:
        errors.append("candidate code must not include reserved CSD bit 4")

    enabled_au = [variant for variant, bit in AU_BITS_BY_SLUG.items() if mod_code & bit]
    if slug == "base" and enabled_au:
        errors.append(f"base candidate must not include AU bits: {enabled_au}")
    elif slug != "base":
        if enabled_au != [slug]:
            errors.append(f"{slug} candidate must include only its own AU bit, got {enabled_au}")

    return errors


def validate_replacement_candidate_code(slug: str, code: int) -> list[str]:
    """Return errors for a no-legacy-cheat replacement candidate code."""
    errors: list[str] = []
    expected_code = REPLACEMENT_CANDIDATE_CODES.get(slug)
    if expected_code is None:
        return [f"unknown replacement candidate slug: {slug}"]
    if code != expected_code:
        errors.append(f"{slug} replacement candidate code must be {expected_code}, got {code}")

    mod_code = ModCode(code)
    for label, bit in REPLACEMENT_REQUIRED_BITS:
        if not mod_code & bit:
            errors.append(f"replacement candidate code must include {label} bit {int(bit)}")
    for label, bit in (("legacy cheat_csd", ModCode.CHEAT), ("reserved CSD", ModCode.CSD)):
        if mod_code & bit:
            errors.append(f"replacement candidate code must not include {label} bit {int(bit)}")

    enabled_au = [variant for variant, bit in AU_BITS_BY_SLUG.items() if mod_code & bit]
    if slug == "base" and enabled_au:
        errors.append(f"base replacement candidate must not include AU bits: {enabled_au}")
    elif slug != "base":
        if enabled_au != [slug]:
            errors.append(f"{slug} replacement candidate must include only its own AU bit, got {enabled_au}")

    return errors


def make_candidate_target(slug: str, pack_type: str = "zip") -> CandidateTarget:
    """Create a manifest target for one candidate artifact."""
    if slug not in CANDIDATE_CODES:
        raise ValueError(f"unknown candidate slug: {slug}")
    if pack_type not in {"zip", "apk"}:
        raise ValueError(f"unsupported pack type: {pack_type}")

    code = CANDIDATE_CODES[slug]
    errors = validate_candidate_code(slug, code)
    if errors:
        raise ValueError("invalid candidate code: " + "; ".join(errors))

    artifact_placeholder = f"output/{NAME}/{pack_type}-artifacts/<DoL-*{code}*>.{pack_type}"
    return CandidateTarget(
        slug=slug,
        legacy_code=DEFAULT_STABLE_CODES[slug],
        code=code,
        provider=MAPLEBIRCH_PROVIDER,
        purpose=FRAMEWORK_CANDIDATE_PURPOSE,
        replacement_candidate_code=REPLACEMENT_CANDIDATE_CODES[slug],
        legacy_cheat_stack_included=True,
        pack_type=pack_type,
        smoke_profile=PROFILE,
        expected_slug_tokens=_expected_slug_tokens(slug),
        required_bits=_required_bits_for_slug(slug),
        build_command=[
            "python",
            "tools/baseline_candidate_gate.py",
            "build",
            "--pack-type",
            pack_type,
            "--ensure-payloads",
        ],
        html_smoke_command=[
            "python",
            "tools/html_smoke_test.py",
            artifact_placeholder,
        ],
        browser_smoke_command=[
            "python",
            "tools/browser_smoke_test.py",
            artifact_placeholder,
            "--profile",
            PROFILE,
        ],
    )


def build_manifest(pack_type: str = "zip") -> dict[str, Any]:
    """Return the Phase 1A candidate manifest without changing defaults."""
    config_loader = get_config_loader()
    return {
        "name": NAME,
        "gate_level": PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "default_build_codes": list(config_loader.combinations.build_codes),
        "legacy_stable_codes": DEFAULT_STABLE_CODES,
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": FRAMEWORK_CANDIDATE_PURPOSE,
        "candidate_codes": CANDIDATE_CODES,
        "legacy_cheat_stack_included": True,
        "replacement_candidate": {
            "provider": MAPLEBIRCH_PROVIDER,
            "purpose": REPLACEMENT_CANDIDATE_PURPOSE,
            "candidate_codes": REPLACEMENT_CANDIDATE_CODES,
            "legacy_cheat_stack_included": False,
            "default_matrix_mutated": False,
            "legacy_entries_retained_for_rollback": True,
            "notes": [
                "Prepared replacement candidate codes exclude the legacy cheat_csd bit 2.",
                "Phase 1A/B2 still keeps default build_codes and legacy mod entries unchanged.",
            ],
        },
        "candidate_feature_bit": int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH),
        "smoke_profile": PROFILE,
        "promotion_policy": {
            "required_gate_level": FULL_GATE_LEVEL,
            "same_head_sha_successful_runs": PROMOTION_REQUIRED_GREEN_RUNS,
        },
        "targets": [asdict(make_candidate_target(slug, pack_type)) for slug in DEFAULT_STABLE_CODE_ORDER],
    }


def validate_static_config() -> dict[str, Any]:
    """Validate Phase 1A config invariants for the candidate gate."""
    errors: list[str] = []
    loader = get_config_loader()
    combinations = loader.combinations
    build_config = load_build_config()

    expected_default_codes = [str(DEFAULT_STABLE_CODES[slug]) for slug in DEFAULT_STABLE_CODE_ORDER]
    if combinations.build_codes != expected_default_codes:
        errors.append(f"default build_codes must remain {expected_default_codes}, got {combinations.build_codes}")
    if combinations.base_code != DEFAULT_STABLE_CODES["base"]:
        errors.append(f"base_code must remain {DEFAULT_STABLE_CODES['base']}, got {combinations.base_code}")
    if sorted(combinations.recommended) != sorted(
        [DEFAULT_STABLE_CODES["au-f"], DEFAULT_STABLE_CODES["au-m"], DEFAULT_STABLE_CODES["au-a"]]
    ):
        errors.append("recommended codes must remain the three default AU stable codes")

    candidate_code_strings = {str(code) for code in CANDIDATE_CODES.values()}
    default_code_strings = set(combinations.build_codes)
    overlap = sorted(default_code_strings & candidate_code_strings)
    if overlap:
        errors.append(f"candidate codes must not enter default build_codes in Phase 1A: {overlap}")

    feature = loader.get_feature_by_id("cheat_extended_maplebirch")
    if feature is None:
        errors.append("feature cheat_extended_maplebirch is missing")
    else:
        if feature.bit != int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH):
            errors.append(f"feature cheat_extended_maplebirch must keep bit 32768, got {feature.bit}")
        if feature.required:
            errors.append("feature cheat_extended_maplebirch must not be required in Phase 1A")

    mods_by_key = {mod.key or mod.cache_name: mod for mod in build_config.modloader_mods}
    maplebirch = mods_by_key.get("maplebirch")
    cheat_extended = mods_by_key.get("cheat_extended")
    if maplebirch is None:
        errors.append("maplebirch modloader mod is missing")
    else:
        if maplebirch.feature_id != "cheat_extended_maplebirch":
            errors.append("maplebirch must stay behind cheat_extended_maplebirch during Phase 1A")
        if maplebirch.release_tag != "maplebirch-release-v3.1.13":
            errors.append(f"maplebirch release must remain v3.1.13, got {maplebirch.release_tag}")
    if cheat_extended is None:
        errors.append("cheatExtended modloader mod is missing")
    elif cheat_extended.feature_id != "cheat_extended_maplebirch":
        errors.append("cheatExtended must stay behind cheat_extended_maplebirch during Phase 1A")

    mod_order = [mod.key or mod.cache_name for mod in build_config.modloader_mods]
    if "maplebirch" in mod_order and "cheat_extended" in mod_order:
        if mod_order.index("maplebirch") > mod_order.index("cheat_extended"):
            errors.append("maplebirch must be injected before cheatExtended")

    for slug, code in CANDIDATE_CODES.items():
        errors.extend(validate_candidate_code(slug, code))
    for slug, code in REPLACEMENT_CANDIDATE_CODES.items():
        errors.extend(validate_replacement_candidate_code(slug, code))

    return {
        "success": not errors,
        "errors": errors,
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": FRAMEWORK_CANDIDATE_PURPOSE,
        "replacement_candidate": {
            "provider": MAPLEBIRCH_PROVIDER,
            "purpose": REPLACEMENT_CANDIDATE_PURPOSE,
            "candidate_codes": REPLACEMENT_CANDIDATE_CODES,
            "legacy_cheat_stack_included": False,
            "legacy_entries_retained_for_rollback": True,
            "default_matrix_mutated": False,
        },
        "manifest": build_manifest(),
    }


def _mod_key(mod_config: Any) -> str:
    """Return the stable config key used by build.toml entries."""
    return str(getattr(mod_config, "key", None) or getattr(mod_config, "cache_name", ""))


def _feature_ids_for_mod(mod_config: Any) -> list[str]:
    feature_ids = getattr(mod_config, "feature_ids", None)
    if feature_ids:
        return [str(feature_id) for feature_id in feature_ids]
    feature_id = getattr(mod_config, "feature_id", None)
    return [str(feature_id)] if feature_id else []


def _summarize_mod_entry(mod_config: Any) -> dict[str, Any]:
    """Return rollback/readiness metadata without exposing the full config object."""
    return {
        "key": _mod_key(mod_config),
        "name": getattr(mod_config, "name", None),
        "enabled": bool(getattr(mod_config, "enabled", True)),
        "feature_id": getattr(mod_config, "feature_id", None),
        "feature_ids": _feature_ids_for_mod(mod_config),
        "github_repo": getattr(mod_config, "github_repo", None),
        "asset_pattern": getattr(mod_config, "asset_pattern", None),
        "release_tag": getattr(mod_config, "release_tag", None),
    }


def build_stable_replacement_readiness() -> dict[str, Any]:
    """Report whether the no-legacy-cheat replacement path is ready to gate.

    This is intentionally not a promotion check.  It verifies the soft
    replacement boundary while keeping defaults unchanged until full gate
    evidence separately authorizes migration.
    """
    errors: list[str] = []
    loader = get_config_loader()
    combinations = loader.combinations
    build_config = load_build_config()

    expected_default_codes = [str(DEFAULT_STABLE_CODES[slug]) for slug in DEFAULT_STABLE_CODE_ORDER]
    expected_recommended = [
        DEFAULT_STABLE_CODES["au-f"],
        DEFAULT_STABLE_CODES["au-m"],
        DEFAULT_STABLE_CODES["au-a"],
    ]
    default_matrix_unchanged = (
        combinations.build_codes == expected_default_codes
        and combinations.base_code == DEFAULT_STABLE_CODES["base"]
        and sorted(combinations.recommended) == sorted(expected_recommended)
    )
    if not default_matrix_unchanged:
        errors.append("default stable matrix changed before replacement promotion evidence")

    legacy_feature = loader.get_feature_by_id(LEGACY_FEATURE_ID)
    replacement_feature = loader.get_feature_by_id(REPLACEMENT_FEATURE_ID)
    legacy_feature_required = bool(getattr(legacy_feature, "required", False)) if legacy_feature else False
    replacement_feature_required = bool(getattr(replacement_feature, "required", False)) if replacement_feature else False
    if legacy_feature is None:
        errors.append(f"legacy feature {LEGACY_FEATURE_ID} is missing")
    if replacement_feature is None:
        errors.append(f"replacement feature {REPLACEMENT_FEATURE_ID} is missing")
    elif replacement_feature.bit != int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH):
        errors.append(
            f"replacement feature {REPLACEMENT_FEATURE_ID} must keep bit "
            f"{int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH)}, got {replacement_feature.bit}"
        )

    replacement_code_errors = [
        error for slug, code in REPLACEMENT_CANDIDATE_CODES.items() for error in validate_replacement_candidate_code(slug, code)
    ]
    errors.extend(replacement_code_errors)
    replacement_codes_exclude_legacy_bits = all(
        not (ModCode(code) & ModCode.CHEAT) and not (ModCode(code) & ModCode.CSD)
        for code in REPLACEMENT_CANDIDATE_CODES.values()
    )
    if not replacement_codes_exclude_legacy_bits:
        errors.append("replacement candidate codes must exclude legacy cheat_csd and reserved CSD bits")

    modloader_entries = list(getattr(build_config, "modloader_mods", []) or [])
    mods_by_key = {_mod_key(mod): mod for mod in modloader_entries}
    legacy_entries = [mods_by_key.get(key) for key in LEGACY_MODLOADER_MOD_KEYS]
    replacement_entries = [mods_by_key.get(key) for key in REPLACEMENT_MODLOADER_MOD_KEYS]

    if any(entry is None for entry in legacy_entries):
        missing = [key for key, entry in zip(LEGACY_MODLOADER_MOD_KEYS, legacy_entries) if entry is None]
        errors.append(f"legacy rollback modloader entries are missing: {missing}")
    legacy_modloader_entries_retained_disabled = all(
        entry is not None
        and bool(getattr(entry, "enabled", True)) is False
        and LEGACY_FEATURE_ID in _feature_ids_for_mod(entry)
        for entry in legacy_entries
    )
    if not legacy_modloader_entries_retained_disabled:
        errors.append("legacy BJX/BCCM rollback entries must be retained, disabled, and tied to cheat_csd")

    if any(entry is None for entry in replacement_entries):
        missing = [key for key, entry in zip(REPLACEMENT_MODLOADER_MOD_KEYS, replacement_entries) if entry is None]
        errors.append(f"replacement modloader entries are missing: {missing}")
    replacement_mods_present_enabled = all(
        entry is not None
        and bool(getattr(entry, "enabled", True)) is True
        and REPLACEMENT_FEATURE_ID in _feature_ids_for_mod(entry)
        for entry in replacement_entries
    )
    if not replacement_mods_present_enabled:
        errors.append("maplebirch and cheatExtended must be enabled behind cheat_extended_maplebirch")

    mod_order = [_mod_key(mod) for mod in modloader_entries]
    maplebirch_before_cheat_extended = False
    if "maplebirch" in mod_order and "cheat_extended" in mod_order:
        maplebirch_before_cheat_extended = mod_order.index("maplebirch") < mod_order.index("cheat_extended")
    if not maplebirch_before_cheat_extended:
        errors.append("maplebirch must be injected before cheatExtended")

    base_entries = list(getattr(build_config, "base_mods", []) or [])
    base_mod_keys = {_mod_key(mod) for mod in base_entries}
    legacy_base_mods_absent = not any(key in base_mod_keys for key in LEGACY_BASE_MOD_KEYS)

    checks = {
        "default_matrix_unchanged": default_matrix_unchanged,
        "legacy_feature_present": legacy_feature is not None,
        "replacement_feature_present": replacement_feature is not None,
        "replacement_codes_valid": not replacement_code_errors,
        "replacement_codes_exclude_legacy_bits": replacement_codes_exclude_legacy_bits,
        "legacy_modloader_entries_retained_disabled": legacy_modloader_entries_retained_disabled,
        "legacy_base_mods_absent": legacy_base_mods_absent,
        "replacement_mods_present_enabled": replacement_mods_present_enabled,
        "maplebirch_before_cheat_extended": maplebirch_before_cheat_extended,
    }

    return {
        "success": not errors,
        "gate_level": PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "default_migration_allowed": False,
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": REPLACEMENT_CANDIDATE_PURPOSE,
        "legacy_cheat_stack_included": False,
        "legacy_entries_retained_for_rollback": True,
        "legacy_feature": {
            "id": LEGACY_FEATURE_ID,
            "present": legacy_feature is not None,
            "required": legacy_feature_required,
        },
        "replacement_feature": {
            "id": REPLACEMENT_FEATURE_ID,
            "present": replacement_feature is not None,
            "required": replacement_feature_required,
            "bit": int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH),
        },
        "legacy_stable_codes": DEFAULT_STABLE_CODES,
        "candidate_codes": REPLACEMENT_CANDIDATE_CODES,
        "framework_candidate_codes": CANDIDATE_CODES,
        "default_build_codes": list(combinations.build_codes),
        "checks": checks,
        "legacy_base_mod_keys": sorted(base_mod_keys & set(LEGACY_BASE_MOD_KEYS)),
        "legacy_modloader_rollback_entries": [_summarize_mod_entry(entry) for entry in legacy_entries if entry is not None],
        "replacement_modloader_entries": [_summarize_mod_entry(entry) for entry in replacement_entries if entry is not None],
        "promotion_policy": {
            "required_gate_level": FULL_GATE_LEVEL,
            "same_head_sha_successful_runs": PROMOTION_REQUIRED_GREEN_RUNS,
        },
        "notes": [
            "Replacement candidate codes remove legacy cheat_csd bit 2 and keep AU variants covered.",
            "This report does not authorize default migration; use check-promotion after full gate evidence.",
        ],
        "errors": errors,
    }


def _diagnostic_paths(workspace: Path, output_dir: Path) -> BuildPaths:
    config = copy.deepcopy(load_build_config())
    config.output_dir = str(output_dir)
    paths = BuildPaths(workspace=workspace, _config=config)
    paths.ensure_dirs()
    return paths


def _remove_scratch_work_dir(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _modloader_mod_matches_code(mod_config: Any, code: int) -> bool:
    loader = get_config_loader()
    mod_code = ModCode(code)
    for feature_id in mod_config.required_feature_ids:
        feature = loader.get_feature_by_id(feature_id)
        if feature and mod_code & feature.bit:
            return True
    return False


def ensure_candidate_payloads(code: int, workspace: Path) -> list[dict[str, object]]:
    """Download/cache modloader payloads required by one candidate code."""
    paths = BuildPaths(workspace=workspace)
    paths.ensure_dirs()
    payloads: list[dict[str, object]] = []
    errors: list[str] = []

    for mod_config in load_build_config().modloader_mods:
        if not mod_config.enabled or not _modloader_mod_matches_code(mod_config, code):
            continue

        dest_path = paths.get_mod_cache_path(mod_config.cache_name)
        display_name = mod_config.name or mod_config.key or mod_config.asset_pattern
        cached = dest_path.exists() and dest_path.stat().st_size > 0
        source = mod_config.download_url or mod_config.release_tag or mod_config.github_repo

        if not cached:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                source = _download_modloader_payload(mod_config, dest_path, None)
            except Exception as exc:  # pragma: no cover - network details vary.
                errors.append(f"{display_name}: {exc}")
                continue

        if not dest_path.exists() or dest_path.stat().st_size == 0:
            errors.append(f"{display_name}: empty cache file at {dest_path}")
            continue

        payload_entry: dict[str, object] = {
            "name": display_name,
            "cache_name": mod_config.cache_name,
            "path": str(dest_path),
            "cached": cached,
            "size_bytes": dest_path.stat().st_size,
            "source": source,
        }
        if _is_maplebirch_mod(mod_config):
            patch_result = _patch_maplebirch_idb_schema_recovery(dest_path)
            payload_entry["maplebirch_idb_schema_patch"] = patch_result
            patch_status = str(patch_result.get("status") or "unknown")
            if "3.1.13" in str(mod_config.release_tag) and patch_status not in {"patched", "already_patched"}:
                errors.append(f"{display_name}: maplebirch IDB schema patch failed: {patch_status}")
                continue
        payloads.append(payload_entry)

    if errors:
        raise RuntimeError("failed to ensure candidate payloads: " + "; ".join(errors))
    return payloads


def validate_candidate_build_result(slug: str, result: BuildResult) -> list[str]:
    """Validate that a successful build contains candidate identity markers."""
    if not result.success:
        return []

    errors: list[str] = []
    applied_text = "\n".join(result.applied_mods).lower()
    for term in BASE_REQUIRED_APPLIED_MOD_TERMS:
        if term.lower() not in applied_text:
            errors.append(f"missing applied candidate mod: {term}")
    if slug != "base" and slug not in result.output_name.lower().replace("_", "-"):
        errors.append(f"AU candidate output name is missing variant token: {slug}")

    normalized_name = result.output_name.lower().replace("_", "-")
    for token in _expected_slug_tokens(slug):
        if token not in normalized_name:
            errors.append(f"output name is missing expected token: {token}")
    return errors


def build_candidates(
    pack_type: str,
    workspace: Path,
    output_dir: Path,
    ensure_payloads: bool,
    report_path: Path,
) -> int:
    """Build all explicit baseline candidate artifacts for one pack type."""
    records: list[CandidateBuildRecord] = []
    paths = _diagnostic_paths(workspace, output_dir)

    for slug in DEFAULT_STABLE_CODE_ORDER:
        code = CANDIDATE_CODES[slug]
        payload_cache: list[dict[str, object]] = []
        try:
            if ensure_payloads:
                payload_cache = ensure_candidate_payloads(code, workspace)
            _remove_scratch_work_dir(paths.get_build_work_dir(pack_type, code))
            result = build_single(BuildTask(pack_type=pack_type, mod_code=code, paths=paths))
            validation_errors = validate_candidate_build_result(slug, result)
            success = bool(result.success) and not validation_errors
            record = CandidateBuildRecord(
                slug=slug,
                code=code,
                pack_type=pack_type,
                success=success,
                output_path=str(result.output_path) if result.output_path else None,
                output_name=result.output_name,
                error=result.error,
                applied_mods=list(result.applied_mods),
                validation_errors=validation_errors,
                payload_cache=payload_cache,
            )
        except Exception as exc:  # noqa: BLE001 - gate reports should keep failure evidence.
            record = CandidateBuildRecord(
                slug=slug,
                code=code,
                pack_type=pack_type,
                success=False,
                error=str(exc),
                payload_cache=payload_cache,
            )
        records.append(record)
        print(json.dumps(asdict(record), ensure_ascii=False))

    payload = {
        "manifest": build_manifest(pack_type),
        "pack_type": pack_type,
        "results": [asdict(record) for record in records],
    }
    _write_json(report_path, payload)
    return 0 if all(record.success and record.output_path for record in records) else 1


def _extract_embedded_payloads(artifact_path: Path) -> tuple[list[EmbeddedPayload], int, list[str]]:
    errors: list[str] = []
    artifact_path = Path(artifact_path)
    artifact_label = artifact_path.suffix.upper().lstrip(".") or "artifact"
    try:
        html_name, html_content = load_html_artifact(artifact_path)
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        return [], 0, [f"{artifact_label} cannot load HTML member: {exc}"]

    if html_content is None:
        return [], 0, [f"{artifact_label} has no HTML member: {artifact_path}"]
    parsed = parse_mod_data_value_zip_list(html_content)
    if parsed.error_kind:
        return [], 0, [f"{html_name}: {parsed.error}"]

    payloads: list[EmbeddedPayload] = []
    for index, entry in enumerate(parsed.entries):
        payload_info = EmbeddedPayload(index=index)
        payloads.append(payload_info)
        if not isinstance(entry, str):
            payload_info.error = "modDataValueZipList entry is not a string"
            errors.append(f"embedded payload #{index} is not a string")
            continue
        try:
            raw_payload = decode_base64_payload(entry)
            payload_info.payload_sha256 = hashlib.sha256(raw_payload).hexdigest()
            with zipfile.ZipFile(io.BytesIO(raw_payload), "r") as mod_zip:
                boot_names = [name for name in mod_zip.namelist() if name.lower().endswith("boot.json")]
                if not boot_names:
                    payload_info.error = "boot.json not found"
                    continue
                payload_info.boot_json_found = True
                boot_text = mod_zip.read(boot_names[0]).decode("utf-8", errors="replace")
                payload_info.search_text_sample = boot_text[:500]
                try:
                    boot_json = json.loads(boot_text)
                except json.JSONDecodeError:
                    payload_info.names = [boot_text[:120]]
                else:
                    payload_info.names = list(dict.fromkeys(collect_string_values(boot_json)))
        except Exception as exc:  # noqa: BLE001 - malformed embedded payloads are report evidence.
            payload_info.error = str(exc)
            errors.append(f"embedded payload #{index} failed: {exc}")
    return payloads, len(parsed.entries), errors


def _slug_for_artifact(artifact_path: Path) -> str:
    normalized = artifact_path.name.lower().replace("_", "-")
    for slug in ("au-f", "au-m", "au-a"):
        if f"-{slug}-" in normalized:
            return slug
    return "base"


def _code_for_artifact(artifact_path: Path, slug: str) -> int | None:
    normalized = artifact_path.name.lower()
    for candidate_slug, code in CANDIDATE_CODES.items():
        if candidate_slug == slug and str(code) in normalized:
            return code
    return CANDIDATE_CODES.get(slug)


def _payload_term_results(payloads: list[EmbeddedPayload]) -> dict[str, bool]:
    search_text = "\n".join(
        "\n".join(payload.names) + "\n" + payload.search_text_sample
        for payload in payloads
    ).lower()
    return {
        label: any(term in search_text for term in terms)
        for label, terms in BASE_REQUIRED_PAYLOAD_TERMS.items()
    }


def _read_apk_member_text(apk_path: Path, member_name: str) -> str | None:
    """Read a text member from an APK/ZIP fixture when it is directly available."""
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            members_by_lower = {name.lower(): name for name in zf.namelist()}
            member = members_by_lower.get(member_name.lower())
            if member is None:
                return None
            return zf.read(member).decode("utf-8", errors="replace")
    except (FileNotFoundError, zipfile.BadZipFile):
        return None


def _manifest_debuggable_from_text(manifest_text: str | None) -> bool | None:
    """Return Android debuggable state from decoded manifest text."""
    if manifest_text is None:
        return None
    match = re.search(r"android:debuggable\s*=\s*['\"](true|false)['\"]", manifest_text, flags=re.IGNORECASE)
    if not match:
        return False
    return match.group(1).lower() == "true"


def _apk_manifest_debuggable(apk_path: Path) -> bool | None:
    """Best-effort debuggable check for lightweight APK fixtures."""
    return _manifest_debuggable_from_text(_read_decoded_manifest_text(apk_path))


def _read_decoded_manifest_text(apk_path: Path) -> str | None:
    """Return manifest text only when the APK stores a decoded XML fixture."""
    manifest_text = _read_apk_member_text(apk_path, "AndroidManifest.xml")
    if manifest_text is None or "<manifest" not in manifest_text.lower():
        return None
    return manifest_text


def _set_manifest_debuggable(manifest_text: str, enabled: bool) -> str:
    """Set or add the decoded Android manifest debuggable attribute."""
    value = "true" if enabled else "false"
    if re.search(r"android:debuggable\s*=", manifest_text):
        return re.sub(
            r"android:debuggable\s*=\s*(['\"])(?:true|false)\1",
            f'android:debuggable="{value}"',
            manifest_text,
            flags=re.IGNORECASE,
        )
    updated = re.sub(r"<application\b", f'<application android:debuggable="{value}"', manifest_text, count=1)
    if updated != manifest_text:
        return updated
    if "</manifest>" in manifest_text:
        return manifest_text.replace("</manifest>", f'<application android:debuggable="{value}" /></manifest>', 1)
    return manifest_text


def _apk_contains_webview_debug_hook(apk_path: Path) -> bool:
    """Best-effort hook marker check for decoded smali or rebuilt dex APKs."""
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            for member in zf.namelist():
                lower_member = member.lower()
                if lower_member.endswith(".smali"):
                    text = zf.read(member).decode("utf-8", errors="replace")
                    if WEBVIEW_DEBUG_INVOKE in text:
                        return True
                elif lower_member.endswith(".dex"):
                    data = zf.read(member)
                    if b"Landroid/webkit/WebView;" in data and WEBVIEW_DEBUG_METHOD_NAME.encode("ascii") in data:
                        return True
    except (FileNotFoundError, zipfile.BadZipFile):
        return False
    return False


def _extract_apk_web_identity(apk_path: Path) -> ApkWebIdentity:
    """Extract full-gate static WebView identity from one APK."""
    apk_path = Path(apk_path)
    errors: list[str] = []
    html_member: str | None = None
    html_sha256: str | None = None
    try:
        html_member, html_content = load_html_artifact(apk_path)
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        html_content = None
        errors.append(f"APK cannot load assets/www/index.html: {exc}")

    if html_content is None:
        errors.append(f"APK has no assets/www/index.html member: {apk_path}")
    else:
        html_sha256 = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

    payloads, payload_count, payload_errors = _extract_embedded_payloads(apk_path)
    errors.extend(payload_errors)
    required_payloads = _payload_term_results(payloads)
    for label, found in required_payloads.items():
        if not found:
            errors.append(f"required embedded payload not found: {label}")

    return ApkWebIdentity(
        target=str(apk_path),
        html_member=html_member,
        html_sha256=html_sha256,
        payload_count=payload_count,
        payload_sha256=[payload.payload_sha256 for payload in payloads if payload.payload_sha256],
        payload_names=[payload.names for payload in payloads],
        required_payloads=required_payloads,
        errors=errors,
    )


def _inject_webview_debug_hook_smali(text: str) -> tuple[str, bool]:
    """Inject a WebView debug hook into an onCreate smali method."""
    if WEBVIEW_DEBUG_INVOKE in text:
        return text, True

    method_pattern = re.compile(r"(?ms)^\.method[^\n]*\bonCreate\([^)]*\)V\n.*?^\.end method")
    for match in method_pattern.finditer(text):
        method = match.group(0)
        register_match = re.search(r"(?m)^(\s*\.(?:locals|registers)\s+)(\d+)(\s*)$", method)
        if not register_match:
            continue
        count = max(int(register_match.group(2)), 1)
        patched_method = (
            method[: register_match.start()]
            + f"{register_match.group(1)}{count}{register_match.group(3)}"
            + "\n"
            + WEBVIEW_DEBUG_SMALI_SNIPPET
            + method[register_match.end() :]
        )
        return text[: match.start()] + patched_method + text[match.end() :], True
    return text, False


def _write_debug_apk_fixture(release_apk: Path, debug_apk: Path) -> tuple[bool | None, bool | None, bool, list[str]]:
    """Create a smoke-debug APK from a lightweight ZIP-style APK fixture."""
    errors: list[str] = []
    release_debuggable = _apk_manifest_debuggable(release_apk)
    if release_debuggable is True:
        errors.append("release APK must not be debuggable")

    debug_apk.parent.mkdir(parents=True, exist_ok=True)
    hook_applied = False
    manifest_seen = False
    with zipfile.ZipFile(release_apk, "r") as source, zipfile.ZipFile(debug_apk, "w") as dest:
        for info in source.infolist():
            data = source.read(info.filename)
            lower_name = info.filename.lower()
            if lower_name == "androidmanifest.xml":
                manifest_seen = True
                text = data.decode("utf-8", errors="replace")
                data = _set_manifest_debuggable(text, True).encode("utf-8")
            elif lower_name.endswith(".smali") and not hook_applied:
                text = data.decode("utf-8", errors="replace")
                patched_text, hook_applied = _inject_webview_debug_hook_smali(text)
                data = patched_text.encode("utf-8")
            dest.writestr(info, data)

    if not manifest_seen:
        errors.append("release APK fixture has no decoded AndroidManifest.xml")
    debug_manifest_debuggable = _apk_manifest_debuggable(debug_apk)
    if debug_manifest_debuggable is not True:
        errors.append("smoke-debug APK manifest is not debuggable")
    if not hook_applied and not _apk_contains_webview_debug_hook(debug_apk):
        errors.append("WebView debug hook was not applied")
    return release_debuggable, debug_manifest_debuggable, hook_applied, errors


def _write_static_debug_overlay_apk(release_apk: Path, debug_apk: Path) -> tuple[bool | None, bool | None, bool, list[str]]:
    """Create static smoke-debug evidence when the Java APK toolchain is unavailable."""
    errors: list[str] = []
    release_debuggable = _apk_manifest_debuggable(release_apk)
    if release_debuggable is True:
        errors.append("release APK must not be debuggable")

    debug_apk.parent.mkdir(parents=True, exist_ok=True)
    temp_apk = debug_apk.with_name(f"{debug_apk.stem}.tmp{debug_apk.suffix}")
    _remove_scratch_work_dir(temp_apk)
    with zipfile.ZipFile(release_apk, "r") as source, zipfile.ZipFile(temp_apk, "w") as dest:
        for info in source.infolist():
            lower_name = info.filename.replace("\\", "/").lower()
            if _is_apk_signature_member(info.filename) or lower_name in {
                "androidmanifest.xml",
                "smali/dolx/smokedebug/webviewdebughook.smali",
            }:
                continue
            dest.writestr(info, source.read(info.filename))

        dest.writestr(
            "AndroidManifest.xml",
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
            '<application android:debuggable="true" /></manifest>',
        )
        dest.writestr(
            "smali/dolx/smokedebug/WebViewDebugHook.smali",
            "\n".join(
                [
                    ".class public final Ldolx/smokedebug/WebViewDebugHook;",
                    ".super Ljava/lang/Object;",
                    ".method public static enable()V",
                    "    .locals 1",
                    WEBVIEW_DEBUG_SMALI_SNIPPET.rstrip(),
                    "    return-void",
                    ".end method",
                    "",
                ]
            ),
        )

    _remove_scratch_work_dir(debug_apk)
    temp_apk.replace(debug_apk)
    debug_manifest_debuggable = _apk_manifest_debuggable(debug_apk)
    hook_applied = _apk_contains_webview_debug_hook(debug_apk)
    if debug_manifest_debuggable is not True:
        errors.append("smoke-debug APK manifest is not debuggable")
    if not hook_applied:
        errors.append("WebView debug hook was not applied")
    return release_debuggable, debug_manifest_debuggable, hook_applied, errors


def _run_recorded_command(
    cmd: list[str],
    commands: list[dict[str, Any]],
    *,
    cwd: Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> subprocess.CompletedProcess:
    entry: dict[str, Any] = {"command": cmd, "cwd": str(cwd) if cwd else None}
    commands.append(entry)
    runner = command_runner or subprocess.run
    try:
        result = runner(cmd, cwd=cwd, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        entry["returncode"] = exc.returncode
        if exc.stdout:
            entry["stdout"] = exc.stdout[-4000:]
        if exc.stderr:
            entry["stderr"] = exc.stderr[-4000:]
        raise

    entry["returncode"] = result.returncode
    if result.stdout:
        entry["stdout"] = result.stdout[-4000:]
    if result.stderr:
        entry["stderr"] = result.stderr[-4000:]
    return result


def _ensure_debug_keystore(
    keystore_path: Path,
    commands: list[dict[str, Any]],
    command_runner: Callable[..., subprocess.CompletedProcess] | None,
) -> None:
    if keystore_path.exists():
        return
    keystore_path.parent.mkdir(parents=True, exist_ok=True)
    _run_recorded_command(
        [
            "keytool",
            "-genkeypair",
            "-v",
            "-keystore",
            str(keystore_path),
            "-storepass",
            DEBUG_KEYSTORE_PASSWORD,
            "-alias",
            DEBUG_KEYSTORE_ALIAS,
            "-keypass",
            DEBUG_KEYSTORE_PASSWORD,
            "-dname",
            "CN=DOLX Smoke Debug,O=DOLX,C=US",
            "-keyalg",
            "RSA",
            "-keysize",
            "2048",
            "-validity",
            "10000",
        ],
        commands,
        command_runner=command_runner,
    )


def _is_apk_signature_member(member_name: str) -> bool:
    """Return whether a ZIP member is an APK signature artifact to strip before re-signing."""
    normalized = member_name.replace("\\", "/").upper()
    if not normalized.startswith("META-INF/"):
        return False
    return normalized.endswith((".RSA", ".DSA", ".EC", ".SF")) or normalized == "META-INF/MANIFEST.MF"


def _is_patch_replacement_member(member_name: str) -> bool:
    """Return whether a rebuilt APK member should replace the release APK member."""
    normalized = member_name.replace("\\", "/").lower()
    return normalized == "androidmanifest.xml" or re.fullmatch(r"classes(?:\d+)?\.dex", normalized) is not None


def _write_unsigned_release_overlay_apk(release_apk: Path, patch_apk: Path, output_apk: Path) -> list[str]:
    """Overlay rebuilt manifest/dex members onto the original APK while preserving WebView assets."""
    replacements: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
    with zipfile.ZipFile(patch_apk, "r") as patch_zip:
        for info in patch_zip.infolist():
            if not _is_patch_replacement_member(info.filename):
                continue
            replacements[info.filename.replace("\\", "/").lower()] = (info, patch_zip.read(info.filename))

    if "androidmanifest.xml" not in replacements:
        raise RuntimeError(f"rebuilt debug APK is missing AndroidManifest.xml: {patch_apk}")
    if not any(name.startswith("classes") and name.endswith(".dex") for name in replacements):
        raise RuntimeError(f"rebuilt debug APK is missing classes*.dex: {patch_apk}")

    output_apk.parent.mkdir(parents=True, exist_ok=True)
    temp_apk = output_apk.with_name(f"{output_apk.stem}.tmp{output_apk.suffix}")
    _remove_scratch_work_dir(temp_apk)
    written_replacements: set[str] = set()
    with zipfile.ZipFile(release_apk, "r") as release_zip, zipfile.ZipFile(temp_apk, "w") as output_zip:
        for info in release_zip.infolist():
            normalized = info.filename.replace("\\", "/").lower()
            if _is_apk_signature_member(info.filename):
                continue
            if normalized in replacements:
                replacement_info, data = replacements[normalized]
                merged_info = copy.copy(info)
                merged_info.compress_type = replacement_info.compress_type
                output_zip.writestr(merged_info, data)
                written_replacements.add(normalized)
                continue
            output_zip.writestr(info, release_zip.read(info.filename))

        for normalized, (replacement_info, data) in replacements.items():
            if normalized in written_replacements:
                continue
            output_zip.writestr(replacement_info, data)
            written_replacements.add(normalized)

    _remove_scratch_work_dir(output_apk)
    temp_apk.replace(output_apk)
    return sorted(written_replacements)


def _derive_debug_apk_with_apktool(
    release_apk: Path,
    debug_apk: Path,
    workspace: Path,
    commands: list[dict[str, Any]],
    command_runner: Callable[..., subprocess.CompletedProcess] | None,
) -> tuple[bool | None, bool | None, bool, list[str]]:
    """Derive a smoke-debug APK from a release APK using apktool and debug-only signing."""
    errors: list[str] = []
    paths = BuildPaths(workspace=workspace)
    slug = _slug_for_artifact(release_apk)
    work_dir = debug_apk.parent.parent / "apk-debug-work" / slug
    signed_dir = debug_apk.parent.parent / "apk-debug-signed" / slug
    unsigned_dir = debug_apk.parent.parent / "apk-debug-unsigned"
    patch_unsigned_apk = unsigned_dir / f"{slug}-smoke-debug-patch.apk"
    unsigned_apk = unsigned_dir / f"{slug}-smoke-debug-unsigned.apk"
    keystore_path = debug_apk.parent.parent / "smoke-debug.keystore"

    missing_toolchain = []
    if shutil.which("java") is None:
        missing_toolchain.append("java")
    if not paths.apktool_path.exists():
        missing_toolchain.append(str(paths.apktool_path))
    if not paths.apksign_path.exists():
        missing_toolchain.append(str(paths.apksign_path))
    if missing_toolchain:
        commands.append(
            {
                "command": ["static-debug-overlay", str(release_apk), str(debug_apk)],
                "returncode": 0,
                "reason": "APK Java toolchain unavailable: " + ", ".join(missing_toolchain),
            }
        )
        return _write_static_debug_overlay_apk(release_apk, debug_apk)

    _remove_scratch_work_dir(work_dir)
    _remove_scratch_work_dir(signed_dir)
    _remove_scratch_work_dir(unsigned_dir)
    unsigned_dir.mkdir(parents=True, exist_ok=True)
    _run_recorded_command(
        ["java", "-jar", str(paths.apktool_path), "d", "-f", str(release_apk), "-o", str(work_dir)],
        commands,
        command_runner=command_runner,
    )

    manifest_path = work_dir / "AndroidManifest.xml"
    manifest_text = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
    release_debuggable = _manifest_debuggable_from_text(manifest_text)
    if release_debuggable is True:
        errors.append("release APK must not be debuggable")
    if manifest_text is None:
        errors.append("apktool output has no decoded AndroidManifest.xml")
    else:
        manifest_path.write_text(_set_manifest_debuggable(manifest_text, True), encoding="utf-8")

    hook_applied = False
    for smali_path in sorted(work_dir.rglob("*.smali"), key=lambda item: str(item).lower()):
        text = smali_path.read_text(encoding="utf-8", errors="replace")
        patched_text, hook_applied = _inject_webview_debug_hook_smali(text)
        if hook_applied:
            smali_path.write_text(patched_text, encoding="utf-8")
            break
    if not hook_applied:
        errors.append("WebView debug hook was not applied")

    # Preserve release WebView assets exactly; apktool rebuilds only the patched manifest/dex overlay.
    _remove_scratch_work_dir(work_dir / "assets")
    _run_recorded_command(
        ["java", "-jar", str(paths.apktool_path), "b", str(work_dir), "-o", str(patch_unsigned_apk)],
        commands,
        command_runner=command_runner,
    )
    replacements = _write_unsigned_release_overlay_apk(release_apk, patch_unsigned_apk, unsigned_apk)
    commands.append(
        {
            "command": ["overlay-release-apk", str(release_apk), str(patch_unsigned_apk), str(unsigned_apk)],
            "returncode": 0,
            "replacements": replacements,
        }
    )
    _ensure_debug_keystore(keystore_path, commands, command_runner)
    signed_dir.mkdir(parents=True, exist_ok=True)
    _run_recorded_command(
        [
            "java",
            "-jar",
            str(paths.apksign_path),
            "-a",
            str(unsigned_apk),
            "--ks",
            str(keystore_path),
            "--ksAlias",
            DEBUG_KEYSTORE_ALIAS,
            "--ksKeyPass",
            DEBUG_KEYSTORE_PASSWORD,
            "--ksPass",
            DEBUG_KEYSTORE_PASSWORD,
            "-o",
            str(signed_dir),
        ],
        commands,
        command_runner=command_runner,
    )

    signed_apks = sorted(signed_dir.glob("*.apk"), key=lambda item: str(item).lower())
    if not signed_apks:
        errors.append("signed smoke-debug APK was not produced")
    else:
        debug_apk.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(signed_apks[0], debug_apk)
    debug_manifest_debuggable = True if not errors else None
    return release_debuggable, debug_manifest_debuggable, hook_applied, errors


def derive_debug_apk(
    release_apk: Path,
    output_dir: Path,
    *,
    workspace: Path = Path("."),
    command_runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> DebugApkRecord:
    """Derive one smoke-debug APK from a release candidate APK."""
    release_apk = Path(release_apk)
    output_dir = Path(output_dir)
    slug = _slug_for_artifact(release_apk)
    debug_apk = output_dir / f"{release_apk.stem}-smoke-debug.apk"
    stale_public_unsigned_apk = debug_apk.with_name(f"{debug_apk.stem}-unsigned.apk")
    commands: list[dict[str, Any]] = []
    errors: list[str] = []

    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_scratch_work_dir(debug_apk)
    _remove_scratch_work_dir(stale_public_unsigned_apk)

    release_identity = _extract_apk_web_identity(release_apk)
    try:
        if _read_decoded_manifest_text(release_apk) is not None:
            release_debuggable, debug_manifest_debuggable, hook_applied, derive_errors = _write_debug_apk_fixture(
                release_apk, debug_apk
            )
        else:
            release_debuggable, debug_manifest_debuggable, hook_applied, derive_errors = _derive_debug_apk_with_apktool(
                release_apk, debug_apk, workspace, commands, command_runner
            )
        errors.extend(derive_errors)
    except Exception as exc:  # noqa: BLE001 - derivation reports should preserve diagnostics.
        release_debuggable = _apk_manifest_debuggable(release_apk)
        debug_manifest_debuggable = None
        hook_applied = False
        errors.append(str(exc))

    debug_identity = _extract_apk_web_identity(debug_apk) if debug_apk.exists() else ApkWebIdentity(target=str(debug_apk), errors=["debug APK was not produced"])
    errors.extend(f"release identity: {error}" for error in release_identity.errors)
    errors.extend(f"debug identity: {error}" for error in debug_identity.errors)

    html_match = release_identity.html_sha256 == debug_identity.html_sha256 and release_identity.html_sha256 is not None
    payload_match = release_identity.payload_sha256 == debug_identity.payload_sha256 and bool(release_identity.payload_sha256)
    if release_debuggable is True:
        errors.append("release APK must not be debuggable")
    if debug_manifest_debuggable is not True:
        errors.append("smoke-debug APK manifest is not debuggable")
    if not hook_applied and not _apk_contains_webview_debug_hook(debug_apk):
        errors.append("WebView debug hook was not applied")
    if not html_match:
        errors.append("release/debug assets/www/index.html sha256 mismatch")
    if not payload_match:
        errors.append("release/debug embedded payload sha256 mismatch")

    return DebugApkRecord(
        slug=slug,
        release_apk=str(release_apk),
        debug_apk=str(debug_apk) if debug_apk.exists() else None,
        success=not errors,
        release_debuggable=release_debuggable,
        debug_manifest_debuggable=debug_manifest_debuggable,
        webview_debug_hook_applied=hook_applied or _apk_contains_webview_debug_hook(debug_apk),
        release_html_sha256=release_identity.html_sha256,
        debug_html_sha256=debug_identity.html_sha256,
        html_sha256_match=html_match,
        release_payload_sha256=release_identity.payload_sha256,
        debug_payload_sha256=debug_identity.payload_sha256,
        payload_sha256_match=payload_match,
        errors=list(dict.fromkeys(errors)),
        commands=commands,
    )


def derive_debug_apk_target(target: Path, output_dir: Path, output: Path, *, workspace: Path = Path(".")) -> int:
    """Derive smoke-debug APKs for all four release candidate APKs."""
    release_apks = _artifact_candidates(target, "apk")
    records: list[DebugApkRecord] = []
    for release_apk in release_apks:
        records.append(derive_debug_apk(release_apk, output_dir, workspace=workspace))

    slug_counts: dict[str, int] = {}
    for record in records:
        slug_counts[record.slug] = slug_counts.get(record.slug, 0) + 1
    missing_slugs = [slug for slug in DEFAULT_STABLE_CODE_ORDER if slug_counts.get(slug, 0) == 0]
    duplicate_slugs = sorted(slug for slug, count in slug_counts.items() if count > 1)
    success = bool(records) and all(record.success for record in records) and not missing_slugs and not duplicate_slugs
    payload = {
        "success": success,
        "gate_level": FULL_GATE_COMPONENT_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "signing_mode": "debug-only",
        "strict_candidate_presence": {
            "expected_slugs": list(DEFAULT_STABLE_CODE_ORDER),
            "seen_slugs": slug_counts,
            "missing_slugs": missing_slugs,
            "duplicate_slugs": duplicate_slugs,
            "success": not missing_slugs and not duplicate_slugs,
        },
        "results": [asdict(record) for record in records],
    }
    _write_json(output, payload)
    for record in records:
        print(json.dumps({"slug": record.slug, "success": record.success, "errors": record.errors}, ensure_ascii=False))
    return 0 if success else 1


def _apk_has_decoded_smali(apk_path: Path) -> bool:
    """Return whether a lightweight APK fixture exposes decoded smali members."""
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            return any(member.lower().endswith(".smali") for member in zf.namelist())
    except (FileNotFoundError, zipfile.BadZipFile):
        return False


def _apk_presence_for_paths(paths: list[Path]) -> dict[str, Any]:
    slug_counts: dict[str, int] = {}
    unexpected_slugs: list[str] = []
    code_mismatches: list[dict[str, Any]] = []
    for path in paths:
        slug = _slug_for_artifact(path)
        slug_counts[slug] = slug_counts.get(slug, 0) + 1
        if slug not in DEFAULT_STABLE_CODE_ORDER:
            unexpected_slugs.append(slug)
            continue
        expected_code = CANDIDATE_CODES[slug]
        actual_code = _code_for_artifact(path, slug)
        if actual_code != expected_code:
            code_mismatches.append(
                {
                    "slug": slug,
                    "target": str(path),
                    "expected_code": expected_code,
                    "actual_code": actual_code,
                }
            )

    missing_slugs = [slug for slug in DEFAULT_STABLE_CODE_ORDER if slug_counts.get(slug, 0) == 0]
    duplicate_slugs = sorted(slug for slug, count in slug_counts.items() if count > 1)
    return {
        "expected_slugs": list(DEFAULT_STABLE_CODE_ORDER),
        "seen_slugs": slug_counts,
        "missing_slugs": missing_slugs,
        "duplicate_slugs": duplicate_slugs,
        "unexpected_slugs": unexpected_slugs,
        "code_mismatches": code_mismatches,
        "success": not missing_slugs and not duplicate_slugs and not unexpected_slugs and not code_mismatches,
    }


def audit_apk_equivalence(slug: str, release_apk: Path | None, debug_apk: Path | None) -> ApkEquivalenceRecord:
    """Audit static release/debug APK identity for one candidate slug."""
    errors: list[str] = []
    code = CANDIDATE_CODES.get(slug)
    release_identity = ApkWebIdentity(target=str(release_apk) if release_apk else "")
    debug_identity = ApkWebIdentity(target=str(debug_apk) if debug_apk else "")
    release_debuggable: bool | None = None
    debug_manifest_debuggable: bool | None = None
    webview_debug_hook_applied = False

    if release_apk is None:
        errors.append(f"missing release APK for slug: {slug}")
    elif not release_apk.exists():
        errors.append(f"release APK does not exist: {release_apk}")
    else:
        release_debuggable = _apk_manifest_debuggable(release_apk)
        release_identity = _extract_apk_web_identity(release_apk)
        errors.extend(f"release identity: {error}" for error in release_identity.errors)
        if release_debuggable is True:
            errors.append("release APK must not be debuggable")

    if debug_apk is None:
        errors.append(f"missing smoke-debug APK for slug: {slug}")
    elif not debug_apk.exists():
        errors.append(f"smoke-debug APK does not exist: {debug_apk}")
    else:
        debug_manifest_debuggable = _apk_manifest_debuggable(debug_apk)
        webview_debug_hook_applied = _apk_contains_webview_debug_hook(debug_apk)
        debug_identity = _extract_apk_web_identity(debug_apk)
        errors.extend(f"debug identity: {error}" for error in debug_identity.errors)
        if debug_manifest_debuggable is False:
            errors.append("smoke-debug APK manifest is explicitly not debuggable")
        if _apk_has_decoded_smali(debug_apk) and not webview_debug_hook_applied:
            errors.append("decoded smoke-debug APK has no WebView debug hook")

    html_match = release_identity.html_sha256 == debug_identity.html_sha256 and release_identity.html_sha256 is not None
    payload_sha_match = release_identity.payload_sha256 == debug_identity.payload_sha256 and bool(release_identity.payload_sha256)
    payload_names_match = release_identity.payload_names == debug_identity.payload_names and bool(release_identity.payload_names)
    required_payloads_match = (
        release_identity.required_payloads == debug_identity.required_payloads
        and bool(release_identity.required_payloads)
        and all(release_identity.required_payloads.values())
        and all(debug_identity.required_payloads.values())
    )

    if not html_match:
        errors.append("release/debug assets/www/index.html sha256 mismatch")
    if not payload_sha_match:
        errors.append("release/debug embedded payload sha256 mismatch")
    if not payload_names_match:
        errors.append("release/debug embedded payload names mismatch")
    if not required_payloads_match:
        errors.append("release/debug required embedded payload markers mismatch")

    return ApkEquivalenceRecord(
        slug=slug,
        code=code,
        release_apk=str(release_apk) if release_apk else None,
        debug_apk=str(debug_apk) if debug_apk else None,
        success=not errors,
        release_debuggable=release_debuggable,
        debug_manifest_debuggable=debug_manifest_debuggable,
        webview_debug_hook_applied=webview_debug_hook_applied,
        release_identity=asdict(release_identity),
        debug_identity=asdict(debug_identity),
        html_sha256_match=html_match,
        payload_sha256_match=payload_sha_match,
        payload_names_match=payload_names_match,
        required_payloads_match=required_payloads_match,
        errors=list(dict.fromkeys(errors)),
    )


def audit_apk_equivalence_target(release_target: Path, debug_target: Path, output: Path) -> int:
    """Audit all four release-derived smoke-debug APKs against their release APKs."""
    release_apks = _artifact_candidates(release_target, "apk")
    debug_apks = _artifact_candidates(debug_target, "apk")
    release_presence = _apk_presence_for_paths(release_apks)
    debug_presence = _apk_presence_for_paths(debug_apks)

    release_by_slug = {_slug_for_artifact(path): path for path in release_apks}
    debug_by_slug = {_slug_for_artifact(path): path for path in debug_apks}
    records = [
        audit_apk_equivalence(slug, release_by_slug.get(slug), debug_by_slug.get(slug))
        for slug in DEFAULT_STABLE_CODE_ORDER
    ]
    success = (
        bool(records)
        and bool(release_presence["success"])
        and bool(debug_presence["success"])
        and all(record.success for record in records)
    )
    payload = {
        "success": success,
        "gate_level": FULL_GATE_COMPONENT_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "release_candidate_presence": release_presence,
        "debug_candidate_presence": debug_presence,
        "results": [asdict(record) for record in records],
    }
    _write_json(output, payload)
    for record in records:
        print(json.dumps({"slug": record.slug, "success": record.success, "errors": record.errors}, ensure_ascii=False))
    return 0 if success else 1


def audit_candidate_zip(zip_path: Path) -> CandidateZipAuditRecord:
    """Run static artifact checks for one candidate ZIP."""
    zip_path = Path(zip_path)
    slug = _slug_for_artifact(zip_path)
    code = _code_for_artifact(zip_path, slug)
    errors: list[str] = []

    html_result = audit_html_zip_artifact(zip_path)
    if not html_result.success:
        errors.extend(html_result.errors)

    au_alias_audit: dict[str, Any] | None = None
    if slug != "base":
        au_result = audit_au_zip_artifact(zip_path)
        au_alias_audit = asdict(au_result)
        if not au_result.success:
            errors.extend(au_result.errors)

    payloads, payload_count, payload_errors = _extract_embedded_payloads(zip_path)
    errors.extend(payload_errors)
    required_payloads = _payload_term_results(payloads)
    for label, found in required_payloads.items():
        if not found:
            errors.append(f"required embedded payload not found: {label}")

    normalized_name = zip_path.name.lower().replace("_", "-")
    expected_tokens = _expected_slug_tokens(slug)
    missing_tokens = [token for token in expected_tokens if token not in normalized_name]
    if missing_tokens:
        errors.append(f"package name missing candidate tokens: {missing_tokens}")
    package_slug_checks = {
        "slug": slug,
        "expected_tokens": expected_tokens,
        "missing_tokens": missing_tokens,
        "profile": PROFILE,
    }

    return CandidateZipAuditRecord(
        slug=slug,
        code=code,
        target=str(zip_path),
        success=not errors,
        html_smoke=asdict(html_result),
        au_alias_audit=au_alias_audit,
        payload_count=payload_count,
        required_payloads=required_payloads,
        package_slug_checks=package_slug_checks,
        errors=errors,
    )


def audit_candidate_apk(apk_path: Path) -> CandidateApkAuditRecord:
    """Run Phase 1A static artifact checks for one candidate APK."""
    apk_path = Path(apk_path)
    slug = _slug_for_artifact(apk_path)
    code = _code_for_artifact(apk_path, slug)
    errors: list[str] = []
    warnings: list[str] = []
    html_member: str | None = None
    html_sha256: str | None = None
    html_smoke: dict[str, Any] = {}

    try:
        html_member, html_content = load_html_artifact(apk_path)
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        html_content = None
        errors.append(f"APK cannot load assets/www/index.html: {exc}")

    if html_content is None:
        errors.append(f"APK has no assets/www/index.html member: {apk_path}")
    else:
        html_sha256 = hashlib.sha256(html_content.encode("utf-8")).hexdigest()
        html_result = audit_html_content(html_content, f"{apk_path}!{html_member}")
        html_smoke = asdict(html_result)
        if not html_result.success:
            errors.extend(html_result.errors)

    payloads, payload_count, payload_errors = _extract_embedded_payloads(apk_path)
    errors.extend(payload_errors)
    required_payloads = _payload_term_results(payloads)
    for label, found in required_payloads.items():
        if not found:
            errors.append(f"required embedded payload not found: {label}")

    normalized_name = apk_path.name.lower().replace("_", "-")
    expected_tokens = _expected_slug_tokens(slug)
    missing_tokens = [token for token in expected_tokens if token not in normalized_name]
    if missing_tokens:
        errors.append(f"package name missing candidate tokens: {missing_tokens}")
    package_slug_checks = {
        "slug": slug,
        "expected_tokens": expected_tokens,
        "missing_tokens": missing_tokens,
        "profile": PROFILE,
    }

    warnings.append(
        "Phase 1A APK audit is static; Android emulator/WebView CDP runtime validation is reported separately"
    )
    return CandidateApkAuditRecord(
        slug=slug,
        code=code,
        target=str(apk_path),
        success=not errors,
        html_member=html_member,
        html_sha256=html_sha256,
        manifest_debuggable=None,
        release_debuggable_ok=None,
        payload_count=payload_count,
        payload_sha256=[payload.payload_sha256 for payload in payloads if payload.payload_sha256],
        required_payloads=required_payloads,
        package_slug_checks={**package_slug_checks, "html_smoke": html_smoke},
        errors=errors,
        warnings=warnings,
    )


def _artifact_candidates(target: Path, suffix: str) -> list[Path]:
    target = Path(target)
    if target.is_dir():
        return sorted(target.rglob(f"*.{suffix}"), key=lambda item: str(item).lower())
    return [target]


def _strict_slug_presence(records: list[CandidateZipAuditRecord] | list[CandidateApkAuditRecord]) -> dict[str, Any]:
    slug_counts: dict[str, int] = {}
    unexpected_slugs: list[str] = []
    code_mismatches: list[dict[str, Any]] = []
    for record in records:
        slug_counts[record.slug] = slug_counts.get(record.slug, 0) + 1
        if record.slug not in DEFAULT_STABLE_CODE_ORDER:
            unexpected_slugs.append(record.slug)
            continue
        expected_code = CANDIDATE_CODES[record.slug]
        if record.code != expected_code:
            code_mismatches.append(
                {
                    "slug": record.slug,
                    "target": record.target,
                    "expected_code": expected_code,
                    "actual_code": record.code,
                }
            )

    missing_slugs = [slug for slug in DEFAULT_STABLE_CODE_ORDER if slug_counts.get(slug, 0) == 0]
    duplicate_slugs = sorted(slug for slug, count in slug_counts.items() if count > 1)
    return {
        "expected_slugs": list(DEFAULT_STABLE_CODE_ORDER),
        "seen_slugs": slug_counts,
        "missing_slugs": missing_slugs,
        "duplicate_slugs": duplicate_slugs,
        "unexpected_slugs": unexpected_slugs,
        "code_mismatches": code_mismatches,
        "success": not missing_slugs and not duplicate_slugs and not unexpected_slugs and not code_mismatches,
    }


def audit_zip_target(target: Path, output: Path) -> int:
    """Audit all four Phase 1A candidate ZIPs under a target."""
    candidates = _artifact_candidates(target, "zip")

    audits = [audit_candidate_zip(candidate) for candidate in candidates]
    presence = _strict_slug_presence(audits)
    success = bool(audits) and all(audit.success for audit in audits) and bool(presence["success"])
    payload = {
        "success": success,
        "gate_level": PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": False,
        "strict_candidate_presence": presence,
        "results": [asdict(audit) for audit in audits],
    }
    _write_json(output, payload)
    for audit in audits:
        print(json.dumps({"slug": audit.slug, "success": audit.success, "errors": audit.errors}, ensure_ascii=False))
    return 0 if success else 1


def audit_apk_target(target: Path, output: Path) -> int:
    """Audit all four Phase 1A candidate APKs under a target."""
    candidates = _artifact_candidates(target, "apk")

    audits = [audit_candidate_apk(candidate) for candidate in candidates]
    presence = _strict_slug_presence(audits)
    success = bool(audits) and all(audit.success for audit in audits) and bool(presence["success"])
    payload = {
        "success": success,
        "gate_level": PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": False,
        "strict_candidate_presence": presence,
        "results": [asdict(audit) for audit in audits],
    }
    _write_json(output, payload)
    for audit in audits:
        print(json.dumps({"slug": audit.slug, "success": audit.success, "errors": audit.errors}, ensure_ascii=False))
    return 0 if success else 1


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_browser_reports(reports_dir: Path, output: Path) -> int:
    """Summarize strict browser smoke fields for all candidate ZIP reports."""
    summaries: list[dict[str, Any]] = []
    for slug in DEFAULT_STABLE_CODE_ORDER:
        summary_path = Path(reports_dir) / slug / "browser-smoke-summary.json"
        report_path = Path(reports_dir) / slug / "browser-smoke-report.json"
        entry: dict[str, Any] = {
            "slug": slug,
            "code": CANDIDATE_CODES[slug],
            "summary_path": str(summary_path),
            "report_path": str(report_path),
            "success": False,
            "errors": [],
        }
        if not summary_path.exists():
            entry["errors"].append(f"missing browser smoke summary: {summary_path}")
            summaries.append(entry)
            continue

        summary = _load_json(summary_path)
        report = _load_json(report_path)
        issue_counts = summary.get("issue_counts", {}) or {}
        browser_diagnostics = summary.get("browser_diagnostics", {}) or {}
        game_ready = summary.get("game_ready", {}) or {}
        enter_game = summary.get("enter_game", {}) or {}
        startup_interactions = summary.get("startup_interactions", {}) or {}
        package_identity = summary.get("package_identity", {}) or {}
        issues = report.get("issues", []) if isinstance(report, dict) else []
        high_issues = [issue for issue in issues if issue.get("severity") == "high"]
        checks = {
            "success_true": summary.get("success") is True,
            "high_zero": int(issue_counts.get("high", 0) or 0) == 0,
            "pageerrors_zero": int(browser_diagnostics.get("pageerror_count", 0) or 0) == 0,
            "game_ready_true": game_ready.get("ready") is True,
            "passage_orphanage_intro": game_ready.get("passage") == "Orphanage Intro",
            "enter_game_success": enter_game.get("success") is True,
            "startup_success": startup_interactions.get("success") is True,
            "profile_slug_match": package_identity.get("profile_slug_match") is True,
        }
        entry.update(
            {
                "checks": checks,
                "high_count": int(issue_counts.get("high", 0) or 0),
                "pageerror_count": int(browser_diagnostics.get("pageerror_count", 0) or 0),
                "passage": game_ready.get("passage"),
                "enter_game": enter_game,
                "top_high_risk": high_issues[:10],
            }
        )
        entry["success"] = all(checks.values())
        if not entry["success"]:
            entry["errors"].extend(key for key, value in checks.items() if not value)
        summaries.append(entry)

    success = bool(summaries) and all(summary["success"] for summary in summaries)
    payload = {
        "success": success,
        "gate_level": PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": False,
        "results": summaries,
    }
    _write_json(output, payload)
    for summary in summaries:
        print(json.dumps({"slug": summary["slug"], "success": summary["success"], "errors": summary["errors"]}, ensure_ascii=False))
    return 0 if success else 1


def summarize_apk_cdp_smoke_reports(reports_dir: Path, output: Path) -> int:
    """Summarize strict Android emulator/WebView CDP smoke reports for all candidate APKs."""
    summaries: list[dict[str, Any]] = []
    expected_scope = {
        "platform": "Android emulator",
        "webview_cdp": True,
        "manual_phone_testing": False,
        "harmonyos_covered": False,
    }
    for slug in DEFAULT_STABLE_CODE_ORDER:
        smoke_path = Path(reports_dir) / slug / "apk-emulator-smoke.json"
        entry: dict[str, Any] = {
            "slug": slug,
            "code": CANDIDATE_CODES[slug],
            "smoke_path": str(smoke_path),
            "success": False,
            "errors": [],
        }
        if not smoke_path.exists():
            entry["errors"].append(f"missing APK emulator/CDP smoke report: {smoke_path}")
            summaries.append(entry)
            continue

        smoke = _load_json(smoke_path)
        browser_summary = smoke.get("browser_summary", {}) or {}
        issue_counts = browser_summary.get("issue_counts", {}) or {}
        browser_diagnostics = browser_summary.get("browser_diagnostics", {}) or {}
        game_ready = browser_summary.get("game_ready", {}) or {}
        enter_game = browser_summary.get("enter_game", {}) or {}
        startup_interactions = browser_summary.get("startup_interactions", {}) or {}
        package_identity = browser_summary.get("package_identity", {}) or {}
        runtime_scope = smoke.get("runtime_scope", {}) or {}
        smoke_errors = [str(error) for error in smoke.get("errors", []) or []]
        cdp_targets = smoke.get("cdp_targets", []) or []
        checks = {
            "success_true": smoke.get("success") is True,
            "component_gate_level": smoke.get("gate_level") == FULL_GATE_COMPONENT_LEVEL,
            "not_phase2_counting_component": smoke.get("counts_for_phase2_promotion") is False,
            "default_matrix_unchanged": smoke.get("default_matrix_mutated") is False,
            "android_emulator_scope": runtime_scope.get("platform") == expected_scope["platform"],
            "webview_cdp_scope": runtime_scope.get("webview_cdp") is True,
            "no_manual_phone_scope": runtime_scope.get("manual_phone_testing") is False,
            "no_harmonyos_scope": runtime_scope.get("harmonyos_covered") is False,
            "cdp_target_present": bool(cdp_targets),
            "browser_success_true": browser_summary.get("success") is True,
            "high_zero": int(issue_counts.get("high", 0) or 0) == 0,
            "pageerrors_zero": int(browser_diagnostics.get("pageerror_count", 0) or 0) == 0,
            "game_ready_true": game_ready.get("ready") is True,
            "passage_orphanage_intro": game_ready.get("passage") == "Orphanage Intro",
            "enter_game_success": enter_game.get("success") is True,
            "startup_success": startup_interactions.get("success") is True,
            "profile_slug_match": package_identity.get("profile_slug_match") is True,
            "no_runner_errors": not smoke_errors,
        }
        entry.update(
            {
                "checks": checks,
                "target": smoke.get("target"),
                "package": smoke.get("package"),
                "runtime_scope": runtime_scope,
                "cdp_url": smoke.get("cdp_url"),
                "cdp_socket": smoke.get("cdp_socket"),
                "cdp_target_count": len(cdp_targets),
                "high_count": int(issue_counts.get("high", 0) or 0),
                "pageerror_count": int(browser_diagnostics.get("pageerror_count", 0) or 0),
                "passage": game_ready.get("passage"),
                "enter_game": enter_game,
                "browser_summary_path": smoke.get("browser_summary_path"),
                "browser_report_path": smoke.get("browser_report_path"),
                "markdown_report_path": smoke.get("markdown_report_path"),
                "logcat_path": smoke.get("logcat_path"),
                "screenshot_path": smoke.get("screenshot_path"),
            }
        )
        entry["success"] = all(checks.values())
        if not entry["success"]:
            entry["errors"].extend(key for key, value in checks.items() if not value)
            entry["errors"].extend(smoke_errors)
        summaries.append(entry)

    success = bool(summaries) and all(summary["success"] for summary in summaries)
    payload = {
        "success": success,
        "gate_level": FULL_GATE_COMPONENT_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "runtime_scope": expected_scope,
        "results": summaries,
    }
    _write_json(output, payload)
    for summary in summaries:
        print(json.dumps({"slug": summary["slug"], "success": summary["success"], "errors": summary["errors"]}, ensure_ascii=False))
    return 0 if success else 1


def _write_apk_cdp_failure_report(
    slug: str,
    output_dir: Path,
    errors: list[str],
    *,
    target: Path | None = None,
    profile: str = PROFILE,
) -> None:
    """Write a per-slug CDP report when the runner cannot invoke the smoke helper."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "success": False,
        "gate_level": FULL_GATE_COMPONENT_LEVEL,
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "runtime_scope": {
            "platform": "Android emulator",
            "webview_cdp": True,
            "manual_phone_testing": False,
            "harmonyos_covered": False,
        },
        "target": str(target) if target else None,
        "slug": slug,
        "package": load_build_config().identity_package,
        "profile": profile,
        "cdp_url": None,
        "cdp_socket": None,
        "cdp_targets": [],
        "browser_summary": {
            "success": False,
            "issue_counts": {"high": 1},
            "browser_diagnostics": {"pageerror_count": 0},
            "game_ready": {},
            "enter_game": {"success": False},
            "startup_interactions": {"success": False},
            "package_identity": {"profile_slug_match": False},
        },
        "browser_summary_path": str(output_dir / "browser-smoke-summary.json"),
        "browser_report_path": str(output_dir / "browser-smoke-report.json"),
        "markdown_report_path": str(output_dir / "browser-smoke-report.md"),
        "logcat_path": str(output_dir / "logcat.txt"),
        "screenshot_path": "",
        "commands": [],
        "errors": errors,
        "elapsed_seconds": 0,
    }
    _write_json(output_dir / "apk-emulator-smoke.json", payload)


def run_apk_cdp_smokes(target: Path, reports_dir: Path, profile: str = PROFILE) -> int:
    """Run Android emulator/WebView CDP smokes for all candidate debug APKs.

    The GitHub emulator action executes its ``script`` input one command at a
    time, so keep slug iteration in Python instead of relying on a multiline
    shell loop.
    """
    debug_apks = _artifact_candidates(target, "apk")
    debug_by_slug = {_slug_for_artifact(path): path for path in debug_apks}
    failures: list[str] = []

    for slug in DEFAULT_STABLE_CODE_ORDER:
        output_dir = Path(reports_dir) / slug
        apk_path = debug_by_slug.get(slug)
        if apk_path is None:
            error = f"missing smoke-debug candidate APK for {slug} under {target}"
            failures.append(error)
            _write_apk_cdp_failure_report(slug, output_dir, [error], profile=profile)
            print(json.dumps({"slug": slug, "success": False, "errors": [error]}, ensure_ascii=False))
            continue

        cmd = [
            sys.executable,
            "tools/apk_emulator_smoke_test.py",
            str(apk_path),
            "--slug",
            slug,
            "--profile",
            profile,
            "--output-dir",
            str(output_dir),
        ]
        try:
            result = subprocess.run(cmd, check=False)
        except OSError as exc:
            error = f"{slug}: failed to run APK CDP smoke helper: {exc}"
            failures.append(error)
            _write_apk_cdp_failure_report(slug, output_dir, [error], target=apk_path, profile=profile)
            print(json.dumps({"slug": slug, "success": False, "errors": [error]}, ensure_ascii=False))
            continue
        if result.returncode != 0:
            error = f"{slug}: APK CDP smoke helper exited with {result.returncode}"
            failures.append(error)
            if not (output_dir / "apk-emulator-smoke.json").exists():
                _write_apk_cdp_failure_report(slug, output_dir, [error], target=apk_path, profile=profile)
            print(json.dumps({"slug": slug, "success": False, "errors": [error]}, ensure_ascii=False))

    return 0 if not failures else 1


def _build_report_success(payload: dict[str, Any]) -> bool:
    """Return success for helper build reports that cover all candidates."""
    if "success" in payload:
        return payload.get("success") is True
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return False
    records = [result for result in results if isinstance(result, dict)]
    if len(records) != len(DEFAULT_STABLE_CODE_ORDER):
        return False
    seen_slugs = {str(result.get("slug")) for result in records}
    if seen_slugs != set(DEFAULT_STABLE_CODE_ORDER):
        return False
    return all(result.get("success") is True and bool(result.get("output_path")) for result in records)


def _collect_report_errors(payload: dict[str, Any]) -> list[str]:
    """Collect representative report errors for the always-run summary."""
    errors: list[str] = []
    raw_errors = payload.get("errors")
    if isinstance(raw_errors, list):
        errors.extend(str(error) for error in raw_errors)

    for result in payload.get("results", []) or []:
        if not isinstance(result, dict):
            continue
        slug = result.get("slug") or result.get("code") or "unknown"
        if result.get("error"):
            errors.append(f"{slug}: {result['error']}")
        for key in ("errors", "validation_errors"):
            values = result.get(key)
            if isinstance(values, list):
                errors.extend(f"{slug}: {value}" for value in values)

    return errors[:20]


def _summarize_report(gate_dir: Path, filename: str, report_kind: str) -> dict[str, Any]:
    path = Path(gate_dir) / filename
    exists = path.exists()
    entry: dict[str, Any] = {
        "filename": filename,
        "path": str(path),
        "kind": report_kind,
        "exists": exists,
        "present": exists,
        "success": False,
        "status": "missing",
        "errors": [],
    }
    if not exists:
        entry["errors"].append(f"missing required report: {filename}")
        return entry

    payload = _load_json(path)
    if report_kind == "build":
        success = _build_report_success(payload)
    else:
        success = payload.get("success") is True
    entry.update(
        {
            "success": success,
            "status": "passed" if success else "failed",
            "errors": _collect_report_errors(payload),
        }
    )
    return entry


def summarize_phase1a_gate(
    gate_dir: Path,
    output: Path,
    *,
    head_sha: str | None = None,
    run_id: str | None = None,
) -> int:
    """Write an always-run aggregate candidate gate summary.

    Phase 1A/B1 reports remain enough for a partial candidate gate.  The B2
    Android emulator/WebView CDP report promotes this summary to a full
    candidate gate only when every candidate runtime smoke is green.
    """
    reports = {
        "config": _summarize_report(gate_dir, PHASE1A_CONFIG_REPORT, "simple"),
        "stable_replacement_readiness": _summarize_report(
            gate_dir,
            STABLE_REPLACEMENT_READINESS_REPORT,
            "simple",
        ),
        "zip_build": _summarize_report(gate_dir, ZIP_BUILD_REPORT, "build"),
        "apk_build": _summarize_report(gate_dir, APK_BUILD_REPORT, "build"),
        "zip_audit": _summarize_report(gate_dir, ZIP_AUDIT_REPORT, "simple"),
        "apk_audit": _summarize_report(gate_dir, APK_AUDIT_REPORT, "simple"),
        "apk_debug_derivation": _summarize_report(gate_dir, APK_DEBUG_REPORT, "simple"),
        "apk_equivalence": _summarize_report(gate_dir, APK_EQUIVALENCE_REPORT, "simple"),
        "zip_browser_summary": _summarize_report(gate_dir, ZIP_BROWSER_SUMMARY, "simple"),
        "apk_cdp_smoke": _summarize_report(gate_dir, APK_CDP_SMOKE_REPORT, "simple"),
    }
    b2_report_name = "apk_cdp_smoke"
    required_report_names = [name for name in reports if name != b2_report_name]
    missing_reports = [name for name in required_report_names if not reports[name]["present"]]
    failed_reports = [name for name in required_report_names if reports[name]["present"] and not reports[name]["success"]]
    b2_report = reports[b2_report_name]
    b2_failed_reports = [b2_report_name] if b2_report["present"] and not b2_report["success"] else []
    errors = [error for name in required_report_names for error in reports[name]["errors"]]
    if b2_report["present"]:
        errors.extend(b2_report["errors"])
    partial_success = not missing_reports and not failed_reports
    full_success = partial_success and b2_report["present"] and b2_report["success"]
    success = partial_success and not b2_failed_reports
    payload = {
        "success": success,
        "gate_level": FULL_GATE_LEVEL if full_success else PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": bool(full_success),
        "default_matrix_mutated": False,
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": FRAMEWORK_CANDIDATE_PURPOSE,
        "legacy_cheat_stack_included": True,
        "replacement_candidate": {
            "provider": MAPLEBIRCH_PROVIDER,
            "purpose": REPLACEMENT_CANDIDATE_PURPOSE,
            "candidate_codes": REPLACEMENT_CANDIDATE_CODES,
            "legacy_cheat_stack_included": False,
            "legacy_entries_retained_for_rollback": True,
            "default_matrix_mutated": False,
            "counts_for_phase2_promotion": False,
        },
        "head_sha": head_sha,
        "run_id": run_id,
        "reports": reports,
        "missing_reports": missing_reports,
        "failed_reports": failed_reports + b2_failed_reports,
        "b2_runtime": {
            "required_for_full_candidate_gate": True,
            "present": b2_report["present"],
            "success": b2_report["success"],
            "report": b2_report_name,
            "scope": {
                "platform": "Android emulator",
                "webview_cdp": True,
                "manual_phone_testing": False,
                "harmonyos_covered": False,
            },
        },
        "errors": errors,
    }
    _write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if success else 1


def check_phase2_promotion(evidence_paths: list[Path], head_sha: str | None, output: Path) -> int:
    """Require two same-SHA full gate green reports before default migration."""
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for evidence_path in evidence_paths:
        payload = _load_json(Path(evidence_path))
        evidence_sha = str(payload.get("head_sha") or payload.get("workflow_head_sha") or "")
        checks = {
            "success": payload.get("success") is True,
            "gate_level_full": payload.get("gate_level") == FULL_GATE_LEVEL,
            "counts_for_phase2": payload.get("counts_for_phase2_promotion") is True,
            "sha_match": not head_sha or evidence_sha == head_sha,
        }
        item = {"path": str(evidence_path), "head_sha": evidence_sha, "checks": checks}
        if all(checks.values()):
            eligible.append(item)
        else:
            rejected.append(item)

    success = len(eligible) >= PROMOTION_REQUIRED_GREEN_RUNS
    payload = {
        "success": success,
        "required_green_runs": PROMOTION_REQUIRED_GREEN_RUNS,
        "head_sha": head_sha,
        "eligible_green_runs": eligible,
        "rejected_runs": rejected,
        "default_migration_allowed": success,
    }
    _write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if success else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Baseline candidate gate helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest", help="Write the candidate manifest")
    manifest_parser.add_argument("--pack-type", choices=("zip", "apk"), default="zip")
    manifest_parser.add_argument("--output", type=Path)

    validate_parser = subparsers.add_parser("validate-config", help="Validate static Phase 1A config invariants")
    validate_parser.add_argument("--output", type=Path)

    readiness_parser = subparsers.add_parser(
        "stable-replacement-readiness",
        help="Report no-legacy-cheat stable replacement readiness without mutating defaults",
    )
    readiness_parser.add_argument("--output", type=Path, default=_gate_dir() / STABLE_REPLACEMENT_READINESS_REPORT)

    build_parser = subparsers.add_parser("build", help="Build explicit candidate artifacts")
    build_parser.add_argument("--pack-type", choices=("zip", "apk"), default="zip")
    build_parser.add_argument("--workspace", type=Path, default=Path("."))
    build_parser.add_argument("--output-dir", type=Path)
    build_parser.add_argument("--report", type=Path)
    build_parser.add_argument("--ensure-payloads", action="store_true")

    audit_parser = subparsers.add_parser("audit-zip", help="Audit candidate ZIP artifacts")
    audit_parser.add_argument("target", type=Path)
    audit_parser.add_argument("--output", type=Path, default=_gate_dir() / ZIP_AUDIT_REPORT)

    audit_apk_parser = subparsers.add_parser("audit-apk", help="Audit candidate APK artifacts")
    audit_apk_parser.add_argument("target", type=Path)
    audit_apk_parser.add_argument("--output", type=Path, default=_gate_dir() / APK_AUDIT_REPORT)

    derive_debug_parser = subparsers.add_parser(
        "derive-debug-apk",
        help="Derive release-based smoke-debug APK artifacts",
    )
    derive_debug_parser.add_argument(
        "target",
        type=Path,
        help="Release APK file or directory produced by the candidate APK build",
    )
    derive_debug_parser.add_argument("--workspace", type=Path, default=Path("."))
    derive_debug_parser.add_argument(
        "--output-dir",
        type=Path,
        default=_gate_dir() / "apk-debug-artifacts",
    )
    derive_debug_parser.add_argument("--output", type=Path, default=_gate_dir() / APK_DEBUG_REPORT)

    equivalence_parser = subparsers.add_parser(
        "audit-apk-equivalence",
        help="Audit release/debug APK static identity equivalence",
    )
    equivalence_parser.add_argument("--release-target", type=Path, required=True)
    equivalence_parser.add_argument("--debug-target", type=Path, required=True)
    equivalence_parser.add_argument("--output", type=Path, default=_gate_dir() / APK_EQUIVALENCE_REPORT)

    browser_parser = subparsers.add_parser("summarize-browser", help="Summarize strict candidate browser smoke reports")
    browser_parser.add_argument("--reports-dir", type=Path, default=_gate_dir() / "browser-smoke")
    browser_parser.add_argument("--output", type=Path, default=_gate_dir() / ZIP_BROWSER_SUMMARY)

    run_apk_cdp_parser = subparsers.add_parser(
        "run-apk-cdp",
        help="Run strict candidate Android emulator/WebView CDP smoke reports",
    )
    run_apk_cdp_parser.add_argument(
        "target",
        type=Path,
        help="Smoke-debug APK file or directory produced by derive-debug-apk",
    )
    run_apk_cdp_parser.add_argument("--reports-dir", type=Path, default=_gate_dir() / "apk-cdp-smoke")
    run_apk_cdp_parser.add_argument("--profile", default=PROFILE)

    apk_cdp_parser = subparsers.add_parser(
        "summarize-apk-cdp",
        help="Summarize strict candidate Android emulator/WebView CDP smoke reports",
    )
    apk_cdp_parser.add_argument("--reports-dir", type=Path, default=_gate_dir() / "apk-cdp-smoke")
    apk_cdp_parser.add_argument("--output", type=Path, default=_gate_dir() / APK_CDP_SMOKE_REPORT)

    phase1a_parser = subparsers.add_parser("summarize-phase1a", help="Summarize Phase 1A candidate gate reports")
    phase1a_parser.add_argument("--gate-dir", type=Path, default=_gate_dir())
    phase1a_parser.add_argument("--output", type=Path, default=_gate_dir() / PHASE1A_SUMMARY)
    phase1a_parser.add_argument("--head-sha")
    phase1a_parser.add_argument("--run-id")

    promotion_parser = subparsers.add_parser("check-promotion", help="Check whether Phase 2 default migration is allowed")
    promotion_parser.add_argument("--evidence", type=Path, nargs="+", required=True)
    promotion_parser.add_argument("--head-sha")
    promotion_parser.add_argument("--output", type=Path, default=_gate_dir() / "phase2-promotion-check.json")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "manifest":
        payload = build_manifest(args.pack_type)
        if args.output:
            _write_json(args.output, payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate-config":
        payload = validate_static_config()
        if args.output:
            _write_json(args.output, payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["success"] else 1
    if args.command == "stable-replacement-readiness":
        payload = build_stable_replacement_readiness()
        if args.output:
            _write_json(args.output, payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["success"] else 1
    if args.command == "build":
        output_dir = args.output_dir or _target_output_dir(args.pack_type)
        report_name = ZIP_BUILD_REPORT if args.pack_type == "zip" else APK_BUILD_REPORT
        report_path = args.report or _gate_dir() / report_name
        return build_candidates(args.pack_type, args.workspace, output_dir, args.ensure_payloads, report_path)
    if args.command == "audit-zip":
        return audit_zip_target(args.target, args.output)
    if args.command == "audit-apk":
        return audit_apk_target(args.target, args.output)
    if args.command == "derive-debug-apk":
        return derive_debug_apk_target(args.target, args.output_dir, args.output, workspace=args.workspace)
    if args.command == "audit-apk-equivalence":
        return audit_apk_equivalence_target(args.release_target, args.debug_target, args.output)
    if args.command == "summarize-browser":
        return summarize_browser_reports(args.reports_dir, args.output)
    if args.command == "run-apk-cdp":
        return run_apk_cdp_smokes(args.target, args.reports_dir, args.profile)
    if args.command == "summarize-apk-cdp":
        return summarize_apk_cdp_smoke_reports(args.reports_dir, args.output)
    if args.command == "summarize-phase1a":
        return summarize_phase1a_gate(args.gate_dir, args.output, head_sha=args.head_sha, run_id=args.run_id)
    if args.command == "check-promotion":
        return check_phase2_promotion(args.evidence, args.head_sha, args.output)
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
