#!/usr/bin/env python3
"""Check staged/outgoing Git content without printing matched private material.

Optional machine-only literals live in .local/publication-denylist.json. This is
a prevention check, not a claim that all historic credentials can be detected.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 4_000_000
PRIVATE_REF = re.compile(r"(?:^|/)(?:backup|private|pre-redact)(?:[-/]|$)", re.I)
PRIVATE_PATH = re.compile(
    r"(?:^|/)(?:\.local|secrets?|private-research)(?:/|$)"
    r"|\.(?:jks|keystore|p12|pfx)$|(?:^|/)\.env$", re.I
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")
ACCESS_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b")
CREDENTIAL_URL = re.compile(r"https?://[^\s/@:]+:[^\s/@]{8,}@", re.I)
ASSIGNMENT = re.compile(
    r'''(?i)(?:\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passphrase|decrypt(?:ion)?[_-]?key|client[_-]?secret)\b|密钥|口令)["']?\s*[:=：]\s*["'`]([^"'`\r\n]{8,})["'`]'''
)
PRIVATE_MESSAGE = re.compile(r"解密|密钥|口令|\bdecrypt(?:ion|ed)?\b|\bpassphrase\b|pre-redact", re.I)


def git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", "-C", str(root), *args], input=input, capture_output=True)
    if proc.returncode:
        raise RuntimeError("Git inspection failed; nothing was published by this check")
    return proc.stdout


def load_literals(root: Path) -> list[str]:
    path = root / ".local/publication-denylist.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    values = data.get("literals")
    if not isinstance(values, list) or not all(isinstance(v, str) and len(v) >= 4 for v in values):
        raise ValueError("Invalid private denylist")
    return values


def placeholder(value: str) -> bool:
    return (value.startswith(("<", "${", "$env:", "os.", "process.", "secrets."))
            or value.lower().startswith(("example", "placeholder", "your_", "dummy_", "test_")))


def check_text(text: str, *, path: str, literals=(), message: bool = False) -> list[dict]:
    findings = []
    rules = [("private-key", PRIVATE_KEY), ("access-token", ACCESS_TOKEN), ("credential-url", CREDENTIAL_URL)]
    if message:
        rules.append(("private-research-message", PRIVATE_MESSAGE))
    for rule, pattern in rules:
        for match in pattern.finditer(text):
            findings.append({"path": path, "rule": rule, "line": text.count("\n", 0, match.start()) + 1})
    for match in ASSIGNMENT.finditer(text):
        if not placeholder(match[1]):
            findings.append({"path": path, "rule": "credential-literal", "line": text.count("\n", 0, match.start()) + 1})
    for literal in literals:
        start = text.find(literal)
        if start >= 0:
            findings.append({"path": path, "rule": "private-literal", "line": text.count("\n", 0, start) + 1})
    return findings


def scan_blob(root: Path, object_id: str, path: str, literals) -> list[dict]:
    if PRIVATE_PATH.search(path):
        return [{"path": path, "rule": "private-file"}]
    size = int(git(root, "cat-file", "-s", object_id))
    if size > MAX_BYTES:
        return [{"path": path, "rule": "oversized-review-required"}]
    blob = git(root, "cat-file", "blob", object_id)
    if b"\0" in blob[:8192]:
        return [{"path": path, "rule": "private-literal"} for value in literals if value.encode() in blob]
    return check_text(blob.decode("utf-8", "replace"), path=path, literals=literals)


def scan_index(root: Path, literals) -> list[dict]:
    changed = set(git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0"))
    findings = []
    for entry in git(root, "ls-files", "--stage", "-z").decode().split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, oid, stage = meta.split()
        if path in changed:
            if stage != "0":
                raise ValueError("Unmerged index")
            if mode != "160000":
                findings.extend(scan_blob(root, oid, path, literals))
    return findings


def scan_tree(root: Path, ref: str, literals) -> list[dict]:
    findings = []
    for entry in git(root, "ls-tree", "-rz", ref).decode().split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        _, kind, oid = meta.split()
        if kind == "blob":
            findings.extend(scan_blob(root, oid, path, literals))
    return findings


def outgoing(root: Path, lines: str, literals, remote_name: str = "origin") -> list[dict]:
    findings = []
    seen = set()
    for line in lines.splitlines():
        local_ref, local_oid, remote_ref, remote_oid = line.split()
        if set(local_oid) == {"0"}:
            continue
        if PRIVATE_REF.search(local_ref) or PRIVATE_REF.search(remote_ref):
            findings.append({"path": remote_ref, "rule": "private-ref"})
        if git(root, "cat-file", "-t", local_oid).strip() == b"tag":
            annotation = git(root, "cat-file", "tag", local_oid).decode("utf-8", "replace")
            findings.extend(check_text(annotation, path="tag:" + local_oid, literals=literals, message=True))
        revision = [local_oid]
        if set(remote_oid) != {"0"}:
            revision.append("^" + remote_oid)
        else:
            revision.extend(["--not", "--remotes=" + remote_name])
        for commit in git(root, "rev-list", *revision).decode().splitlines():
            if commit in seen:
                continue
            seen.add(commit)
            message = git(root, "show", "-s", "--format=%B", commit).decode("utf-8", "replace")
            findings.extend(check_text(message, path="commit:" + commit, literals=literals, message=True))
            findings.extend(scan_tree(root, commit, literals))
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--staged", action="store_true")
    modes.add_argument("--pre-push", action="store_true")
    modes.add_argument("--ref", default=None)
    parser.add_argument("--remote-name", default="origin")
    parser.add_argument("--message-file", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        literals = load_literals(root)
        if args.pre_push:
            findings = outgoing(root, sys.stdin.read(), literals, args.remote_name)
        elif args.staged:
            findings = scan_index(root, literals)
        else:
            findings = scan_tree(root, args.ref or "HEAD", literals)
        if args.message_file:
            findings += check_text(args.message_file.read_text(encoding="utf-8"), path="commit-message", literals=literals, message=True)
    except (RuntimeError, ValueError, OSError):
        print("publication guard: inspection failed (private details omitted)")
        return 2
    unique = list({json.dumps(x, sort_keys=True): x for x in findings}.values())
    for row in unique:
        print(json.dumps(row, ensure_ascii=True))
    print(f"publication guard: {'BLOCKED' if unique else 'clean'}; findings={len(unique)}")
    return int(bool(unique))


if __name__ == "__main__":
    raise SystemExit(main())
