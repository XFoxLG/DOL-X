#!/usr/bin/env python3
"""Clean single-variable A/B for the DOL-X desktop-pet passage-remount patch.

The older ``measure_pet_remount_ab.py`` re-ran its ENABLE helper after every
passage hop. That helper calls ``$.wiki("<<updatesidebarimg>>")``, which is
exactly the macro the remount patch invokes on ``:passagedisplay``. Any control
group therefore got the pet remounted by the harness itself and both arms
measured 17587 opaque pixels, hiding the treatment difference.

This script enables the pet exactly once, then navigates passages and measures
the live DOM without touching the pet pipeline. A treatment arm (patch present)
should keep a mounted, clothed canvas; a control arm (patch removed) should show
a fresh, empty container after a passage render.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from tools.apk_emulator_smoke_test import (  # noqa: E402
    _CdpWebSocketSession,
    _discover_cdp_endpoint,
)
from tools.browser_smoke_test import (  # noqa: E402
    MODAL_BLOCKER_SELECTORS,
    STARTUP_CONFIRM_LABELS,
    STARTUP_CONSENT_LABELS,
    _game_ready_script,
    _startup_gate_status_script,
    _startup_interaction_script,
)

ADB = os.environ.get("DOLX_ADB", r"D:\MuMu\nx_device\12.0\shell\adb.exe")
SERIAL = os.environ.get("DOLX_SERIAL", "127.0.0.1:16384")
PACKAGE = "com.vrelnir.dol.xfox"
CDP_PORT = 9222
os.environ["ANDROID_SERIAL"] = SERIAL

OPTIONS = {
    "password": None,
    "modalSelectors": list(MODAL_BLOCKER_SELECTORS),
    "confirmLabels": list(STARTUP_CONFIRM_LABELS),
    "consentLabels": list(STARTUP_CONSENT_LABELS),
}

READY = (
    "(() => { try { return !!(window.SugarCube && SugarCube.State && "
    "SugarCube.Story && SugarCube.Engine); } catch(e){ return false; } })()"
)

GATE = r"""
(() => {
  const vis = e => e && (e.offsetWidth||e.offsetHeight||e.getClientRects().length) &&
        getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none';
  const txt = e => (e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();
  const out = {checkbox:false, button:null};
  const boxes = Array.from(document.querySelectorAll('input[type=checkbox]')).filter(vis);
  for (const cb of boxes) {
    const root = cb.closest('label,p,div,li,section,article,form') || cb.parentElement;
    const t = root ? txt(root) : '';
    if (/18|age|confirm|know|read|同意|确认|年龄/i.test(t)) {
      if (!cb.checked) { cb.checked = true; cb.dispatchEvent(new Event('input',{bubbles:true})); cb.dispatchEvent(new Event('change',{bubbles:true})); }
      out.checkbox = true; break;
    }
  }
  const cands = Array.from(document.querySelectorAll('button,input[type=button],input[type=submit],a,[role=button],.swal2-confirm')).filter(vis);
  for (const b of cands) {
    const t = (txt(b) || b.value || '').trim();
    if (/^(enter|start|continue|进入|開始|开始|確定|确定|继续|繼續|我已知晓|我確認)$/i.test(t) || /enter|进入游戏|我已知晓/i.test(t)) {
      b.click(); out.button = t; break;
    }
  }
  return out;
})()
"""

# Turns the pet on once. Never call this between passage hops.
ENABLE_ONCE = r"""
(() => { try {
  const v=SugarCube.State.variables; v.options=v.options||{};
  v.options.maplebirch=v.options.maplebirch||{};
  v.options.maplebirch.character=v.options.maplebirch.character||{};
  v.options.maplebirch.character.pet=v.options.maplebirch.character.pet||{};
  v.options.maplebirch.character.pet.enabled=true;
  try { window.maplebirch?.char?.pet?.sync?.(); } catch(e){}
  try { $.wiki("<<updatesidebarimg>>"); } catch(e){}
  return {ok:true, enabled:v.options.maplebirch.character.pet.enabled};
} catch(e){ return {ok:false,error:String(e)}; } })()
"""

# Read-only probe. Mirrors what the player sees: the live container that
# SugarCube just rebuilt, not the framework's possibly-detached reference.
PROBE = r"""
(() => {
  const out = {passage:null, petEnabled:null, liveContainer:null, canvas:null, errorBanner:null};
  try { out.passage = SugarCube.State.passage; } catch(e){}
  try { out.petEnabled = !!(SugarCube.State.variables?.options?.maplebirch?.character?.pet?.enabled); } catch(e){}
  try { const b=document.querySelector('.error, .error-view'); out.errorBanner = b? String(b.innerText||'').slice(0,90): null; } catch(e){}
  const el = document.getElementById('maplebirch-character-pet');
  if (el) {
    out.liveContainer = {children: el.childElementCount, connected: el.isConnected};
    const cv = el.querySelector('canvas');
    if (cv) {
      out.canvas = {w: cv.width, h: cv.height};
      try {
        const d = cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;
        let n = 0;
        for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
        out.canvas.opaque = n;
      } catch(e) { out.canvas.pixelError = String(e); }
    }
  }
  // The framework's own view, to show whether it still points at a detached node.
  try {
    const pet = window.maplebirch?.char?.pet;
    const held = pet?.container;
    if (held) {
      out.frameworkContainer = {children: held.childElementCount, connected: held.isConnected !== false};
    }
  } catch(e) {}
  return out;
})()
"""


def adb(args, timeout=900):
    result = subprocess.run(
        [ADB, "-s", SERIAL, *args], capture_output=True, timeout=timeout
    )
    return (
        result.returncode,
        (result.stdout or b"").decode("utf-8", "replace"),
        (result.stderr or b"").decode("utf-8", "replace"),
    )


class Page:
    def __init__(self, websocket_url: str) -> None:
        self.session = _CdpWebSocketSession(websocket_url, 120.0)
        self.session.send_command("Runtime.enable")
        self.session.send_command("Page.enable")

    def evaluate(self, expression: str, timeout: float = 120.0):
        last = None
        for _attempt in range(4):
            try:
                result = self.session.send_command(
                    "Runtime.evaluate",
                    {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": True,
                        "userGesture": True,
                    },
                    timeout_seconds=timeout,
                )
                if result.get("exceptionDetails"):
                    raise RuntimeError(
                        json.dumps(result["exceptionDetails"], ensure_ascii=False)[:300]
                    )
                return (result.get("result") or {}).get("value")
            except Exception as exc:  # noqa: BLE001 - retry transient CDP stalls.
                last = exc
                time.sleep(5)
                try:
                    self.session.send_command("Runtime.enable", timeout_seconds=30)
                except Exception:  # noqa: BLE001
                    pass
        raise last

    def call(self, script: str, options=None):
        payload = json.dumps(options) if options is not None else ""
        return self.evaluate(f"({script})({payload})")

    def screenshot(self, destination: pathlib.Path) -> int:
        result = self.session.send_command("Page.captureScreenshot", {"format": "png"})
        payload = base64.b64decode(result.get("data") or "")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return len(payload)

    def close(self) -> None:
        self.session.close()


def attach() -> Page:
    endpoint = _discover_cdp_endpoint(
        ADB, PACKAGE, [], cdp_port=CDP_PORT, timeout_seconds=120
    )
    if not endpoint.get("success"):
        raise SystemExit("CDP discovery failed: " + str(endpoint.get("error")))
    targets = [
        target
        for target in endpoint.get("targets", [])
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl")
    ]
    if not targets:
        raise SystemExit("no attachable page target")
    return Page(targets[0]["webSocketDebuggerUrl"])


def run_arm(apk: str, label: str, out_path: str) -> dict:
    print("=" * 70)
    print("GROUP:", label)
    code, stdout, stderr = adb(["install", "-r", apk])
    print(f"install rc={code}")
    if code != 0:
        print(stdout[-400:])
        print(stderr[-400:])
        return {"label": label, "install_failed": True}

    adb(["shell", f"am force-stop {PACKAGE}"])
    time.sleep(2)
    adb(["shell", f"monkey -p {PACKAGE} -c android.intent.category.LAUNCHER 1"])
    result = {"label": label, "apk": apk, "steps": []}
    page = None
    for attempt in range(10):
        time.sleep(10)
        try:
            page = attach()
            print("cdp attached attempt", attempt + 1)
            break
        except SystemExit as exc:
            print("attach retry", attempt + 1, str(exc)[:70])
    if page is None:
        result["attach_failed"] = True
        return result

    try:
        ready = False
        for index in range(60):
            try:
                if page.evaluate(READY):
                    ready = True
                    print("SugarCube ready after ~", index * 5, "s")
                    break
            except Exception as exc:  # noqa: BLE001
                print("ready poll", index, "err", str(exc)[:60])
            time.sleep(5)
        if not ready:
            print("WARNING: SugarCube not detected; continuing")

        for step in range(30):
            try:
                state = page.call(_game_ready_script())
                gate = page.call(_startup_gate_status_script(), OPTIONS)
            except Exception as exc:  # noqa: BLE001
                print("startup poll err", str(exc)[:70])
                time.sleep(5)
                continue
            passage = str(state.get("passage") or "").lower()
            if state.get("ready") and not gate.get("has_gate") and passage not in ("", "start", "loading"):
                print("playable at passage:", state.get("passage"))
                break
            try:
                page.call(GATE)
                action = page.call(_startup_interaction_script(), OPTIONS)
                result["steps"].append(
                    {
                        "step": step + 1,
                        "passage": state.get("passage"),
                        "clicked": action.get("clicked"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                print("  step", step + 1, "interaction err", str(exc)[:60])
            time.sleep(1.5)

        print("post-startup passage:", page.evaluate(
            "(function(){try{return SugarCube.State.passage}catch(e){return null}})()"
        ))

        # Enable the pet exactly once, then never touch the pet pipeline again.
        print("enable pet (once):", json.dumps(page.evaluate(ENABLE_ONCE), ensure_ascii=False))
        time.sleep(4)
        baseline = page.evaluate(PROBE)
        result["baseline"] = baseline
        print(
            "  baseline  passage=%-16s container=%-28s canvas=%s"
            % (
                baseline.get("passage"),
                json.dumps(baseline.get("liveContainer")),
                json.dumps(baseline.get("canvas")),
            )
        )

        walk = []
        for name in ["Orphanage Intro", "Start", "Bedroom", "Start"]:
            try:
                page.evaluate(f"SugarCube.Engine.play({json.dumps(name)})")
            except Exception as exc:  # noqa: BLE001
                print("play err", str(exc)[:100])
                continue
            time.sleep(6)
            state = page.evaluate(PROBE)  # read-only: no ENABLE, no macro call
            walk.append({"requested": name, "state": state})
            canvas = (state or {}).get("canvas") or {}
            container = (state or {}).get("liveContainer") or {}
            print(
                "  %-18s passage=%-16s opaque=%-7s children=%-4s connected=%-5s enabled=%s"
                % (
                    name,
                    (state or {}).get("passage"),
                    canvas.get("opaque"),
                    container.get("children"),
                    container.get("connected"),
                    (state or {}).get("petEnabled"),
                )
            )
        result["walk"] = walk
        result["screenshot"] = str(
            REPO_ROOT / "output" / f"pet-ab-clean-{label}.png"
        )
        page.screenshot(pathlib.Path(result["screenshot"]))
    finally:
        page.close()

    pathlib.Path(out_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: pet_remount_ab_device_check.py <apk> <label> <out.json>\n"
            "  env: DOLX_ADB (default D:\\MuMu\\nx_device\\12.0\\shell\\adb.exe),"
            " DOLX_SERIAL (default 127.0.0.1:16384)"
        )
        return 2
    apk = sys.argv[1]
    label = sys.argv[2]
    out_path = sys.argv[3]
    result = run_arm(apk, label, out_path)
    opaque = [
        ((hop.get("state") or {}).get("canvas") or {}).get("opaque")
        for hop in result.get("walk", [])
    ]
    print(json.dumps({"label": result.get("label"), "opaque": opaque}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
