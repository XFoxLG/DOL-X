"""Maplebirch face-style basehead fallback compatibility tests."""

import zipfile
from types import SimpleNamespace

import pytest

from lyra.build import (
    BuildTask,
    MAPLEBIRCH_BASEHEAD_MEMBER,
    MAPLEBIRCH_BASEHEAD_OLD,
    MAPLEBIRCH_PET_REMOUNT_OLD,
    ZipBuilder,
    _maplebirch_basehead_replacement,
    patch_maplebirch_basehead_fallback,
    resolve_maplebirch_face_index_identifier,
)
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths


def _face_index_helper(identifier: str) -> str:
    """Reproduce Maplebirch's real aO() helper, which owns the face-index Set.

    The patch must bind its ``.has()`` call to whatever this Set is named in the
    asset being patched.  Upstream renamed it from ``aP`` (v4.1.13) to ``aI``
    (v4.1.14), so fixtures have to carry the real helper shape rather than a
    hand-written ``const aP = ...`` alias, which is what previously let a broken
    replacement pass the suite.
    """
    return (
        f"let {identifier}=new Set;"
        f"function aO(e){{let t=e.find(e=>{identifier}.has(e));if(t)return t;"
        'let n="";for(let t of e){let e=no(t);if(e===t||!0===e)return t;'
        "!1===e||n||(n=t)}return n||e[0]}"
    )


# The Maplebirch payload receives two chained fail-closed patches, so the fake
# payload must carry both upstream needles for the injection path to succeed.
MAPLEBIRCH_SCRIPT = (
    f"{_face_index_helper('aP')}"
    f"const layers={{{MAPLEBIRCH_BASEHEAD_OLD},freckles:{{}}}};"
    f"class Character{{{MAPLEBIRCH_PET_REMOUNT_OLD},this.use('pre',aB,'main')}}}}"
)

# Same payload with the Set renamed the way upstream v4.1.14 renamed it.
MAPLEBIRCH_SCRIPT_RENAMED_SET = (
    f"{_face_index_helper('aI')}"
    "let aP={wolf:e=>V.wolfbuild=e,cat:e=>V.catbuild=e};"
    f"const layers={{{MAPLEBIRCH_BASEHEAD_OLD},freckles:{{}}}};"
    f"class Character{{{MAPLEBIRCH_PET_REMOUNT_OLD},this.use('pre',aB,'main')}}}}"
)


def _write_maplebirch_payload(path, script: str = MAPLEBIRCH_SCRIPT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.14"}',
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
    assert result["face_index_identifier"] == "aP"
    patched_script = _read_maplebirch_script(target)
    assert MAPLEBIRCH_BASEHEAD_OLD not in patched_script
    assert _maplebirch_basehead_replacement("aP") in patched_script
    assert "img/body/base-head.png" in patched_script

    original_script = _read_maplebirch_script(source)
    assert MAPLEBIRCH_BASEHEAD_OLD in original_script


@pytest.mark.config
def test_face_index_identifier_is_resolved_from_the_asset(tmp_path):
    """The Set name is read out of the payload, not assumed to be aP."""
    assert resolve_maplebirch_face_index_identifier(MAPLEBIRCH_SCRIPT) == "aP"
    assert resolve_maplebirch_face_index_identifier(MAPLEBIRCH_SCRIPT_RENAMED_SET) == "aI"
    assert resolve_maplebirch_face_index_identifier("let x=new Set;") is None


@pytest.mark.config
def test_basehead_patch_binds_to_renamed_face_index_set(tmp_path):
    """Regression: upstream v4.1.14 renamed the face-index Set from aP to aI.

    The previous patch hardcoded ``aP``, and in v4.1.14 ``aP`` is an unrelated
    transformation table, so the emitted srcfn threw
    ``TypeError: aP.has is not a function`` on every render.  The replacement must
    follow the rename.
    """
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source, MAPLEBIRCH_SCRIPT_RENAMED_SET)

    result = patch_maplebirch_basehead_fallback(source, target)

    assert result["status"] == "patched"
    assert result["face_index_identifier"] == "aI"
    patched_script = _read_maplebirch_script(target)
    assert _maplebirch_basehead_replacement("aI") in patched_script
    # The stale hardcoded form must not survive anywhere in the emitted payload.
    assert "aP.has(" not in patched_script


@pytest.mark.config
def test_basehead_patch_fails_closed_when_face_index_set_cannot_be_resolved(tmp_path):
    """No provable Set means no patch: guessing produced the aP/aI defect."""
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(
        source,
        f"const layers={{{MAPLEBIRCH_BASEHEAD_OLD}}};",
    )

    result = patch_maplebirch_basehead_fallback(source, target)

    assert result["applied"] is False
    assert result["status"] == "face_index_identifier_unresolved"
    assert not target.exists()


@pytest.mark.config
def test_maplebirch_basehead_patch_preserves_unrelated_payload_members(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source)

    patch_maplebirch_basehead_fallback(source, target)

    with zipfile.ZipFile(target, "r") as payload_zip:
        assert payload_zip.read("README.md") == b"unchanged"
        assert payload_zip.read("boot.json") == (
            b'{"name":"maplebirch","version":"4.1.14"}'
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
    assert _maplebirch_basehead_replacement("aP") in _read_maplebirch_script(
        injected_path
    )
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
        release_tag="maplebirch-release-v4.1.14",
        asset_pattern="maplebirch-0.5.10.12-v4.1.14.mod.zip",
    )

    with pytest.raises(RuntimeError, match="source mismatch"):
        builder._modloader_mod_path_for_injection(drifted_config, source)
