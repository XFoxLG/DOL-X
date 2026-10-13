#!/usr/bin/env python3
"""Verify a Maplebirch payload against the content-derived contract matrix.

The framework repository deletes tags and rewrites release metadata, so a version
identity is never taken from a filename or a tag string. This tool reads the
payload itself - ``boot.json`` version and GameVersion floor, the
``faceStyleSrcFn`` export, and the fail-closed build-patch needles - and compares
that content fingerprint with ``config/framework-contract-matrix.toml``.

Fail-closed: an unknown fingerprint, a fingerprint that contradicts the metadata
version, or a mismatch against the registered row all exit non-zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sweep_ledger import atomic_write_json


SCHEMA = "dolx.framework_contract_check.v1"
DEFAULT_MATRIX = Path("config/framework-contract-matrix.toml")
BOOT_MEMBER = "boot.json"
SCRIPT_MEMBER = "dist/inject_early.js"
PASS = "consistent"
FAIL_VERDICTS = (
    "content_version_mismatch",
    "unregistered_version",
    "matrix_mismatch",
    "infrastructure_fail",
)


def _needles() -> tuple[dict[str, str], str | None]:
    """Return the build-patch needles plus an import error, when there is one."""
    try:
        from lyra.build import (
            MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
            MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD,
            MAPLEBIRCH_PET_REMOUNT_OLD,
        )
    except Exception as exc:  # pragma: no cover - depends on the environment
        return {}, f"{type(exc).__name__}: {exc}"
    return (
        {
            "maplebirch_au_variant_dir_priority": (
                MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD
            ),
            "maplebirch_au_face_variant_insertion": (
                MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD
            ),
            "maplebirch_pet_remount": MAPLEBIRCH_PET_REMOUNT_OLD,
        },
        None,
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_matrix(path: Path) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        matrix = tomllib.load(handle)
    if matrix.get("schema") != "dolx.framework-contract-matrix.v1":
        raise ValueError(f"{path}: unexpected matrix schema")
    if not matrix.get("candidates"):
        raise ValueError(f"{path}: matrix has no candidates")
    return matrix


def game_version_floor(boot: Mapping[str, Any]) -> str | None:
    for dependency in boot.get("dependenceInfo") or ():
        if dependency.get("modName") == "GameVersion":
            return str(dependency.get("version") or "") or None
    return None


def read_payload(path: Path) -> dict[str, Any]:
    """Extract the content fingerprint of one Maplebirch payload."""
    raw = Path(path).read_bytes()
    facts: dict[str, Any] = {
        "path": str(path),
        "filename": Path(path).name,
        "bytes": len(raw),
        "sha256": _sha256(raw),
    }
    needles, needle_error = _needles()
    facts["needle_source"] = "lyra.build" if needles else "unavailable"
    if needle_error:
        facts["needle_source_error"] = needle_error

    try:
        with zipfile.ZipFile(path, "r") as payload:
            members = payload.namelist()
            facts["members"] = sorted(members)
            if BOOT_MEMBER not in members:
                facts["status"] = "infrastructure_fail"
                facts["error"] = f"{BOOT_MEMBER} is missing from the payload"
                return facts
            boot = json.loads(payload.read(BOOT_MEMBER).decode("utf-8", "replace"))
            facts["boot_name"] = boot.get("name")
            facts["boot_version"] = boot.get("version")
            facts["game_version_floor"] = game_version_floor(boot)
            if SCRIPT_MEMBER not in members:
                facts["status"] = "infrastructure_fail"
                facts["error"] = f"{SCRIPT_MEMBER} is missing from the payload"
                return facts
            script = payload.read(SCRIPT_MEMBER).decode("utf-8", "replace")
    except zipfile.BadZipFile as exc:
        facts["status"] = "infrastructure_fail"
        facts["error"] = f"not a zip: {exc}"
        return facts

    facts["face_style_src_fn_count"] = script.count("faceStyleSrcFn")
    facts["face_style_src_fn_export"] = facts["face_style_src_fn_count"] > 0
    facts["dist_signature_present"] = (
        'function aD(e){let t="function"==typeof e?e:()=>e;' in script
    )
    facts["needle_hits"] = {
        name: script.count(needle) for name, needle in needles.items()
    }
    facts["status"] = "read"
    return facts


def _compare(row: Mapping[str, Any], facts: Mapping[str, Any]) -> list[str]:
    mismatches: list[str] = []

    def check(field: str, fact_field: str | None = None) -> None:
        expected = row.get(field)
        if expected is None or expected == "":
            return
        actual = facts.get(fact_field or field)
        if actual != expected:
            mismatches.append(f"{field}: expected {expected!r}, got {actual!r}")

    check("asset_sha256", "sha256")
    check("asset_bytes", "bytes")
    check("game_version_floor")
    check("face_style_src_fn_export")
    check("payload_face_style_src_fn_count", "face_style_src_fn_count")

    expected_hits = row.get("needle_hits")
    if expected_hits:
        actual_hits = facts.get("needle_hits") or {}
        for name, expected in expected_hits.items():
            actual = actual_hits.get(name)
            if actual != expected:
                mismatches.append(
                    f"needle_hits[{name}]: expected {expected!r}, got {actual!r}"
                )
    return mismatches


def classify_payload(
    facts: Mapping[str, Any],
    matrix: Mapping[str, Any],
    *,
    expect_version: str | None = None,
) -> dict[str, Any]:
    """Resolve the content-derived version and compare it with the matrix."""
    result = dict(facts)
    result["mismatches"] = []

    if facts.get("status") != "read":
        result["verdict"] = "infrastructure_fail"
        return result

    boot_version = facts.get("boot_version")
    candidates = list(matrix.get("candidates") or ())
    row = next(
        (item for item in candidates if item.get("claimed_metadata_version") == boot_version),
        None,
    )
    if row is None:
        result["verdict"] = "unregistered_version"
        result["detail"] = (
            f"no matrix candidate claims metadata version {boot_version!r}"
        )
        return result

    result["matrix_version"] = row.get("version")
    result["content_verdict"] = row.get("content_verdict")

    mismatches = _compare(row, facts)
    result["mismatches"] = mismatches

    if mismatches:
        result["verdict"] = "matrix_mismatch"
        return result

    if row.get("content_verdict") != "consistent":
        # The row itself says the metadata version does not describe the content.
        result["verdict"] = "content_version_mismatch"
        result["detail"] = (
            f"tag/metadata claims {boot_version} but the content fingerprint "
            f"matches the {row.get('version')} era ({row.get('notes', '')})"
        )
        return result

    if expect_version is not None and row.get("version") != expect_version:
        result["verdict"] = "content_version_mismatch"
        result["detail"] = (
            f"expected version {expect_version!r}, content says {row.get('version')!r}"
        )
        return result

    result["verdict"] = PASS
    return result


def find_asset(matrix: Mapping[str, Any], row: Mapping[str, Any], root: Path) -> Path | None:
    pattern = str(row.get("asset_pattern") or "")
    if not pattern:
        return None
    search_dirs = (matrix.get("assets") or {}).get("search_dirs") or ()
    for relative in search_dirs:
        candidate = root / str(relative) / pattern
        if candidate.exists():
            return candidate
    return None


def self_check(matrix: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Verify every held row against the payload it is supposed to describe."""
    rows = []
    for row in matrix.get("candidates") or ():
        if not row.get("asset_held"):
            continue
        asset = find_asset(matrix, row, root)
        entry: dict[str, Any] = {
            "version": row.get("version"),
            "asset_pattern": row.get("asset_pattern"),
            "found": asset is not None,
        }
        if asset is None:
            entry["verdict"] = "asset_not_found"
            rows.append(entry)
            continue
        entry["asset_path"] = str(asset)
        facts = read_payload(asset)
        if facts.get("status") != "read":
            entry["verdict"] = "infrastructure_fail"
            entry["error"] = facts.get("error")
            rows.append(entry)
            continue
        mismatches = _compare(row, facts)
        entry["mismatches"] = mismatches
        entry["sha256"] = facts.get("sha256")
        entry["verdict"] = PASS if not mismatches else "matrix_mismatch"
        rows.append(entry)
    required = sum(1 for row in matrix.get("candidates") or () if row.get("asset_held"))
    checked = sum(1 for row in rows if row.get("verdict") == PASS)
    return {
        "required": required,
        "checked": checked,
        "rows": rows,
        "verdict": PASS if required == checked else "matrix_mismatch",
    }


def build_report(
    matrix_path: Path,
    payloads: Iterable[Path],
    *,
    root: Path,
    expect_version: str | None = None,
    run_self_check: bool = False,
) -> dict[str, Any]:
    matrix = load_matrix(matrix_path)
    rows = []
    for payload in payloads:
        facts = read_payload(payload)
        rows.append(
            classify_payload(facts, matrix, expect_version=expect_version)
        )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "matrix": str(matrix_path),
        "matrix_schema": matrix.get("schema"),
        "locked_version": matrix.get("locked_version"),
        "game_version_in_use": matrix.get("game_version_in_use"),
        "payloads": rows,
    }
    if run_self_check:
        report["self_check"] = self_check(matrix, root)
    checks = [row["verdict"] for row in rows]
    if run_self_check:
        checks.append(report["self_check"]["verdict"])
    report["verdict"] = PASS if checks and all(item == PASS for item in checks) else "fail"
    report["failures"] = [
        {"path": row.get("path"), "verdict": row["verdict"], "detail": row.get("detail")}
        for row in rows
        if row["verdict"] != PASS
    ]
    return report


def write_report(payload: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "framework-contract-check.json"
    md_path = out_dir / "framework-contract-check.md"
    atomic_write_json(json_path, payload)

    lines = [
        "# Framework contract check",
        "",
        f"- matrix: `{payload.get('matrix')}`",
        f"- locked version: `{payload.get('locked_version')}`",
        f"- game version in use: `{payload.get('game_version_in_use')}`",
        f"- verdict: **{payload.get('verdict')}**",
        "",
        "| payload | sha256 | content version | verdict | detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("payloads", ()):
        lines.append(
            "| `{name}` | `{sha}` | `{version}` | {verdict} | {detail} |".format(
                name=row.get("filename", ""),
                sha=str(row.get("sha256", ""))[:12],
                version=row.get("matrix_version") or row.get("boot_version") or "?",
                verdict=row.get("verdict"),
                detail=(row.get("detail") or "").replace("|", "/"),
            )
        )
    self_check_row = payload.get("self_check")
    if self_check_row:
        lines += [
            "",
            "## Self check",
            "",
            f"- held assets verified: {self_check_row.get('checked')}"
            f"/{self_check_row.get('required')}"
            f" ({self_check_row.get('verdict')})",
        ]
        for row in self_check_row.get("rows", ()):
            lines.append(
                f"- `{row.get('asset_pattern')}` -> {row.get('verdict')}"
                + (
                    f" ({'; '.join(row.get('mismatches') or [])})"
                    if row.get("mismatches")
                    else ""
                )
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "payloads",
        nargs="*",
        type=Path,
        help="Maplebirch payload .mod.zip files to verify",
    )
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--expect-version",
        default=None,
        help="fail unless the content-derived version equals this value",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="also verify the locally held payloads named by the matrix",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--out", type=Path, default=Path(".local/framework-contract"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.payloads and not args.self_check:
        print("nothing to check: pass payloads, --self-check, or both", file=sys.stderr)
        return 2
    try:
        report = build_report(
            args.matrix,
            args.payloads,
            root=args.repo_root,
            expect_version=args.expect_version,
            run_self_check=args.self_check,
        )
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"framework contract check failed: {exc}", file=sys.stderr)
        return 2
    json_path, _ = write_report(report, args.out)
    for row in report["payloads"]:
        print(
            f"{row.get('filename')}: {row['verdict']} "
            f"(content version {row.get('matrix_version') or '?'})"
        )
    if "self_check" in report:
        print(
            "self-check: "
            f"{report['self_check']['checked']}/{report['self_check']['required']} "
            f"-> {report['self_check']['verdict']}"
        )
    print(f"report: {json_path}")
    return 0 if report["verdict"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
