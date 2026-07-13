"""DOLI float-button icon path compatibility patch tests."""

import zipfile
from types import SimpleNamespace

import pytest

from lyra.build import (
    BuildTask,
    DOLI_FLOAT_ICON_MEMBER,
    DOLI_FLOAT_ICON_NEW,
    DOLI_FLOAT_ICON_OLD,
    ZipBuilder,
    patch_doli_float_icon_path,
)
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths


DOLI_FLOAT_SCRIPT = """class FloatButton {
    mount() {
        const icon = document.createElement('img');
        icon.className = `${constants_js_1.CSS_PREFIX}btn-icon-img`;
        icon.src = 'img/ui/sym_awareness.png';
        icon.alt = '';
    }
}
"""


def _write_doli_payload(path, script: str = DOLI_FLOAT_SCRIPT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("boot.json", '{"name":"DOLI"}')
        zf.writestr(DOLI_FLOAT_ICON_MEMBER, script)
        zf.writestr("README.md", "unchanged")


def _read_icon_script(path) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        return zf.read(DOLI_FLOAT_ICON_MEMBER).decode("utf-8")


def _read_entries(path, member_name: str) -> list[str]:
    with zipfile.ZipFile(path, "r") as zf:
        return [
            zf.read(member).decode("utf-8")
            for member in zf.infolist()
            if member.filename == member_name
        ]


def _doli_config():
    return next(mod for mod in load_build_config().modloader_mods if mod.cache_name == "doli")


@pytest.mark.config
def test_doli_float_icon_patch_rewrites_stale_asset_path(tmp_path):
    source = tmp_path / "doli.mod.zip"
    target = tmp_path / "doli.patched.mod.zip"
    _write_doli_payload(source)

    result = patch_doli_float_icon_path(source, target)

    assert result["status"] == "patched"
    assert result["applied"] is True
    patched_script = _read_icon_script(target)
    assert DOLI_FLOAT_ICON_OLD not in patched_script
    assert DOLI_FLOAT_ICON_NEW in patched_script
    assert "icon.src = 'img/ui/sym-awareness.png';" in patched_script

    original_script = _read_icon_script(source)
    assert DOLI_FLOAT_ICON_OLD in original_script


@pytest.mark.config
def test_doli_float_icon_patch_preserves_duplicate_zip_entries(tmp_path):
    source = tmp_path / "doli.mod.zip"
    target = tmp_path / "doli.patched.mod.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("boot.json", '{"name":"DOLI"}')
        zf.writestr(DOLI_FLOAT_ICON_MEMBER, DOLI_FLOAT_SCRIPT)
        zf.writestr("README.md", "first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr("README.md", "second")

    with pytest.warns(UserWarning, match="Duplicate name"):
        result = patch_doli_float_icon_path(source, target)

    assert result["status"] == "patched"
    assert _read_entries(target, "README.md") == ["first", "second"]


@pytest.mark.config
def test_doli_float_icon_patch_is_idempotent(tmp_path):
    source = tmp_path / "doli.mod.zip"
    first_target = tmp_path / "doli.first.mod.zip"
    second_target = tmp_path / "doli.second.mod.zip"
    _write_doli_payload(source)

    first = patch_doli_float_icon_path(source, first_target)
    second = patch_doli_float_icon_path(first_target, second_target)

    assert first["status"] == "patched"
    assert second["status"] == "already_patched"
    assert second["applied"] is False
    assert not second_target.exists()


@pytest.mark.config
def test_doli_injection_uses_build_local_patched_payload(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=8388608, paths=paths))
    source = paths.get_mod_cache_path("doli")
    _write_doli_payload(source)

    injected_path = builder._modloader_mod_path_for_injection(_doli_config(), source)

    assert injected_path != source
    assert injected_path.exists()
    assert DOLI_FLOAT_ICON_NEW in _read_icon_script(injected_path)
    assert DOLI_FLOAT_ICON_OLD not in _read_icon_script(injected_path)
    assert DOLI_FLOAT_ICON_OLD in _read_icon_script(source)


@pytest.mark.config
def test_doli_injection_fails_closed_when_patch_needle_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=8388608, paths=paths))
    source = paths.get_mod_cache_path("doli")
    _write_doli_payload(source, "const icon = document.createElement('img');\n")

    with pytest.raises(RuntimeError, match="patch failed: patch_needle_not_found"):
        builder._modloader_mod_path_for_injection(_doli_config(), source)


@pytest.mark.config
def test_doli_injection_fails_closed_when_source_metadata_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=8388608, paths=paths))
    source = paths.get_mod_cache_path("doli")
    _write_doli_payload(source)

    drifted_config = SimpleNamespace(
        cache_name="doli",
        github_repo="example/wrong",
        release_tag="v0.2.3",
        asset_pattern="DOLI.mod.zip",
    )

    with pytest.raises(RuntimeError, match="source mismatch"):
        builder._modloader_mod_path_for_injection(drifted_config, source)
