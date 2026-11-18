"""Candidate settings must reach spawned workers without mutating defaults."""
import json
import multiprocessing
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from lyra.config_loader import load_build_config
from lyra.compatibility import MORE_LOVE_DRAG_PATCH_KEY, compatibility_surface_by_key, compatibility_source_errors
from lyra.build import MAPLEBIRCH_PET_UPSTREAM_562, patch_maplebirch_pet_passage_remount


ROOT = Path(__file__).resolve().parents[1]


def test_selected_config_reaches_spawned_build_worker(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    build = cfg / "build.toml"
    build.write_text(build.read_text(encoding="utf-8").replace('name = "XFox"', 'name = "Candidate"', 1), encoding="utf-8")
    monkeypatch.setenv("DOLX_CONFIG_DIR", str(cfg))
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        selected = pool.submit(load_build_config).result(timeout=30)
    assert selected.identity_name == "Candidate"
    assert 'name = "XFox"' in (ROOT / "config/build.toml").read_text(encoding="utf-8")


def test_incomplete_explicit_config_fails_before_prepare(tmp_path):
    completed = subprocess.run([sys.executable, str(ROOT / "main.py"), "--config-dir", str(tmp_path), "prepare"], cwd=ROOT, capture_output=True)
    assert completed.returncode == 2
    assert b"build.toml" in completed.stderr
    assert not (tmp_path / "base").exists()


def test_more_love_018_accepts_only_the_reviewed_source():
    source = SimpleNamespace(cache_name="more_love", github_repo="Nephthelana/DoL-More-Love-Interests-Mod", release_tag="More-Love-Interests-Mod-v0.1.8.0", asset_pattern="More.Love.Interests.Mod.mod.zip")
    surface = compatibility_surface_by_key(MORE_LOVE_DRAG_PATCH_KEY)
    assert compatibility_source_errors(surface, source) == []
    source.github_repo = "unreviewed/fork"
    assert compatibility_source_errors(surface, source)


def test_framework_native_sync_is_not_patched_or_assumed_for_unknown_versions(tmp_path):
    source, target = tmp_path / "framework.zip", tmp_path / "patched.zip"
    def write(version, script):
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("boot.json", json.dumps({"name": "maplebirch", "version": version}))
            archive.writestr("dist/inject_early.js", script)
    write("5.6.2", MAPLEBIRCH_PET_UPSTREAM_562)
    before = source.read_bytes()
    assert patch_maplebirch_pet_passage_remount(source, target)["status"] == "upstream_managed"
    assert source.read_bytes() == before and not target.exists()
    write("5.6.2", MAPLEBIRCH_PET_UPSTREAM_562.replace(":passageend", ":storyready"))
    assert patch_maplebirch_pet_passage_remount(source, target)["status"] == "patch_needle_not_found"
    write("5.6.3", MAPLEBIRCH_PET_UPSTREAM_562)
    assert patch_maplebirch_pet_passage_remount(source, target)["status"] == "patch_needle_not_found"
