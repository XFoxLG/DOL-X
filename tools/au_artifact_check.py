#!/usr/bin/env python3
"""Artifact-level AU face alias checks for built ZIP packages."""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.artifact_inspection import (
    decode_base64_payload,
    load_preferred_html_from_zip,
    parse_mod_data_value_zip_list,
)


REQUIRED_NESTED_BLUSH = "img/face/default/default/blush1.png"


@dataclass
class AuArtifactResult:
    """Validation result for one built ZIP artifact."""

    target: str
    is_au: bool
    success: bool = False
    nested_blush_count: int = 0
    outer_nested_blush_count: int = 0
    embedded_nested_blush_count: int = 0
    required_nested_blush_present: bool = False
    outer_required_nested_blush_present: bool = False
    embedded_required_nested_blush_present: bool = False
    errors: list[str] = field(default_factory=list)


def _is_au_zip(path: Path) -> bool:
    normalized = path.name.lower().replace("_", "-")
    return any(token in normalized for token in ("-au-f-", "-au-m-", "-au-a-"))


def _is_embedded_default_blush(name: str) -> bool:
    normalized = name.replace("\\", "/").lower()
    return (
        "/img/face/default/default/blush" in normalized
        and normalized.endswith(".png")
    )


def _is_required_embedded_default_blush(name: str) -> bool:
    normalized = name.replace("\\", "/").lower()
    return _is_embedded_default_blush(normalized) and (
        normalized.endswith("/blush-1.png") or normalized.endswith("/blush1.png")
    )


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
    result = AuArtifactResult(target=str(zip_path), is_au=_is_au_zip(zip_path))

    if not result.is_au:
        result.success = True
        return result

    if not zip_path.exists():
        result.errors.append(f"ZIP artifact does not exist: {zip_path}")
        return result

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            outer_names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        result.errors.append(f"ZIP artifact is invalid: {exc}")
        return result

    outer_nested_blush = sorted(
        name
        for name in outer_names
        if name.startswith("img/face/default/default/blush") and name.endswith(".png")
    )
    embedded_names = _embedded_mod_member_names(zip_path)
    embedded_nested_blush = sorted(
        name for name in embedded_names if _is_embedded_default_blush(name)
    )

    result.outer_nested_blush_count = len(outer_nested_blush)
    result.embedded_nested_blush_count = len(embedded_nested_blush)
    result.nested_blush_count = result.outer_nested_blush_count + result.embedded_nested_blush_count
    result.outer_required_nested_blush_present = REQUIRED_NESTED_BLUSH in outer_names
    result.embedded_required_nested_blush_present = any(
        _is_required_embedded_default_blush(name) for name in embedded_nested_blush
    )
    result.required_nested_blush_present = (
        result.outer_required_nested_blush_present
        or result.embedded_required_nested_blush_present
    )

    if not result.required_nested_blush_present:
        result.errors.append(
            f"missing required AU face alias: {REQUIRED_NESTED_BLUSH} "
            "or embedded */img/face/default/default/blush-1.png"
        )
    if result.nested_blush_count < 6:
        result.errors.append(
            f"expected at least 6 nested AU blush aliases, found {result.nested_blush_count}"
        )

    result.success = not result.errors
    return result


def audit_target(path: Path) -> list[AuArtifactResult]:
    """Audit a ZIP artifact or every ZIP under a directory."""
    path = Path(path)
    if path.is_dir():
        candidates = sorted(path.rglob("*.zip"), key=lambda item: str(item).lower())
        if not candidates:
            return [
                AuArtifactResult(
                    target=str(path),
                    is_au=False,
                    errors=["directory contains no ZIP artifacts"],
                )
            ]
        return [audit_zip_artifact(candidate) for candidate in candidates]

    return [audit_zip_artifact(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AU nested blush aliases in ZIP artifacts")
    parser.add_argument("target", type=Path, help="ZIP artifact or directory containing ZIP artifacts")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    results = audit_target(args.target)
    payload = [asdict(result) for result in results]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
