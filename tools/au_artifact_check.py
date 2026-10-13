#!/usr/bin/env python3
"""Artifact-level AU compatibility checks for built ZIP and APK packages."""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.artifact_inspection import (
    decode_base64_payload,
    load_html_from_apk,
    load_preferred_html_from_zip,
    parse_boot_json,
    parse_mod_data_value_zip_list,
)
from lyra.build import (
    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW,
    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER,
    MAPLEBIRCH_PET_REMOUNT_MARKER,
)


CURRENT_REQUIRED_NESTED_BLUSH = "img/face/default/default/blush-1.png"
LEGACY_REQUIRED_NESTED_BLUSH = "img/face/default/default/blush1.png"
REQUIRED_NUMBERED_NESTED_BLUSH_LAYERS = frozenset(range(1, 6))
EXPECTED_FACE_VARIANT_SWITCH_MARKERS = 3
EXPECTED_FACE_VARIANT_MIGRATION_MARKERS = 1
MAPLEBIRCH_MOD_NAME = "maplebirch"
MAPLEBIRCH_FACE_PATCH_MEMBER = "dist/inject_early.js"
POST_I18N_FACE_PATCH_MARKER = "dolxAuFaceVariantAfterI18n"
AU_CONTRACT_SCHEMA = "dolx.au_contract.v1"
FRAMEWORK_FACE_STYLE_EXPORT_NEEDLE = "faceStyleSrcFn"
# AU passes this options object at nine call sites. The inner payload is not
# readable inside a built artifact, so the count is only obtainable from plaintext
# material; otherwise the contract records a runtime-query obligation.
AU_VARIANT_FLAG_RE = re.compile(r"\{\s*variant\s*:\s*true\s*\}")
AU_PAYLOAD_OPAQUE_SUFFIXES = (".crypt", ".salt", ".nonce")
AU_PAYLOAD_SCAN_MAX_BYTES = 200_000
# The outer AU payload boot.json has always claimed 1.1.0 while the inner
# archive identifies as 1.2.8, so the metadata version is recorded as a clue only.
AU_PAYLOAD_BOOT_VERSION_CLUE = "1.1.0"
AU_PAYLOAD_RUNTIME_IDENTITY = "1.2.8"
# The 2026-10-13 A/B measured the variant-directory shim as a visual no-op under the
# locked payload set, so the AU layer gap returns to accepted_upstream and carries an
# explicit visual_incomplete tag.  "fixed" stays reserved for a measured visual
# improvement, which would also join the query regression set.
AU_DEFECT_STATUS = "accepted_upstream"
AU_DEFECT_VISUAL_STATUS = "visual_incomplete"
AU_FACE_AB_VERDICT = "no_visual_change"
AU_FACE_AB_EVIDENCE = "docs/CURRENT_PROJECT_STATE.md#au-face-shim-ab-2026-10-13"
EXPECTED_AU_VARIANT_DIR_SHIM_MARKERS = 1
AU_MODEL_NAME_BY_VARIANT = {
    "au-f": "【aufemale】model",
    "au-m": "【aumale】model",
    "au-a": "【auandrogynous】model",
}
AU_MODEL_NAMES = frozenset(AU_MODEL_NAME_BY_VARIANT.values())
AU_FACE_MOD_NAME = "【ausdol】facial expansion"
FACE_VARIANT_SWITCH_MARKER = (
    "Object.values(setup.faceVariantOptions[$facestyle] || {})[0]"
)
FACE_VARIANT_MIGRATION_MARKER = (
    "!legalVariants.includes(V.facevariant)"
)
FACE_VARIANT_FALLBACK_EXPRESSION = (
    '<<run $facevariant = '
    'Object.values(setup.faceVariantOptions[$facestyle] || {})[0] || "default">>'
)
FACE_VARIANT_SWITCH_CONTEXTS = (
    '<<set $facestyle to _facestyle>>\n'
    f'\t\t\t{FACE_VARIANT_FALLBACK_EXPRESSION}',
    '<<set $facestyle to _faceStyles[_i]>>\n'
    f'\t\t\t\t\t{FACE_VARIANT_FALLBACK_EXPRESSION}',
    '<<set $facestyle to _styleValue>>\n'
    f'\t\t\t\t\t\t\t{FACE_VARIANT_FALLBACK_EXPRESSION}',
)
LEGACY_FACE_VARIANT_SWITCH_CONTEXTS = (
    '<<set $facestyle to _facestyle>>\n'
    '\t\t\t<<set $facevariant to "default">>',
    '<<set $facestyle to _faceStyles[_i]>>\n'
    '\t\t\t\t\t<<set $facevariant to "default">>',
    '<<set $facestyle to _styleValue>>\n'
    '\t\t\t\t\t\t\t<<set $facevariant to "default">>',
)
FACE_VARIANT_MIGRATION_CONTEXT = (
    "/* Code that should not be moved into a check like above */\n"
    "\t<<run (() => {const legalVariants = Object.values("
    "setup.faceVariantOptions[V.facestyle] || {});"
    "if (legalVariants.length && "
    "!legalVariants.includes(V.facevariant)) "
    "V.facevariant = legalVariants[0];})()>>\n"
    "\t<<set $runWardrobeSanityChecker to true>>"
)
LEGACY_FACE_VARIANT_MIGRATION_CONTEXT = (
    "/* Code that should not be moved into a check like above */\n"
    "\t<<set $runWardrobeSanityChecker to true>>"
)
FACE_VARIANT_PASSAGE_PATCH_RULES = (
    (
        "Widgets Mirror",
        LEGACY_FACE_VARIANT_SWITCH_CONTEXTS[0],
        FACE_VARIANT_SWITCH_CONTEXTS[0],
    ),
    (
        "Cheats",
        LEGACY_FACE_VARIANT_SWITCH_CONTEXTS[1],
        FACE_VARIANT_SWITCH_CONTEXTS[1],
    ),
    (
        "Widgets Settings",
        LEGACY_FACE_VARIANT_SWITCH_CONTEXTS[2],
        FACE_VARIANT_SWITCH_CONTEXTS[2],
    ),
    (
        "Widgets variablesVersionUpdate",
        LEGACY_FACE_VARIANT_MIGRATION_CONTEXT,
        FACE_VARIANT_MIGRATION_CONTEXT,
    ),
)
EXPECTED_POST_I18N_RULES = (
    "patchRules="
    + json.dumps(
        FACE_VARIANT_PASSAGE_PATCH_RULES,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    + ";"
)
EXPECTED_POST_I18N_EXECUTION = (
    f'(()=>{{const patchName="{POST_I18N_FACE_PATCH_MARKER}",'
    f"{EXPECTED_POST_I18N_RULES}"
    "for(const[passageName,oldContext,newContext]of patchRules){"
    "const passage=r.get(passageName);"
    "if(!passage?.content)"
    "throw new Error(`${patchName}: missing passage ${passageName}`);"
    "const contextCount=passage.content.split(oldContext).length-1;"
    "if(1!==contextCount)"
    "throw new Error(`${patchName}: ${passageName} context count ${contextCount}`);"
    "passage.content=passage.content.replace(oldContext,newContext);"
    "r.set(passageName,passage)}})();"
)


@dataclass
class AuContractReport:
    """Static half of the AU/framework face-source contract.

    The framework side is fully observable from the built artifact. The AU side is
    not, because the facial-expansion logic ships inside an opaque member, so an
    unobservable call-site count becomes an explicit ``runtime_query_required``
    obligation rather than a silent pass.
    """

    schema: str = AU_CONTRACT_SCHEMA
    framework_export_required: bool = False
    framework_face_style_src_fn_export_count: int = 0
    framework_variant_dir_shim_marker_count: int = 0
    framework_pet_remount_marker_count: int = 0
    au_payload_present: bool = False
    au_payload_boot_version: str = ""
    au_payload_runtime_identity: str = AU_PAYLOAD_RUNTIME_IDENTITY
    au_payload_opaque_members: list[str] = field(default_factory=list)
    au_payload_skipped_members: list[str] = field(default_factory=list)
    au_payload_scanned_members: list[str] = field(default_factory=list)
    # True only when the AU call sites themselves are readable. Readable README or
    # loader text does not count while the logic still sits behind a .crypt member.
    au_payload_logic_observable: bool = False
    au_variant_true_site_count: int = 0
    au_variant_true_sites_unobservable: bool = True
    runtime_query_required: bool = False
    legacy_naming_404_count: int | None = None
    defect_status: str = AU_DEFECT_STATUS
    defect_visual_status: str = AU_DEFECT_VISUAL_STATUS
    ab_verdict: str = AU_FACE_AB_VERDICT
    ab_evidence: str = AU_FACE_AB_EVIDENCE
    errors: list[str] = field(default_factory=list)


@dataclass
class AuArtifactResult:
    """Validation result for one built ZIP or APK artifact."""

    target: str
    is_au: bool
    success: bool = False
    nested_blush_count: int = 0
    outer_nested_blush_count: int = 0
    embedded_nested_blush_count: int = 0
    required_nested_blush_present: bool = False
    outer_required_nested_blush_present: bool = False
    embedded_required_nested_blush_present: bool = False
    face_variant_switch_marker_count: int = 0
    face_variant_migration_marker_count: int = 0
    post_i18n_patch_marker_count: int = 0
    numbered_nested_blush_layers: list[int] = field(default_factory=list)
    au_contract: AuContractReport = field(default_factory=AuContractReport)
    errors: list[str] = field(default_factory=list)


def _artifact_variant_from_filename(path: Path) -> str | None:
    """Return the declared base/AU variant from a built artifact filename."""
    normalized = path.name.lower().replace("_", "-")
    variant_tokens = {
        variant: f"-{variant}-"
        for variant in (*AU_MODEL_NAME_BY_VARIANT, "base")
    }
    matching_variants = [
        variant
        for variant, token in variant_tokens.items()
        if token in normalized
    ]
    if len(matching_variants) == 1:
        return matching_variants[0]
    return None


def _has_au_filename(path: Path) -> bool:
    return _artifact_variant_from_filename(path) in AU_MODEL_NAME_BY_VARIANT


def _embedded_mod_inventory(
    html_content: str,
) -> tuple[list[str | None], list[str], list[str]]:
    """Return all Maplebirch scripts and embedded mod names."""
    parsed = parse_mod_data_value_zip_list(html_content)
    if parsed.error_kind:
        return [], [], [
            "embedded mod list is unreadable: "
            f"{parsed.error_kind}: {parsed.error or ''}".rstrip()
        ]

    maplebirch_scripts: list[str | None] = []
    mod_names: list[str] = []
    inventory_errors: list[str] = []
    for index, entry in enumerate(parsed.entries):
        if not isinstance(entry, str):
            inventory_errors.append(
                f"embedded mod entry {index} is not a Base64 string"
            )
            continue
        try:
            payload = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as payload_zip:
                if "boot.json" not in payload_zip.namelist():
                    continue
                boot_json = parse_boot_json(
                    payload_zip.read("boot.json").decode("utf-8-sig")
                )
                mod_name = str(boot_json.get("name") or "").lower()
                mod_names.append(mod_name)
                if mod_name != MAPLEBIRCH_MOD_NAME:
                    continue
                if MAPLEBIRCH_FACE_PATCH_MEMBER not in payload_zip.namelist():
                    maplebirch_scripts.append(None)
                    continue
                maplebirch_scripts.append(
                    payload_zip.read(MAPLEBIRCH_FACE_PATCH_MEMBER).decode(
                        "utf-8",
                        errors="replace",
                    )
                )
        except Exception as exc:
            inventory_errors.append(
                f"embedded mod entry {index} is unreadable: "
                f"{type(exc).__name__}: {exc}"
            )
            continue

    return maplebirch_scripts, mod_names, inventory_errors


def _is_au_artifact(path: Path, html_content: str | None) -> bool:
    """Identify AU artifacts from either naming or embedded model identity."""
    if _has_au_filename(path):
        return True
    if html_content is None:
        return False
    _maplebirch_scripts, mod_names, _inventory_errors = (
        _embedded_mod_inventory(html_content)
    )
    return bool(AU_MODEL_NAMES & set(mod_names))


def _record_payload_identity_errors(
    result: AuArtifactResult,
    path: Path,
    mod_names: list[str],
) -> None:
    """Bind each public artifact variant to its required embedded AU payloads."""
    declared_variant = _artifact_variant_from_filename(path)
    embedded_model_names = [
        mod_name for mod_name in mod_names if mod_name in AU_MODEL_NAMES
    ]

    if declared_variant == "base":
        if embedded_model_names:
            result.errors.append(
                "base artifact contains AU model payloads: "
                + ", ".join(sorted(embedded_model_names))
            )
        if mod_names.count(AU_FACE_MOD_NAME):
            result.errors.append("base artifact contains the AU Face payload")
        return

    if declared_variant not in AU_MODEL_NAME_BY_VARIANT:
        result.errors.append(
            "release artifact filename must declare exactly one of "
            "base/au-f/au-m/au-a: "
            f"{path.name}"
        )
        return

    expected_model_name = AU_MODEL_NAME_BY_VARIANT[declared_variant]
    if embedded_model_names != [expected_model_name]:
        result.errors.append(
            f"{declared_variant} artifact must contain exactly the matching AU model "
            f"{expected_model_name!r}; found {sorted(embedded_model_names)}"
        )
    au_face_payload_count = mod_names.count(AU_FACE_MOD_NAME)
    if au_face_payload_count != 1:
        result.errors.append(
            f"{declared_variant} artifact must contain exactly one AU Face payload "
            f"{AU_FACE_MOD_NAME!r}; found {au_face_payload_count}"
        )


def _au_face_payload_probe(html_content: str) -> dict[str, object]:
    """Read the embedded AU facial-expansion payload as far as it is readable.

    The AU logic ships inside an opaque ``.crypt`` member, so the plaintext call
    sites that pass ``{ variant: true }`` are normally unobservable from a built
    artifact. Large binary members (the 5 MB loader wrapper) and unreadable members
    are recorded as opaque instead of being decoded.
    """
    parsed = parse_mod_data_value_zip_list(html_content)
    if parsed.error_kind:
        return {
            "present": False,
            "error": f"{parsed.error_kind}: {parsed.error or ''}".strip(),
        }

    for entry in parsed.entries:
        if not isinstance(entry, str):
            continue
        try:
            payload = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as payload_zip:
                if "boot.json" not in payload_zip.namelist():
                    continue
                boot_json = parse_boot_json(
                    payload_zip.read("boot.json").decode("utf-8-sig")
                )
                if str(boot_json.get("name") or "").lower() != AU_FACE_MOD_NAME:
                    continue

                opaque_members: list[str] = []
                skipped_members: list[str] = []
                scanned_members: list[str] = []
                variant_true_sites = 0
                export_sites = 0
                for item in payload_zip.infolist():
                    name = item.filename
                    if name.lower().endswith(AU_PAYLOAD_OPAQUE_SUFFIXES):
                        opaque_members.append(name)
                        continue
                    if item.file_size > AU_PAYLOAD_SCAN_MAX_BYTES:
                        skipped_members.append(name)
                        continue
                    try:
                        text = payload_zip.read(name).decode("utf-8")
                    except UnicodeDecodeError:
                        opaque_members.append(name)
                        continue
                    scanned_members.append(name)
                    variant_true_sites += len(AU_VARIANT_FLAG_RE.findall(text))
                    export_sites += text.count(FRAMEWORK_FACE_STYLE_EXPORT_NEEDLE)

                # The call sites are only trustworthy when the payload is fully
                # readable, or when a readable member actually carries them.
                logic_observable = (
                    not opaque_members
                    and not skipped_members
                ) or bool(variant_true_sites or export_sites)
                return {
                    "present": True,
                    "boot_version": str(boot_json.get("version") or ""),
                    "opaque_members": sorted(opaque_members),
                    "skipped_members": sorted(skipped_members),
                    "scanned_members": sorted(scanned_members),
                    "logic_observable": logic_observable,
                    "variant_true_sites": variant_true_sites,
                    "export_sites": export_sites,
                }
        except Exception:
            continue
    return {"present": False}


def _record_au_contract(
    result: AuArtifactResult,
    html_content: str | None,
    maplebirch_script: str,
) -> None:
    """Cross-assert the framework export against the AU facial-expansion needs.

    The fail-fast case the plan names is "framework side 0 while AU side references
    more than 0": the AU facial expansion calls ``faceStyleSrcFn`` at nine sites, so
    a payload that exports it zero times cannot serve an AU build.
    """
    contract = result.au_contract
    contract.framework_export_required = result.is_au
    contract.framework_face_style_src_fn_export_count = maplebirch_script.count(
        FRAMEWORK_FACE_STYLE_EXPORT_NEEDLE
    )
    contract.framework_variant_dir_shim_marker_count = maplebirch_script.count(
        MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER
    )
    contract.framework_pet_remount_marker_count = maplebirch_script.count(
        MAPLEBIRCH_PET_REMOUNT_MARKER
    )

    if html_content is not None:
        probe = _au_face_payload_probe(html_content)
        contract.au_payload_present = bool(probe.get("present"))
        contract.au_payload_boot_version = str(probe.get("boot_version") or "")
        contract.au_payload_opaque_members = list(
            probe.get("opaque_members") or ()
        )
        contract.au_payload_skipped_members = list(
            probe.get("skipped_members") or ()
        )
        contract.au_payload_scanned_members = list(
            probe.get("scanned_members") or ()
        )
        contract.au_payload_logic_observable = bool(probe.get("logic_observable"))
        contract.au_variant_true_site_count = int(
            probe.get("variant_true_sites") or 0
        )
        contract.au_variant_true_sites_unobservable = (
            not contract.au_payload_logic_observable
        )
        if probe.get("error"):
            contract.errors.append(f"AU payload probe failed: {probe['error']}")

    if not result.is_au:
        return

    if not contract.au_payload_present:
        contract.errors.append(
            "AU contract: the artifact carries no readable AU facial-expansion payload"
        )
    if contract.framework_face_style_src_fn_export_count == 0:
        contract.errors.append(
            "AU contract violation: the Maplebirch payload exports faceStyleSrcFn 0 "
            "times while the AU facial expansion calls it at nine sites "
            "(js/faceSelector.js and addon/svr.js); every flagged layer source throws "
            "'faceStyleSrcFn is not a function'. This is the measured 4.2.9 "
            "regression that moved the framework pin back to 4.1.14."
        )
    if (
        contract.framework_variant_dir_shim_marker_count
        != EXPECTED_AU_VARIANT_DIR_SHIM_MARKERS
    ):
        contract.errors.append(
            "AU contract: expected exactly "
            f"{EXPECTED_AU_VARIANT_DIR_SHIM_MARKERS} variant-directory priority shim "
            f"marker, found {contract.framework_variant_dir_shim_marker_count}"
        )
    contract.runtime_query_required = bool(
        result.is_au and contract.au_variant_true_sites_unobservable
    )
    result.errors.extend(contract.errors)


def _record_face_variant_markers(
    result: AuArtifactResult,
    html_name: str | None,
    html_content: str | None,
) -> None:
    """Record required HTML patch markers for one AU artifact."""
    if html_name is None or html_content is None:
        result.errors.append("AU artifact does not contain a readable HTML entry")
        return

    maplebirch_scripts, mod_names, inventory_errors = (
        _embedded_mod_inventory(html_content)
    )
    result.errors.extend(inventory_errors)
    _record_payload_identity_errors(result, Path(result.target), mod_names)
    if len(maplebirch_scripts) != 1:
        result.errors.append(
            "AU artifact must contain exactly one Maplebirch payload owner, found "
            f"{len(maplebirch_scripts)}"
        )
        return
    maplebirch_script = maplebirch_scripts[0]
    if maplebirch_script is None:
        result.errors.append(
            "AU artifact Maplebirch payload does not contain a readable patch member"
        )
        return

    _record_au_contract(result, html_content, maplebirch_script)

    result.face_variant_switch_marker_count = maplebirch_script.count(
        FACE_VARIANT_SWITCH_MARKER
    )
    result.face_variant_migration_marker_count = maplebirch_script.count(
        FACE_VARIANT_MIGRATION_MARKER
    )
    result.post_i18n_patch_marker_count = maplebirch_script.count(
        POST_I18N_FACE_PATCH_MARKER
    )

    expected_rule_count = maplebirch_script.count(EXPECTED_POST_I18N_RULES)
    if expected_rule_count != 1:
        result.errors.append(
            "AU post-ModI18N face patch rules are missing or misplaced: "
            f"context count {expected_rule_count}"
        )
    execution_count = maplebirch_script.count(EXPECTED_POST_I18N_EXECUTION)
    if execution_count != 1:
        result.errors.append(
            "AU post-ModI18N face patch execution is missing or misplaced: "
            f"context count {execution_count}"
        )
    owner_context_count = maplebirch_script.count(
        MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW
    )
    obsolete_owner_context_count = maplebirch_script.count(
        MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD
    )
    if owner_context_count != 1:
        result.errors.append(
            "AU post-ModI18N face patch is outside the Maplebirch owner: "
            f"context count {owner_context_count}"
        )
    if obsolete_owner_context_count:
        result.errors.append(
            "unpatched Maplebirch modifyFaceStyle owner remains: "
            f"context count {obsolete_owner_context_count}"
        )

    normalized_html_content = html_content.replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    escaped_legacy_switch_contexts = [
        html.escape(context, quote=False)
        for context in LEGACY_FACE_VARIANT_SWITCH_CONTEXTS
    ]
    escaped_patched_switch_contexts = [
        html.escape(context, quote=False) for context in FACE_VARIANT_SWITCH_CONTEXTS
    ]
    source_switch_context_counts = [
        normalized_html_content.count(context)
        for context in escaped_legacy_switch_contexts
    ]
    obsolete_switch_context_counts = [
        normalized_html_content.count(context)
        for context in escaped_patched_switch_contexts
    ]
    source_migration_context_count = normalized_html_content.count(
        html.escape(LEGACY_FACE_VARIANT_MIGRATION_CONTEXT, quote=False)
    )
    obsolete_migration_context_count = normalized_html_content.count(
        html.escape(FACE_VARIANT_MIGRATION_CONTEXT, quote=False)
    )
    if source_switch_context_counts != [1] * EXPECTED_FACE_VARIANT_SWITCH_MARKERS:
        result.errors.append(
            "AU ModI18N source face-style contexts are missing or changed: "
            f"context counts {source_switch_context_counts}"
        )
    if any(obsolete_switch_context_counts):
        result.errors.append(
            "obsolete pre-ModI18N face-style patch remains in AU HTML: "
            f"context counts {obsolete_switch_context_counts}"
        )
    if source_migration_context_count != EXPECTED_FACE_VARIANT_MIGRATION_MARKERS:
        result.errors.append(
            "AU ModI18N source backComp context is missing or changed: "
            f"context count {source_migration_context_count}"
        )
    if obsolete_migration_context_count:
        result.errors.append(
            "obsolete pre-ModI18N backComp patch remains in AU HTML"
        )


def _record_required_errors(result: AuArtifactResult) -> None:
    """Apply shared AU resource and HTML patch requirements."""
    if not result.required_nested_blush_present:
        result.errors.append(
            "missing required AU face alias: "
            f"{CURRENT_REQUIRED_NESTED_BLUSH}, {LEGACY_REQUIRED_NESTED_BLUSH}, "
            "or an embedded equivalent"
        )
    missing_blush_layers = sorted(
        REQUIRED_NUMBERED_NESTED_BLUSH_LAYERS
        - set(result.numbered_nested_blush_layers)
    )
    if missing_blush_layers:
        result.errors.append(
            "expected distinct numbered nested AU blush layers 1-5; missing "
            + ", ".join(str(layer) for layer in missing_blush_layers)
        )
    if (
        result.face_variant_switch_marker_count
        != EXPECTED_FACE_VARIANT_SWITCH_MARKERS
    ):
        result.errors.append(
            "expected exactly "
            f"{EXPECTED_FACE_VARIANT_SWITCH_MARKERS} AU face-style switch markers, "
            f"found {result.face_variant_switch_marker_count}"
        )
    if (
        result.face_variant_migration_marker_count
        != EXPECTED_FACE_VARIANT_MIGRATION_MARKERS
    ):
        result.errors.append(
            "expected exactly one AU old-save face migration marker, found "
            f"{result.face_variant_migration_marker_count}"
        )
    if result.post_i18n_patch_marker_count != 1:
        result.errors.append(
            "expected exactly one AU post-ModI18N payload marker, found "
            f"{result.post_i18n_patch_marker_count}"
        )


def _is_numbered_default_blush(name: str) -> bool:
    """Return whether a member is a numbered nested blush layer.

    Official AU assets provide blush-1.png through blush-5.png plus the
    independent blusher.png asset. The latter is not a numbered blush layer.
    Legacy payloads may still use the unhyphenated blush1.png spelling.
    """
    return _default_blush_layer_number(name) is not None


def _default_blush_layer_number(name: str) -> int | None:
    """Return a nested blush layer number, ignoring non-numbered assets."""
    normalized = name.replace("\\", "/").lower()
    match = re.search(
        r"(?:^|/)img/face/default/default/blush-?(\d+)\.png$",
        normalized,
    )
    return int(match.group(1)) if match else None


def _is_required_embedded_default_blush(name: str) -> bool:
    normalized = name.replace("\\", "/").lower()
    return _is_numbered_default_blush(normalized) and (
        normalized.endswith("/blush-1.png") or normalized.endswith("/blush1.png")
    )


def _is_outer_default_blush(name: str) -> bool:
    normalized = name.replace("\\", "/").lower()
    return bool(
        re.fullmatch(
            r"img/face/default/default/blush-?\d+\.png",
            normalized,
        )
    )


def _is_required_outer_default_blush(name: str) -> bool:
    normalized = name.replace("\\", "/").lower()
    return normalized in {
        CURRENT_REQUIRED_NESTED_BLUSH,
        LEGACY_REQUIRED_NESTED_BLUSH,
    }


def _embedded_mod_member_names(zip_path: Path) -> set[str]:
    """Return readable member names from embedded ModLoader ZIP payloads."""
    try:
        _html_name, html_content = load_preferred_html_from_zip(zip_path)
    except (FileNotFoundError, zipfile.BadZipFile):
        return set()
    if html_content is None:
        return set()

    parsed = parse_mod_data_value_zip_list(html_content)
    if parsed.error_kind:
        return set()

    names: set[str] = set()
    for entry in parsed.entries:
        if not isinstance(entry, str):
            continue
        try:
            payload = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
                names.update(zf.namelist())
        except Exception:
            continue
    return names


def audit_zip_artifact(zip_path: Path) -> AuArtifactResult:
    """Check one ZIP artifact for AU nested blush aliases."""
    zip_path = Path(zip_path)
    if not zip_path.exists():
        result = AuArtifactResult(
            target=str(zip_path),
            is_au=_has_au_filename(zip_path),
        )
        result.errors.append(f"ZIP artifact does not exist: {zip_path}")
        return result

    try:
        html_name, html_content = load_preferred_html_from_zip(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            outer_names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        result = AuArtifactResult(
            target=str(zip_path),
            is_au=_has_au_filename(zip_path),
        )
        result.errors.append(f"ZIP artifact is invalid: {exc}")
        return result

    result = AuArtifactResult(
        target=str(zip_path),
        is_au=_is_au_artifact(zip_path, html_content),
    )
    if not result.is_au:
        _maplebirch_scripts, mod_names, inventory_errors = (
            _embedded_mod_inventory(html_content or "")
        )
        result.errors.extend(inventory_errors)
        _record_payload_identity_errors(result, zip_path, mod_names)
        result.success = not result.errors
        return result

    outer_nested_blush = sorted(
        name
        for name in outer_names
        if _is_outer_default_blush(name)
    )
    embedded_names = _embedded_mod_member_names(zip_path)
    embedded_nested_blush = sorted(
        name for name in embedded_names if _is_numbered_default_blush(name)
    )
    outer_blush_layers = {
        layer
        for name in outer_nested_blush
        if (layer := _default_blush_layer_number(name)) is not None
    }
    embedded_blush_layers = {
        layer
        for name in embedded_nested_blush
        if (layer := _default_blush_layer_number(name)) is not None
    }

    result.outer_nested_blush_count = len(outer_blush_layers)
    result.embedded_nested_blush_count = len(embedded_blush_layers)
    result.numbered_nested_blush_layers = sorted(
        outer_blush_layers | embedded_blush_layers
    )
    result.nested_blush_count = len(result.numbered_nested_blush_layers)
    result.outer_required_nested_blush_present = any(
        _is_required_outer_default_blush(name) for name in outer_nested_blush
    )
    result.embedded_required_nested_blush_present = any(
        _is_required_embedded_default_blush(name) for name in embedded_nested_blush
    )
    result.required_nested_blush_present = (
        result.outer_required_nested_blush_present
        or result.embedded_required_nested_blush_present
    )
    _record_face_variant_markers(result, html_name, html_content)
    _record_required_errors(result)

    result.success = not result.errors
    return result


def audit_apk_artifact(apk_path: Path) -> AuArtifactResult:
    """Check one APK artifact for AU aliases and face-variant patch markers."""
    apk_path = Path(apk_path)
    if not apk_path.exists():
        result = AuArtifactResult(
            target=str(apk_path),
            is_au=_has_au_filename(apk_path),
        )
        result.errors.append(f"APK artifact does not exist: {apk_path}")
        return result

    try:
        html_name, html_content = load_html_from_apk(apk_path)
        with zipfile.ZipFile(apk_path, "r") as archive:
            member_names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        result = AuArtifactResult(
            target=str(apk_path),
            is_au=_has_au_filename(apk_path),
        )
        result.errors.append(f"APK artifact is invalid: {exc}")
        return result


    result = AuArtifactResult(
        target=str(apk_path),
        is_au=_is_au_artifact(apk_path, html_content),
    )
    if not result.is_au:
        _maplebirch_scripts, mod_names, inventory_errors = (
            _embedded_mod_inventory(html_content or "")
        )
        result.errors.extend(inventory_errors)
        _record_payload_identity_errors(result, apk_path, mod_names)
        result.success = not result.errors
        return result

    nested_blush = sorted(
        name for name in member_names if _is_numbered_default_blush(name)
    )
    blush_layers = {
        layer
        for name in nested_blush
        if (layer := _default_blush_layer_number(name)) is not None
    }
    result.outer_nested_blush_count = len(blush_layers)
    result.numbered_nested_blush_layers = sorted(blush_layers)
    result.nested_blush_count = len(blush_layers)
    result.outer_required_nested_blush_present = any(
        _is_required_embedded_default_blush(name) for name in nested_blush
    )
    result.required_nested_blush_present = (
        result.outer_required_nested_blush_present
    )

    _record_face_variant_markers(result, html_name, html_content)
    _record_required_errors(result)
    result.success = not result.errors
    return result


def audit_target(path: Path) -> list[AuArtifactResult]:
    """Audit one ZIP/APK artifact or every artifact under a directory."""
    path = Path(path)
    if path.is_dir():
        candidates = sorted(
            [*path.rglob("*.zip"), *path.rglob("*.apk")],
            key=lambda item: str(item).lower(),
        )
        if not candidates:
            return [
                AuArtifactResult(
                    target=str(path),
                    is_au=False,
                    errors=["directory contains no ZIP or APK artifacts"],
                )
            ]
        return [
            audit_apk_artifact(candidate)
            if candidate.suffix.lower() == ".apk"
            else audit_zip_artifact(candidate)
            for candidate in candidates
        ]

    if path.suffix.lower() == ".apk":
        return [audit_apk_artifact(path)]
    return [audit_zip_artifact(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AU aliases and face patches in ZIP/APK artifacts")
    parser.add_argument("target", type=Path, help="ZIP/APK artifact or artifact directory")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    results = audit_target(args.target)
    payload = [asdict(result) for result in results]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    for result in results:
        if not result.is_au:
            continue
        contract = result.au_contract
        print(
            "au-contract "
            f"framework_faceStyleSrcFn={contract.framework_face_style_src_fn_export_count} "
            f"variant_dir_shim={contract.framework_variant_dir_shim_marker_count} "
            f"pet_remount={contract.framework_pet_remount_marker_count} "
            f"au_payload={'plaintext' if contract.au_payload_logic_observable else 'opaque'} "
            f"variant_true_sites="
            f"{'unobservable' if contract.au_variant_true_sites_unobservable else contract.au_variant_true_site_count} "
            f"runtime_query_required={contract.runtime_query_required} "
            f"legacy_naming_404={contract.legacy_naming_404_count} "
            f"defect_status={contract.defect_status} "
            f"visual_status={contract.defect_visual_status} "
            f"ab_verdict={contract.ab_verdict}",
            file=sys.stderr,
        )

    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
