"""Browser acceptance for a DOL-X candidate build.

Replays startup, cheat controls, custom hair, DOLI settings and history,
clothes/pet, face matrix, expressions, self save/reload, and the 1014 device
snapshot copy. The package is served from a fresh extraction of the ZIP; the
snapshot file itself is never modified.

Usage:
    python tools/candidate_acceptance/browser_acceptance.py \
        --repo . --variant base --artifacts-dir output \
        --diagnostics-dir <diagnostics-dir> --snapshot <1014-device-saves-copy.json>
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, required=True, help="project root for tools import")
parser.add_argument("--variant", required=True, help="base, au-f, au-m or au-a")
parser.add_argument("--artifacts-dir", type=Path, default=Path("output"))
parser.add_argument("--diagnostics-dir", type=Path, required=True)
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--out", type=Path)
parser.add_argument(
    "--tag", default="v0.5.12.13-1.0.1a-1118", help="artifact version tag"
)
args = parser.parse_args()
sys.path.insert(0, str(args.repo))

from playwright.sync_api import sync_playwright  # noqa: E402
from tools import browser_smoke_test as smoke  # noqa: E402

out = args.out or Path("acceptance") / f"browser-{args.variant}"
out.mkdir(parents=True, exist_ok=True)
target = args.artifacts_dir / (
    f"DoL-0.5.12.13-XFox-Candidate-unified-1.0.1a-{args.variant}-1118.zip"
)
diagnostics = args.diagnostics_dir
snapshot_source = args.snapshot
if not target.is_file():
    raise SystemExit(f"ZIP not found: {target}")
if not diagnostics.is_dir():
    raise SystemExit(f"Diagnostics directory not found: {diagnostics}")
if not snapshot_source.is_file():
    raise SystemExit(f"Snapshot not found: {snapshot_source}")

events = []
stage = "startup"
result = {"variant": args.variant, "target": str(target), "checks": {}}
snapshot_js = """() => JSON.parse(JSON.stringify({
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


def write():
    (out / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def await_npc_sidebar_ready(page):
    page.wait_for_function(
        """() => ['Tsukihan', 'Rowan', 'Adrian', 'Marlow', 'Grant']
            .every(n => Object.hasOwn(V.options.maplebirch.npcsidebar.display, n))""",
        timeout=60000,
    )


try:
    game, html = smoke._resolve_target(target, out / "extracted")
    with smoke._serve_directory(game) as server, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.on(
            "pageerror",
            lambda e: events.append({"type": "pageerror", "text": str(e)}),
        )
        page.on(
            "console",
            lambda m: events.append({"type": m.type, "text": m.text})
            if m.type in ("error", "warning")
            else None,
        )
        page.on(
            "response",
            lambda r: events.append({"type": "http", "url": r.url, "status": r.status})
            if r.status >= 400
            else None,
        )
        page.on(
            "requestfailed",
            lambda r: events.append(
                {
                    "type": "requestfailed",
                    "url": r.url,
                    "failure": r.failure,
                    "stage": stage,
                    "pageUrl": page.url,
                }
            ),
        )
        report = smoke.BrowserSmokeReport(str(target), "candidate-functional", True)
        page.goto(
            smoke._relative_url(server, game, html),
            wait_until="domcontentloaded",
            timeout=180000,
        )
        page.wait_for_function("() => !!window.SugarCube?.State", timeout=180000)
        result["startup"] = smoke._run_startup_interactions(
            report, page, smoke.PROFILES["ucb-cheat-extended-maplebirch"]
        )
        write()
        if not result["startup"]["success"]:
            raise RuntimeError("Startup failed; see retained startup trace")
        await_npc_sidebar_ready(page)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out / "01-enter-game.png"), full_page=True)
        result["mods"] = page.evaluate(
            "() => modUtils.getModListNameNoAlias().map(n => "
            "({name: n, version: modUtils.getMod(n).version}))"
        )
        result["compat"] = page.evaluate("() => window.dolxCompat || null")
        if args.variant != "base":
            state = result["compat"]
            if (
                not state
                or not state["registered"]
                or state["registrationCount"] != 1
                or state["petCaptureCount"] != 1
                or state["beforeCaches"]
            ):
                raise RuntimeError(
                    "Standalone compatibility mod did not initialize once "
                    "before first model creation"
                )
        elif result["compat"] is not None:
            raise RuntimeError("Base game incorrectly loaded AU compatibility")

        for name in ("functional-controls", "doli-native-settings", "hair-ui", "clothing-pet"):
            stage = name
            result["checks"][name] = page.evaluate(
                (diagnostics / f"{name}.js").read_text(encoding="utf-8")
            )
            write()
        page.screenshot(path=str(out / "02-clothes-hair-pet.png"), full_page=True)
        stage = "face-matrix"
        result["checks"]["face-matrix"] = page.evaluate(
            (diagnostics / "face-matrix.js").read_text(encoding="utf-8")
        )
        write()
        stage = "expressions"
        result["checks"]["expressions"] = page.evaluate(
            (diagnostics / "expressions.js").read_text(encoding="utf-8")
        )
        write()
        if args.variant == "au-m":
            result["checks"]["pet-frame-clean"] = page.evaluate(
                (diagnostics / "pet-frame-clean.js").read_text(encoding="utf-8")
            )
            write()
            if not result["checks"]["pet-frame-clean"]["passed"]:
                raise RuntimeError("AU-M pet animation has stray pixels")
        result["checks"]["doli-history"] = page.evaluate(
            (diagnostics / "doli-engine-history.js").read_text(encoding="utf-8")
        )
        write()

        page.evaluate(
            "() => {V.dolxCandidateAcceptance='2026-11-18';"
            "SugarCube.Engine.play('Bedroom');}"
        )
        page.wait_for_timeout(700)
        before = page.evaluate(snapshot_js)
        saved = page.evaluate("SugarCube.Save.serialize()")
        stage = "self-save-reload"
        result["selfSaveBefore"] = before
        page.reload(wait_until="domcontentloaded", timeout=180000)
        smoke._run_startup_interactions(
            report, page, smoke.PROFILES["ucb-cheat-extended-maplebirch"]
        )
        await_npc_sidebar_ready(page)
        page.evaluate("s => SugarCube.Save.deserialize(s)", saved)
        page.wait_for_timeout(700)
        result["selfSaveAfter"] = page.evaluate(snapshot_js)
        keys = [
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
        ]
        result["selfSaveMatches"] = all(
            result["selfSaveAfter"][k] == before[k] for k in keys
        )

        stage = "old-save-import"
        old = snapshot_source.read_text(encoding="utf-8")
        result["oldSaveImport"] = page.evaluate(
            "s => {localStorage.setItem('degrees-of-lewdity.saves', s);"
            "return SugarCube.Save.slots.load(4);}",
            old,
        )
        page.wait_for_timeout(700)
        result["oldSaveLoaded"] = page.evaluate(snapshot_js)
        page.evaluate("() => SugarCube.Engine.play('Bedroom')")
        page.wait_for_timeout(500)
        old_before = page.evaluate(snapshot_js)
        result["oldSaveBeforeExport"] = old_before
        old_export = page.evaluate("SugarCube.Save.serialize()")
        page.screenshot(path=str(out / "03-old-save-continued.png"), full_page=True)
        stage = "old-save-reload"
        page.reload(wait_until="domcontentloaded", timeout=180000)
        smoke._run_startup_interactions(
            report, page, smoke.PROFILES["ucb-cheat-extended-maplebirch"]
        )
        await_npc_sidebar_ready(page)
        page.evaluate("s => SugarCube.Save.deserialize(s)", old_export)
        page.wait_for_timeout(700)
        result["oldSaveAfterRestart"] = page.evaluate(snapshot_js)
        result["oldSaveMatches"] = all(
            result["oldSaveAfterRestart"][k] == old_before[k] for k in keys
        )
        page.screenshot(path=str(out / "04-after-restart.png"), full_page=True)
        result["final"] = page.evaluate(snapshot_js)
        context.close()
        browser.close()
except Exception as exc:
    result["exception"] = f"{type(exc).__name__}: {exc}"
finally:
    result["events"] = events
    result["unexpectedHttp"] = [
        event
        for event in events
        if event["type"] in ("http", "requestfailed")
        and urlparse(event["url"]).path
        not in ["/style.css", "/usettings.js", "/img/misc/banner.png"]
    ]
    result["runtimeErrors"] = [
        event
        for event in events
        if event["type"] == "pageerror"
        or (
            event["type"] == "error"
            and not event["text"].startswith("Failed to load resource:")
        )
    ]
    checks = result["checks"]
    controls = checks.get("functional-controls", {})
    result["passed"] = bool(
        not result.get("exception")
        and result.get("selfSaveMatches")
        and result.get("oldSaveMatches")
        and all(
            controls.get(k, {}).get("passed")
            for k in ("attribute", "item", "time", "hair")
        )
        and all(
            checks.get(k, {}).get("passed")
            for k in (
                "doli-native-settings",
                "hair-ui",
                "clothing-pet",
                "doli-history",
            )
        )
        and not result.get("final", {}).get("errors")
        and not result.get("final", {}).get("imageErrors")
        and all(
            not row["errors"] and row["pixels"] > 0
            for row in checks.get("face-matrix", [])
        )
        and all(
            not row["errors"] for row in checks.get("expressions", [])
        )
        and not result["unexpectedHttp"]
        and not result["runtimeErrors"]
    )
    write()

print(
    json.dumps(
        {
            "variant": args.variant,
            "exception": result.get("exception"),
            "checks": {
                key: value.get("passed")
                for key, value in result["checks"].items()
                if isinstance(value, dict)
            },
            "selfSaveMatches": result.get("selfSaveMatches"),
            "oldSaveMatches": result.get("oldSaveMatches"),
            "finalImageErrors": result.get("final", {}).get("imageErrors"),
            "unexpectedHttp": len(result["unexpectedHttp"]),
            "runtimeErrors": len(result["runtimeErrors"]),
            "passed": result["passed"],
        },
        ensure_ascii=False,
    )
)
sys.exit(0 if result["passed"] else 1)
