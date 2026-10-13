"""Pure ModLoader ZIP dependency and opaque-surface tests."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tools.mod_dependency_graph import build_graph, inspect_mod_zip


def _make_mod(path: Path, boot: dict, members: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("boot.json", json.dumps(boot))
        for name, value in members.items():
            archive.writestr(name, value)


def test_inspect_mod_zip_records_passages_dependencies_and_encryption(tmp_path: Path) -> None:
    path = tmp_path / "demo.mod.zip"
    _make_mod(
        path,
        {
            "name": "Demo Mod",
            "version": "1.0",
            "dependenceInfo": [{"name": "maplebirch", "version": ">=4.1"}],
            "addonPlugin": [{"name": "TweeReplacer"}],
        },
        {
            "game/demo.twee": ":: Demo\n<<widget 'demoWidget'>>\n<</widget>>\n",
            "pack.zip.crypt": b"opaque",
            "pack.salt": b"salt",
        },
    )
    report = inspect_mod_zip(path)
    assert report["name"] == "Demo Mod"
    assert report["dependencies"] == [
        {"name": "maplebirch", "optional": False, "version": ">=4.1", "source": {"name": "maplebirch", "version": ">=4.1"}}
    ]
    assert report["encrypted"] is True
    assert report["passages"][0]["name"] == "Demo"
    assert report["widgets"][0]["name"] == "demoWidget"


def test_build_graph_resolves_declared_dependency(tmp_path: Path) -> None:
    framework = tmp_path / "framework.zip"
    addon = tmp_path / "addon.zip"
    _make_mod(framework, {"name": "maplebirch"}, {})
    _make_mod(addon, {"name": "Addon", "dependenceInfo": ["maplebirch"]}, {})
    graph = build_graph([framework, addon])
    edge = next(item for item in graph["edges"] if item["from"] == "Addon")
    assert edge["resolved"] is True
    assert edge["to"] == "maplebirch"
