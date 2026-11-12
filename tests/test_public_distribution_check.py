"""Public upload rejection for real released AU identities and encodings."""
import base64
import io
import json
import zipfile

import pytest

from tools.public_distribution_check import check_artifact


def package_html(mod_name, prefix=""):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr(prefix + "boot.json", json.dumps({"name": mod_name, "version": "1.2.16"}))
    payload = base64.b64encode(raw.getvalue()).decode()
    return "window.modDataValueZipList = " + json.dumps([payload]) + ";"


@pytest.mark.parametrize("name,prefix", [
    ("【AUfemale】model", "AUfemale/"),
    ("【AUmale】model", "AUmale/"),
    ("【AUandrogynous】model", "AUandrogynous/"),
    ("【AUsDoL】facial expansion", ""),
    ("AU面部扩展", ""),
])
@pytest.mark.parametrize("format", ["html", "zip", "apk"])
def test_restricted_payload_detected_inside_game_even_if_renamed(tmp_path, name, prefix, format):
    path = tmp_path / ("renamed-game." + format)
    html = package_html(name, prefix)
    if format == "html":
        path.write_text(html, encoding="utf-8")
    else:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("assets/www/index.html" if format == "apk" else "Degrees of Lewdity.html", html)
    findings = check_artifact(path)
    assert len(findings) == 1
    assert findings[0]["mod"] == name
    assert findings[0]["rule"] == ("redistribution-permission-unconfirmed" if "facial" in name or "面部" in name else "author-prohibits-redistribution")


def test_base_and_independent_compat_source_are_not_au_assets(tmp_path):
    path = tmp_path / "base.html"
    path.write_text(package_html("dolx-compat"), encoding="utf-8")
    assert check_artifact(path) == []


def test_unreadable_game_never_counts_as_permission_clear(tmp_path):
    path = tmp_path / "empty.html"
    path.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ValueError, match="payload inspection failed"):
        check_artifact(path)
