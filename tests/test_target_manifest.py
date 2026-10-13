"""Fail-closed target identity tests."""

from __future__ import annotations

import json

from tools.target_manifest import build_manifest, validate_manifest


def _write_zip(tmp_path):
    import io
    import zipfile

    path = tmp_path / "game.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("game/index.html", "<html><body>stub</body></html>")
    return path


def test_manifest_is_deterministic_and_fails_without_version(tmp_path) -> None:
    target = _write_zip(tmp_path)
    first = build_manifest(target, expected_version="0.5.11.9")
    second = build_manifest(target, expected_version="0.5.11.9")

    assert first["target"]["game_version"] is None
    assert first["target"]["package_sha256"] == second["target"]["package_sha256"]
    assert first["identity_ok"] is False
    ok, diagnostics = validate_manifest(first)
    assert ok is False
    assert any("game version missing" in item for item in diagnostics)
