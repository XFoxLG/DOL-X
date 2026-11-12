#!/usr/bin/env python3
"""Reject shipped AU payloads at public artifact upload boundaries.

Local packaging and compatibility tests stay available. AU's author forbids
redistribution; the separately authored face extension has no confirmed grant.
The reviewed source and scope are recorded in docs/DISTRIBUTION_POLICY.md.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.artifact_inspection import (
    collect_string_values,
    decode_base64_payload,
    load_html_artifact,
    parse_boot_json,
    parse_mod_data_value_zip_list,
)


RESTRICTED_MODS = {
    "【aufemale】model": "author-prohibits-redistribution",
    "【aumale】model": "author-prohibits-redistribution",
    "【auandrogynous】model": "author-prohibits-redistribution",
    "【ausdol】facial expansion": "redistribution-permission-unconfirmed",
    "au面部扩展": "redistribution-permission-unconfirmed",
}


def check_artifact(target: Path) -> list[dict]:
    _, html = load_html_artifact(target)
    if html is None:
        raise ValueError("Game HTML not found")
    parsed = parse_mod_data_value_zip_list(html)
    if parsed.error_kind:
        raise ValueError("ModLoader payload inspection failed: " + parsed.error_kind)
    findings = []
    for value in collect_string_values(parsed.entries):
        raw = decode_base64_payload(value)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            boots = [name for name in archive.namelist() if Path(name).name == "boot.json"]
            if not boots:
                raise ValueError("Embedded mod has no boot.json")
            for member in boots:
                boot = parse_boot_json(archive.read(member).decode("utf-8-sig"))
                name = boot["name"]
                reason = RESTRICTED_MODS.get(name.casefold())
                if reason:
                    findings.append({"artifact": target.name, "mod": name, "version": boot["version"], "rule": reason})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    files = []
    for path in args.paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.iterdir() if p.is_file() and p.suffix.casefold() in (".zip", ".apk", ".html")))
        else:
            files.append(path)
    if not files:
        print(json.dumps({"passed": False, "rule": "no-artifacts-to-inspect"}))
        return 2
    findings = []
    errors = []
    for path in files:
        try:
            findings.extend(check_artifact(path))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            errors.append({"artifact": path.name, "rule": "artifact-inspection-failed", "error_type": type(exc).__name__})
    print(json.dumps({"passed": not findings and not errors, "artifacts": len(files), "findings": findings, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if findings or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
