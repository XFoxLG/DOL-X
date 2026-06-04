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
from typing import Any

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
CANDIDATE_CODES: dict[str, int] = {
    slug: code + int(ModCode.CHEAT_EXTENDED_MAPLEBIRCH)
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
APK_DEBUG_REPORT = "baseline-candidate-apk-debug-derivation.json"
APK_CDP_SMOKE_REPORT = "baseline-candidate-apk-cdp-smoke.json"
WEBVIEW_DEBUG_INVOKE = "Landroid/webkit/WebView;->setWebContentsDebuggingEnabled(Z)V"


@dataclass(frozen=True)
class CandidateTarget:
    """One explicit candidate build target."""

    slug: str
    legacy_code: int
    code: int
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
        "candidate_codes": CANDIDATE_CODES,
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

    return {
        "success": not errors,
        "errors": errors,
        "manifest": build_manifest(),
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

    warnings.append("Phase 1A APK audit is static; emulator/CDP WebView validation remains Phase 1B")
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

    payload = {
        "gate_level": PARTIAL_GATE_LEVEL,
        "counts_for_phase2_promotion": False,
        "results": summaries,
    }
    _write_json(output, payload)
    for summary in summaries:
        print(json.dumps({"slug": summary["slug"], "success": summary["success"], "errors": summary["errors"]}, ensure_ascii=False))
    return 0 if summaries and all(summary["success"] for summary in summaries) else 1


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

    browser_parser = subparsers.add_parser("summarize-browser", help="Summarize strict candidate browser smoke reports")
    browser_parser.add_argument("--reports-dir", type=Path, default=_gate_dir() / "browser-smoke")
    browser_parser.add_argument("--output", type=Path, default=_gate_dir() / ZIP_BROWSER_SUMMARY)

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
    if args.command == "build":
        output_dir = args.output_dir or _target_output_dir(args.pack_type)
        report_name = ZIP_BUILD_REPORT if args.pack_type == "zip" else APK_BUILD_REPORT
        report_path = args.report or _gate_dir() / report_name
        return build_candidates(args.pack_type, args.workspace, output_dir, args.ensure_payloads, report_path)
    if args.command == "audit-zip":
        return audit_zip_target(args.target, args.output)
    if args.command == "audit-apk":
        return audit_apk_target(args.target, args.output)
    if args.command == "summarize-browser":
        return summarize_browser_reports(args.reports_dir, args.output)
    if args.command == "check-promotion":
        return check_phase2_promotion(args.evidence, args.head_sha, args.output)
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
