#!/usr/bin/env python3
"""Fail-closed identity check for a sweep target package.

The 2026-10-06 CI daily run exposed two carrier defects: the workflow called
``main.py prepare`` without ``--tag`` (so the runner built the then-latest
0.5.12.13 instead of the locked 0.5.11.9 stack) and it uploaded only the raw
prepare HTML (which embeds the ModLoader base payloads + ModI18N but none of
the DOL-X mods). Both classes of defect are silent: the sweeps still boot and
still produce "ok" verdicts, they just measure a different product.

This tool pins the carrier identity before any shard spends browser time:

* game version marker ``StartConfig.version`` must match ``--expect-version``
* every ``--expect`` mod name must exist among the embedded ModLoader payloads
* ``--min-mods`` guards against a payload list that lost entries entirely

It writes the decoded inventory next to the run so downstream reports can
carry the same identity.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):  # allow ``python tools/target_package_check.py``
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.artifact_inspection import (  # noqa: E402
    decode_base64_payload,
    load_html_artifact,
    parse_boot_json,
    parse_mod_data_value_zip_list,
)

START_CONFIG_VERSION_RE = re.compile(
    r"StartConfig\s*=\s*\{(?P<body>.*?)\};", re.DOTALL
)
VERSION_FIELD_RE = re.compile(r"version\s*:\s*\"(?P<version>[^\"]+)\"")


def normalize_name(name: str) -> str:
    """Lowercase and strip separators so mod names compare across sources."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def game_version_marker(html: str) -> str | None:
    """Return ``StartConfig.version`` from a built HTML payload."""
    match = START_CONFIG_VERSION_RE.search(html)
    if not match:
        return None
    field = VERSION_FIELD_RE.search(match.group("body"))
    return field.group("version") if field else None


def embedded_mods(html: str) -> tuple[list[dict[str, Any]], list[str], int | None]:
    """Decode every embedded ModLoader payload into name/version records."""
    parsed = parse_mod_data_value_zip_list(html)
    if parsed.error_kind:
        detail = f"{parsed.error_kind}: {parsed.error or ''}".strip()
        return [], [detail], None
    mods: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, entry in enumerate(parsed.entries):
        if not isinstance(entry, str):
            errors.append(f"embedded entry {index} is not a base64 string")
            continue
        try:
            payload = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                if "boot.json" not in zf.namelist():
                    continue
                boot = parse_boot_json(zf.read("boot.json").decode("utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - report, never crash the check.
            errors.append(f"embedded entry {index} unreadable: {type(exc).__name__}: {exc}")
            continue
        mods.append(
            {
                "index": index,
                "name": str(boot.get("name") or ""),
                "nickname": boot.get("nickName"),
                "version": boot.get("version"),
            }
        )
    return mods, errors, len(parsed.entries)


def check_package(
    target: Path,
    *,
    expect_mods: Iterable[str] = (),
    expect_version: str | None = None,
    min_mods: int | None = None,
) -> dict[str, Any]:
    member, html = load_html_artifact(target)
    if html is None:
        return {
            "target": str(target),
            "ok": False,
            "errors": [f"no readable HTML found in {target.name}"],
        }
    version = game_version_marker(html)
    mods, errors, list_length = embedded_mods(html)
    normalized = {normalize_name(mod["name"]) for mod in mods}
    missing = [
        name for name in expect_mods if normalize_name(name) not in normalized
    ]
    if expect_version and version != expect_version:
        errors.append(
            f"game version mismatch: StartConfig.version={version!r}, "
            f"expected {expect_version!r}"
        )
    if min_mods is not None and len(mods) < int(min_mods):
        errors.append(f"embedded mod payloads {len(mods)} < required {int(min_mods)}")
    if missing:
        errors.append("missing expected mods: " + ", ".join(missing))
    return {
        "target": str(target),
        "html_member": member,
        "game_version": version,
        "list_length": list_length,
        "mod_count": len(mods),
        "mods": mods,
        "expected_mods": list(expect_mods),
        "missing_mods": missing,
        "errors": errors,
        "ok": not errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", type=Path, help="built .zip /.html / .apk package")
    parser.add_argument(
        "--expect",
        default="",
        help="comma-separated mod names that must be embedded (case/space insensitive)",
    )
    parser.add_argument(
        "--expect-version",
        default=None,
        help="required StartConfig.version marker, e.g. 0.5.11.9",
    )
    parser.add_argument("--min-mods", type=int, default=None)
    parser.add_argument(
        "--write-manifest",
        type=Path,
        default=None,
        help="write the decoded inventory here (JSON)",
    )
    parser.add_argument("--print", action="store_true", dest="dump", help="print inventory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    expect_mods = [item.strip() for item in str(args.expect or "").split(",") if item.strip()]
    report = check_package(
        args.target,
        expect_mods=expect_mods,
        expect_version=args.expect_version,
        min_mods=args.min_mods,
    )
    if args.write_manifest:
        args.write_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.write_manifest.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.dump or not report["ok"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[target-check] ok version={report['game_version']} "
            f"mods={report['mod_count']} -> {args.target.name}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
