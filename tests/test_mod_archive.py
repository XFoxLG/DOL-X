"""Exercise the published v1 container layout at download and injection boundaries."""
import base64
import hashlib
import io
import json
import struct
import zipfile

from bson import BSON
import pytest
import xxhash

from lyra.mod_archive import MODPACK_MAGIC, ModArchiveError, mod_zip_bytes
from lyra.config_loader import ModloaderModConfig, get_config_loader
from lyra.paths import BuildPaths
from lyra.prepare import ModInjector
from lyra.warmup import ResourceWarmer


def make_modpack(*, name="tiny", filename="code.js", version="1.0.0"):
    boot = json.dumps({"name": name, "version": version}).encode()
    body = b"window.fixture = true;\x00"
    meta = BSON.encode({
        "magicNumber": "SmVyZW1pZU1vZExvYWRlcg", "name": name,
        "protocolVersion": 1, "blockSize": 64,
        "bootJsonFile": {"b": 0, "e": 0, "l": len(boot)},
        "fileTreeBlock": {"b": 2, "e": 2, "l": 5},
        "fileMeta": {filename: {"b": 1, "e": 1, "l": len(body)}},
    })
    padded = meta + b"\x00" * (-len(meta) % 64)
    data = MODPACK_MAGIC.ljust(64, b"\x00")
    data += struct.pack("<QQQ", 128, 128 + len(meta), 128 + len(padded)).ljust(64, b"\x00")
    data += padded + boot.ljust(64, b"\x00") + body.ljust(64, b"\x00") + BSON.encode({}).ljust(64, b"\x00")
    return data + struct.pack("<Q", xxhash.xxh64(data).intdigest()), boot, body


def test_container_conversion_preserves_members_and_zip_identity():
    data, boot, body = make_modpack()
    converted = mod_zip_bytes(data)
    assert converted == mod_zip_bytes(data)
    assert mod_zip_bytes(converted) == converted
    with zipfile.ZipFile(io.BytesIO(converted)) as zf:
        assert zf.read("boot.json") == boot
        assert zf.read("code.js") == body


def test_corrupt_container_is_rejected_before_injection(tmp_path):
    data, _, _ = make_modpack()
    mod = tmp_path / "tiny.modpack"
    mod.write_bytes(data[:-9] + bytes([data[-9] ^ 1]) + data[-8:])
    html = tmp_path / "index.html"
    original = "window.modDataValueZipList = [];"
    html.write_text(original)
    with pytest.raises(ModArchiveError, match="xxHash64"):
        ModInjector(BuildPaths(workspace=tmp_path)).add_mods(html, [mod])
    assert html.read_text() == original


def test_unsafe_member_path_is_rejected():
    data, _, _ = make_modpack(filename="../outside.js")
    with pytest.raises(ModArchiveError, match="member path"):
        mod_zip_bytes(data)


def test_injector_embeds_a_real_zip_for_modpack(tmp_path):
    data, boot, _ = make_modpack()
    mod = tmp_path / "tiny.modpack"
    mod.write_bytes(data)
    html = tmp_path / "index.html"
    html.write_text("window.modDataValueZipList = [];")
    ModInjector(BuildPaths(workspace=tmp_path)).add_mods(html, [mod])
    entries = json.loads(html.read_text().split("=", 1)[1].strip().rstrip(";"))
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(entries[0]))) as archive:
        assert archive.read("boot.json") == boot


@pytest.mark.parametrize("explicit_config", [False, True])
def test_warmup_keeps_original_digest_and_regenerates_normalized_cache(tmp_path, monkeypatch, explicit_config):
    data, boot, _ = make_modpack()
    config = ModloaderModConfig("example/tiny", "tiny.modpack", key="tiny", feature_id="cheat_extended_maplebirch", release_tag="v1.0.0", download_url="https://example.invalid/tiny.modpack")
    monkeypatch.delenv("DOLX_CONFIG_DIR", raising=False)
    if explicit_config:
        lock_dir = tmp_path / "candidate-config"
        monkeypatch.setenv("DOLX_CONFIG_DIR", str(lock_dir))
    else:
        lock_dir = tmp_path / "config"
    lock = lock_dir / "mods.lock.json"
    lock.parent.mkdir()
    lock.write_text(json.dumps({"mods": {"tiny": {"last_tested_sha256": hashlib.sha256(data).hexdigest()}}}))
    warmer = ResourceWarmer(BuildPaths(workspace=tmp_path), codes=["15704320"])
    warmer.paths.temp_dir.mkdir(parents=True)
    downloads = []
    def download(url, path, quiet):
        downloads.append(url)
        path.write_bytes(data)
    monkeypatch.setattr("lyra.warmup.download_file", download)
    warmer._download_modloader_mod(config, get_config_loader())
    raw = warmer.paths.temp_dir / "tiny.modpack"
    normalized = warmer.paths.get_mod_cache_path("tiny")
    assert raw.read_bytes() == data
    normalized.write_bytes(b"stale derived payload")
    warmer._download_modloader_mod(config, get_config_loader())
    assert len(downloads) == 1
    with zipfile.ZipFile(normalized) as archive:
        assert archive.read("boot.json") == boot
    raw.write_bytes(make_modpack(name="changed")[0])
    with pytest.raises(RuntimeError, match="digest mismatch"):
        warmer._download_modloader_mod(config, get_config_loader())
    assert not normalized.exists(), "Rejected source must not leave a usable derived cache"
