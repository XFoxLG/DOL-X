#!/usr/bin/env python3
"""Inspect ModLoader ZIP dependencies and opaque payload boundaries."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

from tools.artifact_inspection import parse_boot_json
from tools.mod_passage_inventory import extract_twee_passages, extract_widget_name


ENCRYPTED_SUFFIXES = (".crypt", ".salt", ".nonce")
TEXT_SUFFIXES = (".twee", ".tw", ".txt", ".js", ".json", ".css", ".html")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    return []


def _dependency_names(boot: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("dependenceInfo", "dependencies", "depends", "requires", "addonPlugin"):
        value = boot.get(key)
        for item in _strings(value):
            clean = item.strip()
            if clean and clean not in names:
                names.append(clean)
    return names


def _normalize_dependency_name(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _declared_dependencies(boot: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dependencies = boot.get("dependenceInfo") or boot.get("dependencies") or []
    if not isinstance(dependencies, list):
        return rows
    for item in dependencies:
        if isinstance(item, str):
            rows.append({"name": item.strip(), "optional": False})
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or "").strip()
            if name:
                rows.append(
                    {
                        "name": name,
                        "optional": bool(item.get("optional", False)),
                        "version": item.get("version"),
                        "source": dict(item),
                    }
                )
    return rows


def inspect_mod_zip(path: Path, *, owner: str | None = None) -> dict[str, Any]:
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        boot: dict[str, Any] = {}
        if "boot.json" in names:
            value = parse_boot_json(zf.read("boot.json").decode("utf-8-sig", errors="replace"))
            if isinstance(value, dict):
                boot = value
        passages: list[dict[str, Any]] = []
        widgets: list[dict[str, Any]] = []
        for member in names:
            if not member.lower().endswith(TEXT_SUFFIXES):
                continue
            try:
                text = zf.read(member).decode("utf-8", errors="replace")
            except Exception:
                continue
            for name, body in extract_twee_passages(text).items():
                passages.append({"name": name, "path": member, "widget": extract_widget_name(body)})
                if extract_widget_name(body):
                    widgets.append({"name": extract_widget_name(body), "passage": name, "path": member})
        encrypted = [name for name in names if name.lower().endswith(ENCRYPTED_SUFFIXES)]
        bad_paths = [name for name in names if "\\" in name]
        return {
            "schema": "dolx.mod-graph.v1",
            "path": str(path),
            "owner": owner,
            "name": str(boot.get("name") or boot.get("nickName") or path.stem),
            "version": boot.get("version"),
            "boot": boot,
            "dependencies": _declared_dependencies(boot),
            "entries": names,
            "passages": passages,
            "widgets": widgets,
            "encrypted": bool(encrypted),
            "encryption_markers": encrypted,
            "backslash_paths": bad_paths,
            "boot_refs": {
                "tweeFileList": boot.get("tweeFileList", []),
                "scriptFileList": boot.get("scriptFileList", []),
                "styleFileList": boot.get("styleFileList", []),
                "addonPlugin": boot.get("addonPlugin", []),
            },
        }


def build_graph(paths: Iterable[Path]) -> dict[str, Any]:
    mods = [inspect_mod_zip(Path(path)) for path in paths]
    by_name = {str(mod["name"]).casefold(): mod for mod in mods}
    edges: list[dict[str, Any]] = []
    for mod in mods:
        source = str(mod["name"])
        for dependency in mod["dependencies"]:
            normalized = _normalize_dependency_name(str(dependency["name"]))
            resolved = next(
                (target["name"] for key, target in by_name.items() if _normalize_dependency_name(str(target["name"])) == normalized),
                None,
            )
            edges.append(
                {
                    "from": source,
                    "to": resolved or dependency["name"],
                    "resolved": resolved is not None,
                    "optional": bool(dependency.get("optional")),
                    "kind": "optional" if dependency.get("optional") else "required",
                }
            )
    return {
        "schema": "dolx.mod-graph.v1",
        "mods": sorted(mods, key=lambda item: str(item["name"]).casefold()),
        "edges": edges,
        "stats": {
            "mods": len(mods),
            "encrypted": sum(1 for mod in mods if mod["encrypted"]),
            "backslash_path_mods": sum(1 for mod in mods if mod["backslash_paths"]),
            "passages": sum(len(mod["passages"]) for mod in mods),
            "widgets": sum(len(mod["widgets"]) for mod in mods),
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="Mod ZIP files")
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_graph(args.paths)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
