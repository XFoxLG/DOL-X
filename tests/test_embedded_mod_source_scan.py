"""Embedded ModLoader source scanner tests."""

import base64
import io
import json
import zipfile

import pytest

from tools.embedded_mod_source_scan import scan_target


def _embedded_mod_zip(boot_json: dict, files: dict[str, str]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", json.dumps(boot_json, ensure_ascii=False))
        for name, content in files.items():
            zf.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _write_html(path, payloads: list[str]) -> None:
    path.write_text(
        "<html><script>window.modDataValueZipList = "
        + json.dumps(payloads)
        + ";</script></html>",
        encoding="utf-8",
    )


@pytest.mark.config
def test_embedded_mod_source_scan_finds_source_file_matches(tmp_path):
    html_path = tmp_path / "Degrees of Lewdity.html"
    payload = _embedded_mod_zip(
        {"name": "Custom-Spellbook"},
        {
            "main.js": "function handler(ev) {\n  ev.preventDefault();\n}\n",
            "readme.txt": "no match",
        },
    )
    _write_html(html_path, [payload])

    result = scan_target(html_path, r"ev\.preventDefault")

    assert result.success is True
    assert result.errors == []
    assert len(result.hits) == 1
    assert result.hits[0].mod_name == "Custom-Spellbook"
    assert result.hits[0].member == "main.js"
    assert result.hits[0].line == 2
    assert "ev.preventDefault" in result.hits[0].sample


@pytest.mark.config
def test_embedded_mod_source_scan_accepts_zip_artifact_targets(tmp_path):
    html_payload = _embedded_mod_zip(
        {"name": "ExampleMod"},
        {"dist/mod.js": "console.log('loaded');"},
    )
    html_content = (
        "<html><script>window.modDataValueZipList = "
        + json.dumps([html_payload])
        + ";</script></html>"
    )
    zip_path = tmp_path / "DoL-au-f-example.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Degrees of Lewdity.html", html_content)

    result = scan_target(zip_path, r"console\.log")

    assert result.success is True
    assert len(result.hits) == 1
    assert result.hits[0].mod_name == "ExampleMod"
    assert result.hits[0].member == "dist/mod.js"


@pytest.mark.config
def test_embedded_mod_source_scan_reports_missing_mod_list(tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    result = scan_target(html_path, r"anything")

    assert result.success is False
    assert any("modDataValueZipList" in error for error in result.errors)
