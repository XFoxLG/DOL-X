#!/usr/bin/env python3
"""Shared helpers for inspecting built HTML/ZIP artifacts.

The HTML smoke, browser smoke, and embedded-source scanner all need the same
ModLoader payload extraction contract. Keeping that parsing here prevents the
three tools from drifting when the generated HTML shape changes.
"""

from __future__ import annotations

import base64
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


MOD_DATA_VALUE_ZIP_LIST_PATTERN = re.compile(
    r"window\.modDataValueZipList\s*=\s*(\[.*?\]);",
    re.DOTALL,
)


@dataclass(frozen=True)
class ModDataValueZipListParse:
    """Parsed `window.modDataValueZipList` entries from a built HTML file."""

    entries: list[Any] = field(default_factory=list)
    error_kind: str | None = None
    error: str | None = None


def collect_string_values(value: Any) -> Iterable[str]:
    """Yield every string contained in a nested JSON-like value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from collect_string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from collect_string_values(item)


def decode_base64_payload(encoded: str) -> bytes:
    """Decode one base64 ModLoader payload, accepting omitted padding."""
    payload = encoded.strip()
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)
    return base64.b64decode(payload, validate=True)


def parse_mod_data_value_zip_list(content: str) -> ModDataValueZipListParse:
    """Parse the generated ModLoader payload list from raw HTML content."""
    match = MOD_DATA_VALUE_ZIP_LIST_PATTERN.search(content)
    if not match:
        return ModDataValueZipListParse(error_kind="missing", error="HTML does not contain modDataValueZipList")

    try:
        entries = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return ModDataValueZipListParse(error_kind="invalid_json", error=str(exc))

    if not isinstance(entries, list):
        return ModDataValueZipListParse(error_kind="not_list", error="modDataValueZipList is not an array")

    return ModDataValueZipListParse(entries=entries)


def load_preferred_html_from_zip(zip_path: Path) -> tuple[str | None, str | None]:
    """Return the preferred HTML member name and content from a ZIP artifact."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        html_names = [name for name in zf.namelist() if name.lower().endswith(".html")]
        if not html_names:
            return None, None

        preferred = sorted(
            html_names,
            key=lambda name: ("degrees of lewdity" not in name.lower(), name.lower()),
        )[0]
        return preferred, zf.read(preferred).decode("utf-8", errors="replace")


def load_html_artifact(target: Path) -> tuple[str | None, str | None]:
    """Load HTML content from a raw HTML file or the preferred member of a ZIP."""
    target = Path(target)
    if target.suffix.lower() == ".zip":
        return load_preferred_html_from_zip(target)
    return target.name, target.read_text(encoding="utf-8")
