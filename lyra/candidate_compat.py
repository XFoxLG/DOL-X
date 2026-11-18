"""Small fixes for the reviewed November community payloads.

The upstream archive stays unchanged. Unexpected script revisions fail with the
member and needle so updating a mod cannot silently drop a compatibility fix.
"""

import hashlib
import io
import json
import re
import struct
import zipfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .compatibility import compatibility_source_errors, compatibility_surface_by_key


def replace_once(script: str, old: str, new: str, member: str) -> str:
    count = script.count(old)
    if count != 1:
        raise RuntimeError(f"Compatibility source drift in {member}: expected one {old[:80]!r}, got {count}")
    return script.replace(old, new, 1)


def validate_weather_location_patch(html: str, payload: Path) -> None:
    """Require the exact reviewed game function before ModLoader applies its patch."""
    with zipfile.ZipFile(payload) as archive:
        patch = json.loads(archive.read("patches/weather-location.json"))
    entry, = patch["js"]
    count = html.count(entry["from"])
    if count != 1:
        raise RuntimeError(
            f"Compatibility source drift in {entry['fileName']}: expected one weather init, got {count}"
        )


def custom_hair_offline(script: str) -> str:
    """Run the existing color initialization synchronously, without its fake API."""
    start = script.index("async function fetchDataAsync_customhair() {")
    body_start = script.index("        setup.customhairs = {}", start)
    end = script.index("    }\n}\nfetchDataAsync_customhair()", body_start)
    call_end = script.index("});", end) + 3
    body = script[body_start:end]
    return script[:start] + "function initializeCustomHairColors() {\n" + body + "}\ninitializeCustomHairColors();" + script[call_end:]


def doli_settings_entry(script: str) -> str:
    data = json.loads(script)
    entry = next(item for item in data["twee"] if item["passageName"] == "overlayReplace")
    entry["to"] = replace_once(entry["to"], "\n\t\t<<if !window.maplebirch>>", "", "patches/overlay-replace.json")
    entry["to"] = replace_once(entry["to"], "\n\t\t<</if>>", "", "patches/overlay-replace.json")
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def more_love_optional_mods(script: str) -> str:
    # getModListName includes aliases, matching getMod's lookup semantics, but
    # absence of an optional collaboration mod does not create an error log.
    return re.sub(r"window\.modUtils\.getMod\((['\"])(.*?)\1\)",
                  r"window.modUtils.getModListName().includes(\1\2\1)", script)


DOLI_HISTORY_METHODS = '''
    _dolxCaptureHistory() {
        const state = window.SugarCube.State;
        const fields = {};
        for (const key of ['_turnIndex', '_lifecycleState', '_latestTurnExtraction',
            '_sessionAutoGenerate', '_lastRecordedTurnIndex', '_combatId',
            '_narrativeOutputs', '_preCombatContext']) fields[key] = this[key];
        state.variables.dolxDoliCombatHistory = structuredClone({
            moment: state.turns, fields,
            initialNames: [...this._anchorState.initialNames],
            prevNames: [...this._anchorState.prevNames],
            hintedSwitches: [...this._anchorState.hintedSwitches],
            prevState: this._eventExtractor._prevState,
            prevIntent: this._eventExtractor._prevIntent,
        });
    }
    _dolxRestoreHistory() {
        const saved = window.SugarCube.State.variables.dolxDoliCombatHistory;
        if (!saved) {
            // Saves written before this fix have no narrator history.
            this._releaseCombatSession();
            this._lifecycleState = (0, session_lifecycle_js_1.createSessionLifecycleState)();
            return;
        }
        const copy = structuredClone(saved);
        Object.assign(this, copy.fields);
        this._anchorState.initialNames = new Map(copy.initialNames);
        this._anchorState.prevNames = new Map(copy.prevNames);
        this._anchorState.hintedSwitches = new Set(copy.hintedSwitches);
        this._eventExtractor._prevState = copy.prevState;
        this._eventExtractor._prevIntent = copy.prevIntent;
    }
'''


def doli_history(script: str) -> str:
    member = 'dist/DOLI.js'
    script = replace_once(script, '    _onPassageStart() {',
        DOLI_HISTORY_METHODS + '    _onPassageStart() {\n        this._dolxRestoreHistory();', member)
    script = replace_once(script, "        $doc.on(':passageend', () => this._onPassageEnd());",
        "        $doc.on(':passageend', () => { this._onPassageEnd(); this._dolxCaptureHistory(); });", member)
    script = replace_once(script, '    _onPassageEnd() {', '''    _onPassageEnd() {
        const state = window.SugarCube.State;
        if (state.variables.dolxDoliCombatHistory?.moment === state.turns) return;''', member)
    script = replace_once(script, '        this._narrativeOutputs.push({ turnIndex, text });',
        '        this._narrativeOutputs.push({ turnIndex, text });\n        this._dolxCaptureHistory();', member)
    script = replace_once(script, '            this._narrativeOutputs[this._narrativeOutputs.length - 1] = { turnIndex, text };',
        '            this._narrativeOutputs[this._narrativeOutputs.length - 1] = { turnIndex, text };\n            this._dolxCaptureHistory();', member)
    script = replace_once(script, '                        this._lastRecordedTurnIndex = extraction.turnIndex;',
        '                        this._lastRecordedTurnIndex = extraction.turnIndex;\n                        this._dolxCaptureHistory();', member)
    script = replace_once(script, '                this._sessionAutoGenerate = enabled;',
        '                this._sessionAutoGenerate = enabled;\n                this._dolxCaptureHistory();', member)
    script = replace_once(script, '            delete V.options.doli;',
        '            delete V.options.doli;\n            delete V.dolxDoliCombatHistory;', member)
    script = replace_once(script, '                delete frame.variables.options.doli;',
        '                delete frame.variables.options.doli;\n                delete frame.variables.dolxDoliCombatHistory;', member)
    return script


def ce_optional_framework(script: str) -> str:
    for call in ("window.modUtils.getMod('Simple Frameworks')",
                 "modUtils.getMod('Simple Frameworks')",
                 "window.modUtils.getAnyModByNameNoAlias('Simple Frameworks')",
                 "window.modUtils?.getAnyModByNameNoAlias?.('Simple Frameworks')"):
        names = 'getModListNameNoAlias' if 'NoAlias' in call else 'getModListName'
        receiver = 'window.modUtils' if call.startswith('window.') else 'modUtils'
        replacement = f"({receiver}.{names}().includes('Simple Frameworks') ? {call} : undefined)"
        script = re.sub(r"(?<![\w.])" + re.escape(call), lambda match: replacement, script)
    return script


def legacy_art_existing_assets(script: str, base_paths: Sequence[str]) -> str:
    """Probe renamed files only when the game or an active mod actually has them."""
    script = replace_once(script, '        const failureSet = new Set();',
        '        const failureSet = new Set();\n'
        '        const dolxAvailableBaseImages = new Set(' + json.dumps(base_paths) + ');\n'
        '''        function dolxHasConcreteImage(relativePath) {
            const path = relativePath.startsWith("img/") ? relativePath : "img/" + relativePath;
            const entries = window.modImgLoaderHooker.imgLookupTable.get(path);
            return dolxAvailableBaseImages.has(path) ||
                entries?.some(entry => !entry.imgData.getter.invalid) ||
                window.addonBeautySelectorAddon.checkImageExist(path) === true;
        }''', 'dolrename.js')
    script = replace_once(script, '            const cleanedGuess = cleanPath(guessPath);',
        '            const cleanedGuess = cleanPath(guessPath);\n'
        '            if (!dolxHasConcreteImage(guessPath)) return null;',
        'dolrename.js')
    script = replace_once(script, '                if (RENAME_MAP.has(key)) return true;',
        '''                if (RENAME_MAP.has(key)) {
                    return dolxHasConcreteImage(key) || dolxHasConcreteImage(RENAME_MAP.get(key));
                }''', 'dolrename.js')
    script = replace_once(script, '                if (getMatchedPatternRules(key).length > 0) return true;',
        '''                const matches = getMatchedPatternRules(key);
                if (matches.length > 0) {
                    return dolxHasConcreteImage(key) ||
                        matches.some(item => item.paths.some(path => dolxHasConcreteImage(path)));
                }''', 'dolrename.js')
    return replace_once(script, '                if (key.startsWith("clothes/")) return true;',
        '                if (key.startsWith("clothes/")) return dolxHasConcreteImage(key) ? true : undefined;',
        'dolrename.js')


def maplebirch_existing_assets(script: str, base_paths: Sequence[str]) -> str:
    """Keep 4.1.14's face order while choosing known assets before async probes."""
    script = replace_once(script,
        'let aI=new Set;function aO(e){let t=e.find(e=>aI.has(e));if(t)return t;',
        'let aI=new Set,dolxAvailableBaseImages=new Set(' + json.dumps(base_paths) + ');'
        'function aO(e){let t=e.find(e=>window.addonBeautySelectorAddon.checkImageExist(e)===true);'
        'if(t)return t;'
        't=e.find(e=>window.modImgLoaderHooker.checkImageExist(e)===true||dolxAvailableBaseImages.has(e));'
        'if(t)return t;', 'dist/inject_early.js')
    script = replace_once(script,
        'return function(e){let n=[t(e)].flat(),r=e.facestyle||"default",a=e.facevariant||"default";return aO(',
        'return function(e){let n=[t(e)].flat(),r=e.facestyle||"default",a=e.facevariant||"default";'
        'if(n.length===1&&n[0]==="eyes"&&V.SE?.au_eyes_show===false&&'
        'window.modUtils.getModListNameNoAlias().includes("AU面部扩展")&&'
        'window.modUtils.getMod("AU面部扩展").version==="1.2.8")return"";return aO(',
        'dist/inject_early.js')
    return replace_once(script,
        'return this.layers.push({target:n,layers:t}),r?.pet&&this.pet.use(t),this',
        'this.layers.push({target:n,layers:t});'
        'if(n==="main"&&!r?.pet&&Object.keys(t).join(",")==="eyes,ears,left_iris,right_iris,freckles,mouth,makeup_lipstick,blush,makeup_blusher,tears"&&'
        'window.modUtils.getMod("AU面部扩展").version==="1.2.8")'
        '{const e=Renderer.CanvasModels.main;'
        'const n=Object.fromEntries(Object.entries(t).map(([t,n])=>[t,{...e.layers[t],...n}]));'
        'this.pet.use(n);delete Renderer.CanvasModels.pet;this.pet.capture(e);}'
        'else if(r?.pet)this.pet.use(t);return this',
        'dist/inject_early.js')


def au_pet_default_mask(script: str) -> str:
    # The AU full-body sprite occupies the left 128 pixels; +25 includes part of
    # its adjacent portrait. This changes new-game defaults, not saved settings.
    return replace_once(script,
        'character:{mask:0,rotation:0,pet:{enabled:!1,mask:25,rotation:0,scale:1}',
        'character:{mask:0,rotation:0,pet:{enabled:!1,mask:0,rotation:0,scale:1}',
        'dist/inject_early.js')


AU_M_BODY_MEMBER = "AUmale/img/body/base-classic.png"


def au_m_body_frame_alpha(data: bytes) -> bytes:
    """Remove the published 0.4.2 portrait spill into the second body frame."""
    with Image.open(io.BytesIO(data)) as original:
        sprite = original.convert("RGBA")
        metadata = PngInfo()
        if "gamma" in original.info:
            metadata.add(b"gAMA", struct.pack("!I", round(original.info["gamma"] * 100000)))
        if "chromaticity" in original.info:
            metadata.add(b"cHRM", struct.pack("!8I", *(round(v * 100000) for v in original.info["chromaticity"])))
        for key, value in original.text.items():
            metadata.add_text(key, value)
    region = (256, 158, 264, 192)
    alpha = sprite.getchannel("A")
    opaque = sum(value > 0 for value in alpha.crop(region).tobytes())
    if sprite.size != (512, 256) or opaque != 213:
        raise RuntimeError(f"AU-M sprite source drift: size={sprite.size}, stray pixels={opaque}; expected 512x256 and 213")
    alpha.paste(0, region)
    sprite.putalpha(alpha)
    output = io.BytesIO()
    # Pillow retains ICC from image.info; retain the other published PNG metadata too.
    sprite.save(output, format="PNG", pnginfo=metadata, dpi=sprite.info.get("dpi"))
    return output.getvalue()


def patch_au_m_body(mod_config, source: Path, target: Path) -> Path:
    surface = compatibility_surface_by_key("au_m_body_frame_alpha")
    errors = compatibility_source_errors(surface, mod_config)
    if errors:
        raise RuntimeError("AU-M sprite source mismatch: " + "; ".join(errors))
    with zipfile.ZipFile(source) as original:
        boot = json.loads(original.read("boot.json"))
        if (boot["name"], boot["version"]) != ("【AUmale】model", "0.4.2"):
            raise RuntimeError("AU-M sprite requires the published model 0.4.2")
        repaired = au_m_body_frame_alpha(original.read(AU_M_BODY_MEMBER))
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w") as output:
            for entry in original.infolist():
                output.writestr(entry, repaired if entry.filename == AU_M_BODY_MEMBER else original.read(entry))
    return target



def patch_candidate_payload(mod_config, source: Path, target: Path, base_paths: Sequence[str] = ()) -> Path:
    key = mod_config.cache_name
    surface_key = {"custom_hair": "custom_hair_offline_colors", "doli": "doli_settings_entry",
                   "more_love": "more_love_optional_mods", "cheat_extended": "ce_optional_framework",
                   "legacy_art_compat": "legacy_art_existing_assets",
                   "maplebirch": "maplebirch_414_concrete_face_assets"}[key]
    surface = compatibility_surface_by_key(surface_key)
    errors = compatibility_source_errors(surface, mod_config)
    if errors:
        raise RuntimeError(f"{surface_key} source mismatch: {'; '.join(errors)}")
    with zipfile.ZipFile(source) as archive:
        members = {entry.filename: (entry, archive.read(entry)) for entry in archive.infolist()}
    if key == "custom_hair":
        patches = {"main.js": custom_hair_offline}
    elif key == "legacy_art_compat":
        patches = {"dolrename.js": lambda script: legacy_art_existing_assets(script, base_paths)}
    elif key == "maplebirch":
        patches = {"dist/inject_early.js": lambda script: maplebirch_existing_assets(script, base_paths)}
    elif key == "doli":
        patches = {"patches/overlay-replace.json": doli_settings_entry, "dist/DOLI.js": doli_history}
    elif key == "cheat_extended":
        patches = {name: ce_optional_framework for name in (
            "scriptEarly/CERegist.js", "scriptEarly/framework_detector.js", "scripts/CE_MoneyCheat.js",
            "scripts/CE_Time_Event.js", "scripts/CE_forceAttendSchool.js",
            "scripts/CE_TimeTravelPlus.js", "scripts/CE_sideBarIcon.js", "scripts/CE_tattoo.js",
        )}
    else:
        patches = {name: more_love_optional_mods for name in (
            "game/more_love_interest_main.twee", "game/more_love_interest_icon.twee",
            "game/More_Love_Interest_Mod_Collab.js",
        )}
    for name, patch in patches.items():
        entry, data = members[name]
        if key in ("custom_hair", "legacy_art_compat"):
            expected = {"custom_hair": "9cf4351716d17e597f019ae3400f110a2d7690229547367dd23714e783b92ff7",
                        "legacy_art_compat": "766111ced11316b23ab1d3993577b9ae52089ee02113128a4eb2b1499e3db7a6"}[key]
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f"{surface_key}: published source differs in {name}")
        original = data.decode("utf-8").replace("\r\n", "\n")
        changed = patch(original)
        if changed == original:
            raise RuntimeError(f"{surface_key}: patch needle missing in {name}")
        members[name] = entry, changed.encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for entry, data in members.values():
            archive.writestr(entry, data)
    return target
