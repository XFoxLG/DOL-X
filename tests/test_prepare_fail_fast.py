"""Fail-fast tests for required base mod injection."""

import pytest

from lyra.paths import BuildPaths
from lyra.prepare import GamePreparer, ModInjectionError


@pytest.mark.config
def test_missing_required_base_mods_fail_fast(tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text(
        '<script>window.modDataValueZipList = ["existing"];</script>',
        encoding="utf-8",
    )

    preparer = GamePreparer(BuildPaths(workspace=tmp_path))

    with pytest.raises(ModInjectionError, match="required base mods"):
        preparer._inject_mods(html_path, {})


@pytest.mark.config
def test_missing_mod_data_list_fails_instead_of_silently_skipping(tmp_path):
    html_path = tmp_path / "index.html"
    mod_path = tmp_path / "mod.mod.zip"
    html_path.write_text("<html></html>", encoding="utf-8")
    mod_path.write_bytes(b"not checked here")

    injector = GamePreparer(BuildPaths(workspace=tmp_path)).mod_injector

    with pytest.raises(ModInjectionError, match="modDataValueZipList"):
        injector.add_mods(html_path, [mod_path])
