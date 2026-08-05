"""Maplebirch face-style basehead fallback compatibility tests."""

import zipfile
from types import SimpleNamespace

import pytest

from lyra.build import (
    BuildTask,
    MAPLEBIRCH_BASEHEAD_MEMBER,
    MAPLEBIRCH_BASEHEAD_NEW,
    MAPLEBIRCH_BASEHEAD_OLD,
    ZipBuilder,
    patch_maplebirch_basehead_fallback,
)
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths


MAPLEBIRCH_SCRIPT = (
    "const faceImagePaths = new Set();"
    "const aP = faceImagePaths;"
    f"const layers={{{MAPLEBIRCH_BASEHEAD_OLD},freckles:{{}}}};"
)


def _write_maplebirch_payload(path, script: str = MAPLEBIRCH_SCRIPT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.13"}',
        )
        payload_zip.writestr(MAPLEBIRCH_BASEHEAD_MEMBER, script)
        payload_zip.writestr("README.md", "unchanged")


def _read_maplebirch_script(path) -> str:
    with zipfile.ZipFile(path, "r") as payload_zip:
        return payload_zip.read(MAPLEBIRCH_BASEHEAD_MEMBER).decode("utf-8")


def _maplebirch_config():
    return next(
        mod
        for mod in load_build_config().modloader_mods
        if mod.cache_name == "maplebirch"
    )


@pytest.mark.config
def test_maplebirch_basehead_patch_uses_completed_face_image_index(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    result = patch_maplebirch_basehead_fallback(source, target)

    assert result["status"] == "patched"
    assert result["applied"] is True
    patched_script = _read_maplebirch_script(target)
    assert MAPLEBIRCH_BASEHEAD_OLD not in patched_script
    assert MAPLEBIRCH_BASEHEAD_NEW in patched_script
    assert "img/body/base-head.png" in patched_script

    original_script = _read_maplebirch_script(source)
    assert MAPLEBIRCH_BASEHEAD_OLD in original_script


@pytest.mark.config
def test_maplebirch_basehead_patch_preserves_unrelated_payload_members(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    patch_maplebirch_basehead_fallback(source, target)

    with zipfile.ZipFile(target, "r") as payload_zip:
        assert payload_zip.read("README.md") == b"unchanged"
        assert payload_zip.read("boot.json") == (
            b'{"name":"maplebirch","version":"4.1.13"}'
        )


@pytest.mark.config
def test_maplebirch_basehead_patch_is_idempotent(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    first_target = tmp_path / "maplebirch.first.mod.zip"
    second_target = tmp_path / "maplebirch.second.mod.zip"
    _write_maplebirch_payload(source)

    first_result = patch_maplebirch_basehead_fallback(source, first_target)
    second_result = patch_maplebirch_basehead_fallback(
        first_target,
        second_target,
    )

    assert first_result["status"] == "patched"
    assert second_result["status"] == "already_patched"
    assert second_result["applied"] is False
    assert not second_target.exists()


@pytest.mark.config
def test_maplebirch_injection_uses_build_local_patched_payload(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source)

    injected_path = builder._modloader_mod_path_for_injection(
        _maplebirch_config(),
        source,
    )

    assert injected_path != source
    assert injected_path.exists()
    assert MAPLEBIRCH_BASEHEAD_NEW in _read_maplebirch_script(injected_path)
    assert MAPLEBIRCH_BASEHEAD_OLD in _read_maplebirch_script(source)


@pytest.mark.config
def test_maplebirch_injection_fails_closed_when_patch_needle_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source, "const layers = { basehead: {} };")

    with pytest.raises(RuntimeError, match="patch failed: patch_needle_not_found"):
        builder._modloader_mod_path_for_injection(_maplebirch_config(), source)


@pytest.mark.config
def test_maplebirch_injection_fails_closed_when_source_metadata_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source)

    drifted_config = SimpleNamespace(
        cache_name="maplebirch",
        github_repo="example/wrong",
        release_tag="maplebirch-release-v4.1.13",
        asset_pattern="maplebirch-0.5.10.12-v4.1.13.mod.zip",
    )

    with pytest.raises(RuntimeError, match="source mismatch"):
        builder._modloader_mod_path_for_injection(drifted_config, source)
