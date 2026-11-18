"""Interactive local acceptance session for a built game; isolated browser data.

Commands are JSON lines on stdin: eval (script/arg), screenshot (path), reload,
or close. Evidence includes all console/page errors and failed asset requests.
This developer harness never opens a player's browser profile.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from tools import browser_smoke_test as smoke


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    events = []
    report = smoke.BrowserSmokeReport(str(args.target), "candidate-functional", True)
    # Accept an already extracted candidate to avoid repeated 160 MB expansion.
    root, html = smoke._resolve_target(args.target, args.output / "extracted")
    with smoke._serve_directory(root) as server, sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda e: events.append({"type": "pageerror", "text": str(e)}))
        page.on("console", lambda m: events.append({"type": m.type, "text": m.text}) if m.type in ("error", "warning") else None)
        page.on("requestfailed", lambda r: events.append({"type": "requestfailed", "url": r.url, "failure": r.failure}))
        page.on("response", lambda r: events.append({"type": "http", "url": r.url, "status": r.status}) if r.status >= 400 else None)
        try:
            page.goto(smoke._relative_url(server, root, html), wait_until="domcontentloaded", timeout=180000)
            page.wait_for_function("() => !!window.SugarCube?.State", timeout=180000)
            startup = smoke._run_startup_interactions(report, page, smoke.PROFILES["ucb-cheat-extended-maplebirch"])
            page.wait_for_timeout(1500)
            (args.output / "startup.json").write_text(json.dumps(startup, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"ready": startup.get("success"), "passage": page.evaluate("SugarCube.State.passage")}), flush=True)
            for line in sys.stdin:
                try:
                    command = json.loads(line)
                    op = command["op"]
                    if op == "close":
                        break
                    if op == "eval":
                        value = page.evaluate(command["script"], command.get("arg"))
                    elif op == "eval_file":
                        value = page.evaluate(Path(command["path"]).read_text(encoding="utf-8"), command.get("arg"))
                    elif op == "screenshot":
                        page.screenshot(path=command["path"], full_page=True)
                        value = command["path"]
                    elif op == "reload":
                        page.reload(wait_until="domcontentloaded", timeout=180000)
                        value = smoke._run_startup_interactions(report, page, smoke.PROFILES["ucb-cheat-extended-maplebirch"])["success"]
                    else:
                        raise ValueError(f"Unknown operation: {op}")
                    page.wait_for_timeout(command.get("settle_ms", 250))
                    result = {"ok": True, "result": value}
                    # A diagnostic expression can return a cyclic browser object.
                    # Report that command as failed without losing the session.
                    json.dumps(result)
                except Exception as exc:
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                with (args.output / "commands.jsonl").open("a", encoding="utf-8") as log:
                    log.write(json.dumps({"command": command, "result": result}, ensure_ascii=False) + "\n")
                (args.output / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(result, ensure_ascii=False), flush=True)
        finally:
            (args.output / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
