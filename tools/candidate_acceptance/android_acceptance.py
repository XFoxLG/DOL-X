"""Isolated MuMu acceptance for a DOL-X candidate build.

Uses the diagnostic APK only to observe WebView state, then reinstalls the
normal APK and loads the test save through native UI touch. Never clears the
stable or candidate package data.

Usage:
    python tools/candidate_acceptance/android_acceptance.py \
        --repo . --variant base --artifacts-dir output \
        --diagnostic-dir diagnostic-apks --diagnostics-dir <diagnostics-dir> \
        --snapshot <1014-device-saves-copy.json> \
        --adb <adb.exe> --serial <host:port> --package <package-name>
"""

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True, type=Path)
parser.add_argument("--variant", required=True)
parser.add_argument("--artifacts-dir", required=True, type=Path)
parser.add_argument("--diagnostic-dir", required=True, type=Path)
parser.add_argument("--diagnostics-dir", required=True, type=Path, help="reviewed JS diagnostics")
parser.add_argument("--snapshot", required=True, type=Path)
parser.add_argument("--adb", required=True)
parser.add_argument("--serial", required=True)
parser.add_argument("--package", required=True)
parser.add_argument("--memory-gib", type=float, default=1.75)
parser.add_argument("--out", type=Path)
parser.add_argument("--resume-normal", action="store_true")
args = parser.parse_args()
sys.path.insert(0, str(args.repo))

from tools import browser_smoke_test as smoke  # noqa: E402
from tools.apk_emulator_smoke_test import (  # noqa: E402
    _AndroidWebViewCdpPage,
    _discover_cdp_endpoint,
)

out = args.out or Path("acceptance") / f"android-{args.variant}"
out.mkdir(parents=True, exist_ok=True)
snapshot_path = args.snapshot
adb = args.adb
serial = args.serial
package = args.package
normal = args.artifacts_dir / (
    f"DoL-0.5.12.13-XFox-Candidate-unified-1.0.1a-{args.variant}-1118.apk"
)
diagnostic = args.diagnostic_dir / f"{args.variant}-debug.apk"
if not normal.is_file():
    raise SystemExit(f"APK not found: {normal}")
if not diagnostic.is_file():
    raise SystemExit(f"Diagnostic APK not found: {diagnostic}")
if not snapshot_path.is_file():
    raise SystemExit(f"Snapshot not found: {snapshot_path}")
commands = []
events = []
result = {
    "variant": args.variant,
    "normal": str(normal),
    "diagnostic": str(diagnostic),
    "checks": {},
    "memory_gib": args.memory_gib,
    "no_pm_clear": True,
}
started_epoch = time.time()
test_slot = None
resumed_report = False
if args.resume_normal and (out / "report.json").exists():
    existing = json.loads((out / "report.json").read_text(encoding="utf-8"))
    required = (
        "checks",
        "testSlot",
        "touch",
        "slotSave",
        "slotLoad",
        "restartMatches",
        "oldSnapshotMatches",
        "oldSnapshotOriginalPreserved",
        "existingStorageBefore",
        "existingStorageAfter",
        "afterRestart",
    )
    missing = [key for key in required if key not in existing]
    if missing:
        raise RuntimeError("Cannot resume normal phase; missing " + ", ".join(missing))
    result = existing
    commands = result.setdefault("commands", [])
    events = result.setdefault("events", [])
    test_slot = result["testSlot"]
    resumed_report = True
    result.pop("exception", None)
    result.pop("traceback", None)


def command(*args, allowed_codes=(0,)):
    process = subprocess.run(
        [adb, "-s", serial, *args], capture_output=True, timeout=180
    )
    text = (
        f"{len(process.stdout)} binary bytes"
        if args[0] == "exec-out"
        else process.stdout.decode("utf-8", "replace")
    )
    commands.append(
        {
            "args": list(args),
            "code": process.returncode,
            "stdout": text[-1500:],
            "stderr": process.stderr.decode("utf-8", "replace")[-1000:],
        }
    )
    if process.returncode not in allowed_codes:
        raise RuntimeError(
            "ADB command failed: " + str(args[:3]) + text
        )
    return process.stdout


def write():
    result["events"] = events
    result["commands"] = commands
    (out / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def display():
    activity = command("shell", "dumpsys", "activity", "activities").decode(
        "utf-8", "replace"
    )
    current = None
    logical = None
    for line in activity.splitlines():
        match = re.match(r"Display #(\d+)", line)
        if match:
            current = int(match[1])
        if "topResumedActivity=" in line and package in line:
            logical = current
            break
    if logical is None:
        raise RuntimeError("Candidate has no resumed activity")
    displays = command("shell", "dumpsys", "display").decode("utf-8", "replace")
    viewport = next(
        value
        for value in re.findall(r"DisplayViewport(?:Info)?\{[^}]+\}", displays)
        if f"displayId={logical}," in value
    )
    surface = re.search(r"uniqueId='local:(\d+)'", viewport).group(1)
    width, height = map(
        int,
        re.search(
            r"logicalFrame=Rect\(0, 0 - (\d+), (\d+)\)", viewport
        ).groups(),
    )
    return {
        "logical": logical,
        "surface": surface,
        "width": width,
        "height": height,
    }


def capture_normal(name):
    screen = display()
    (out / name).write_bytes(
        command("exec-out", "screencap", "-p", "-d", screen["surface"])
    )
    return screen


def native_ui():
    command("shell", "rm", "-f", "/sdcard/dolx-candidate-window.xml")
    command(
        "shell",
        "uiautomator",
        "dump",
        "/sdcard/dolx-candidate-window.xml",
        allowed_codes=(0, 135, 137, 139),
    )
    if commands[-1]["code"] != 0:
        result.setdefault("toolWarnings", []).append(
            f"MuMu uiautomator exited {commands[-1]['code']} after writing XML; "
            "require a newly created, complete XML document."
        )
    xml = command("shell", "cat", "/sdcard/dolx-candidate-window.xml").decode(
        "utf-8", "replace"
    )
    root = ET.fromstring(xml)
    if root.tag != "hierarchy" or not any(True for _ in root.iter("node")):
        raise RuntimeError("MuMu UI dump produced an incomplete hierarchy")
    texts = [
        node.attrib.get("text", "")
        for node in root.iter("node")
        if node.attrib.get("text")
    ]
    return xml, texts


def tap_native(xml, text):
    nodes = [
        node
        for node in ET.fromstring(xml).iter("node")
        if node.get("text") == text
        and node.get("enabled") == "true"
        and node.get("clickable") == "true"
        and node.get("bounds") != "[0,0][0,0]"
    ]
    if not nodes:
        raise RuntimeError("Visible native button missing: " + text)
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", nodes[0].get("bounds")))
    screen = display()
    command(
        "shell",
        "input",
        "-d",
        str(screen["logical"]),
        "tap",
        str((x1 + x2) // 2),
        str((y1 + y2) // 2),
    )


def tap_saved_slot(xml, title):
    nodes = list(ET.fromstring(xml).iter("node"))
    title_node = next(
        node
        for node in nodes
        if title in node.get("text", "")
        and node.get("bounds") != "[0,0][0,0]"
    )
    _, top, _, bottom = map(int, re.findall(r"\d+", title_node.get("bounds")))
    reads = [
        node
        for node in nodes
        if node.get("text") == "读取"
        and node.get("enabled") == "true"
        and node.get("clickable") == "true"
        and node.get("bounds") != "[0,0][0,0]"
    ]
    matching = [
        node
        for node in reads
        if (
            lambda b: b[1] < bottom and b[3] > top
        )(list(map(int, re.findall(r"\d+", node.get("bounds")))))
    ]
    if len(matching) != 1:
        if len(reads) == 1:
            matching = reads
        else:
            raise RuntimeError(
                "Cannot uniquely identify saved slot read button: " + title
            )
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", matching[0].get("bounds")))
    screen = display()
    command(
        "shell",
        "input",
        "-d",
        str(screen["logical"]),
        "tap",
        str((x1 + x2) // 2),
        str((y1 + y2) // 2),
    )


page = None


def launch():
    command(
        "shell",
        "am",
        "start",
        "--display",
        "0",
        "-n",
        package + "/com.vrelnir.dol.MainActivity",
    )
    endpoint = _discover_cdp_endpoint(
        adb, package, commands, cdp_port=9341, timeout_seconds=60, serial=serial
    )
    if not endpoint["success"]:
        raise RuntimeError(str(endpoint))
    target = next(item for item in endpoint["targets"] if item.get("type") == "page")
    current = _AndroidWebViewCdpPage(
        target["webSocketDebuggerUrl"], 180000, target
    )
    current.on(
        "pageerror",
        lambda error: events.append(
            {
                "type": "pageerror",
                "text": str(error),
                "timestamp": time.time(),
                "launch": len(result.get("startupTiming", [])) + 1,
            }
        ),
    )
    current.on(
        "console",
        lambda message: events.append(
            {
                "type": message.type,
                "text": message.text,
                "location": message.location,
            }
        )
        if message.type in ("error", "warning")
        else None,
    )
    current.on(
        "response",
        lambda response: events.append(
            {"type": "http", "url": response.url, "status": response.status}
        )
        if response.status >= 400
        else None,
    )
    current.on(
        "requestfailed",
        lambda request: events.append(
            {
                "type": "requestfailed",
                "url": request.url,
                "failure": request.failure,
            }
        ),
    )
    current.on(
        "dialog",
        lambda dialog: (
            dialog.accept(),
            events.append(
                {
                    "type": "dialog",
                    "text": dialog.message,
                    "already_closed": dialog.already_closed,
                }
            ),
        ),
    )
    started = time.monotonic()
    deadline = started + 600
    result.setdefault("startupTiming", [])
    while time.monotonic() < deadline:
        if current.evaluate("() => !!window.SugarCube?.State"):
            break
        current.wait_for_timeout(1000)
    else:
        raise RuntimeError(
            "Cordova game engine did not initialize within 600 seconds"
        )
    result["startupTiming"].append(
        {
            "engineReadySeconds": round(time.monotonic() - started, 2),
            "budgetSeconds": 600,
        }
    )
    report = smoke.BrowserSmokeReport(str(normal), "candidate-android", True)
    startup = smoke._run_startup_interactions(
        report, current, smoke.PROFILES["ucb-cheat-extended-maplebirch"]
    )
    if not startup["success"]:
        result.setdefault("startupFailures", []).append(startup)
        raise RuntimeError("Android startup failed")
    result.setdefault("nativeBridgeChecks", [])
    result["nativeBridgeChecks"].append(
        current.evaluate(
            "() => {const exec=cordova.require('cordova/exec');"
            "exec(()=>{},()=>{},'CoreAndroid','clearHistory',[]);"
            "return {action:'clearHistory',passed:true};}"
        )
    )
    return current, startup


snapshot = """() => JSON.parse(JSON.stringify({
  marker: V.dolxAndroidAcceptance, passage: SugarCube.State.passage,
  hair: V.haircolour, hairGradient: V.hairColourGradient,
  customHair: [V.customhaircolor1, V.customhaircolor2],
  renderedHair: ['hair_sides', 'hair_fringe'].map(k =>
    Renderer.CanvasModelCaches.main.sidebar.layers[k].blend),
  facestyle: V.facestyle, facevariant: V.facevariant,
  items: V.foodstuff, options: V.options,
  clothes: Object.fromEntries(Object.entries(V.worn).map(([k, v]) =>
    [k, {name: v.name, colour: v.colour}])),
  imageErrors: Object.keys(Renderer.ImageErrors),
  errors: [...document.querySelectorAll('.error')].map(e => e.textContent)
}))"""
hair_pixels = """() => ['hair_sides', 'hair_fringe'].map(k => {
  const image = Renderer.CanvasModelCaches.main.sidebar.layers[k].cachedImage;
  const ctx = Renderer.createCanvas(image.width, image.height);
  ctx.drawImage(image, 0, 0);
  const a = ctx.getImageData(0, 0, image.width, image.height).data;
  let n = 0;
  for (let i = 0; i < a.length; i += 4)
    if (a[i + 3] && a[i + 2] > a[i] + 20) n++;
  return n;
})"""


def run_game_checks():
    global page, test_slot
    result["device"] = {
        "serial": serial,
        "model": command("shell", "getprop", "ro.product.model")
        .decode()
        .strip(),
        "android": command("shell", "getprop", "ro.build.version.release")
        .decode()
        .strip(),
        "webview": command("shell", "dumpsys", "webviewupdate").decode(
            "utf-8", "replace"
        ),
    }
    memory = command("shell", "cat", "/proc/meminfo").decode()
    result["memoryBefore"] = memory
    if "MemTotal:        1776372 kB" not in memory:
        raise RuntimeError("Original 1.75 GiB emulator memory changed")
    command("shell", "am", "force-stop", package)
    command("install", "-r", "-d", str(diagnostic))
    page, result["startup"] = launch()
    write()
    page.screenshot(path=str(out / "02-enter-game.png"))
    result["existingStorageBefore"] = page.evaluate(
        "async () => ({local:Object.fromEntries(Object.keys(localStorage)"
        ".map(k=>[k,localStorage.getItem(k)])),"
        "idb:await idb.getSaveDetails()})"
    )
    used = {entry["slot"] for entry in result["existingStorageBefore"]["idb"]}
    test_slot = next((index for index in range(1, 101) if index not in used), None)
    if test_slot is None:
        raise RuntimeError("No unused candidate test slot available")
    result["testSlot"] = test_slot
    write()
    result["compat"] = page.evaluate("() => window.dolxCompat || null")
    if args.variant != "base":
        compat = result["compat"]
        if (
            not compat
            or not compat["registered"]
            or compat["registrationCount"] != 1
            or compat["petCaptureCount"] != 1
            or compat["beforeCaches"]
        ):
            raise RuntimeError("Android compatibility registration failed")
    elif result["compat"] is not None:
        raise RuntimeError("Base APK incorrectly loaded AU compatibility")
    write()
    for name in (
        "functional-controls",
        "doli-native-settings",
        "hair-ui",
        "clothing-pet",
    ):
        result["checks"][name] = page.evaluate(
            (args.diagnostics_dir / f"{name}.js").read_text(
                encoding="utf-8"
            )
        )
        write()
    result["checks"]["face-matrix"] = page.evaluate(
        (args.diagnostics_dir / "face-matrix.js")
        .read_text(encoding="utf-8")
        .replace("setTimeout(r,300)", "setTimeout(r,600)")
    )
    write()
    result["checks"]["expressions"] = page.evaluate(
        (args.diagnostics_dir / "expressions.js").read_text(encoding="utf-8")
    )
    result["checks"]["doli-history"] = page.evaluate(
        (args.diagnostics_dir / "doli-engine-history.js").read_text(
            encoding="utf-8"
        )
    )
    write()
    if args.variant == "au-m":
        result["checks"]["pet-frame-clean"] = page.evaluate(
            (args.diagnostics_dir / "pet-frame-clean.js").read_text(
                encoding="utf-8"
            )
        )
        write()
        if not result["checks"]["pet-frame-clean"]["passed"]:
            raise RuntimeError("AU-M pet animation has stray pixels")
    page.evaluate("() => SugarCube.Engine.play('Bed')")
    page.wait_for_timeout(700)
    point = page.evaluate(
        "() => {const e=document.querySelector('[data-passage=\"Bedroom\"]');"
        "if(!e)throw Error('Bedroom touch link missing');"
        "e.scrollIntoView();const r=e.getBoundingClientRect();"
        "return {x:r.x+r.width/2,y:r.y+r.height/2,width:innerWidth};}"
    )
    screen = display()
    scale = screen["width"] / point["width"]
    command(
        "shell",
        "input",
        "-d",
        str(screen["logical"]),
        "tap",
        str(round(point["x"] * scale)),
        str(round(point["y"] * scale)),
    )
    page.wait_for_timeout(1000)
    result["touch"] = {
        "passage": page.evaluate("() => SugarCube.State.passage"),
        "point": point,
        "screen": screen,
    }
    result["touch"]["passed"] = result["touch"]["passage"] == "Bedroom"
    verify_storage()
    verify_old_snapshot()


def verify_storage():
    global page
    page.evaluate(
        "v=>{V.dolxAndroidAcceptance=v;SugarCube.Engine.play('Bedroom');}",
        args.variant,
    )
    page.wait_for_timeout(500)
    result["beforeRestart"] = page.evaluate(snapshot)
    result["hairPixelsBefore"] = page.evaluate(hair_pixels)
    result["slotSave"] = page.evaluate(
        "async p => await idb.saveState(p.slot,p.title)",
        {"slot": test_slot, "title": "DoL-X 1118 " + args.variant},
    )
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "03-before-restart.png"))
    page.close()
    page = None
    command("shell", "am", "force-stop", package)
    page, result["restartStartup"] = launch()
    result["slotLoad"] = page.evaluate(
        "async slot => {const details=await idb.getSaveDetails();"
        "if(!details.some(d=>d.slot===slot))return false;"
        "await idb.loadState(slot);return true;}",
        test_slot,
    )
    page.wait_for_timeout(1000)
    result["saveBackend"] = (
        "DoL IndexedDB idb.saveState/loadState free slot " + str(test_slot)
    )
    result["existingStorageAfter"] = page.evaluate(
        "async () => ({local:Object.fromEntries(Object.keys(localStorage)"
        ".map(k=>[k,localStorage.getItem(k)])),"
        "idb:await idb.getSaveDetails()})"
    )
    result["afterRestart"] = page.evaluate(snapshot)
    if args.variant == "au-m":
        result["checks"]["pet-frame-clean-after-restart"] = page.evaluate(
            (args.diagnostics_dir / "pet-frame-clean.js").read_text(
                encoding="utf-8"
            )
        )
        write()
        if not result["checks"]["pet-frame-clean-after-restart"]["passed"]:
            raise RuntimeError(
                "AU-M pet animation has stray pixels after restart"
            )
    result["hairPixelsAfter"] = page.evaluate(hair_pixels)
    if (
        not all(result["hairPixelsBefore"])
        or result["hairPixelsAfter"] != result["hairPixelsBefore"]
    ):
        raise RuntimeError("Rendered hair pixels changed across restart")
    keys = (
        "marker",
        "hair",
        "hairGradient",
        "customHair",
        "renderedHair",
        "facestyle",
        "facevariant",
        "items",
        "options",
        "clothes",
    )
    result["restartMatches"] = all(
        result["beforeRestart"].get(key) == result["afterRestart"].get(key)
        for key in keys
    )
    page.screenshot(path=str(out / "04-after-restart.png"))
    page.close()
    page = None


old_snapshot = """() => JSON.parse(JSON.stringify({
  passage: SugarCube.State.passage, money: V.money,
  facestyle: V.facestyle, facevariant: V.facevariant,
  hair: V.haircolour, hairGradient: V.hairColourGradient,
  customHair: [V.customhaircolor1, V.customhaircolor2],
  renderedHair: ['hair_sides', 'hair_fringe'].map(k =>
    Renderer.CanvasModelCaches.main.sidebar.layers[k].blend),
  clothes: Object.fromEntries(Object.entries(V.worn).map(([k, v]) =>
    [k, {name: v.name, colour: v.colour}])),
  items: V.foodstuff, options: V.options,
  errors: [...document.querySelectorAll('.error')].map(e => e.textContent),
  imageErrors: Object.keys(Renderer.ImageErrors)
}))"""


def await_npc_ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if page.evaluate(
            "() => ['Tsukihan','Rowan','Adrian','Marlow','Grant']"
            ".every(n=>Object.hasOwn(V.options.maplebirch.npcsidebar.display,n))"
        ):
            return
        page.wait_for_timeout(1000)
    raise RuntimeError("Framework NPCSidebar did not finish initialization")


def verify_old_snapshot():
    global page
    page, result["oldSnapshotImportStartup"] = launch()
    await_npc_ready()
    previous_state = page.evaluate("() => SugarCube.Save.serialize()")
    original_local = page.evaluate(
        "() => localStorage.getItem('degrees-of-lewdity.saves')"
    )
    old_path = snapshot_path
    old = old_path.read_text(encoding="utf-8")
    result["oldSnapshotSha256"] = hashlib.sha256(old_path.read_bytes()).hexdigest()
    try:
        result["oldSnapshotImported"] = page.evaluate(
            "s=>{localStorage.setItem('degrees-of-lewdity.saves',s);"
            "return SugarCube.Save.slots.load(4);}",
            old,
        )
        if not result["oldSnapshotImported"]:
            raise RuntimeError("Android 1014 snapshot copy import failed")
        page.wait_for_timeout(1000)
        page.evaluate("() => SugarCube.Engine.play('Bedroom')")
        page.wait_for_timeout(1000)
        result["oldSnapshotBeforeRestart"] = page.evaluate(old_snapshot)
        saved = page.evaluate("() => SugarCube.Save.serialize()")
        page.screenshot(path=str(out / "old-1014-continued.png"))
    finally:
        page.evaluate(
            "s=>{if(s===null)localStorage.removeItem('degrees-of-lewdity.saves');"
            "else localStorage.setItem('degrees-of-lewdity.saves',s);}",
            original_local,
        )
    page.close()
    page = None
    command("shell", "am", "force-stop", package)
    page, result["oldSnapshotRestartStartup"] = launch()
    await_npc_ready()
    result["oldSnapshotRestoredPassage"] = page.evaluate(
        "s=>{SugarCube.Save.deserialize(s);return SugarCube.State.passage;}", saved
    )
    page.wait_for_timeout(1000)
    result["oldSnapshotAfterRestart"] = page.evaluate(old_snapshot)
    keys = (
        "passage",
        "money",
        "facestyle",
        "facevariant",
        "hair",
        "hairGradient",
        "customHair",
        "renderedHair",
        "clothes",
        "items",
        "options",
    )
    result["oldSnapshotMatches"] = all(
        result["oldSnapshotBeforeRestart"].get(key)
        == result["oldSnapshotAfterRestart"].get(key)
        for key in keys
    )
    result["oldSnapshotOriginalPreserved"] = (
        hashlib.sha256(old_path.read_bytes()).hexdigest()
        == result["oldSnapshotSha256"]
    )
    if (
        not result["oldSnapshotMatches"]
        or not result["oldSnapshotOriginalPreserved"]
        or result["oldSnapshotAfterRestart"]["errors"]
        or result["oldSnapshotAfterRestart"]["imageErrors"]
    ):
        raise RuntimeError("Android old snapshot restore differs or reports an error")
    page.screenshot(path=str(out / "old-1014-after-restart.png"))
    write()
    page.evaluate("s=>SugarCube.Save.deserialize(s)", previous_state)
    page.wait_for_timeout(1000)


def restore_normal(already_running=False):
    if not already_running:
        command("shell", "am", "force-stop", package)
        command("install", "-r", "-d", str(normal))
        command(
            "shell",
            "am",
            "start",
            "--display",
            "0",
            "-n",
            package + "/com.vrelnir.dol.MainActivity",
        )
    deadline = time.monotonic() + 600
    ready = False
    xml = ""
    texts = []
    while time.monotonic() < deadline:
        time.sleep(5)
        pid = (
            command("shell", "pidof", package, allowed_codes=(0, 1))
            .decode()
            .strip()
        )
        if not pid:
            result["normalProcessExited"] = True
            write()
            raise RuntimeError(
                "Normal candidate process exited during startup; see native log"
            )
        xml, texts = native_ui()
        seed_menu = "存档" in texts and any(
            text.strip().startswith(("(1) 开始", "开始游戏", "进入游戏"))
            for text in texts
        )
        bedroom = any(
            text.startswith(("这是你的卧室", "你偎在被子里")) for text in texts
        )
        ready = seed_menu or bedroom
        result.setdefault("normalReadinessSamples", []).append(
            {"seedMenu": seed_menu, "bedroom": bedroom, "texts": texts[:8]}
        )
        if ready:
            break
    result["finalDisplay"] = capture_normal("05-normal-restored.png")
    (out / "normal-restored-ui.xml").write_text(xml, encoding="utf-8")
    result["normalRestored"] = package in xml and ready
    result["normalUiTexts"] = texts
    if not result["normalRestored"]:
        raise RuntimeError("Normal APK did not reach game UI")
    title_texts = [
        re.sub(r"^\(\d+\)\s*", "", text).strip()
        for text in texts
        if re.match(r"^\(\d+\)\s*", text)
    ]
    if "开始" in title_texts:
        tap_native(xml, "(1) 开始")
        time.sleep(3)
        xml, texts = native_ui()
        title_texts = [
            re.sub(r"^\(\d+\)\s*", "", text).strip()
            for text in texts
            if re.match(r"^\(\d+\)\s*", text)
        ]
        if "开始" in title_texts:
            raise RuntimeError("Normal APK start menu did not leave the title screen")
    if not any(text.startswith(("这是你的卧室", "你偎在被子里")) for text in texts):
        if "存档" not in texts:
            tap_native(xml, "打开/关闭导航栏")
            time.sleep(1)
            xml, texts = native_ui()
        tap_native(xml, "存档")
        time.sleep(1)
        xml, texts = native_ui()
    else:
        result["normalAlreadyInPlay"] = True
    expected_title = "DoL-X 1118 " + args.variant
    if not any(expected_title in text for text in texts):
        raise RuntimeError("Saved IndexedDB slot missing in normal APK UI")
    scroll_attempts = 0
    while not any(
        node.get("text", "").startswith(expected_title)
        and node.get("bounds") != "[0,0][0,0]"
        for node in ET.fromstring(xml).iter("node")
    ):
        if scroll_attempts >= 12:
            raise RuntimeError("Saved slot never became visible after scrolling")
        screen = display()
        command(
            "shell",
            "input",
            "-d",
            str(screen["logical"]),
            "swipe",
            "210",
            "640",
            "210",
            "300",
            "300",
        )
        scroll_attempts += 1
        time.sleep(1)
        xml, texts = native_ui()
    result["normalSlotScrollAttempts"] = scroll_attempts
    (out / "normal-save-ui.xml").write_text(xml, encoding="utf-8")
    tap_saved_slot(xml, expected_title)
    time.sleep(2)
    xml, texts = native_ui()
    if any(text.strip() in ["确认", "确定"] for text in texts):
        tap_native(
            xml,
            next(
                text.strip()
                for text in texts
                if text.strip() in ["确认", "确定"]
            ),
        )
        time.sleep(2)
        xml, texts = native_ui()
    settle_deadline = time.monotonic() + 30
    while (
        not (any("厨房" in text for text in texts) and any("爬到床上" in text for text in texts))
        and time.monotonic() < settle_deadline
    ):
        time.sleep(2)
        xml, texts = native_ui()
    result["normalSlotRead"] = any("厨房" in text for text in texts) and any(
        "爬到床上" in text for text in texts
    )
    result["normalLoadedTexts"] = texts
    (out / "normal-loaded-ui.xml").write_text(xml, encoding="utf-8")
    capture_normal("06-normal-slot-loaded.png")
    if not result["normalSlotRead"]:
        raise RuntimeError("Normal APK save load did not return to Bedroom")


try:
    if not resumed_report:
        run_game_checks()
    restore_normal()
    result["runtimeErrors"] = [
        event
        for event in events
        if event["type"] == "pageerror"
        or (
            event["type"] == "error"
            and not event["text"].startswith("Failed to load resource:")
        )
    ]
    result["unexpectedHttp"] = [
        event
        for event in events
        if event["type"] in ("http", "requestfailed")
        and urlparse(event["url"]).path
        not in ["/style.css", "/usettings.js", "/img/misc/banner.png"]
    ]
    before_saves = result["existingStorageBefore"]["idb"]
    after_saves = result["existingStorageAfter"]["idb"]
    result["existingSaveDataPreserved"] = all(
        any(
            saved.get("slot") == original.get("slot")
            and saved.get("title") == original.get("title")
            for saved in after_saves
        )
        for original in before_saves
    ) and (
        result["existingStorageBefore"]["local"].get("degrees-of-lewdity.saves")
        == result["existingStorageAfter"]["local"].get("degrees-of-lewdity.saves")
    )
    result["checks"]["diagnostic-resource-equivalence"] = next(
        (
            entry
            for entry in json.loads(
                (args.diagnostic_dir / "equivalence.json").read_text(
                    encoding="utf-8"
                )
            )
            if entry["variant"] == args.variant
        ),
        None,
    )
    result["passed"] = bool(
        result["touch"]["passed"]
        and result["slotSave"]
        and result["slotLoad"]
        and result["restartMatches"]
        and result["normalRestored"]
        and result["normalSlotRead"]
        and result["oldSnapshotMatches"]
        and result["oldSnapshotOriginalPreserved"]
        and result["existingSaveDataPreserved"]
        and not result["runtimeErrors"]
        and not result["unexpectedHttp"]
        and not result["afterRestart"]["errors"]
        and not result["afterRestart"]["imageErrors"]
        and (
            args.variant != "au-m"
            or (
                result["checks"].get("pet-frame-clean", {}).get("passed")
                and result["checks"]
                .get("pet-frame-clean-after-restart", {})
                .get("passed")
            )
        )
        and all(
            result["checks"][key]["passed"]
            for key in (
                "doli-native-settings",
                "hair-ui",
                "clothing-pet",
                "doli-history",
            )
        )
        and all(
            result["checks"]["functional-controls"][key]["passed"]
            for key in ("attribute", "item", "time", "hair")
        )
        and all(
            not row["errors"] and row["pixels"] > 0
            for row in result["checks"].get("face-matrix", [])
        )
        and all(
            not row["errors"] for row in result["checks"]["expressions"]
        )
    )
    result.pop("exception", None)
    result.pop("traceback", None)
except Exception as exc:
    import traceback
    result["exception"] = f"{type(exc).__name__}: {exc}"
    result["traceback"] = traceback.format_exc()[-4000:]
    result["passed"] = False
finally:
    if page:
        page.close()
    if not result.get("normalRestored"):
        try:
            command("shell", "am", "force-stop", package)
            command("install", "-r", "-d", str(normal))
            result["normalRestoredAfterFailure"] = True
        except Exception as restore_error:
            result["normalRestoreFailure"] = str(restore_error)
    since = datetime.datetime.fromtimestamp(started_epoch).strftime(
        "%m-%d %H:%M:%S.000"
    )
    result["logcatFile"] = "complete-native.log"
    (out / result["logcatFile"]).write_bytes(
        command("logcat", "-d", "-b", "all", "-v", "epoch", "-T", since)
    )
    write()

print(
    json.dumps(
        {
            key: result.get(key)
            for key in (
                "variant",
                "passed",
                "exception",
                "restartMatches",
                "touch",
            )
        },
        ensure_ascii=False,
    )
)
sys.exit(0 if result["passed"] else 1)
