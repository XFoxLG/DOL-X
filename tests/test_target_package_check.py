"""Unit tests for the sweep target package identity check."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

from tools import target_package_check as tpc


def _embedded_payload(name: str, version: str) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", json.dumps({"name": name, "version": version}))
        zf.writestr("README.md", "payload")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _built_html(
    entries: list[tuple[str, str]],
    *,
    game_version: str = "0.5.11.9",
    include_list: bool = True,
) -> str:
    payloads = ", ".join(json.dumps(_embedded_payload(name, ver)) for name, ver in entries)
    list_block = (
        f"<script>window.modDataValueZipList = [{payloads}];</script>"
        if include_list
        else ""
    )
    return (
        "<html><head><script>\n"
        "const StartConfig = {\n"
        "\tdebug: false,\n"
        f'\tversion: "{game_version}",\n'
        "};\n"
        "</script></head><body></body>"
        f"{list_block}</html>"
    )


def _write_html(tmp_path: Path, html: str) -> Path:
    target = tmp_path / "Degrees of Lewdity.html"
    target.write_text(html, encoding="utf-8")
    return target


def _write_zip(tmp_path: Path, html: str) -> Path:
    target = tmp_path / "DoL-0.5.11.9-XFox-1.0.0a-base-1004.zip"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("Degrees of Lewdity.html", html)
        zf.writestr("img/.gitkeep", "")
    return target


def test_game_version_marker_reads_start_config() -> None:
    assert tpc.game_version_marker(_built_html([])) == "0.5.11.9"
    assert tpc.game_version_marker("<html></html>") is None


def test_check_package_ok_with_case_insensitive_mod_names(tmp_path: Path) -> None:
    target = _write_zip(
        tmp_path,
        _built_html([("maplebirch", "4.1.14"), ("More Love Interests Mod", "0.1.7.0")]),
    )
    report = tpc.check_package(
        target,
        expect_mods=["Maplebirch", "moreloveinterestsmod"],
        expect_version="0.5.11.9",
        min_mods=2,
    )
    assert report["ok"] is True
    assert report["mod_count"] == 2
    assert report["missing_mods"] == []
    assert report["game_version"] == "0.5.11.9"


def test_check_package_flags_missing_mods_and_low_payload_count(tmp_path: Path) -> None:
    target = _write_html(tmp_path, _built_html([("ModLoaderGui", "1.9.1")]))
    report = tpc.check_package(target, expect_mods=["maplebirch"], min_mods=30)
    assert report["ok"] is False
    assert report["missing_mods"] == ["maplebirch"]
    joined = " ".join(report["errors"])
    assert "missing expected mods" in joined
    assert "< required 30" in joined


def test_check_package_flags_version_mismatch(tmp_path: Path) -> None:
    target = _write_html(
        tmp_path, _built_html([("maplebirch", "4.1.14")], game_version="0.5.12.13")
    )
    report = tpc.check_package(
        target, expect_mods=["maplebirch"], expect_version="0.5.11.9"
    )
    assert report["ok"] is False
    assert any("game version mismatch" in item for item in report["errors"])


def test_check_package_flags_missing_payload_list(tmp_path: Path) -> None:
    target = _write_html(tmp_path, _built_html([], include_list=False))
    report = tpc.check_package(target, expect_mods=["maplebirch"])
    assert report["ok"] is False
    assert any("missing" in item for item in report["errors"])


def test_main_writes_manifest_and_returns_exit_code(tmp_path: Path) -> None:
    target = _write_zip(tmp_path, _built_html([("maplebirch", "4.1.14")]))
    manifest = tmp_path / "mods-manifest.json"
    code = tpc.main(
        [
            str(target),
            "--expect",
            "maplebirch",
            "--expect-version",
            "0.5.11.9",
            "--write-manifest",
            str(manifest),
        ]
    )
    assert code == 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["mods"][0]["name"] == "maplebirch"

    assert tpc.main([str(target), "--expect", "cheat extended"]) == 1
