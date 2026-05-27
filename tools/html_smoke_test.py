#!/usr/bin/env python3
"""Phase 3: static HTML smoke test for built DoL packages.

This first pass intentionally avoids browser automation so it can run quickly in
CI for every build artifact. It validates that the built HTML exists, contains a
ModLoader data list, and that embedded mod ZIP payloads are readable.
"""

import argparse
import base64
import io
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


MOD_LIST_PATTERN = re.compile(
    r"window\.modDataValueZipList\s*=\s*(\[.*?\]);",
    re.DOTALL,
)


@dataclass
class HtmlSmokeResult:
    """Result for one HTML smoke audit target."""

    target: str
    success: bool = False
    html_found: bool = False
    mod_count: int = 0
    valid_zip_count: int = 0
    invalid_zip_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _load_html_from_zip(zip_path: Path) -> tuple[Optional[str], Optional[str]]:
    """Return the first HTML member name and contents from a ZIP artifact."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        html_names = [name for name in zf.namelist() if name.lower().endswith(".html")]
        if not html_names:
            return None, None

        preferred = sorted(
            html_names,
            key=lambda name: ("degrees of lewdity" not in name.lower(), name.lower()),
        )[0]
        return preferred, zf.read(preferred).decode("utf-8", errors="replace")


def _decode_mod_zip(encoded: str) -> bytes:
    """Decode a base64-encoded embedded mod ZIP payload."""
    payload = encoded.strip()
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)
    return base64.b64decode(payload, validate=True)


def audit_html_content(content: str, target: str) -> HtmlSmokeResult:
    """Audit raw HTML content."""
    result = HtmlSmokeResult(target=target, html_found=True)

    match = MOD_LIST_PATTERN.search(content)
    if not match:
        result.errors.append("HTML 文件中未找到 modDataValueZipList")
        return result

    try:
        mod_entries = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        result.errors.append(f"modDataValueZipList 不是有效 JSON: {exc}")
        return result

    if not isinstance(mod_entries, list):
        result.errors.append("modDataValueZipList 不是数组")
        return result

    result.mod_count = len(mod_entries)
    if not mod_entries:
        result.errors.append("modDataValueZipList 为空")
        return result

    for index, entry in enumerate(mod_entries):
        if not isinstance(entry, str):
            result.invalid_zip_count += 1
            result.errors.append(f"modDataValueZipList[{index}] 不是字符串")
            continue

        try:
            payload = _decode_mod_zip(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
                bad_file = zf.testzip()
                if bad_file:
                    result.invalid_zip_count += 1
                    result.errors.append(f"内嵌 mod #{index} ZIP 损坏: {bad_file}")
                    continue

                names = zf.namelist()
                if not any(name.lower().endswith("boot.json") for name in names):
                    result.warnings.append(f"内嵌 mod #{index} 未发现 boot.json")
                result.valid_zip_count += 1
        except Exception as exc:
            result.invalid_zip_count += 1
            result.errors.append(f"内嵌 mod #{index} 不是有效 ZIP: {exc}")

    result.success = not result.errors and result.valid_zip_count == result.mod_count
    return result


def audit_html(html_path: Path) -> HtmlSmokeResult:
    """Audit a local HTML file."""
    html_path = Path(html_path)
    if not html_path.exists():
        return HtmlSmokeResult(
            target=str(html_path),
            html_found=False,
            errors=[f"HTML 文件不存在: {html_path}"],
        )

    return audit_html_content(html_path.read_text(encoding="utf-8"), str(html_path))


def audit_zip_artifact(zip_path: Path) -> HtmlSmokeResult:
    """Audit the first HTML file inside a built ZIP package."""
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return HtmlSmokeResult(
            target=str(zip_path),
            html_found=False,
            errors=[f"ZIP 文件不存在: {zip_path}"],
        )

    try:
        html_name, content = _load_html_from_zip(zip_path)
    except zipfile.BadZipFile as exc:
        return HtmlSmokeResult(
            target=str(zip_path),
            html_found=False,
            errors=[f"构建产物不是有效 ZIP: {exc}"],
        )

    if content is None:
        return HtmlSmokeResult(
            target=str(zip_path),
            html_found=False,
            errors=["ZIP 构建产物中未找到 HTML 文件"],
        )

    return audit_html_content(content, f"{zip_path}!{html_name}")


def audit_target(path: Path) -> list[HtmlSmokeResult]:
    """Audit an HTML file, one ZIP artifact, or all ZIP/HTML files in a directory."""
    path = Path(path)
    if path.is_dir():
        candidates = sorted(
            [*path.rglob("*.zip"), *path.rglob("*.html")],
            key=lambda item: str(item).lower(),
        )
        if not candidates:
            return [
                HtmlSmokeResult(
                    target=str(path),
                    html_found=False,
                    errors=["目录中未找到 ZIP 或 HTML 目标"],
                )
            ]
        return [audit_target(candidate)[0] for candidate in candidates]

    if path.suffix.lower() == ".zip":
        return [audit_zip_artifact(path)]
    return [audit_html(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description="DoL-X Phase 3 HTML smoke test")
    parser.add_argument("target", type=Path, help="HTML、ZIP 构建产物或产物目录")
    parser.add_argument("--output", type=Path, help="可选 JSON 报告输出路径")
    args = parser.parse_args()

    results = audit_target(args.target)
    report = {"total": len(results), "results": [asdict(result) for result in results]}

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for result in results:
        status = "OK" if result.success else "FAIL"
        print(f"[{status}] {result.target}: mods={result.mod_count}, valid_zip={result.valid_zip_count}")
        for error in result.errors:
            print(f"  ERROR: {error}")
        for warning in result.warnings:
            print(f"  WARN: {warning}")

    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
