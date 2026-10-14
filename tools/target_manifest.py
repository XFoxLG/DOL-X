"""Immutable target identity for DOL-X test runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # allow ``python tools/target_manifest.py``
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from tools.sweep_ledger import atomic_write_json, sha256_text
from tools.target_package_check import check_package, game_version_marker


SCHEMA = "dolx.target.v1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_json(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - identity must fail closed.
        return {"_error": f"{type(exc).__name__}: {exc}"}
    return value if isinstance(value, dict) else {"_error": "root is not an object"}


def _safe_toml(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {}
    try:
        with Path(path).open("rb") as handle:
            value = tomllib.load(handle)
    except Exception as exc:  # noqa: BLE001 - identity must fail closed.
        return {"_error": f"{type(exc).__name__}: {exc}"}
    return value if isinstance(value, dict) else {"_error": "root is not an object"}


def build_manifest(
    target: Path,
    *,
    expected_version: str | None = None,
    apk: Path | None = None,
    mods_lock: Path | None = None,
    build_toml: Path | None = None,
    source_commit: str | None = None,
    source_index: Path | None = None,
    runner_revision: str | None = None,
    environment: dict[str, Any] | None = None,
    tag: str | None = None,
    local_head: str | None = None,
) -> dict[str, Any]:
    target = Path(target).resolve()
    package_sha256 = file_sha256(target)
    check = check_package(
        target,
        expect_version=expected_version,
        expect_mods=(),
        min_mods=None,
    )
    lock = _safe_json(mods_lock)
    build = _safe_toml(build_toml)
    source_index_digest = file_sha256(source_index) if source_index and Path(source_index).exists() else None
    # ``apk_sha256`` is optional: desktop-only evidence predates it, so a
    # manifest without it stays valid; the release gate binds it fail-closed.
    apk_sha256 = file_sha256(apk) if apk and Path(apk).exists() else None
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "target": {
            "game_version": check.get("game_version"),
            "expected_version": expected_version,
            "target_tag": tag,
            "package_sha256": package_sha256,
            "apk_sha256": apk_sha256,
            "html_member": check.get("html_member"),
            "package_path": str(target),
            "package_type": "base" if "base" in target.stem.casefold() else "derived",
            "source_commit": source_commit,
            "local_head": local_head,
        },
        "mods_lock_sha256": file_sha256(mods_lock) if mods_lock and Path(mods_lock).exists() else None,
        "embedded_payloads": check.get("mods") or [],
        "embedded_mod_count": check.get("mod_count") or 0,
        "embedded_list_length": check.get("list_length"),
        "build_toml_evidence": build,
        "mods_lock_evidence": lock,
        "source_index_sha256": source_index_digest,
        "runner_revision": runner_revision,
        "environment": environment or {},
        "identity_errors": check.get("errors") or [],
    }
    manifest["identity_ok"] = not manifest["identity_errors"] and bool(check.get("game_version"))
    manifest["manifest_sha256"] = sha256_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, Any]) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []
    if manifest.get("schema") != SCHEMA:
        diagnostics.append("schema mismatch")
    if manifest.get("identity_ok") is not True:
        diagnostics.extend(manifest.get("identity_errors") or [])
        if not manifest.get("target", {}).get("game_version"):
            diagnostics.append("game version missing")
    if not manifest.get("target", {}).get("package_sha256"):
        diagnostics.append("package sha256 missing")
    if manifest.get("embedded_mod_count", 0) < 1:
        diagnostics.append("embedded payload count missing")
    return not diagnostics, diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--expect-version")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--mods-lock", type=Path)
    parser.add_argument("--build-toml", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--runner-revision")
    parser.add_argument("--tag")
    parser.add_argument("--local-head")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_manifest(
        args.target,
        expected_version=args.expect_version,
        apk=args.apk,
        mods_lock=args.mods_lock,
        build_toml=args.build_toml,
        source_commit=args.source_commit,
        source_index=args.source_index,
        runner_revision=args.runner_revision,
        tag=args.tag,
        local_head=args.local_head,
    )
    ok, diagnostics = validate_manifest(manifest)
    manifest["validation_diagnostics"] = diagnostics
    if args.out:
        atomic_write_json(args.out, manifest)
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
