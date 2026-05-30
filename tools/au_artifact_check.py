#!/usr/bin/env python3
"""Artifact-level AU face alias checks for built ZIP packages."""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


REQUIRED_NESTED_BLUSH = "img/face/default/default/blush1.png"


@dataclass
class AuArtifactResult:
    """Validation result for one built ZIP artifact."""

    target: str
    is_au: bool
    success: bool = False
    nested_blush_count: int = 0
    required_nested_blush_present: bool = False
    errors: list[str] = field(default_factory=list)


def _is_au_zip(path: Path) -> bool:
    normalized = path.name.lower().replace("_", "-")
    return any(token in normalized for token in ("-au-f-", "-au-m-", "-au-a-"))


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
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        result.errors.append(f"ZIP artifact is invalid: {exc}")
        return result

    nested_blush = sorted(
        name
        for name in names
        if name.startswith("img/face/default/default/blush") and name.endswith(".png")
    )
    result.nested_blush_count = len(nested_blush)
    result.required_nested_blush_present = REQUIRED_NESTED_BLUSH in names

    if not result.required_nested_blush_present:
        result.errors.append(f"missing required AU face alias: {REQUIRED_NESTED_BLUSH}")
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
