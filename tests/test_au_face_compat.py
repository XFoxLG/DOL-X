"""AU facial expansion asset compatibility tests."""

import pytest

from lyra.build import BuildTask, ZipBuilder
from lyra.paths import BuildPaths


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
