#!/usr/bin/env python3
"""Fail-closed guard: no save payloads, fixtures or machine-private paths in git.

DOL-X treats saves as radioactive: the desktop test stack stores fixtures and
imported saves under ``.local/`` (gitignored) and *never* in the repository. This
guard is the enforcement half of that policy and runs on every pytest/CI pass.

Rules (all fail-closed):

``save-filename``   a tracked path that looks like a save file (``*.save``,
                    ``*.sav``, ``save-*.json``, ...)
``lzstring-save``   a long base64 blob whose LZString payload contains save keys
                    (``id``/``state``/``variables``/``passage``) - this is the
                    on-disk ``.save`` format the game writes
``save-json-shape`` an uncompressed ``{id, state}`` save object
``fixture-payload`` fixture markers (``__dolx_type__``) or a ``{meta, variables,
                    stats}`` fixture document with a real payload
``personal-path``   absolute Windows/POSIX home or project paths

Usage::

    python tools/save_safety_guard.py            # tracked files, exit 1 on findings
    python tools/save_safety_guard.py --json .local/sweep/save-guard.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_BASE64_REVERSE = {char: index for index, char in enumerate(BASE64_ALPHABET)}

SAVE_PATH_RE = re.compile(
    r"(?i)(?:^|/)(?:[^/]*\.(?:save|sav)(?:\.(?:gz|zip|json|txt))?$"
    r"|save[-_][^/]*\.(?:json|txt|dat)$"
    r"|saves/[^/]+$"
    r"|slot[0-9]+\.(?:json|txt)$)"
)
FIXTURE_MARKER_RE = re.compile(r"__dolx_type__")
BASE64_RUN_RE = re.compile(r"[A-Za-z0-9+/=]{400,}")

# Built from fragments so this file never contains the literals it hunts for.
_PLACEHOLDER_NAMES = {"runner", "user", "you", "username", "example", "test", "name", "public"}
PERSONAL_PATH_RES = (
    re.compile(r"(?i)\b[A-Z]:\\Users\\([A-Za-z0-9_.\-]{1,})"),
    re.compile(r"(?i)\b[A-Z]:\\projects\\([A-Za-z0-9_.\-]{1,})"),
    re.compile(r"(?<![\w/])/home/([A-Za-z0-9_.\-]{1,})/"),
    re.compile(r"(?<![\w/])/Users/([A-Za-z0-9_.\-]{1,})/"),
)

SKIP_DIRS = {
    ".git",
    ".local",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "workspace",
    "output",
    "downloads",
    "pairs",
    "base",
}
BINARY_SUFFIXES = {
    ".apk", ".zip", ".jar", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".ogg", ".wav", ".pdf",
    ".so", ".dll", ".exe", ".dylib", ".class", ".crypt", ".salt", ".nonce", ".jks",
}


# --------------------------------------------------------------------------- #
# LZString (faithful port of the reference decompressor used by SugarCube)
# --------------------------------------------------------------------------- #


def _js_falsy(value: Any) -> bool:
    return value is None or value is False or value == 0 or value == ""


def _decompress(length: int, reset_value: int, get_next_value) -> str | None:
    """Port of ``LZString._decompress`` (numeric semantics preserved)."""
    dictionary: list[Any] = [0, 1, 2]
    enlarge_in = 4
    dict_size = 4
    num_bits = 3
    entry: Any = ""
    result: list[Any] = []

    data_val = get_next_value(0)
    data_val = 0 if data_val is None else data_val
    position = reset_value
    index = 1

    def read_bits(width: int) -> int:
        nonlocal data_val, position, index
        bits = 0
        power = 1
        maxpower = 1 << width
        while power != maxpower:
            resb = data_val & position
            position >>= 1
            if position == 0:
                position = reset_value
                nxt = get_next_value(index)
                index += 1
                data_val = 0 if nxt is None else nxt
            bits |= (1 if resb > 0 else 0) * power
            power <<= 1
        return bits

    next_code = read_bits(2)
    if next_code == 0:
        char = chr(read_bits(8))
    elif next_code == 1:
        char = chr(read_bits(16))
    elif next_code == 2:
        return ""
    else:
        return None

    dictionary.append(char)
    w = char
    result.append(char)

    while True:
        if index > length:
            return ""
        c = read_bits(num_bits)
        if c == 0:
            dictionary.append(chr(read_bits(8)))
            c = dict_size
            dict_size += 1
            enlarge_in -= 1
        elif c == 1:
            dictionary.append(chr(read_bits(16)))
            c = dict_size
            dict_size += 1
            enlarge_in -= 1
        elif c == 2:
            return "".join(result)
        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1
        if c < len(dictionary) and not _js_falsy(dictionary[c]):
            entry = dictionary[c]
        elif c == dict_size:
            entry = str(w) + str(w)[:1]
        else:
            return None
        result.append(entry)
        dictionary.append(str(w) + str(entry)[:1])
        dict_size += 1
        enlarge_in -= 1
        w = entry
        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1


def lzstring_decompress_from_base64(data: str) -> str | None:
    """Decompress a base64 LZString blob; ``None`` when the input is not usable."""
    if not data:
        return None
    cleaned = re.sub(r"\s+", "", data)
    if not cleaned:
        return None

    def get_next(index: int) -> int | None:
        if index >= len(cleaned):
            return None  # JS: undefined & mask === 0
        return _BASE64_REVERSE.get(cleaned[index])

    try:
        return _decompress(len(cleaned), 32, get_next)
    except Exception:  # noqa: BLE001 - malformed input must never crash the guard
        return None


def _looks_like_save_json(payload: str) -> bool:
    if '"state"' not in payload:
        return False
    return any(hint in payload for hint in ('"id"', '"variables"', '"passage"', '"idx"'))


def _lzstring_looks_like_save(blob: str) -> bool:
    decoded = lzstring_decompress_from_base64(blob)
    if not decoded or len(decoded) < 40:
        return False
    if not _looks_like_save_json(decoded):
        return False
    try:
        json.loads(decoded)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


def _finding(rel: str, rule: str, detail: str) -> dict[str, str]:
    return {"path": rel, "rule": rule, "detail": detail[:300]}


def check_path(rel: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if SAVE_PATH_RE.search(rel):
        findings.append(_finding(rel, "save-filename", "path looks like a save payload"))
    return findings


def check_text(text: str, rel: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    # The marker alone is not evidence: our own serializer/inspector sources
    # legitimately mention it. Payload-scale means many markers inside a large
    # data blob; smaller fixtures are caught by the JSON-shape rule below.
    marker_count = len(FIXTURE_MARKER_RE.findall(text))
    if marker_count >= 4 and len(text) >= 64_000 and '"variables"' in text:
        findings.append(
            _finding(
                rel,
                "fixture-payload",
                f"payload-scale fixture blob ({marker_count} markers, {len(text)} bytes)",
            )
        )
    for pattern in PERSONAL_PATH_RES:
        for match in pattern.finditer(text):
            name = (match.group(1) or "").lower()
            if name in _PLACEHOLDER_NAMES or name.startswith(("<", "%")):
                continue
            findings.append(
                _finding(rel, "personal-path", f"machine-private path: {match.group(0)[:80]}")
            )
            break
    stripped = text.strip()
    if stripped.startswith("{") and len(stripped) < 8_000_000:
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            if "state" in parsed and "id" in parsed:
                findings.append(
                    _finding(rel, "save-json-shape", "uncompressed {id, state} save object")
                )
            if (
                isinstance(parsed.get("variables"), dict)
                and len(parsed["variables"]) >= 50
                and ("stats" in parsed or "meta" in parsed)
            ):
                findings.append(
                    _finding(
                        rel,
                        "fixture-payload",
                        f"fixture document with {len(parsed['variables'])} variables",
                    )
                )
    candidates: list[str] = []
    if stripped and len(stripped) >= 400 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", stripped):
        candidates.append(stripped)
    candidates.extend(match.group(0) for match in list(BASE64_RUN_RE.finditer(text))[:3])
    for blob in candidates[:4]:
        if _lzstring_looks_like_save(blob):
            findings.append(
                _finding(rel, "lzstring-save", "base64 LZString payload decodes to a save object")
            )
            break
    return findings


# --------------------------------------------------------------------------- #
# File discovery
# --------------------------------------------------------------------------- #


def _git(root: Path, args: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {root}: "
            f"{proc.stderr.decode('utf-8', 'replace')[:200]}"
        )
    return [item for item in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if item]


def tracked_files(root: Path) -> list[str]:
    return _git(root, ["ls-files", "-z"])


def untracked_files(root: Path) -> list[str]:
    return _git(root, ["ls-files", "-z", "--others", "--exclude-standard"])


def tree_files(root: Path) -> list[str]:
    found: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        found.append(str(path.relative_to(root)).replace("\\", "/"))
    return found


# --------------------------------------------------------------------------- #
# Guard
# --------------------------------------------------------------------------- #


def guard(
    root: Path,
    *,
    paths: Iterable[str] | None = None,
    include_untracked: bool = False,
    use_git: bool = True,
    max_file_bytes: int = 4_000_000,
) -> dict[str, Any]:
    """Scan ``root`` for save payloads / fixtures / personal paths."""
    root = Path(root).resolve()
    if paths is None:
        if use_git:
            selected = tracked_files(root)
            if include_untracked:
                selected += untracked_files(root)
        else:
            selected = tree_files(root)
    else:
        selected = list(paths)

    findings: list[dict[str, str]] = []
    scanned = 0
    skipped: list[dict[str, str]] = []
    for rel in sorted(set(selected)):
        rel_posix = rel.replace("\\", "/")
        findings.extend(check_path(rel_posix))
        if Path(rel_posix).suffix.lower() in BINARY_SUFFIXES:
            skipped.append({"path": rel_posix, "reason": "binary suffix"})
            continue
        full = root / rel_posix
        try:
            if not full.is_file():
                skipped.append({"path": rel_posix, "reason": "not a file"})
                continue
            size = full.stat().st_size
        except OSError as exc:
            skipped.append({"path": rel_posix, "reason": f"stat failed: {exc}"})
            continue
        if size > max_file_bytes:
            skipped.append({"path": rel_posix, "reason": f"too large ({size} bytes)"})
            continue
        try:
            raw = full.read_bytes()
        except OSError as exc:
            skipped.append({"path": rel_posix, "reason": f"read failed: {exc}"})
            continue
        if b"\0" in raw[:8192]:
            skipped.append({"path": rel_posix, "reason": "binary content"})
            continue
        text = raw.decode("utf-8", "replace")
        scanned += 1
        findings.extend(check_text(text, rel_posix))

    return {
        "root": str(root),
        "ok": not findings,
        "scanned": scanned,
        "skipped": skipped[:200],
        "skipped_count": len(skipped),
        "findings": findings,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "# DOL-X save-safety guard",
        "",
        f"- root: `{report['root']}`",
        f"- scanned: {report['scanned']} files (skipped {report.get('skipped_count', 0)})",
        f"- verdict: **{'ok' if report['ok'] else 'FAILED'}**",
        "",
    ]
    if report["findings"]:
        lines.append("| path | rule | detail |")
        lines.append("| --- | --- | --- |")
        for item in report["findings"]:
            lines.append(
                f"| `{item['path']}` | {item['rule']} | {item['detail'].replace('|', chr(92) + '|')} |"
            )
    else:
        lines.append("No save payloads, fixtures or machine-private paths found.")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DOL-X save-safety guard")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", type=Path, default=None, help="also write the report as JSON")
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="walk the tree instead of asking git (for non-repo checkouts)",
    )
    parser.add_argument("--max-file-bytes", type=int, default=4_000_000)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = guard(
        args.root,
        include_untracked=args.include_untracked,
        use_git=not args.all_files,
        max_file_bytes=args.max_file_bytes,
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.quiet:
        print(format_report(report))
    else:
        print(
            f"[guard] scanned={report['scanned']} findings={len(report['findings'])} "
            f"ok={report['ok']}"
        )
    for item in report["findings"][:20]:
        if args.quiet:
            print(f"  {item['rule']}: {item['path']} :: {item['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
