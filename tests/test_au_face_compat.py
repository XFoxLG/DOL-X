"""AU facial expansion asset compatibility tests."""

import zipfile

import pytest

from lyra.build import BuildTask, ZipBuilder
from lyra.paths import BuildPaths
from tools.au_artifact_check import audit_target, audit_zip_artifact


def _zip_builder(tmp_path, mod_code: int) -> ZipBuilder:
    paths = BuildPaths(workspace=tmp_path)
    task = BuildTask(pack_type="zip", mod_code=mod_code, paths=paths)
    return ZipBuilder(task)


@pytest.mark.config
def test_au_face_compatibility_aliases_copy_default_blush_layers(tmp_path):
    """AU builds copy default blush layers to the nested runtime path."""
    builder = _zip_builder(tmp_path, 28930)
    source = builder.img_path / "face" / "default" / "blush1.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-png")

    copied = builder._apply_au_face_compatibility_aliases()

    target = builder.img_path / "face" / "default" / "default" / "blush1.png"
    assert target.exists()
    assert target.read_bytes() == b"fake-png"
    assert copied == ["face/default/default/blush1.png"]


@pytest.mark.config
def test_au_face_compatibility_aliases_preserve_existing_targets(tmp_path):
    """Existing nested assets are left untouched if upstream starts shipping them."""
    builder = _zip_builder(tmp_path, 25858)
    source = builder.img_path / "face" / "default" / "blush1.png"
    target = builder.img_path / "face" / "default" / "default" / "blush1.png"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source-png")
    target.write_bytes(b"already-present")

    copied = builder._apply_au_face_compatibility_aliases()

    assert copied == []
    assert target.read_bytes() == b"already-present"


@pytest.mark.config
def test_au_face_compatibility_aliases_skip_non_au_build(tmp_path):
    """Stable base builds do not create AU-only compatibility aliases."""
    builder = _zip_builder(tmp_path, 24834)
    source = builder.img_path / "face" / "default" / "blush1.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-png")

    copied = builder._apply_au_face_compatibility_aliases()

    target = builder.img_path / "face" / "default" / "default" / "blush1.png"
    assert copied == []
    assert not target.exists()


def _write_zip(path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, b"png")


@pytest.mark.config
def test_au_artifact_check_accepts_nested_blush_aliases(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush{index}.png" for index in range(1, 7)]
    _write_zip(zip_path, names)

    result = audit_zip_artifact(zip_path)

    assert result.success is True
    assert result.is_au is True
    assert result.required_nested_blush_present is True
    assert result.nested_blush_count == 6
    assert result.errors == []


@pytest.mark.config
def test_au_artifact_check_rejects_missing_nested_blush_aliases(tmp_path):
    zip_path = tmp_path / "DoL-au-a-ucb-more-love-custom-spellbook.zip"
    _write_zip(zip_path, ["img/face/default/default/blush2.png"])

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert result.required_nested_blush_present is False
    assert result.nested_blush_count == 1
    assert any("blush1.png" in error for error in result.errors)
    assert any("at least 6" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_ignores_non_au_zip(tmp_path):
    zip_path = tmp_path / "DoL-ucb-more-love-custom-spellbook.zip"
    _write_zip(zip_path, [])

    result = audit_zip_artifact(zip_path)

    assert result.success is True
    assert result.is_au is False


@pytest.mark.config
def test_au_artifact_check_directory_covers_all_zips(tmp_path):
    au_zip = tmp_path / "DoL-au-m-ucb-more-love-custom-spellbook.zip"
    base_zip = tmp_path / "DoL-ucb-more-love-custom-spellbook.zip"
    _write_zip(au_zip, [f"img/face/default/default/blush{index}.png" for index in range(1, 7)])
    _write_zip(base_zip, [])

    results = audit_target(tmp_path)

    assert len(results) == 2
    assert all(result.success for result in results)
    assert any(result.is_au for result in results)
    assert any(not result.is_au for result in results)
