"""More Love runtime compatibility patch tests."""

import zipfile
from types import SimpleNamespace

import pytest

from lyra.build import (
    BuildTask,
    MORE_LOVE_DRAG_MEMBER,
    MORE_LOVE_DRAG_PATCH_MARKER,
    ZipBuilder,
    patch_more_love_drag_event_handlers,
)
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths


MORE_LOVE_DRAG_SCRIPT = """function allowDropMLIM(ev) {
\tev.preventDefault();
}
function dragMLIM(ev) {
\tev.dataTransfer.setData("Text", ev.target.id);
}
function dropLoveMLIM(ev) {
\tev.preventDefault();
    var data = ev.dataTransfer.getData("Text");
}
document.body.ondrop = function (ev) {
\tev.preventDefault()
\tev.stopPropagation()
}
"""


def _write_more_love_payload(path, script: str = MORE_LOVE_DRAG_SCRIPT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("boot.json", '{"name":"More Love Interests Mod"}')
        zf.writestr(MORE_LOVE_DRAG_MEMBER, script)
        zf.writestr("README.md", "unchanged")


def _read_drag_script(path) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        return zf.read(MORE_LOVE_DRAG_MEMBER).decode("utf-8")


def _read_entries(path, member_name: str) -> list[str]:
    with zipfile.ZipFile(path, "r") as zf:
        return [
            zf.read(member).decode("utf-8")
            for member in zf.infolist()
            if member.filename == member_name
        ]


def _more_love_config():
    return next(mod for mod in load_build_config().modloader_mods if mod.cache_name == "more_love")


@pytest.mark.config
def test_more_love_drag_payload_patch_guards_non_dom_event_arguments(tmp_path):
    source = tmp_path / "more_love.mod.zip"
    target = tmp_path / "more_love.patched.mod.zip"
    _write_more_love_payload(source)

    result = patch_more_love_drag_event_handlers(source, target)

    assert result["status"] == "patched"
    assert result["applied"] is True
    patched_script = _read_drag_script(target)
    assert patched_script.startswith(";\n")
    assert patched_script.rstrip().endswith(";")
    assert MORE_LOVE_DRAG_PATCH_MARKER in patched_script
    assert "ev.preventDefault()" not in patched_script
    assert "ev.stopPropagation()" not in patched_script
    assert "ev.dataTransfer.getData" not in patched_script
    assert "ev.dataTransfer.setData" not in patched_script
    assert "preventDefaultMLIM(ev);" in patched_script
    assert "stopPropagationMLIM(ev);" in patched_script
    assert "getDataTransferTextMLIM(ev)" in patched_script
    assert 'setDataTransferTextMLIM(ev, ev && ev.target ? ev.target.id : "");' in patched_script

    original_script = _read_drag_script(source)
    assert "ev.preventDefault();" in original_script
    assert "ev.dataTransfer.setData" in original_script


@pytest.mark.config
def test_more_love_drag_payload_patch_preserves_duplicate_zip_entries(tmp_path):
    source = tmp_path / "more_love.mod.zip"
    target = tmp_path / "more_love.patched.mod.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("boot.json", '{"name":"More Love Interests Mod"}')
        zf.writestr(MORE_LOVE_DRAG_MEMBER, MORE_LOVE_DRAG_SCRIPT)
        zf.writestr("README.md", "first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr("README.md", "second")

    with pytest.warns(UserWarning, match="Duplicate name"):
        result = patch_more_love_drag_event_handlers(source, target)

    assert result["status"] == "patched"
    assert _read_entries(target, "README.md") == ["first", "second"]


@pytest.mark.config
def test_more_love_drag_payload_patch_is_idempotent(tmp_path):
    source = tmp_path / "more_love.mod.zip"
    first_target = tmp_path / "more_love.first.mod.zip"
    second_target = tmp_path / "more_love.second.mod.zip"
    _write_more_love_payload(source)

    first = patch_more_love_drag_event_handlers(source, first_target)
    second = patch_more_love_drag_event_handlers(first_target, second_target)

    assert first["status"] == "patched"
    assert second["status"] == "already_patched"
    assert second["applied"] is False
    assert not second_target.exists()


@pytest.mark.config
def test_more_love_injection_uses_build_local_patched_payload(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("more_love")
    _write_more_love_payload(source)

    injected_path = builder._modloader_mod_path_for_injection(_more_love_config(), source)

    assert injected_path != source
    assert injected_path.exists()
    assert MORE_LOVE_DRAG_PATCH_MARKER in _read_drag_script(injected_path)
    assert MORE_LOVE_DRAG_PATCH_MARKER not in _read_drag_script(source)


@pytest.mark.config
def test_non_more_love_payload_injection_uses_original_path(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("custom_spellbook")
    _write_more_love_payload(source)

    injected_path = builder._modloader_mod_path_for_injection(
        SimpleNamespace(cache_name="custom_spellbook"),
        source,
    )

    assert injected_path == source


@pytest.mark.config
def test_more_love_injection_fails_closed_when_patch_needle_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("more_love")
    _write_more_love_payload(source, "function dragMLIM(ev) { return true; }\n")

    with pytest.raises(RuntimeError, match="patch failed: patch_needle_not_found"):
        builder._modloader_mod_path_for_injection(_more_love_config(), source)


@pytest.mark.config
def test_more_love_injection_fails_closed_when_source_metadata_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=24834, paths=paths))
    source = paths.get_mod_cache_path("more_love")
    _write_more_love_payload(source)

    drifted_config = SimpleNamespace(
        cache_name="more_love",
        github_repo="example/wrong",
        release_tag="More-Love-Interests-Mod-v0.1.6.0",
        asset_pattern="More.Love.Interests.Mod.mod.zip",
    )

    with pytest.raises(RuntimeError, match="source mismatch"):
        builder._modloader_mod_path_for_injection(drifted_config, source)
