import hashlib
import io
import json
import subprocess
import zipfile
from types import SimpleNamespace

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from lyra.build import ApkBuilder, BuildTask, ZipBuilder
from lyra.candidate_compat import AU_M_BODY_MEMBER, DOLI_HISTORY_METHODS, au_m_body_frame_alpha, au_pet_default_mask, ce_optional_framework, custom_hair_offline, doli_settings_entry, legacy_art_existing_assets, maplebirch_existing_assets, more_love_optional_mods
from lyra.config_loader import ModloaderModConfig, get_config_loader
from lyra.mod_archive import zip_without_empty_directories
from lyra.paths import BuildPaths
from lyra.warmup import ResourceWarmer


def test_custom_hair_initializes_even_when_network_would_succeed_or_fail():
    script = '''async function fetchDataAsync_customhair() {
    try { await fetch('https://api.example.com/data'); } catch (error) {
        setup.customhairs = {};
        for (let i=1;i<=4;i++) setup.customhairs['customcolor'+i] = '#FFFFFF';
    }
}
fetchDataAsync_customhair().then(data => {}).catch(err => {});'''
    patched = custom_hair_offline(script)
    completed = subprocess.run(['node', '-e',
        "const setup={};const fetch=()=>{throw Error('network must not be called')};"
        + patched + ";if(Object.keys(setup.customhairs).length!==4)process.exit(1);"],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_doli_native_entry_preserves_button_and_render_action():
    source = json.dumps({'twee': [{'passageName': 'overlayReplace', 'from': 'original',
        'to': 'existing\n\t\t<<if !window.maplebirch>>\n<<button "DOLI">><<run window.doli?.renderOptionsTab?.()>><</button>>\n\t\t<</if>>'}]})
    changed = json.loads(doli_settings_entry(source))['twee'][0]
    assert changed['from'] == 'original'
    assert changed['to'] == 'existing\n<<button "DOLI">><<run window.doli?.renderOptionsTab?.()>><</button>>'
    with pytest.raises(RuntimeError, match='source drift'):
        doli_settings_entry(json.dumps({'twee': [{'passageName':'overlayReplace', 'to':'changed upstream'}]}))


def test_optional_mod_detection_preserves_present_alias_and_absent_cases():
    patched = more_love_optional_mods('window.modUtils.getMod("Wraith\'sReflection")')
    completed = subprocess.run(['node', '-e',
        "const window={modUtils:{getModListName:()=>[\"Wraith'sReflection\"],getMod:()=>{throw Error('required lookup')}}};"
        + f"if(!({patched}))process.exit(1);window.modUtils.getModListName=()=>[];if({patched})process.exit(2);"],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_ce_optional_framework_retains_lookup_when_present():
    for call in ["window.modUtils.getMod('Simple Frameworks')",
                 "modUtils.getMod('Simple Frameworks')",
                 "window.modUtils.getAnyModByNameNoAlias('Simple Frameworks')",
                 "window.modUtils?.getAnyModByNameNoAlias?.('Simple Frameworks')"]:
        patched = ce_optional_framework(call)
        result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');let names=[];let calls=0;"
            "const window={modUtils:{getModListName:()=>names,getModListNameNoAlias:()=>names,getMod:()=>++calls,getAnyModByNameNoAlias:()=>++calls}};const modUtils=window.modUtils;"
            f"assert.equal({patched},undefined);assert.equal(calls,0);names=['Simple Frameworks'];assert.equal({patched},1);"],
            capture_output=True,text=True)
        assert result.returncode == 0, result.stderr


def test_ce_optional_framework_preserves_version_object_in_detector():
    patched = ce_optional_framework("if (modUtils.getMod('Simple Frameworks')) result = modUtils.getMod('Simple Frameworks').version;")
    result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');let calls=0,result='absent';"
        "const modUtils={getModListName:()=>[],getMod:()=>{calls++;return {version:'2.0.5'};}};" + patched +
        "assert.equal(result,'absent');assert.equal(calls,0);modUtils.getModListName=()=>['Simple Frameworks'];" + patched +
        "assert.equal(result,'2.0.5');assert.equal(calls,2);"],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_legacy_alias_probe_uses_base_loader_and_selected_bsa_assets():
    source = '''        const failureSet = new Set();
    function load(guessPath) {
            const cleanedGuess = cleanPath(guessPath);
            requests.push(guessPath); return guessPath;
    }
    function check(key) {
                if (RENAME_MAP.has(key)) return true;
                if (getMatchedPatternRules(key).length > 0) return true;
                if (key.startsWith("clothes/")) return true;
                return undefined;
    }'''
    patched = legacy_art_existing_assets(source, ['img/native.png'])
    result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');const requests=[];const cleanPath=p=>p;"
        "const RENAME_MAP=new Map([['old.png','mod.png'],['missing-old.png','absent.png']]);"
        "const getMatchedPatternRules=p=>p==='face/old-blush.png'?[{paths:['selected-au.png']}]:p==='face/missing.png'?[{paths:['absent.png']}]:[];"
        "const window={modImgLoaderHooker:{imgLookupTable:new Map([['img/mod.png',[{imgData:{getter:{invalid:false}}}]],['img/invalid.png',[{imgData:{getter:{invalid:true}}}]]])},"
        "addonBeautySelectorAddon:{checkImageExist:p=>p==='img/selected-au.png'}};" + patched +
        "for(const p of ['img/native.png','img/mod.png','img/selected-au.png'])assert.equal(load(p),p);"
        "assert.equal(load('img/missing_gray.png'),null);assert.equal(load('img/invalid.png'),null);assert.equal(requests.length,3);"
        "assert.equal(check('old.png'),true);assert.equal(check('missing-old.png'),false);"
        "assert.equal(check('face/old-blush.png'),true);assert.equal(check('face/missing.png'),false);"
        "assert.equal(check('clothes/missing.png'),undefined);"], capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_maplebirch_414_chooses_known_active_and_base_faces_before_probing():
    source = 'let aI=new Set;function aO(e){let t=e.find(e=>aI.has(e));if(t)return t;let n="";for(let t of e){let e=no(t);if(e===t||!0===e)return t;!1===e||n||(n=t)}return n||e[0]}function aD(t){return function(e){let n=[t(e)].flat(),r=e.facestyle||"default",a=e.facevariant||"default";return aO(n);}}class Character{use(t,n,r){return this.layers.push({target:n,layers:t}),r?.pet&&this.pet.use(t),this}}'
    patched = maplebirch_existing_assets(source, ['img/body/base-head.png'])
    result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');const probes=[];"
        "const active=new Set(['img/face/default/blush-1.png']);const aliases=new Set(['img/face/default/blush1.png']);"
        "const V={SE:{au_eyes_show:false}};let auVersion='1.2.8';"
        "const window={modUtils:{getModListNameNoAlias:()=>['AU面部扩展'],getMod:()=>({version:auVersion})},addonBeautySelectorAddon:{checkImageExist:p=>active.has(p)},modImgLoaderHooker:{checkImageExist:p=>aliases.has(p)}};"
        "const no=p=>{probes.push(p);return false;};" + patched +
        "assert.equal(aO(['img/face/default/blush1.png','img/face/default/blush-1.png']),'img/face/default/blush-1.png');"
        "assert.equal(aO(['img/face/default/base-head.png','img/body/base-head.png']),'img/body/base-head.png');"
        "assert.equal(probes.length,0);aI.add('img/disabled-pack.png');"
        "assert.equal(aO(['img/missing.png','img/disabled-pack.png']),'img/missing.png');assert.deepEqual(probes,['img/missing.png','img/disabled-pack.png']);"
        "const eyes=aD(()=> 'eyes');assert.equal(eyes({}),'');V.SE.au_eyes_show=true;assert.equal(eyes({}),'eyes');"
        "V.SE.au_eyes_show=false;auVersion='1.2.16';assert.equal(eyes({}),'eyes');"
        "const names='eyes,ears,left_iris,right_iris,freckles,mouth,makeup_lipstick,blush,makeup_blusher,tears'.split(',');"
        "const Renderer={CanvasModels:{main:{layers:Object.fromEntries(names.map(k=>[k,{z:30,showfn:()=>true}]))},pet:{old:true}}};"
        "const character=new Character();character.layers=[];let captures=0;character.pet={layers:[],use(t){this.layers.push(t);},capture(model){captures++;Renderer.CanvasModels.pet=model;}};"
        "auVersion='1.2.8';const defs=Object.fromEntries(names.map(k=>[k,{srcfn:()=>k}]));character.use(defs,'main');"
        "assert.equal(captures,1);assert.equal(character.pet.layers.length,1);assert.equal(character.pet.layers[0].eyes.z,30);"
        "assert.equal(character.pet.layers[0].eyes.srcfn(),'eyes');character.use({head:{}},'main');assert.equal(captures,1);"
        "auVersion='1.2.16';character.use(defs,'main');assert.equal(captures,1);"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_maplebirch_414_asset_patch_does_not_route_to_modern_framework(tmp_path, monkeypatch):
    builder = ZipBuilder(BuildTask(pack_type='zip', mod_code=15705344, paths=BuildPaths(workspace=tmp_path)))
    payload = tmp_path / 'framework.zip'
    config = ModloaderModConfig('MaplebirchLeaf/SCML-DOL-maplebirchFramework', 'maplebirch-0.5.10.12-v4.1.14.mod.zip',
                                 key='maplebirch', release_tag='maplebirch-release-v4.1.14')
    monkeypatch.setattr(builder, '_patch_maplebirch_pet_remount', lambda config, path: path)
    calls = []
    monkeypatch.setattr('lyra.build.patch_candidate_payload', lambda config, path, target, base_paths: calls.append(base_paths) or target)
    image = builder.img_path / 'body/base-head.png'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'published image')
    monkeypatch.setattr(builder, '_uses_reviewed_legacy_framework', lambda: True)
    assert builder._patch_maplebirch_payload(config, payload) != payload
    assert calls == [['img/body/base-head.png']]
    monkeypatch.setattr(builder, '_uses_reviewed_legacy_framework', lambda: False)
    assert builder._patch_maplebirch_payload(config, payload) == payload
    assert len(calls) == 1


def test_legacy_common_fixes_require_the_actual_414_payload(tmp_path, monkeypatch):
    import lyra.build as build
    builder = ZipBuilder(BuildTask(pack_type="zip", mod_code=15705344, paths=BuildPaths(workspace=tmp_path)))
    configured = SimpleNamespace(cache_name="maplebirch", enabled=True, release_tag="maplebirch-release-v4.1.14")
    monkeypatch.setattr(build, "load_build_config", lambda: SimpleNamespace(modloader_mods=[configured]))
    archive = builder.paths.get_mod_cache_path("maplebirch")
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("boot.json", json.dumps({"name": "maplebirch", "version": "4.1.14"}))
    assert builder._uses_reviewed_legacy_framework()
    calls = []
    monkeypatch.setattr(build, "patch_candidate_payload", lambda config, source, target, base_paths: calls.append(config.cache_name) or target)
    payload = tmp_path / "hair.zip"
    config = ModloaderModConfig("HiddenCirno/DoL-CustomHair", "*.zip", key="custom_hair", release_tag="CustomHair")
    assert builder._modloader_mod_path_for_injection(config, payload) != payload
    assert calls == ["custom_hair"]
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("boot.json", json.dumps({"name": "maplebirch", "version": "4.1.13"}))
    assert not builder._uses_reviewed_legacy_framework()
    assert builder._modloader_mod_path_for_injection(config, payload) == payload
    assert calls == ["custom_hair"]


def test_au_pet_new_game_default_preserves_saved_and_npc_settings():
    source = 'const defaults={character:{mask:0,rotation:0,pet:{enabled:!1,mask:25,rotation:0,scale:1}},npc:{pet:{mask:25}}};'
    patched = au_pet_default_mask(source)
    result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');const saved={pet:{mask:19}};" + patched +
        "assert.equal(defaults.character.pet.mask,0);assert.equal(defaults.npc.pet.mask,25);assert.equal(saved.pet.mask,19);"],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_au_m_body_repair_changes_only_stray_alpha_and_preserves_legacy_payload(tmp_path, monkeypatch):
    original = Image.new('RGBA', (512, 256), (67, 89, 123, 255))
    for y in range(158, 192):
        for x in range(256, 264):
            original.putpixel((x, y), (67, 89, 123, 255 if (y-158)*8+x-256 < 213 else 0))
    metadata=PngInfo();metadata.add(b'gAMA', bytes.fromhex('0000b18f'));metadata.add_text('Software','Celsys Studio Tool')
    buffer = io.BytesIO(); original.save(buffer, format='PNG',pnginfo=metadata,dpi=(300.482,300.482),icc_profile=b'profile preserved')
    original_info=Image.open(io.BytesIO(buffer.getvalue())).info
    config = ModloaderModConfig('AOKIUTAGE/UTAGEsDOL3.0', 'AUmale.model_v0.4.2.zip', key='au_m', release_tag='mod')
    source = tmp_path/'model.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('boot.json', json.dumps({'name':'【AUmale】model','version':'0.4.2'}))
        archive.writestr(AU_M_BODY_MEMBER, buffer.getvalue())
        archive.writestr('other.png', b'untouched source')
    before = source.read_bytes()
    builder = ZipBuilder(BuildTask(pack_type='zip',mod_code=15706368,paths=BuildPaths(workspace=tmp_path)))
    monkeypatch.setattr(builder, '_uses_modern_au_face', lambda: True)
    target = builder._modloader_mod_path_for_injection(config, source)
    assert target != source and source.read_bytes() == before
    with zipfile.ZipFile(target) as patched, zipfile.ZipFile(source) as archive:
        assert patched.namelist() == archive.namelist()
        for name in ['boot.json', 'other.png']:
            assert patched.read(name) == archive.read(name)
        repaired = Image.open(io.BytesIO(patched.read(AU_M_BODY_MEMBER))).convert('RGBA')
    assert repaired.info == original_info
    changed = 0
    for y in range(256):
        for x in range(512):
            a, b = original.getpixel((x,y)), repaired.getpixel((x,y))
            assert a[:3] == b[:3]
            if a != b:
                changed += 1
                assert 256 <= x < 264 and 158 <= y < 192 and b[3] == 0
    assert changed == 213
    monkeypatch.setattr(builder, '_uses_modern_au_face', lambda: False)
    monkeypatch.setattr(builder, '_uses_modern_framework', lambda: False)
    assert builder._modloader_mod_path_for_injection(config, source) == source
    assert source.read_bytes() == before
    # A replacement upstream asset must be reviewed rather than cleared blindly.
    original.putpixel((256,158), (67,89,123,0))
    buffer = io.BytesIO(); original.save(buffer, format='PNG')
    with pytest.raises(RuntimeError, match='source drift'):
        au_m_body_frame_alpha(buffer.getvalue())


@pytest.mark.parametrize('previous', ['com.vrelnir.dol', 'com.vrelnir.dol.xfox.candidate.modern', 'com.vrelnir.dol.xfox.candidate.unified'])
def test_apk_identity_uses_selected_config_with_a_reused_prepared_cache(tmp_path, monkeypatch, previous):
    import xml.etree.ElementTree as ET
    builder = ApkBuilder(BuildTask(pack_type='apk',mod_code=15704320,paths=BuildPaths(workspace=tmp_path)))
    builder.work_dir.mkdir(parents=True)
    manifest=builder.work_dir/'AndroidManifest.xml'
    manifest.write_text(f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{previous}"><application><activity android:name="com.vrelnir.dol.MainActivity"/><provider android:authorities="{previous}.androidx-startup"/><provider android:authorities="third.party"/></application></manifest>',encoding='utf-8')
    strings=builder.work_dir/'res/values/strings.xml';strings.parent.mkdir(parents=True)
    strings.write_text('<resources><string name="app_name">Old</string><string name="activity_name">@string/launcher_name</string><string name="launcher_name">Old</string><string name="other">Keep</string></resources>',encoding='utf-8')
    monkeypatch.setattr('lyra.build.load_build_config',lambda:SimpleNamespace(identity_package='com.vrelnir.dol.xfox.candidate.unified',identity_apk_name='DoL XFox Candidate unified'))
    builder._apply_identity()
    root=ET.parse(manifest).getroot();android='{http://schemas.android.com/apk/res/android}'
    assert root.attrib['package']=='com.vrelnir.dol.xfox.candidate.unified'
    assert root.find('./application/activity').get(android+'name')=='com.vrelnir.dol.MainActivity'
    assert [p.get(android+'authorities') for p in root.findall('./application/provider')]==['com.vrelnir.dol.xfox.candidate.unified.androidx-startup','third.party']
    assert {e.get('name'):e.text for e in ET.parse(strings).getroot()}=={'app_name':'DoL XFox Candidate unified','activity_name':'DoL XFox Candidate unified','launcher_name':'DoL XFox Candidate unified','other':'Keep'}


def test_apk_declares_no_external_mods_and_retains_existing_external_manifest(tmp_path):
    builder=ApkBuilder(BuildTask(pack_type='apk',mod_code=15704320,paths=BuildPaths(workspace=tmp_path)))
    manifest=builder.work_dir/'assets/www/modList.json';manifest.parent.mkdir(parents=True)
    builder._ensure_external_mod_manifest()
    assert json.loads(manifest.read_text())==[]
    manifest.write_text('["extra.mod.zip"]',encoding='utf-8')
    builder._ensure_external_mod_manifest()
    assert json.loads(manifest.read_text())==['extra.mod.zip']


def test_cordova_bridge_changes_only_class_visibility_and_preserves_legacy(tmp_path, monkeypatch):
    builder=ApkBuilder(BuildTask(pack_type='apk',mod_code=15704320,paths=BuildPaths(workspace=tmp_path)))
    path=builder.work_dir/'smali/org/apache/cordova/engine/SystemExposedJsApi.smali'
    path.parent.mkdir(parents=True)
    original='.class Lorg/apache/cordova/engine/SystemExposedJsApi;\n.super Ljava/lang/Object;\n.method public exec()V\n.end method\n'
    path.write_text(original,encoding='utf-8')
    monkeypatch.setattr(builder,'_uses_modern_framework',lambda:False)
    assert not builder._patch_cordova_js_interface()
    assert path.read_text()==original
    monkeypatch.setattr(builder,'_uses_modern_framework',lambda:True)
    assert builder._patch_cordova_js_interface()
    assert path.read_text()==original.replace('.class ','.class public ',1)
    assert not builder._patch_cordova_js_interface()
    path.write_text('.class changed.bridge;\n',encoding='utf-8')
    with pytest.raises(RuntimeError,match='source drift'):
        builder._patch_cordova_js_interface()


def test_cordova_dialog_already_closed_is_distinct_from_protocol_failure():
    from tools.apk_emulator_smoke_test import _CdpDialog
    class Page:
        error='CDP Page.handleJavaScriptDialog failed: No dialog is showing'
        def _send_command(self,*args):raise RuntimeError(self.error)
    page=Page();dialog=_CdpDialog(page,'alert','notice')
    dialog.accept();assert dialog.already_closed and dialog.accepted
    page.error='CDP transport disconnected'
    with pytest.raises(RuntimeError,match='transport disconnected'):_CdpDialog(page,'alert','notice').accept()



def test_wolf_pattern_alias_keeps_original_image_bytes(tmp_path, monkeypatch):
    builder=ZipBuilder(BuildTask(pack_type='zip',mod_code=15704320,paths=BuildPaths(workspace=tmp_path)))
    monkeypatch.setattr(builder, '_uses_modern_framework', lambda: True)
    monkeypatch.setattr(builder, '_patch_maplebirch_payload', lambda config,path: path)
    source=builder.img_path/'ui/sym-harmony.png';source.parent.mkdir(parents=True)
    source.write_bytes(b'original image bytes')
    payload=tmp_path/'framework.zip'
    builder._modloader_mod_path_for_injection(SimpleNamespace(cache_name='maplebirch'),payload)
    assert (builder.img_path/'ui/wolfharmony.png').read_bytes()==source.read_bytes()


def test_doli_snapshot_restores_counter_anchors_and_outputs_after_rewind_and_json_save():
    source = '''
const assert=require('node:assert/strict');
const window={SugarCube:{State:{turns:4,variables:{}}}};
const session_lifecycle_js_1={createSessionLifecycleState:()=>({phase:'inactive'})};
class Narrator {
 constructor() {
  this._turnIndex=2;this._lifecycleState={phase:'active'};
  this._anchorState={initialNames:new Map([[0,'NPC']]),prevNames:new Map([[0,'NPC']]),hintedSwitches:new Set([0])};
  this._eventExtractor={_prevState:{health:80},_prevIntent:{action:'wait'}};
  this._narrativeOutputs=[{turnIndex:1,text:'saved'}];this._lastRecordedTurnIndex=1;
 }
 _releaseCombatSession(){this._turnIndex=0;}
 METHODS
}
const n=new Narrator();n._dolxCaptureHistory();
const saved=JSON.stringify(window.SugarCube.State.variables);
n._turnIndex=3;n._narrativeOutputs.push({turnIndex:2,text:'future'});n._anchorState.prevNames.set(0,'changed');
assert.equal(window.SugarCube.State.variables.dolxDoliCombatHistory.fields._narrativeOutputs.length,1);
window.SugarCube.State.variables=JSON.parse(saved);n._dolxRestoreHistory();
assert.equal(n._turnIndex,2);assert.equal(n._anchorState.prevNames.get(0),'NPC');
assert.equal(n._narrativeOutputs.length,1);assert.equal(n._eventExtractor._prevState.health,80);
assert(n._anchorState.hintedSwitches.has(0));
window.SugarCube.State.variables={};n._dolxRestoreHistory();
assert.equal(n._turnIndex,0);assert.equal(n._lifecycleState.phase,'inactive');
'''.replace('METHODS', DOLI_HISTORY_METHODS)
    completed=subprocess.run(['node','-e',source],capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr


def test_archived_input_replaces_stale_cache_and_preserves_original_on_rejection(tmp_path, monkeypatch):
    monkeypatch.delenv('DOLX_CONFIG_DIR', raising=False)
    config_dir = tmp_path/'config'; config_dir.mkdir()
    original = config_dir/'face.zip'; original.write_bytes(b'reviewed attachment')
    (config_dir/'mods.lock.json').write_text(json.dumps({'mods':{'au_face':{
        'last_tested_sha256':hashlib.sha256(original.read_bytes()).hexdigest()}}}))
    warmer = ResourceWarmer(BuildPaths(workspace=tmp_path), codes=['15705344'])
    config = ModloaderModConfig.from_dict({'key':'au_face', 'feature_id':'au-f',
        'github_repo':'AOKIUTAGE/UTAGEsDOL3.0','asset_pattern':'face.zip', 'local_path':'face.zip'})
    loader = SimpleNamespace(config_dir=config_dir, get_feature_by_id=get_config_loader().get_feature_by_id)
    warmer._download_modloader_mod(config, loader)
    cached = warmer.paths.get_mod_cache_path('au_face')
    assert cached.read_bytes() == original.read_bytes()
    cached.write_bytes(b'stale cache')
    warmer._download_modloader_mod(config, loader)
    assert cached.read_bytes() == original.read_bytes()
    original.write_bytes(b'unreviewed replacement')
    with pytest.raises(RuntimeError, match='digest mismatch'):
        warmer._download_modloader_mod(config, loader)
    assert original.read_bytes() == b'unreviewed replacement'
    assert not cached.exists()
    original.unlink()
    with pytest.raises(FileNotFoundError):
        warmer._download_modloader_mod(config, loader)


def test_directory_cleanup_preserves_real_member_bytes_and_checks_crc():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw,'w') as archive:
        archive.writestr('scripts/', b'')
        archive.writestr('scripts/main.js', b'actual unmodified script')
    data = raw.getvalue()
    with zipfile.ZipFile(io.BytesIO(zip_without_empty_directories(data))) as archive:
        assert archive.namelist() == ['scripts/main.js']
        assert archive.read('scripts/main.js') == b'actual unmodified script'
        assert archive.testzip() is None
    with pytest.raises(zipfile.BadZipFile):
        zip_without_empty_directories(data.replace(b'actual unmodified script', b'broken unmodified script'))


def test_modern_au_uses_actual_pair_without_legacy_framework_mutation(tmp_path, monkeypatch):
    mods = [ModloaderModConfig('MaplebirchLeaf/SCML-DOL-maplebirchFramework','framework.zip',key='maplebirch',release_tag='maplebirch-release-v5.6.2'),
            ModloaderModConfig('AOKIUTAGE/UTAGEsDOL3.0','face.zip',key='au_face',release_tag='community-v1.2.16')]
    builder=ZipBuilder(BuildTask(pack_type='zip',mod_code=15705344,paths=BuildPaths(workspace=tmp_path)))
    monkeypatch.setattr('lyra.build.load_build_config',lambda:SimpleNamespace(modloader_mods=mods))
    builder.paths.temp_dir.mkdir(parents=True)
    def write(key,name,version):
        with zipfile.ZipFile(builder.paths.get_mod_cache_path(key),'w') as archive:
            archive.writestr('boot.json',json.dumps({'name':name,'version':version}))
    write('maplebirch','maplebirch','5.6.2'); write('au_face','AU面部扩展','1.2.16')
    framework=builder.paths.get_mod_cache_path('maplebirch'); before=framework.read_bytes()
    assert builder._patch_maplebirch_au_face_variants(mods[0],framework)==framework
    assert framework.read_bytes()==before
    assert builder._validate_au_face_variant_source()['status']=='upstream_managed'
    write('au_face','AU面部扩展','1.2.8')
    with pytest.raises(RuntimeError,match='source mismatch'):
        builder._patch_maplebirch_au_face_variants(mods[0],framework)
