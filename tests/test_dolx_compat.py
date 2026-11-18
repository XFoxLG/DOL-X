"""Verify the standalone ownership move at its source, cache and runtime seams."""

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import zipfile

import pytest

from lyra.build import BuildTask, ZipBuilder
from lyra.config_loader import ConfigLoader, ModloaderModConfig, get_config_loader
from lyra.mod_archive import ModArchiveError, source_mod_zip_bytes
from lyra.paths import BuildPaths
from lyra.prepare import ModInjector
from lyra.warmup import ResourceWarmer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mods/dolx-compat"
CANDIDATE = ROOT / "config/candidates/november-unified"


def test_candidate_source_resolves_and_declares_exact_dependencies():
    config = ConfigLoader(CANDIDATE).build
    mod = next(m for m in config.modloader_mods if m.cache_name == "dolx_compat")
    assert (CANDIDATE / mod.source_dir).resolve() == SOURCE
    assert mod.required_feature_ids == ["ucb"]
    assert mod.release_tag == "1.0.1"
    boot = json.loads((SOURCE / "boot.json").read_text(encoding="utf-8"))
    assert boot["dependenceInfo"] == [
        {"modName": "GameVersion", "version": "=0.5.12.13"},
        {"modName": "maplebirch", "version": "=5.6.2"},
    ]
    assert boot["replacePatchList"] == ["patches/weather-location.json"]


def test_source_mod_copies_only_declared_files_and_has_reproducible_zip(tmp_path):
    boot = {"name": "fixture", "version": "1.0.0", "scriptFileList": ["code.js"]}
    (tmp_path / "boot.json").write_text(json.dumps(boot))
    script = tmp_path / "code.js"
    script.write_bytes(b"window.fixture = true;")
    (tmp_path / "private-notes.txt").write_text("must stay outside the archive")
    before = source_mod_zip_bytes(tmp_path)
    os.utime(script, (1_700_000_000, 1_700_000_000))
    assert source_mod_zip_bytes(tmp_path) == before
    with zipfile.ZipFile(io.BytesIO(before)) as archive:
        assert archive.namelist() == ["boot.json", "code.js"]
        assert archive.read("code.js") == script.read_bytes()
    html = tmp_path / "index.html"
    html.write_text("window.modDataValueZipList = [];")
    payload = tmp_path / "fixture.mod.zip"
    payload.write_bytes(before)
    ModInjector(BuildPaths(workspace=tmp_path)).add_mods(html, [payload])
    embedded = json.loads(html.read_text().split("=", 1)[1].strip().rstrip(";"))
    assert base64.b64decode(embedded[0]) == before
    script.unlink()
    with pytest.raises(FileNotFoundError):
        source_mod_zip_bytes(tmp_path)


def test_declared_member_cannot_read_outside_source_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (tmp_path / "private.txt").write_text("private")
    (source / "boot.json").write_text(json.dumps({"scriptFileList": ["../private.txt"]}))
    with pytest.raises(ModArchiveError, match="member"):
        source_mod_zip_bytes(source)


def test_source_warmup_rebuilds_changes_and_rejects_version_drift(tmp_path, monkeypatch):
    loader = SimpleNamespace(config_dir=tmp_path, get_feature_by_id=get_config_loader().get_feature_by_id)
    source = tmp_path / "mod"
    source.mkdir()
    boot = {"name": "fixture", "version": "1.0.0", "scriptFileList": ["code.js"]}
    (source / "boot.json").write_text(json.dumps(boot))
    code = source / "code.js"
    code.write_text("window.fixture = 1;")
    config = ModloaderModConfig.from_dict({
        "key": "fixture", "asset_pattern": "fixture.mod.zip", "source_dir": "mod",
        "feature_id": "au-f", "release_tag": "1.0.0", "track_upstream": False,
    })
    warmer = ResourceWarmer(BuildPaths(workspace=tmp_path), codes=["15705344"])
    monkeypatch.setattr("lyra.warmup.download_file", lambda *a, **k: pytest.fail("source mod must not download"))
    warmer._download_modloader_mod(config, loader)
    payload = warmer.paths.get_mod_cache_path("fixture")
    code.write_text("window.fixture = 2;")
    warmer._download_modloader_mod(config, loader)
    with zipfile.ZipFile(payload) as archive:
        assert archive.read("code.js") == code.read_bytes()
    assert all(str(tmp_path) not in v.source for v in warmer.registry)
    boot["version"] = "1.1.0"
    (source / "boot.json").write_text(json.dumps(boot))
    with pytest.raises(ValueError, match="differs from configured"):
        warmer._download_modloader_mod(config, loader)
    assert not payload.exists()
    config.download_url = "https://example.invalid/fixture.zip"
    with pytest.raises(ValueError, match="mutually exclusive"):
        warmer._download_modloader_mod(config, loader)


def test_reviewed_release_manifest_mismatch_requires_matching_payload(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("DOLX_CONFIG_DIR", str(cfg))
    payload = tmp_path / "published.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("boot.json", json.dumps({"name": "DOLI", "version": "0.2.2"}))
        archive.writestr("code.js", b"reviewed original")
    mod = ModloaderModConfig("ArsNativa/Degrees-of-Lewdity-Intelligence", "DOLI.mod.zip", key="doli", release_tag="v0.2.3")
    warmer = ResourceWarmer(BuildPaths(workspace=tmp_path), codes=["15704320"])
    assert warmer._cached_payload_version_mismatch(mod, payload) == ("v0.2.3", "0.2.2")
    lock = {"mods": {"doli": {"release_tag": "v0.2.3", "boot_version": "0.2.2",
                            "last_tested_sha256": hashlib.sha256(payload.read_bytes()).hexdigest()}}}
    (cfg / "mods.lock.json").write_text(json.dumps(lock))
    assert warmer._cached_payload_version_mismatch(mod, payload) is None
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("boot.json", json.dumps({"name": "DOLI", "version": "0.2.2"}))
        archive.writestr("code.js", b"changed payload with the same old version")
    assert warmer._cached_payload_version_mismatch(mod, payload) == ("v0.2.3", "0.2.2")


@pytest.mark.parametrize("code, has_au", [(15704320, False), (15705344, True), (15706368, True), (15708416, True)])
def test_compat_injection_covers_game_and_runs_after_optional_face(tmp_path, monkeypatch, code, has_au):
    mods = [m for m in ConfigLoader(CANDIDATE).build.modloader_mods if m.cache_name in ("au_face", "dolx_compat")]
    monkeypatch.setattr("lyra.build.load_build_config", lambda: SimpleNamespace(modloader_mods=mods))
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=code, paths=BuildPaths(workspace=tmp_path)))
    builder.paths.temp_dir.mkdir(parents=True)
    for mod in mods:
        with zipfile.ZipFile(builder.paths.get_mod_cache_path(mod.cache_name), "w") as archive:
            archive.writestr("boot.json", json.dumps({"name": mod.cache_name, "version": "1"}))
    builder.html_path.parent.mkdir(parents=True)
    builder.html_path.write_text("window.modDataValueZipList = [];", encoding="utf-8")
    monkeypatch.setattr(builder, "_modloader_mod_path_for_injection", lambda config, path: path)
    builder._inject_modloader_mods()
    entries = json.loads(builder.html_path.read_text().split("=", 1)[1].strip().rstrip(";"))
    names = []
    for entry in entries:
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(entry))) as archive:
            names.append(json.loads(archive.read("boot.json"))["name"])
    assert names == (["au_face", "dolx_compat"] if has_au else ["dolx_compat"])


def test_au_build_copy_preserves_every_actual_file(tmp_path, monkeypatch):
    config = next(m for m in ConfigLoader(CANDIDATE).build.modloader_mods if m.cache_name == "au_face")
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=15705344, paths=BuildPaths(workspace=tmp_path)))
    monkeypatch.setattr(builder, "_uses_modern_au_face", lambda: True)
    builder.paths.temp_dir.mkdir(parents=True)
    source = tmp_path / "face.zip"
    files = {"boot.json": b'{"name":"AU face","version":"1.2.16"}',
             "scripts/svr.js": b"original script including original whitespace\r\n",
             "README.md": b"original author and update notes"}
    with zipfile.ZipFile(source, "w") as archive:
        for folder in ("game/", "scriptEarly/", "scriptEarly/Utils/", "scripts/"):
            archive.writestr(folder, b"")
        for name, data in files.items():
            archive.writestr(name, data)
    before = source.read_bytes()
    normalized = builder._modloader_mod_path_for_injection(config, source)
    assert source.read_bytes() == before
    with zipfile.ZipFile(normalized) as archive:
        assert set(archive.namelist()) == set(files)
        assert {name: archive.read(name) for name in files} == files
        assert archive.testzip() is None


def test_runtime_resolver_pet_capture_and_duplicate_failure(tmp_path):
    script = (SOURCE / "au-compat.js").read_text(encoding="utf-8")
    fixture = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const readFileSync = require('node:fs').readFileSync;
const script = readFileSync(process.argv[2], 'utf8');
function context(version='5.6.2') {
  const mods = {'maplebirch': {version}, 'AU面部扩展': {version:'1.2.16'}};
  const available = new Set(['img/face/style/variant/mouth-smile.png', 'img/face/style/variant/tear-3.png']);
  const result={calls:0,captures:0};
  const c={window:{}, modUtils:{getMod:name=>mods[name],getModListName:()=>Object.keys(mods)},
    V:{SE:{au_eyes_show:true,mixFaceEnable:false,org_exp:true},orgasmdown:0},
    Renderer:{CanvasModelCaches:{main:{}},CanvasModels:{main:{layers:{}},pet:{}}},
    addonBeautySelectorAddon:{checkImageExist:path=>available.has(path)},
    modImgLoaderHooker:{checkImageExist:()=>true},
    maplebirch:{char:{use:(layers,target,opts)=>{result.calls++;result.layers=layers;
      assert.equal(target,'main');assert.equal(opts.pet,true);},
      pet:{capture:model=>{result.captures++;assert.equal(model,c.Renderer.CanvasModels.main);}}}}};
  vm.createContext(c);return {c,result,available};
}
const {c,result,available}=context();vm.runInContext(script,c);
const o={facestyle:'style',facevariant:'variant',mouth:'smile',tears:3,show_face:true};
assert.equal(result.layers.mouth.srcfn(o),'img/face/style/variant/mouth-smile.png');
assert.equal(result.layers.tears.srcfn(o),'img/face/style/variant/tear-3.png');
assert.equal(result.layers.tears.srcfn({...o,tears:0}),'');
assert.equal(result.layers.eyes.srcfn(o),'img/face/default/variant/eyes.png');
// The variant is unknown, so no speculative path may satisfy the optional eyes.
assert.equal(result.layers.eyes.srcfn({...o,facevariant:'unknown'}),'');
assert.equal(result.layers.mouth.srcfn({...o,facestyle:'default',facevariant:'default'}),'img/face/default/mouth-smile.png');
available.add('img/face/default/default/mouth-smile.png');
assert.equal(result.layers.mouth.srcfn({...o,facestyle:'default',facevariant:'default'}),'img/face/default/default/mouth-smile.png');
available.add('img/face/style/variant/eyes.png');
c.V.SE.au_eyes_show=false;assert.equal(result.layers.eyes.srcfn(o),'');
c.V.SE.au_eyes_show=true;assert.equal(result.layers.eyes.srcfn(o),'img/face/style/variant/eyes.png');
assert.equal(result.calls,1);assert.equal(result.captures,1);
assert.equal(c.window.dolxCompat.registered,true);
assert.equal(c.window.dolxCompat.registrationCount,1);
assert.equal(c.window.dolxCompat.petCaptureCount,1);
assert.equal(Object.keys(c.V.SE).length,3);
assert.throws(()=>vm.runInContext(script,c),/重复初始化/);
assert.equal(result.calls,1);assert.equal(result.captures,1);
const old=context('4.1.14');assert.throws(()=>vm.runInContext(script,old.c),/4\.1\.14/);
assert.equal(old.result.calls,0);assert.equal(old.result.captures,0);
const base=context();base.c.modUtils.getModListName=()=>['maplebirch'];
vm.runInContext(script,base.c);assert.equal(base.result.calls,0);assert.equal(base.c.window.dolxCompat,undefined);
'''
    # Pick an actual base variant for the positive optional-eye case.
    fixture = fixture.replace("assert.equal(result.layers.eyes.srcfn(o),'img/face/default/variant/eyes.png');",
                              "assert.equal(result.layers.eyes.srcfn({...o,facevariant:'default'}),'img/face/default/default/eyes.png');")
    path = tmp_path / "fixture.js"
    path.write_text(fixture, encoding="utf-8")
    result = subprocess.run(["node", str(path), str(SOURCE / "au-compat.js")], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
