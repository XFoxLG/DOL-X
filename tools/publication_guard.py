#!/usr/bin/env python3
"""Check staged/outgoing Git content without printing matched private material.

Optional machine-only literals live in .local/publication-denylist.json. This is
a prevention check, not a claim that all historic credentials can be detected.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

MAX_BYTES = 4_000_000
PRIVATE_REF = re.compile(r"(?:^|/)(?:backup|private|pre-redact|recovery)(?:[-/]|$)", re.I)
PRIVATE_PATH = re.compile(
    r"(?:^|/)(?:\.local|secrets?|private-research)(?:/|$)"
    r"|\.(?:jks|keystore|p12|pfx)$|(?:^|/)\.env$", re.I
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")
ACCESS_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b")
CREDENTIAL_URL = re.compile(r"https?://[^\s/@]+@", re.I)
ASSIGNMENT = re.compile(
    r'''(?i)(?:\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passphrase|decrypt(?:ion)?[_-]?key|client[_-]?secret)\b|密钥|口令)["']?\s*[:=：]\s*["'`]([^"'`\r\n]{8,})["'`]'''
)
PRIVATE_MESSAGE = re.compile(r"解密|密钥|口令|\bdecrypt(?:ion|ed)?\b|\bpassphrase\b|pre-redact", re.I)


def git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", "-C", str(root), *args], input=input, capture_output=True)
    if proc.returncode:
        raise RuntimeError("Git inspection failed; nothing was published by this check")
    return proc.stdout


def load_private_policy(root: Path, path: Path | None = None) -> dict:
    """Load machine-only literals and identity aliases without printing them."""
    configured = os.environ.get("DOLX_PUBLICATION_DENYLIST")
    selected = path or (Path(configured) if configured else root / ".local/publication-denylist.json")
    if not selected.exists():
        if path is not None or configured:
            raise FileNotFoundError("The explicit private policy was not found")
        return {"literals": [], "identities": []}
    data = json.loads(selected.read_text(encoding="utf-8"))
    literals = data.get("literals", [])
    identities = data.get("identities", [])
    if not isinstance(literals, list) or not all(
        isinstance(v, str) and len(v) >= 4 for v in literals
    ):
        raise ValueError("Invalid private denylist literals")
    if not isinstance(identities, list) or not all(isinstance(v, dict) for v in identities):
        raise ValueError("Invalid private identity policy")
    for identity in identities:
        if not isinstance(identity.get("name"), str) or not isinstance(identity.get("email"), str):
            raise ValueError("Invalid private identity entry")
    return {"literals": literals, "identities": identities}


def identity_findings(commit: str, author_name: str, author_email: str,
                      committer_name: str, committer_email: str, identities) -> list[dict]:
    findings = []
    for role, name, email in (
        ("author", author_name, author_email),
        ("committer", committer_name, committer_email),
    ):
        for identity in identities:
            if name == identity.get("name") and email == identity.get("email"):
                findings.append({"path": f"commit:{commit}", "rule": f"private-{role}-identity"})
                break
    return findings


def tag_identity_findings(object_id: str, annotation: str, identities) -> list[dict]:
    header = annotation.split("\n\n", 1)[0]
    match = re.search(r"^tagger (.*?) <([^>]+)> \d+ [+-]\d{4}$", header, re.M)
    if match and any(match[1] == row["name"] and match[2] == row["email"] for row in identities):
        return [{"path": f"tag:{object_id}", "rule": "private-tagger-identity"}]
    return []


def scan_commit_metadata(root: Path, commit: str, literals, identities) -> list[dict]:
    message = git(root, "show", "-s", "--format=%B", commit).decode("utf-8", "replace")
    findings = check_text(message, path="commit:" + commit, literals=literals, message=True)
    fields = git(root, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", commit).decode("utf-8", "replace").rstrip("\n").split("\x00")
    if len(fields) != 4:
        raise ValueError("Git identity inspection did not return four fields")
    return findings + identity_findings(commit, *fields, identities)


def placeholder(value: str) -> bool:
    return (value.startswith(("<", "${", "$env:", "os.", "process.", "secrets."))
            or value.lower().startswith(("example", "placeholder", "your_", "dummy_", "test_")))


FIXTURE_TEST_PATH = re.compile(r"(^|/)tests?/|(^|/)test_[^/]*\.py$")
FIXTURE_CREDENTIAL = re.compile(r"fixture[-_]|placeholder|dummy_|your_|short@|tiny@|test[-_]")


def is_test_fixture(path: str, matched: str) -> bool:
    """Credential-shaped samples inside test files are fixtures, not secrets."""
    return bool(FIXTURE_TEST_PATH.search(path.replace("\\", "/"))) and bool(
        FIXTURE_CREDENTIAL.search(matched)
    )


def check_text(text: str, *, path: str, literals=(), message: bool = False) -> list[dict]:
    findings = []
    rules = [("private-key", PRIVATE_KEY), ("access-token", ACCESS_TOKEN), ("credential-url", CREDENTIAL_URL)]
    if message:
        rules.append(("private-research-message", PRIVATE_MESSAGE))
    for rule, pattern in rules:
        for match in pattern.finditer(text):
            if is_test_fixture(path, match[0]):
                continue
            findings.append({"path": path, "rule": rule, "line": text.count("\n", 0, match.start()) + 1})
    for match in ASSIGNMENT.finditer(text):
        # Released maplebirch code selects a header inside a computed property:
        # headers[provider ? "x-api-key" : "Authorization"] = token.
        # The ternary's ':' separates header names, not a credential assignment.
        if re.match(r"\s*\]\s*=", text[match.end():]):
            continue
        if is_test_fixture(path, match[1]):
            continue
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
    blob = git(root, "cat-file", "blob", object_id)
    return scan_payload(blob, path, literals)


def scan_payload(blob: bytes, path: str, literals, *, max_bytes: int = MAX_BYTES) -> list[dict]:
    if PRIVATE_PATH.search(path):
        return [{"path": path, "rule": "private-file"}]
    if path.casefold().endswith((".zip", ".apk", ".tar.gz", ".tgz", ".tar")):
        findings = scan_archive(blob, path, literals, max_bytes=max_bytes)
        if findings is not None:
            return findings
        return [{"path": path, "rule": "archive-unreadable"}]
    if len(blob) > max_bytes:
        return [{"path": path, "rule": "oversized-review-required"}]
    if b"\0" in blob[:8192]:
        return [{"path": path, "rule": "private-literal"} for value in literals if value.encode() in blob]
    return check_text(blob.decode("utf-8", "replace"), path=path, literals=literals)


def scan_archive(blob: bytes, path: str, literals, *, max_bytes: int = MAX_BYTES) -> list[dict] | None:
    """Scan text members of a ZIP/TAR before applying the size gate.

    Returning ``None`` means the suffix looked like an archive but the bytes
    were not a supported archive; the caller then keeps the conservative size
    finding for large opaque data.
    """
    findings = []
    try:
        if path.casefold().endswith((".zip", ".apk")):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    member_path = f"{path}!{member.filename}"
                    if PRIVATE_PATH.search(member.filename):
                        findings.append({"path": member_path, "rule": "private-file"})
                        continue
                    if member.file_size > max_bytes:
                        findings.append({"path": member_path, "rule": "oversized-review-required"})
                        continue
                    data = archive.read(member)
                    findings.extend(scan_payload(data, member_path, literals, max_bytes=max_bytes))
            return findings
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as archive:
            for member in archive.getmembers():
                member_path = f"{path}!{member.name}"
                if not member.isfile():
                    if member.issym() or member.islnk():
                        findings.extend(check_text(member.linkname, path=member_path, literals=literals))
                    continue
                if PRIVATE_PATH.search(member.name):
                    findings.append({"path": member_path, "rule": "private-file"})
                    continue
                if member.size > max_bytes:
                    findings.append({"path": member_path, "rule": "oversized-review-required"})
                    continue
                data = archive.extractfile(member).read()
                findings.extend(scan_payload(data, member_path, literals, max_bytes=max_bytes))
        return findings
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError):
        return None


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


def outgoing(root: Path, lines: str, literals, remote_name: str = "origin", identities=()) -> list[dict]:
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
            findings.extend(tag_identity_findings(local_oid, annotation, identities))
        revision = [local_oid]
        if set(remote_oid) != {"0"}:
            revision.append("^" + remote_oid)
        else:
            revision.extend(["--not", "--remotes=" + remote_name])
        for commit in git(root, "rev-list", *revision).decode().splitlines():
            if commit in seen:
                continue
            seen.add(commit)
            findings.extend(scan_commit_metadata(root, commit, literals, identities))
            findings.extend(scan_tree(root, commit, literals))
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--staged", action="store_true")
    modes.add_argument("--pre-push", action="store_true")
    modes.add_argument("--ref", default=None)
    modes.add_argument("--artifact", type=Path, action="append", help="scan archive or attachment contents outside Git")
    parser.add_argument("--max-member-bytes", type=int, default=MAX_BYTES, help="explicit size budget for attachment audits; unscanned members block")
    parser.add_argument("--remote-name", default="origin")
    parser.add_argument("--message-file", type=Path)
    parser.add_argument("--denylist", type=Path, help="machine-only JSON policy outside the public repository")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        policy = load_private_policy(root, args.denylist)
        literals = policy["literals"]
        identities = policy["identities"]
        if args.max_member_bytes < 1:
            raise ValueError("Attachment size budget must be positive")
        if args.artifact:
            findings = []
            for index, artifact in enumerate(args.artifact, 1):
                # Absolute input paths stay out of public findings.
                findings.extend(scan_payload(artifact.read_bytes(), f"artifact:{index}/{artifact.name}", literals, max_bytes=args.max_member_bytes))
        elif args.pre_push:
            findings = outgoing(root, sys.stdin.read(), literals, args.remote_name, identities)
        elif args.staged:
            findings = scan_index(root, literals)
        else:
            findings = scan_tree(root, args.ref or "HEAD", literals)
            ref = args.ref or "HEAD"
            commit = git(root, "rev-parse", ref + "^{commit}").decode().strip()
            findings.extend(scan_commit_metadata(root, commit, literals, identities))
            object_id = git(root, "rev-parse", ref).decode().strip()
            if git(root, "cat-file", "-t", object_id).strip() == b"tag":
                annotation = git(root, "cat-file", "tag", object_id).decode("utf-8", "replace")
                findings.extend(tag_identity_findings(object_id, annotation, identities))
                findings.extend(check_text(annotation, path="tag:" + object_id, literals=literals, message=True))
        if args.message_file:
            findings += check_text(args.message_file.read_text(encoding="utf-8"), path="commit-message", literals=literals, message=True)
    except (RuntimeError, ValueError, OSError):
        print("publication guard: inspection failed (private details omitted)")
        return 2
    unique = list({json.dumps(x, sort_keys=True): x for x in findings}.values())
    for row in unique:
        for literal in literals:
            row["path"] = row["path"].replace(literal, "<private>")
        print(json.dumps(row, ensure_ascii=True))
    print(f"publication guard: {'BLOCKED' if unique else 'clean'}; findings={len(unique)}")
    return int(bool(unique))


if __name__ == "__main__":
    raise SystemExit(main())
