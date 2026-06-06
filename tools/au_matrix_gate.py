#!/usr/bin/env python3
"""AU matrix gate helpers for build, artifact, and smoke report checks."""

from __future__ import annotations

import argparse
import copy
import io
import json
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.build import BuildTask, build_single
from lyra.config_loader import get_config_loader, load_build_config
from lyra.paths import BuildPaths
from tools.artifact_inspection import (
    decode_base64_payload,
    load_preferred_html_from_zip,
    parse_mod_data_value_zip_list,
)
from tools.au_artifact_check import audit_zip_artifact
from tools.html_smoke_test import audit_zip_artifact as audit_html_zip_artifact


AU_VARIANTS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("au-f", 25858, ("aufemale", "au female", "aufemale.model")),
    ("au-m", 26882, ("aumale", "au male", "aumale.model")),
    ("au-a", 28930, ("auandrogynous", "au androgynous", "auandrogynous.model")),
)

FULL_REQUIRED_TERMS: tuple[str, ...] = (
    "more love interests mod",
    "custom-spellbook",
    "lyra",
    "facial",
)

AU_FACE_CACHE_NAME = "au_face"
AU_FACE_TERMS: tuple[str, ...] = (
    "facial expansion",
    "simplecryptwrapper",
    "zip.crypt",
    "ausdol",
    "au面部",
)
FULL_BUILD_RESULTS = "au-full-build-results.json"
FULL_BROWSER_DIR = "browser-smoke"
FULL_BROWSER_SUMMARY = "au-full-browser-summary.json"
BODY_ONLY_BUILD_RESULTS = "au-body-only-build-results.json"
BODY_ONLY_BROWSER_DIR = "body-only-browser-smoke"
BODY_ONLY_BROWSER_SUMMARY = "au-body-only-browser-summary.json"
BODY_ONLY_COMPARISON = "au-body-only-comparison.json"
MAPLEBIRCH_CACHE_NAME = "maplebirch"
CHEAT_EXTENDED_CACHE_NAME = "cheat_extended"
MAPLEBIRCH_PROVIDER = "maplebirch"
AU_FRAMEWORK_SUPPORT_PURPOSE = "au_framework_support"
MAPLEBIRCH_BUILD_RESULTS = "au-maplebirch-build-results.json"
MAPLEBIRCH_BROWSER_DIR = "maplebirch-browser-smoke"
MAPLEBIRCH_BROWSER_SUMMARY = "au-maplebirch-browser-summary.json"
MAPLEBIRCH_COMPARISON = "au-maplebirch-comparison.json"


@dataclass
class BuildRecord:
    """One AU full build record."""

    slug: str
    code: int
    success: bool
    output_path: str | None = None
    output_name: str = ""
    error: str | None = None
    applied_mods: list[str] = field(default_factory=list)


@dataclass
class EmbeddedPayload:
    """Minimal embedded ModLoader payload metadata."""

    index: int
    names: list[str] = field(default_factory=list)
    boot_json_found: bool = False
    error: str | None = None
    search_text_sample: str = ""


@dataclass
class PayloadAudit:
    """Payload-level audit for one AU full artifact."""

    slug: str
    code: int
    target: str
    success: bool = False
    mod_count: int = 0
    embedded_payloads: list[EmbeddedPayload] = field(default_factory=list)
    found_terms: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class ArtifactAuditRecord:
    """Combined artifact audit result for one AU full artifact."""

    slug: str
    code: int
    target: str
    success: bool
    alias_audit: dict[str, Any]
    html_smoke: dict[str, Any]
    payload_audit: PayloadAudit
    errors: list[str] = field(default_factory=list)


def _gate_dir() -> Path:
    path = Path("output") / "au-matrix-gate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _maplebirch_framework_evidence_metadata() -> dict[str, Any]:
    """Shared metadata for AU + maplebirch framework-support diagnostics."""
    return {
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": AU_FRAMEWORK_SUPPORT_PURPOSE,
        "shared_framework_evidence": True,
        "default_matrix_mutated": False,
        "cheat_extended_included": False,
    }


def _load_build_records(path: Path | None = None) -> list[BuildRecord]:
    source = path or _gate_dir() / FULL_BUILD_RESULTS
    payload = json.loads(source.read_text(encoding="utf-8"))
    return [BuildRecord(**item) for item in payload.get("results", [])]


def _remove_scratch_work_dir(path: Path) -> None:
    """Remove a build scratch directory before retrying a single AU build."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _diagnostic_paths(output_dir: Path) -> BuildPaths:
    """Return BuildPaths with a diagnostic output directory only."""
    config = copy.deepcopy(load_build_config())
    config.output_dir = str(output_dir)
    paths = BuildPaths(_config=config)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def _set_au_face_injection_enabled(enabled: bool) -> list[Any]:
    """Toggle au_face injection in the current process, returning the original list."""
    build_config = get_config_loader().build
    original_mods = build_config.modloader_mods
    if enabled:
        return original_mods

    build_config.modloader_mods = [
        mod_config
        for mod_config in original_mods
        if mod_config.cache_name != AU_FACE_CACHE_NAME
    ]
    return original_mods


def _set_maplebirch_canary_injection_enabled() -> list[Any]:
    """Force maplebirch into AU diagnostics while keeping cheatExtended out."""
    build_config = get_config_loader().build
    original_mods = build_config.modloader_mods
    au_feature_ids = [slug for slug, _code, _terms in AU_VARIANTS]
    canary_mods = []

    for mod_config in original_mods:
        cache_name = mod_config.cache_name
        if cache_name == CHEAT_EXTENDED_CACHE_NAME:
            continue

        canary_config = copy.copy(mod_config)
        if cache_name == MAPLEBIRCH_CACHE_NAME:
            canary_config.enabled = True
            canary_config.feature_id = ""
            canary_config.feature_ids = list(au_feature_ids)
        canary_mods.append(canary_config)

    build_config.modloader_mods = canary_mods
    return original_mods


def _restore_modloader_mods(original_mods: list[Any]) -> None:
    get_config_loader().build.modloader_mods = original_mods


def _applied_mod_contains(applied_mods: list[str], *terms: str) -> bool:
    normalized = [str(mod).lower() for mod in applied_mods]
    return any(any(term.lower() in mod for term in terms) for mod in normalized)


def _failed_alias_audit(target: str, error: str) -> dict[str, Any]:
    return {
        "target": target,
        "is_au": True,
        "success": False,
        "nested_blush_count": 0,
        "required_nested_blush_present": False,
        "errors": [error],
    }


def _failed_html_smoke(target: str, error: str) -> dict[str, Any]:
    return {
        "target": target,
        "success": False,
        "html_found": False,
        "mod_count": 0,
        "valid_zip_count": 0,
        "non_zip_payload_count": 0,
        "invalid_zip_count": 0,
        "errors": [error],
        "warnings": [],
        "payloads": [],
    }


def build_full() -> int:
    """Build AU-F/M/A full ZIP artifacts using the normal configuration."""
    records: list[BuildRecord] = []
    paths = BuildPaths()
    for slug, code, _terms in AU_VARIANTS:
        try:
            _remove_scratch_work_dir(paths.get_build_work_dir("zip", code))
            result = build_single(BuildTask(pack_type="zip", mod_code=code, paths=paths))
            result_dict = result.to_dict()
            record = BuildRecord(
                slug=slug,
                code=code,
                success=bool(result.success),
                output_path=result_dict.get("output_path"),
                output_name=str(result_dict.get("output_name") or ""),
                error=result_dict.get("error"),
                applied_mods=list(result_dict.get("applied_mods") or []),
            )
        except Exception as exc:  # noqa: BLE001 - gate report should capture build failures.
            record = BuildRecord(
                slug=slug,
                code=code,
                success=False,
                error=str(exc),
            )
        records.append(record)
        print(json.dumps(asdict(record), ensure_ascii=False))

    _write_json(
        _gate_dir() / FULL_BUILD_RESULTS,
        {"results": [asdict(record) for record in records]},
    )
    return 0 if all(record.success and record.output_path for record in records) else 1


def build_body_only() -> int:
    """Build temporary AU body-only diagnostic ZIP artifacts without au_face."""
    records: list[BuildRecord] = []
    paths = _diagnostic_paths(_gate_dir() / "body-only-artifacts")
    original_mods = _set_au_face_injection_enabled(False)
    try:
        for slug, code, _terms in AU_VARIANTS:
            try:
                _remove_scratch_work_dir(paths.get_build_work_dir("zip", code))
                result = build_single(BuildTask(pack_type="zip", mod_code=code, paths=paths))
                result_dict = result.to_dict()
                applied_mods = list(result_dict.get("applied_mods") or [])
                success = bool(result.success)
                error = result_dict.get("error")
                if any("AU面部扩展" in str(mod) or str(mod) == AU_FACE_CACHE_NAME for mod in applied_mods):
                    success = False
                    error = "body-only diagnostic unexpectedly injected AU face extension"
                record = BuildRecord(
                    slug=slug,
                    code=code,
                    success=success,
                    output_path=result_dict.get("output_path"),
                    output_name=str(result_dict.get("output_name") or ""),
                    error=error,
                    applied_mods=applied_mods,
                )
            except Exception as exc:  # noqa: BLE001 - diagnostic report should capture build failures.
                record = BuildRecord(
                    slug=slug,
                    code=code,
                    success=False,
                    error=str(exc),
                )
            records.append(record)
            print(json.dumps(asdict(record), ensure_ascii=False))
    finally:
        _restore_modloader_mods(original_mods)

    _write_json(
        _gate_dir() / BODY_ONLY_BUILD_RESULTS,
        {
            "diagnostic": "AU body/model only; AU face extension intentionally skipped",
            "results": [asdict(record) for record in records],
        },
    )
    return 0 if all(record.success and record.output_path for record in records) else 1


def build_maplebirch_canary() -> int:
    """Build AU + AU face + maplebirch diagnostic ZIPs without cheatExtended."""
    records: list[BuildRecord] = []
    paths = _diagnostic_paths(_gate_dir() / "maplebirch-artifacts")
    original_mods = _set_maplebirch_canary_injection_enabled()
    try:
        for slug, code, _terms in AU_VARIANTS:
            try:
                _remove_scratch_work_dir(paths.get_build_work_dir("zip", code))
                result = build_single(BuildTask(pack_type="zip", mod_code=code, paths=paths))
                result_dict = result.to_dict()
                applied_mods = list(result_dict.get("applied_mods") or [])
                success = bool(result.success)
                errors = [str(result_dict["error"])] if result_dict.get("error") else []

                if not _applied_mod_contains(applied_mods, "AU面部扩展", AU_FACE_CACHE_NAME):
                    errors.append("maplebirch canary unexpectedly omitted AU face extension")
                if not _applied_mod_contains(applied_mods, MAPLEBIRCH_CACHE_NAME):
                    errors.append("maplebirch canary did not inject maplebirch")
                if _applied_mod_contains(applied_mods, "cheatextended", CHEAT_EXTENDED_CACHE_NAME):
                    errors.append("maplebirch canary unexpectedly injected cheatExtended")

                record = BuildRecord(
                    slug=slug,
                    code=code,
                    success=success and not errors,
                    output_path=result_dict.get("output_path"),
                    output_name=str(result_dict.get("output_name") or ""),
                    error="; ".join(errors) if errors else None,
                    applied_mods=applied_mods,
                )
            except Exception as exc:  # noqa: BLE001 - diagnostic report should capture build failures.
                record = BuildRecord(
                    slug=slug,
                    code=code,
                    success=False,
                    error=str(exc),
                )
            records.append(record)
            print(json.dumps(asdict(record), ensure_ascii=False))
    finally:
        _restore_modloader_mods(original_mods)

    _write_json(
        _gate_dir() / MAPLEBIRCH_BUILD_RESULTS,
        {
            "diagnostic": "AU body/model plus AU face extension plus maplebirch only; cheatExtended intentionally skipped",
            **_maplebirch_framework_evidence_metadata(),
            "legacy_entries_retained_for_rollback": True,
            "results": [asdict(record) for record in records],
        },
    )
    return 0 if all(record.success and record.output_path for record in records) else 1


def _extract_embedded_payloads(zip_path: Path) -> tuple[list[EmbeddedPayload], int, list[str]]:
    errors: list[str] = []
    html_name, html_content = load_preferred_html_from_zip(zip_path)
    if html_content is None:
        return [], 0, [f"ZIP has no HTML member: {zip_path}"]

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
            with zipfile.ZipFile(io.BytesIO(raw_payload), "r") as mod_zip:
                names = mod_zip.namelist()
                boot_names = [name for name in names if name.lower().endswith("boot.json")]
                if not boot_names:
                    payload_info.error = "boot.json not found"
                    continue

                payload_info.boot_json_found = True
                boot_text = mod_zip.read(boot_names[0]).decode("utf-8", errors="replace")
                payload_info.search_text_sample = boot_text[:500]
                payload_info.names = _extract_payload_names(boot_text)
        except Exception as exc:  # noqa: BLE001 - keep audit artifacts useful.
            payload_info.error = str(exc)
            errors.append(f"embedded payload #{index} failed: {exc}")

    return payloads, len(parsed.entries), errors


def _extract_payload_names(boot_text: str) -> list[str]:
    names: list[str] = []
    try:
        boot_json = json.loads(boot_text)
    except json.JSONDecodeError:
        return [boot_text[:120]]

    def collect(value: Any) -> None:
        if isinstance(value, str):
            if value not in names:
                names.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(boot_json)
    return names


def _term_found(search_text: str, terms: tuple[str, ...]) -> bool:
    normalized = search_text.lower()
    return any(term.lower() in normalized for term in terms)


def audit_payload(zip_path: Path, slug: str, code: int) -> PayloadAudit:
    """Verify embedded payloads contain the AU model, AU face, and stable mods."""
    payloads, mod_count, errors = _extract_embedded_payloads(zip_path)
    joined_text = "\n".join(
        "\n".join(payload.names) + "\n" + payload.search_text_sample
        for payload in payloads
    ).lower()
    variant_terms = next(terms for variant_slug, _code, terms in AU_VARIANTS if variant_slug == slug)
    required_groups = {
        "au_model": variant_terms,
        "au_face": ("facial", "ausdol", "au面部", "face"),
        "more_love": ("more love interests mod",),
        "custom_spellbook": ("custom-spellbook", "custom spellbook"),
        "lyra": ("lyra",),
    }
    found_terms = {key: _term_found(joined_text, terms) for key, terms in required_groups.items()}

    for key, found in found_terms.items():
        if not found:
            errors.append(f"required embedded payload not found: {key}")

    return PayloadAudit(
        slug=slug,
        code=code,
        target=str(zip_path),
        success=not errors,
        mod_count=mod_count,
        embedded_payloads=payloads,
        found_terms=found_terms,
        errors=errors,
    )


def audit_full() -> int:
    """Run AU alias, payload, and HTML smoke audits for full artifacts."""
    records = _load_build_records()
    audits: list[ArtifactAuditRecord] = []
    for record in records:
        errors: list[str] = []
        target = record.output_path or ""
        if not target:
            errors.append(f"build output path is missing for {record.slug}")
            if record.error:
                errors.append(record.error)
            alias_audit = _failed_alias_audit(target, errors[0])
            html_smoke = _failed_html_smoke(target, errors[0])
            payload_result = PayloadAudit(record.slug, record.code, target, errors=list(errors))
        else:
            zip_path = Path(target)
            if not zip_path.exists():
                errors.append(f"build output does not exist: {zip_path}")
                if record.error:
                    errors.append(record.error)
                alias_audit = _failed_alias_audit(str(zip_path), errors[0])
                html_smoke = _failed_html_smoke(str(zip_path), errors[0])
                payload_result = PayloadAudit(record.slug, record.code, str(zip_path), errors=list(errors))
            else:
                alias_result = audit_zip_artifact(zip_path)
                html_result = audit_html_zip_artifact(zip_path)
                payload_result = audit_payload(zip_path, record.slug, record.code)
                alias_audit = asdict(alias_result)
                html_smoke = asdict(html_result)
                if not alias_result.success:
                    errors.extend(alias_result.errors)
                if not html_result.success:
                    errors.extend(html_result.errors)
                if not payload_result.success:
                    errors.extend(payload_result.errors)

        audits.append(
            ArtifactAuditRecord(
                slug=record.slug,
                code=record.code,
                target=target,
                success=not errors,
                alias_audit=alias_audit,
                html_smoke=html_smoke,
                payload_audit=payload_result,
                errors=errors,
            )
        )

    _write_json(
        _gate_dir() / "au-full-artifact-audit.json",
        {"results": [asdict(audit) for audit in audits]},
    )
    for audit in audits:
        print(json.dumps({"slug": audit.slug, "success": audit.success, "errors": audit.errors}, ensure_ascii=False))
    return 0 if all(audit.success for audit in audits) else 1


def _collect_browser_summary(
    records_path: Path,
    browser_dir_name: str,
    output_name: str,
) -> int:
    """Summarize strict AU browser smoke fields after external smoke runs."""
    records = _load_build_records(records_path)
    summaries: list[dict[str, Any]] = []
    for record in records:
        summary_path = _gate_dir() / browser_dir_name / record.slug / "browser-smoke-summary.json"
        report_path = _gate_dir() / browser_dir_name / record.slug / "browser-smoke-report.json"
        entry: dict[str, Any] = {
            "slug": record.slug,
            "code": record.code,
            "summary_path": str(summary_path),
            "report_path": str(report_path),
            "success": False,
            "errors": [],
        }
        if not summary_path.exists():
            entry["errors"].append(f"missing browser smoke summary: {summary_path}")
            summaries.append(entry)
            continue

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        high_count = int(summary.get("issue_counts", {}).get("high", 0))
        pageerror_count = int(summary.get("browser_diagnostics", {}).get("pageerror_count", 0))
        game_ready = summary.get("game_ready", {})
        enter_game = summary.get("enter_game", {})
        startup_interactions = summary.get("startup_interactions", {})
        issues = report.get("issues", []) if isinstance(report, dict) else []
        image_layer_errors = [
            issue
            for issue in issues
            if "Failed to load image" in str(issue.get("message", ""))
            or issue.get("kind") in {"image_layer_load_failed", "face_image_asset_missing"}
        ]
        high_issues = [issue for issue in issues if issue.get("severity") == "high"]

        checks = {
            "success_true": summary.get("success") is True,
            "high_zero": high_count == 0,
            "pageerrors_zero": pageerror_count == 0,
            "game_ready_true": game_ready.get("ready") is True,
            "passage_orphanage_intro": game_ready.get("passage") == "Orphanage Intro",
            "enter_game_success": enter_game.get("success") is True,
            "startup_success": startup_interactions.get("success") is True,
            "no_image_layer_errors": not image_layer_errors,
        }
        entry.update(
            {
                "checks": checks,
                "high_count": high_count,
                "pageerror_count": pageerror_count,
                "passage": game_ready.get("passage"),
                "image_layer_error_count": len(image_layer_errors),
                "image_layer_errors": image_layer_errors[:10],
                "top_high_risk": high_issues[:10],
            }
        )
        entry["success"] = all(checks.values())
        if not entry["success"]:
            entry["errors"].extend(key for key, value in checks.items() if not value)
        summaries.append(entry)

    _write_json(_gate_dir() / output_name, {"results": summaries})
    for summary in summaries:
        print(json.dumps({"slug": summary["slug"], "success": summary["success"], "errors": summary["errors"]}, ensure_ascii=False))
    return 0 if all(summary["success"] for summary in summaries) else 1


def summarize_browser() -> int:
    """Summarize strict AU full browser smoke fields after external smoke runs."""
    return _collect_browser_summary(_gate_dir() / FULL_BUILD_RESULTS, FULL_BROWSER_DIR, FULL_BROWSER_SUMMARY)


def summarize_body_only_browser() -> int:
    """Summarize temporary AU body-only browser smoke fields."""
    return _collect_browser_summary(
        _gate_dir() / BODY_ONLY_BUILD_RESULTS,
        BODY_ONLY_BROWSER_DIR,
        BODY_ONLY_BROWSER_SUMMARY,
    )


def summarize_maplebirch_browser() -> int:
    """Summarize AU + maplebirch-only canary browser smoke fields."""
    return _collect_browser_summary(
        _gate_dir() / MAPLEBIRCH_BUILD_RESULTS,
        MAPLEBIRCH_BROWSER_DIR,
        MAPLEBIRCH_BROWSER_SUMMARY,
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _entries_by_slug(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("slug")): entry
        for entry in payload.get("results", [])
        if isinstance(entry, dict) and entry.get("slug")
    }


def _high_issue_messages(entry: dict[str, Any]) -> list[str]:
    return [str(issue.get("message", "")) for issue in entry.get("top_high_risk", [])]


def compare_body_only() -> int:
    """Compare AU full and body-only diagnostics without treating body-only as shippable."""
    gate_dir = _gate_dir()
    full_builds = _load_build_records(gate_dir / FULL_BUILD_RESULTS)
    body_builds = _load_build_records(gate_dir / BODY_ONLY_BUILD_RESULTS)
    full_summary = _entries_by_slug(_load_json(gate_dir / FULL_BROWSER_SUMMARY))
    body_summary = _entries_by_slug(_load_json(gate_dir / BODY_ONLY_BROWSER_SUMMARY))
    body_build_by_slug = {record.slug: record for record in body_builds}

    variants: list[dict[str, Any]] = []
    for full_record in full_builds:
        body_record = body_build_by_slug.get(full_record.slug)
        full_entry = full_summary.get(full_record.slug, {})
        body_entry = body_summary.get(full_record.slug, {})
        full_high_messages = _high_issue_messages(full_entry)
        body_high_messages = _high_issue_messages(body_entry)
        full_image_errors = int(full_entry.get("image_layer_error_count", 0) or 0)
        body_image_errors = int(body_entry.get("image_layer_error_count", 0) or 0)

        full_has_face = any("AU面部扩展" in str(mod) for mod in full_record.applied_mods)
        body_has_face = bool(
            body_record
            and any("AU面部扩展" in str(mod) or str(mod) == AU_FACE_CACHE_NAME for mod in body_record.applied_mods)
        )
        common_high = sorted(set(full_high_messages) & set(body_high_messages))
        removed_high = sorted(set(full_high_messages) - set(body_high_messages))
        added_high = sorted(set(body_high_messages) - set(full_high_messages))

        if full_entry.get("success") is True:
            diagnosis = "full_passed_body_only_unneeded"
        elif full_image_errors and not body_image_errors:
            diagnosis = "au_face_extension_suspect"
        elif common_high and not removed_high and not added_high:
            diagnosis = "not_au_face_specific_same_high_findings"
        elif removed_high:
            diagnosis = "body_only_reduces_high_findings"
        else:
            diagnosis = "inconclusive"

        variants.append(
            {
                "slug": full_record.slug,
                "code": full_record.code,
                "full_success": full_entry.get("success"),
                "body_only_success": body_entry.get("success"),
                "full_high_count": full_entry.get("high_count"),
                "body_only_high_count": body_entry.get("high_count"),
                "full_image_layer_error_count": full_image_errors,
                "body_only_image_layer_error_count": body_image_errors,
                "full_has_au_face_extension": full_has_face,
                "body_only_has_au_face_extension": body_has_face,
                "common_high_messages": common_high,
                "high_messages_removed_by_body_only": removed_high,
                "high_messages_added_by_body_only": added_high,
                "diagnosis": diagnosis,
            }
        )

    diagnostic_complete = bool(variants) and all(
        body_build_by_slug.get(slug) is not None
        and body_build_by_slug[slug].success
        and not variant["body_only_has_au_face_extension"]
        and slug in body_summary
        for slug, variant in ((str(item["slug"]), item) for item in variants)
    )
    payload = {
        "diagnostic": "body-only is diagnostic control only; AU face extension remains required for full AU builds",
        "diagnostic_complete": diagnostic_complete,
        "full_all_success": all(entry.get("success") is True for entry in full_summary.values()),
        "body_only_all_success": all(entry.get("success") is True for entry in body_summary.values()) if body_summary else False,
        "variants": variants,
    }
    _write_json(gate_dir / BODY_ONLY_COMPARISON, payload)
    print(json.dumps({"diagnostic_complete": diagnostic_complete, "variants": variants}, ensure_ascii=False))
    return 0 if diagnostic_complete else 1


def compare_maplebirch_canary() -> int:
    """Compare full/body-only/maplebirch diagnostics for AU face dependency triage."""
    gate_dir = _gate_dir()
    full_builds = _load_build_records(gate_dir / FULL_BUILD_RESULTS)
    body_builds = _load_build_records(gate_dir / BODY_ONLY_BUILD_RESULTS)
    maplebirch_builds = _load_build_records(gate_dir / MAPLEBIRCH_BUILD_RESULTS)
    full_summary = _entries_by_slug(_load_json(gate_dir / FULL_BROWSER_SUMMARY))
    body_summary = _entries_by_slug(_load_json(gate_dir / BODY_ONLY_BROWSER_SUMMARY))
    maplebirch_summary = _entries_by_slug(_load_json(gate_dir / MAPLEBIRCH_BROWSER_SUMMARY))
    body_build_by_slug = {record.slug: record for record in body_builds}
    maplebirch_build_by_slug = {record.slug: record for record in maplebirch_builds}

    variants: list[dict[str, Any]] = []
    for full_record in full_builds:
        slug = full_record.slug
        body_record = body_build_by_slug.get(slug)
        maplebirch_record = maplebirch_build_by_slug.get(slug)
        full_entry = full_summary.get(slug, {})
        body_entry = body_summary.get(slug, {})
        maplebirch_entry = maplebirch_summary.get(slug, {})
        full_high_messages = _high_issue_messages(full_entry)
        body_high_messages = _high_issue_messages(body_entry)
        maplebirch_high_messages = _high_issue_messages(maplebirch_entry)

        full_set = set(full_high_messages)
        body_set = set(body_high_messages)
        maplebirch_set = set(maplebirch_high_messages)
        removed_by_body = sorted(full_set - body_set)
        removed_by_maplebirch = sorted(full_set - maplebirch_set)
        added_by_maplebirch = sorted(maplebirch_set - full_set)

        maplebirch_has_face = bool(
            maplebirch_record
            and _applied_mod_contains(maplebirch_record.applied_mods, "AU面部扩展", AU_FACE_CACHE_NAME)
        )
        maplebirch_has_maplebirch = bool(
            maplebirch_record
            and _applied_mod_contains(maplebirch_record.applied_mods, MAPLEBIRCH_CACHE_NAME)
        )
        maplebirch_has_cheat_extended = bool(
            maplebirch_record
            and _applied_mod_contains(maplebirch_record.applied_mods, "cheatextended", CHEAT_EXTENDED_CACHE_NAME)
        )

        if maplebirch_entry.get("success") is True and full_entry.get("success") is not True:
            diagnosis = "maplebirch_only_resolves_full_au_failure"
        elif body_entry.get("success") is True and maplebirch_entry.get("success") is not True:
            diagnosis = "maplebirch_only_does_not_resolve_au_face_failure"
        elif added_by_maplebirch:
            diagnosis = "maplebirch_only_introduces_new_high_findings"
        elif full_entry.get("success") is True:
            diagnosis = "full_passed_canary_unneeded"
        else:
            diagnosis = "inconclusive"

        variants.append(
            {
                "slug": slug,
                "code": full_record.code,
                "full_success": full_entry.get("success"),
                "body_only_success": body_entry.get("success"),
                "maplebirch_success": maplebirch_entry.get("success"),
                "full_high_count": full_entry.get("high_count"),
                "body_only_high_count": body_entry.get("high_count"),
                "maplebirch_high_count": maplebirch_entry.get("high_count"),
                "maplebirch_has_au_face_extension": maplebirch_has_face,
                "maplebirch_has_maplebirch": maplebirch_has_maplebirch,
                "maplebirch_has_cheat_extended": maplebirch_has_cheat_extended,
                "high_messages_removed_by_body_only": removed_by_body,
                "high_messages_removed_by_maplebirch": removed_by_maplebirch,
                "high_messages_added_by_maplebirch": added_by_maplebirch,
                "diagnosis": diagnosis,
            }
        )

    diagnostic_complete = bool(variants) and all(
        maplebirch_build_by_slug.get(slug) is not None
        and maplebirch_build_by_slug[slug].success
        and variant["maplebirch_has_au_face_extension"]
        and variant["maplebirch_has_maplebirch"]
        and not variant["maplebirch_has_cheat_extended"]
        and slug in maplebirch_summary
        for slug, variant in ((str(item["slug"]), item) for item in variants)
    )
    payload = {
        "diagnostic": "AU full vs body-only vs AU face + maplebirch-only canary; cheatExtended remains excluded",
        **_maplebirch_framework_evidence_metadata(),
        "diagnostic_complete": diagnostic_complete,
        "full_all_success": all(entry.get("success") is True for entry in full_summary.values()) if full_summary else False,
        "body_only_all_success": all(entry.get("success") is True for entry in body_summary.values()) if body_summary else False,
        "maplebirch_all_success": all(entry.get("success") is True for entry in maplebirch_summary.values()) if maplebirch_summary else False,
        "variants": variants,
    }
    _write_json(gate_dir / MAPLEBIRCH_COMPARISON, payload)
    print(json.dumps({"diagnostic_complete": diagnostic_complete, "variants": variants}, ensure_ascii=False))
    return 0 if diagnostic_complete else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AU matrix gate helper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build-full", help="Build AU-F/M/A full ZIP artifacts")
    subparsers.add_parser("build-body-only", help="Build temporary AU body-only diagnostic ZIP artifacts")
    subparsers.add_parser("build-maplebirch-canary", help="Build AU + maplebirch-only diagnostic ZIP artifacts")
    subparsers.add_parser("audit-full", help="Audit full AU ZIP artifacts")
    subparsers.add_parser("summarize-browser", help="Summarize strict browser smoke fields")
    subparsers.add_parser("summarize-body-only-browser", help="Summarize body-only browser smoke fields")
    subparsers.add_parser("summarize-maplebirch-browser", help="Summarize maplebirch canary browser smoke fields")
    subparsers.add_parser("compare-body-only", help="Compare full and body-only AU diagnostics")
    subparsers.add_parser("compare-maplebirch-canary", help="Compare full/body-only/maplebirch AU diagnostics")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "build-full":
        return build_full()
    if args.command == "build-body-only":
        return build_body_only()
    if args.command == "build-maplebirch-canary":
        return build_maplebirch_canary()
    if args.command == "audit-full":
        return audit_full()
    if args.command == "summarize-browser":
        return summarize_browser()
    if args.command == "summarize-body-only-browser":
        return summarize_body_only_browser()
    if args.command == "summarize-maplebirch-browser":
        return summarize_maplebirch_browser()
    if args.command == "compare-body-only":
        return compare_body_only()
    if args.command == "compare-maplebirch-canary":
        return compare_maplebirch_canary()
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
