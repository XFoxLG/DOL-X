#!/usr/bin/env python3
"""Sanitize sweep reports before they leave the machine (CI artifacts).

The 2026-10-04 automated-testing plan requires reports uploaded from the public
repository's Actions to carry no absolute host paths and no fixture payloads.
This module is dependency-free and idempotent: point it at a report directory
(or the whole ``.local/sweep`` tree) and every ``*.json`` / ``*.md`` / ``*.log``
/ ``*.txt`` file is rewritten in place so that:

* the repo root / user home directory become ``<repo>`` / ``<home>``;
* any other Windows or POSIX absolute path becomes ``<abs-path>``;
* LZString ``.save`` base64 blobs become ``<redacted-save>``;
* fixture payload dumps (``"variables"`` objects with hundreds of keys) become
  ``{"__redacted__": true, "keys": N}``.

Usage:

    python tools/report_sanitize.py DIR [DIR ...]
    python tools/report_sanitize.py --check DIR      # exit 1 if dirty

The real artifacts never enter the repository: this only touches files under
the report directories given on the command line (by convention ``.local/``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = (".json", ".md", ".log", ".txt")

_LZ_SAVE = re.compile(r"\bN4Ig[A-Za-z0-9+/=_-]{80,}")
_LONG_B64 = re.compile(r"(?<![\w./-])[A-Za-z0-9+/]{120,}={0,2}(?![\w./-])")
_WIN_ABS = re.compile(r"\b[A-Za-z]:[\\/][^\s\"'<>|]+")
_POSIX_ABS = re.compile(r"(?<![\w<])/(?:home|root|Users|tmp|mnt|workspace)/[^\s\"'<>|]+")
_REDACT_KEYS = ("variables", "fixture_vars", "fixture_payload", "variables_snapshot")
_REDACT_MIN_KEYS = 200


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _path_pairs() -> list[tuple[str, str]]:
    repo = str(_repo_root())
    home = str(Path.home())
    pairs: list[tuple[str, str]] = []
    for root, tag in ((repo, "<repo>"), (home, "<home>")):
        variants = {root, root.replace("\\", "/"), root.replace("/", "\\")}
        pairs.extend((v, tag) for v in variants if v)
    # longest first so nested prefixes do not shadow each other
    return sorted(pairs, key=lambda kv: len(kv[0]), reverse=True)


def sanitize_text(text: str, pairs: list[tuple[str, str]] | None = None) -> str:
    """Replace host paths and save blobs in a plain string."""
    pairs = pairs if pairs is not None else _path_pairs()
    out = text
    for needle, tag in pairs:
        if needle and needle in out:
            out = out.replace(needle, tag)
    out = _LZ_SAVE.sub("<redacted-save>", out)
    out = _LONG_B64.sub("<redacted-save>", out)
    out = _WIN_ABS.sub("<abs-path>", out)
    out = _POSIX_ABS.sub("<abs-path>", out)
    # Never leak the placeholder-internal backslash form of a replaced path.
    return out


def sanitize_obj(obj: Any, pairs: list[tuple[str, str]] | None = None) -> Any:
    """Recursively sanitize a JSON-compatible object (fixture dumps get cut)."""
    pairs = pairs if pairs is not None else _path_pairs()
    if isinstance(obj, str):
        return sanitize_text(obj, pairs)
    if isinstance(obj, list):
        return [sanitize_obj(item, pairs) for item in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if (
                key in _REDACT_KEYS
                and isinstance(value, dict)
                and len(value) >= _REDACT_MIN_KEYS
            ):
                out[key] = {"__redacted__": True, "keys": len(value)}
            else:
                out[key] = sanitize_obj(value, pairs)
        return out
    return obj


def sanitize_file(path: Path) -> tuple[bool, int]:
    """Sanitize one report file in place. Returns (changed, redactions)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            original = json.loads(text)
        except json.JSONDecodeError:
            cleaned = sanitize_text(text)
            if cleaned != text:
                path.write_text(cleaned, encoding="utf-8")
                return True, 1
            return False, 0
        cleaned_obj = sanitize_obj(original)
        if cleaned_obj == original:
            return False, 0
        path.write_text(
            json.dumps(cleaned_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return True, 1
    cleaned = sanitize_text(text)
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")
        return True, 1
    return False, 0


def iter_report_files(root: Path) -> list[Path]:
    # A single explicit path is echoed back even when missing so callers can
    # report it (main() prints "skip missing"); directories are expanded.
    if not root.is_dir():
        return [root] if root.suffix.lower() in TEXT_SUFFIXES else []
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
    )


def sanitize_dir(root: Path) -> dict[str, int]:
    """Sanitize every report file under ``root``. Returns summary counts."""
    files = [p for p in iter_report_files(root) if p.is_file()]
    changed = 0
    for path in files:
        was_changed, _ = sanitize_file(path)
        if was_changed:
            changed += 1
    return {"files": len(files), "changed": changed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sanitize DOL-X sweep reports")
    parser.add_argument("paths", nargs="+", type=Path, help="report file or directory")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 when any file still carries host data",
    )
    args = parser.parse_args(argv)

    files: list[Path] = []
    for root in args.paths:
        if not root.exists():
            print(f"[sanitize] skip missing: {root}", file=sys.stderr)
            continue
        files.extend(iter_report_files(root))

    if args.check:
        dirty = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() == ".json":
                try:
                    dirty_now = sanitize_obj(json.loads(text)) != json.loads(text)
                except json.JSONDecodeError:
                    dirty_now = sanitize_text(text) != text
            else:
                dirty_now = sanitize_text(text) != text
            if dirty_now:
                dirty.append(str(path))
        if dirty:
            for item in dirty[:40]:
                print(f"[sanitize] DIRTY: {item}")
            print(f"[sanitize] {len(dirty)} dirty file(s)")
            return 1
        print(f"[sanitize] clean: {len(files)} file(s) checked")
        return 0

    summary = {"files": 0, "changed": 0}
    for path in files:
        was_changed, _ = sanitize_file(path)
        summary["files"] += 1
        summary["changed"] += 1 if was_changed else 0
    print(f"[sanitize] files={summary['files']} changed={summary['changed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
