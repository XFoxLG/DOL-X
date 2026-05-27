"""Phase 3 static HTML smoke tests."""

import base64
import io
import json
import zipfile

import pytest

from tools.html_smoke_test import audit_html


def _embedded_mod_zip() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", "{}")
        zf.writestr("main.js", "console.log('ok');")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.config
def test_html_smoke_accepts_embedded_mod_zip(tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text(
        "<html><script>window.modDataValueZipList = "
        + json.dumps([_embedded_mod_zip()])
        + ";</script></html>",
        encoding="utf-8",
    )

    result = audit_html(html_path)

    assert result.success is True
    assert result.html_found is True
    assert result.mod_count == 1
    assert result.valid_zip_count == 1


@pytest.mark.config
def test_html_smoke_fails_without_mod_list(tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    result = audit_html(html_path)

    assert result.success is False
    assert any("modDataValueZipList" in error for error in result.errors)
