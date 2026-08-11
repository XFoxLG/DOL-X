"""Maplebirch desktop pet passage-remount compatibility tests."""

import zipfile
from types import SimpleNamespace

import pytest

from lyra.build import (
    BuildTask,
    MAPLEBIRCH_PET_REMOUNT_MARKER,
    MAPLEBIRCH_PET_REMOUNT_MEMBER,
    MAPLEBIRCH_PET_REMOUNT_NEW,
    MAPLEBIRCH_PET_REMOUNT_OLD,
    ZipBuilder,
    patch_maplebirch_pet_passage_remount,
)
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths


# Mirrors the upstream Character.preInit() pet sync wiring that the patch rewrites.
MAPLEBIRCH_UPSTREAM_BASEHEAD = (
    'basehead:{srcfn:e=>e.mannequin?"img/body/mannequin/base-head.png":'
    'aO([`img/face/${e.facestyle}/base-head.png`,"img/body/base-head.png"])}'
)
MAPLEBIRCH_SCRIPT = (
    f"const layers={{{MAPLEBIRCH_UPSTREAM_BASEHEAD},freckles:{{}}}};"
    f"class Character{{{MAPLEBIRCH_PET_REMOUNT_OLD},this.use('pre',aB,'main')}}}}"
)


def _write_maplebirch_payload(path, script: str = MAPLEBIRCH_SCRIPT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.14"}',
        )
        payload_zip.writestr(MAPLEBIRCH_PET_REMOUNT_MEMBER, script)
        payload_zip.writestr("README.md", "unchanged")


def _read_maplebirch_script(path) -> str:
    with zipfile.ZipFile(path, "r") as payload_zip:
        return payload_zip.read(MAPLEBIRCH_PET_REMOUNT_MEMBER).decode("utf-8")


def _maplebirch_config():
    return next(
        mod
        for mod in load_build_config().modloader_mods
        if mod.cache_name == "maplebirch"
    )


@pytest.mark.config
def test_pet_remount_patch_subscribes_passage_display_to_pet_sync(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    result = patch_maplebirch_pet_passage_remount(source, target)

    assert result["status"] == "patched"
    assert result["applied"] is True
    patched_script = _read_maplebirch_script(target)
    assert MAPLEBIRCH_PET_REMOUNT_NEW in patched_script
    assert patched_script.count(MAPLEBIRCH_PET_REMOUNT_MARKER) == 1
    # The original storyready/updatesidebarimg wiring must survive untouched.
    assert 'e.once(":storyready"' in patched_script
    assert "n.handler.call(this),t.sync()" in patched_script
    assert ':passagedisplay' in patched_script


@pytest.mark.config
def test_pet_remount_patch_refreshes_through_sidebar_macro(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    patch_maplebirch_pet_passage_remount(source, target)
    patched_script = _read_maplebirch_script(target)

    # Pet.draw() falls back to an undressed default model when the sidebar cache
    # is missing, so the remount must reuse the framework's wrapped macro instead
    # of calling pet.sync() directly on a freshly rendered passage.
    assert '$.wiki("<<updatesidebarimg>>")' in patched_script
    remount_handler = patched_script.split(':passagedisplay', 1)[1]
    assert "t.sync()" not in remount_handler


@pytest.mark.config
def test_pet_remount_patch_only_acts_when_enabled_and_container_empty(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    patch_maplebirch_pet_passage_remount(source, target)
    patched_script = _read_maplebirch_script(target)

    # Guard conditions keep the patch inert for disabled pets and for containers
    # that already hold the canvas, which makes repeated events harmless.
    assert "V.options?.maplebirch?.character?.pet?.enabled" in patched_script
    assert "0===r.childElementCount" in patched_script


@pytest.mark.config
def test_pet_remount_patch_preserves_unrelated_payload_members(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    patch_maplebirch_pet_passage_remount(source, target)

    with zipfile.ZipFile(target, "r") as payload_zip:
        assert payload_zip.read("README.md") == b"unchanged"
        assert payload_zip.read("boot.json") == (
            b'{"name":"maplebirch","version":"4.1.14"}'
        )


@pytest.mark.config
def test_pet_remount_patch_is_idempotent(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    first_target = tmp_path / "maplebirch.first.mod.zip"
    second_target = tmp_path / "maplebirch.second.mod.zip"
    _write_maplebirch_payload(source)

    first_result = patch_maplebirch_pet_passage_remount(source, first_target)
    second_result = patch_maplebirch_pet_passage_remount(
        first_target,
        second_target,
    )

    assert first_result["status"] == "patched"
    assert second_result["status"] == "already_patched"
    assert second_result["applied"] is False
    assert not second_target.exists()


@pytest.mark.config
def test_maplebirch_injection_applies_pet_remount_patch(tmp_path):
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
    injected_script = _read_maplebirch_script(injected_path)
    assert MAPLEBIRCH_PET_REMOUNT_MARKER in injected_script
    assert MAPLEBIRCH_UPSTREAM_BASEHEAD in injected_script
    assert ".has(`img/face/${e.facestyle}/base-head.png`)" not in injected_script
    assert MAPLEBIRCH_PET_REMOUNT_MARKER not in _read_maplebirch_script(source)


@pytest.mark.config
def test_pet_remount_injection_fails_closed_when_needle_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(
        source,
        "class Character{preInit(){/* upstream rewrote pet wiring */}}",
    )

    with pytest.raises(
        RuntimeError,
        match="pet remount compatibility patch failed: patch_needle_not_found",
    ):
        builder._modloader_mod_path_for_injection(_maplebirch_config(), source)


@pytest.mark.config
def test_pet_remount_injection_fails_closed_when_source_metadata_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source)

    drifted_config = SimpleNamespace(
        cache_name="maplebirch",
        github_repo="example/wrong",
        release_tag="maplebirch-release-v4.1.14",
        asset_pattern="maplebirch-0.5.10.12-v4.1.14.mod.zip",
    )

    with pytest.raises(RuntimeError, match="source mismatch"):
        builder._modloader_mod_path_for_injection(drifted_config, source)
