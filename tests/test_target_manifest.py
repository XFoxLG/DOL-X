"""Fail-closed target identity tests."""

from __future__ import annotations

import hashlib
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


def test_manifest_records_apk_sha256_when_supplied(tmp_path) -> None:
    target = _write_zip(tmp_path)
    apk = tmp_path / "game.apk"
    apk.write_bytes(b"apk-bytes")

    manifest = build_manifest(target, expected_version="0.5.11.9", apk=apk)

    assert manifest["target"]["apk_sha256"] == hashlib.sha256(b"apk-bytes").hexdigest()


def test_manifest_without_apk_stays_backward_compatible(tmp_path) -> None:
    target = _write_zip(tmp_path)

    manifest = build_manifest(target, expected_version="0.5.11.9")

    assert manifest["target"]["apk_sha256"] is None
    # A missing APK digest is not an identity error: desktop-only evidence
    # predates the field, and only the release gate binds it fail-closed.
    _ok, diagnostics = validate_manifest(manifest)
    assert not any("apk" in item for item in diagnostics)


def test_manifest_ignores_missing_apk_path(tmp_path) -> None:
    target = _write_zip(tmp_path)

    manifest = build_manifest(
        target,
        expected_version="0.5.11.9",
        apk=tmp_path / "not-there.apk",
    )

    assert manifest["target"]["apk_sha256"] is None
