#!/usr/bin/env python3
"""Scan embedded ModLoader payload source files inside built HTML/ZIP artifacts."""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


MOD_LIST_PATTERN = re.compile(
    r"window\.modDataValueZipList\s*=\s*(\[.*?\]);",
    re.DOTALL,
)

TEXT_SUFFIXES = (
    ".js",
    ".json",
    ".twee",
    ".tw",
    ".txt",
    ".html",
    ".css",
    ".md",
)


@dataclass
class SourceHit:
    """One text match inside an embedded mod payload."""

    mod_index: int
    mod_name: str
    member: str
    line: int
    sample: str


@dataclass
class SourceScanResult:
    """Scan result for one HTML/ZIP artifact."""

    target: str
    pattern: str
    success: bool = False
    errors: list[str] = field(default_factory=list)
    hits: list[SourceHit] = field(default_factory=list)


def _decode_base64_payload(value: str) -> bytes:
    payload = value.strip()
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)
    return base64.b64decode(payload, validate=True)


def _load_html(target: Path) -> tuple[str | None, str | None]:
    if target.suffix.lower() == ".zip":
        with zipfile.ZipFile(target, "r") as zf:
            html_names = [name for name in zf.namelist() if name.lower().endswith(".html")]
            if not html_names:
                return None, None
            html_name = sorted(
                html_names,
                key=lambda name: ("degrees of lewdity" not in name.lower(), name.lower()),
            )[0]
            return html_name, zf.read(html_name).decode("utf-8", errors="replace")

    return target.name, target.read_text(encoding="utf-8")


def _mod_name(zf: zipfile.ZipFile, fallback: str) -> str:
    boot_name = next((name for name in zf.namelist() if name.lower().endswith("boot.json")), None)
    if boot_name is None:
        return fallback
    try:
        boot = json.loads(zf.read(boot_name).decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return fallback
    if isinstance(boot, dict) and isinstance(boot.get("name"), str):
        return boot["name"]
    return fallback


def scan_target(target: Path, pattern: str) -> SourceScanResult:
    """Find pattern matches inside embedded ModLoader payload text files."""
    target = Path(target)
    result = SourceScanResult(target=str(target), pattern=pattern)
    if not target.exists():
        result.errors.append(f"target does not exist: {target}")
        return result

    try:
        html_name, html = _load_html(target)
    except zipfile.BadZipFile as exc:
        result.errors.append(f"target ZIP is invalid: {exc}")
        return result

    if html is None:
        result.errors.append("target does not contain an HTML file")
        return result

    match = MOD_LIST_PATTERN.search(html)
    if not match:
        result.errors.append(f"HTML does not contain modDataValueZipList: {html_name}")
        return result

    try:
        entries = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        result.errors.append(f"modDataValueZipList is not valid JSON: {exc}")
        return result

    regex = re.compile(pattern)
    for index, entry in enumerate(entries):
        if not isinstance(entry, str):
            continue
        try:
            payload = _decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as mod_zip:
                mod_name = _mod_name(mod_zip, f"embedded-mod-{index}")
                for member in mod_zip.namelist():
                    if not member.lower().endswith(TEXT_SUFFIXES):
                        continue
                    text = mod_zip.read(member).decode("utf-8", errors="replace")
                    lines = text.splitlines()
                    for line_number, line in enumerate(lines, start=1):
                        if not regex.search(line):
                            continue
                        start = max(0, line_number - 3)
                        end = min(len(lines), line_number + 2)
                        result.hits.append(
                            SourceHit(
                                mod_index=index,
                                mod_name=mod_name,
                                member=member,
                                line=line_number,
                                sample=" | ".join(lines[start:end])[:800],
                            )
                        )
        except (ValueError, zipfile.BadZipFile):
            continue

    result.success = not result.errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan embedded mod source files for a regex")
    parser.add_argument("target", type=Path, help="Built HTML or ZIP artifact")
    parser.add_argument("pattern", help="Regular expression to search for")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    result = scan_target(args.target, args.pattern)
    payload = asdict(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
