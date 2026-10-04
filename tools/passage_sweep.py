#!/usr/bin/env python3
"""DOL-X passage sweep engine (engine A: local headless Chromium on the built HTML).

Why this exists
---------------
The 2026-06 feasibility memo judged full-game automated testing "6-9 months and
not worth it" because it implicitly assumed hundreds of hand-written end-to-end
cases. The 2026-10-04 grill-me session replaced that with a bounded, machine
driven target:

    1. acceptance = every passage of the REAL artifact is force-rendered, plus a
                    small set of hand-asserted functional flows;
    2. carrier    = our own built HTML, headless Chromium, runtime injection only
                    (nothing enters the build config, so nothing can leak into a
                    release artifact);
    3. fixtures   = hybrid: a bootstrap snapshot from a genuinely initialized
                    game + the upstream objectified-globals baseline + per-passage
                    tolerance. A passage that cannot be entered is
                    ``fixture_insufficient``, NOT a bug;
    4. verdicts   = layered (hard / soft / fixture) + baseline diff, so once a
                    baseline is sealed only NEW breakage is reported;
    5. done       = ``python tools/passage_sweep.py <target> --out DIR`` runs the
                    whole sweep and writes a machine + human report.

It intentionally does not touch lyra/, config/, or any build input.
"""

from __future__ import annotations

import argparse
import atexit
import collections
import hashlib
import html as html_mod
import json
import random
import re
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# --------------------------------------------------------------------------- #
# Passage extraction
# --------------------------------------------------------------------------- #

PASSAGE_PATTERN = re.compile(
    r'<tw-passagedata\b[^>]*name="([^"]*)"[^>]*>(.*?)</tw-passagedata>',
    re.DOTALL,
)


@dataclass
class Passage:
    name: str
    body: str


def _html_payload(target: Path) -> tuple[str, Path]:
    """Return (html_text, temp_dir). Unwraps a .zip to a temp dir if needed."""
    if target.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="dolx-sweep-"))
        atexit.register(shutil.rmtree, tmp, ignore_errors=True)
        with zipfile.ZipFile(target) as zf:
            zf.extractall(tmp)
        candidates = sorted(tmp.rglob("*.html"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            raise SystemExit(f"no .html inside {target}")
        path = candidates[0]
    elif target.suffix.lower() in (".html", ".htm"):
        path = target
    else:
        raise SystemExit(f"unsupported target: {target}")
    return path.read_text(encoding="utf-8", errors="replace"), path.parent


def extract_passages(target: Path) -> tuple[list[Passage], Path]:
    raw, _ = _html_payload(target)
    seen: dict[str, str] = {}
    for name, body in PASSAGE_PATTERN.findall(raw):
        # SugarCube stores the passage body with HTML entities escaped once.
        seen.setdefault(html_mod.unescape(name), html_mod.unescape(body))
    passages = [Passage(name=n, body=b) for n, b in seen.items()]
    return passages, target


def resolve_html_path(target: Path) -> Path:
    """Return a concrete .html path Playwright can load via file://."""
    target = target.resolve()
    if target.suffix.lower() in (".html", ".htm"):
        return target
    _raw, tmp = _html_payload(target)
    candidates = sorted(tmp.rglob("*.html"), key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0].resolve()


# --------------------------------------------------------------------------- #
# Fixture ladder / overlay patches / only-file targeting
# --------------------------------------------------------------------------- #


def parse_only_file(path: Path) -> list[str]:
    """Read a newline-separated passage-name list (blank lines and # comments ignored)."""
    names: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def filter_passages(passages: list[Passage], names: list[str]) -> tuple[list[Passage], list[str]]:
    """Keep only passages whose name is in ``names`` (document order preserved).

    Returns ``(kept, missing)`` where ``missing`` lists requested names that do
    not exist in the build, so drift surfaces instead of silently shrinking.
    """
    wanted = set(names)
    kept = [p for p in passages if p.name in wanted]
    seen = {p.name for p in kept}
    missing = [n for n in names if n not in seen]
    return kept, missing


def load_fixture_file(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a fixture JSON (fixture_ladder ``capture`` format or a flat dict).

    Returns ``(variables, meta)``; meta records source path, sha256, format and
    size so every report can be traced back to an exact fixture revision.
    """
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"fixture {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"fixture {path} must be a JSON object")
    if isinstance(data.get("variables"), dict):
        variables = data["variables"]
        source_format = "capture"
    else:
        variables = data
        source_format = "flat"
    if not variables:
        raise SystemExit(f"fixture {path} carries zero variables")
    meta = {
        "source": str(path),
        "sha256": digest,
        "format": source_format,
        "keys": len(variables),
        "bytes": len(raw),
    }
    return variables, meta


def apply_fixture_patch(
    variables: dict[str, Any], patch: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Apply a ``{"dotted.path": value}`` overlay to a deep copy of ``variables``.

    Numeric segments index lists (e.g. ``worn.upper.0.name``). Missing containers
    are created; descending into a scalar raises SystemExit (fail-closed) so a
    mistyped patch can never be silently ignored.
    """
    out = json.loads(json.dumps(variables))
    applied: list[str] = []
    for dotted, value in patch.items():
        if not isinstance(dotted, str) or not dotted:
            raise SystemExit(f"fixture patch key must be a non-empty string: {dotted!r}")
        parts = dotted.split(".")
        node: Any = out
        for i, part in enumerate(parts[:-1]):
            nxt = parts[i + 1]
            if isinstance(node, dict):
                if part not in node or node[part] is None:
                    node[part] = [] if nxt.isdigit() else {}
                node = node[part]
            elif isinstance(node, list):
                if not part.isdigit():
                    raise SystemExit(
                        f"fixture patch {dotted!r}: numeric list index expected at {part!r}"
                    )
                idx = int(part)
                if idx >= len(node):
                    node.extend([None] * (idx - len(node) + 1))
                if node[idx] is None:
                    node[idx] = [] if nxt.isdigit() else {}
                node = node[idx]
            else:
                raise SystemExit(
                    f"fixture patch {dotted!r}: cannot descend into "
                    f"{type(node).__name__} at {part!r}"
                )
        last = parts[-1]
        if isinstance(node, dict):
            node[last] = value
        elif isinstance(node, list) and last.isdigit():
            idx = int(last)
            if idx >= len(node):
                node.extend([None] * (idx - len(node) + 1))
            node[idx] = value
        else:
            raise SystemExit(f"fixture patch {dotted!r}: container mismatch at final segment")
        applied.append(dotted)
    return out, applied


# --------------------------------------------------------------------------- #
# Runtime harness (injected before any page script runs)
# --------------------------------------------------------------------------- #

INIT_HARNESS = r"""
(() => {
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  S.errors = S.errors || [];
  S.done = false;
  S.renderSeq = 0;
  S.hooked = false;
  S.lastPassage = null;
  S.reset = function () {
    S.errors.length = 0;
    S.done = false;
    S.renderSeq = 0;
  };
  const push = (kind, message, source, stack) => {
    const item = { kind: kind, message: String(message).slice(0, 1000), source: String(source || "").slice(0, 300) };
    if (stack) item.stack = String(stack).slice(0, 2500);
    S.errors.push(item);
  };
  window.addEventListener("error", (e) => push("error", e.message || e.error || "error", e.filename, e.error && e.error.stack));
  window.addEventListener("unhandledrejection", (e) => {
    let m = e.reason;
    try { m = m && (m.message || m.toString()); } catch (_) { m = "unhandledrejection"; }
    push("unhandledrejection", m, "", e.reason && e.reason.stack);
  });
  const origError = console.error.bind(console);
  console.error = function (...args) {
    try { push("console.error", args.map(a => (a && a.message) ? a.message : String(a)).join(" "), "", args[0] && args[0].stack); } catch (_) {}
    return origError(...args);
  };
})();
"""


def install_passage_hook() -> str:
    """Register the :passagedisplay hook once SugarCube/jQuery exist."""
    return r"""
(() => {
  const S = window.__DOLX__;
  if (!S || S.hooked) return false;
  if (!window.jQuery || !window.SugarCube) return false;
  const $ = window.jQuery;
  $(document).on(":passagedisplay", () => {
    S.renderSeq += 1;
    S.done = true;
    try { S.lastPassage = window.SugarCube.State.passage; } catch (_) {}
  });
  S.hooked = true;
  return true;
})();
"""


# Serialization note: ``State.variables`` cannot be returned to Python directly.
# Playwright/CDP serialize return values with its own protocol and chokes on the
# game's deep state (observed: "value.o[638].v.o[4].v.d: expected string, got
# object"). So the snapshot runs entirely in-page and returns a JSON *string*;
# Python parses it, and the restore path sends a JSON string back in.
FIXTURE_SNAPSHOT = r"""
() => {
  const MAX_DEPTH = 10, MAX_KEYS = 20000, MAX_ITEMS = 20000, MAX_STRING = 200000;
  const meta = {
    dates: 0, sets: 0, maps: 0, regexps: 0, functions: 0, symbols: 0, bigints: 0,
    nonFinite: 0, circular: 0, depthClipped: 0, keyClipped: 0, itemClipped: 0,
    stringClipped: 0, unserializable: 0,
  };
  const walk = (v, depth, ancestors) => {
    try {
      if (v === null || v === undefined) return null;
      const t = typeof v;
      if (t === "string") {
        if (v.length > MAX_STRING) { meta.stringClipped += 1; return v.slice(0, MAX_STRING); }
        return v;
      }
      if (t === "number") { if (!Number.isFinite(v)) { meta.nonFinite += 1; return null; } return v; }
      if (t === "boolean") return v;
      if (t === "bigint") { meta.bigints += 1; return String(v); }
      if (t === "function") { meta.functions += 1; return "[function]"; }
      if (t === "symbol") { meta.symbols += 1; return String(v); }
      for (let i = 0; i < ancestors.length; i++) {
        if (ancestors[i] === v) { meta.circular += 1; return "[circular]"; }
      }
      if (v instanceof Date) { meta.dates += 1; return { __dolx_type__: "Date", iso: isNaN(v.getTime()) ? null : v.toISOString() }; }
      if (v instanceof RegExp) { meta.regexps += 1; return { __dolx_type__: "RegExp", source: String(v.source), flags: String(v.flags) }; }
      if (v instanceof Set) {
        meta.sets += 1;
        ancestors.push(v);
        const out = { __dolx_type__: "Set", values: Array.from(v).slice(0, MAX_ITEMS).map((x) => walk(x, depth + 1, ancestors)) };
        ancestors.pop();
        return out;
      }
      if (v instanceof Map) {
        meta.maps += 1;
        ancestors.push(v);
        const out = { __dolx_type__: "Map", entries: Array.from(v.entries()).slice(0, MAX_ITEMS).map((kv) => [walk(kv[0], depth + 1, ancestors), walk(kv[1], depth + 1, ancestors)]) };
        ancestors.pop();
        return out;
      }
      if (depth >= MAX_DEPTH) { meta.depthClipped += 1; return "[depth]"; }
      ancestors.push(v);
      let out;
      if (Array.isArray(v)) {
        const n = Math.min(v.length, MAX_ITEMS);
        out = new Array(n);
        for (let i = 0; i < n; i++) out[i] = walk(v[i], depth + 1, ancestors);
        if (v.length > MAX_ITEMS) { meta.itemClipped += 1; out.push("[+" + (v.length - MAX_ITEMS) + " more]"); }
      } else {
        out = {};
        const keys = Object.keys(v);
        const n = Math.min(keys.length, MAX_KEYS);
        for (let i = 0; i < n; i++) out[keys[i]] = walk(v[keys[i]], depth + 1, ancestors);
        if (keys.length > MAX_KEYS) { meta.keyClipped += 1; out.__dolx_clipped_keys__ = keys.length - MAX_KEYS; }
      }
      ancestors.pop();
      return out;
    } catch (e) {
      meta.unserializable += 1;
      return "[unserializable]";
    }
  };
  try {
    const plain = walk(window.SugarCube.State.variables, 0, []);
    return JSON.stringify({ ok: true, meta: meta, variables: plain });
  } catch (e) {
    return JSON.stringify({ ok: false, meta: meta, error: String(e && e.message ? e.message : e), variables: {} });
  }
}
"""


LOAD_FIXTURE = r"""
(payloadStr) => {
  try {
    const parsed = JSON.parse(payloadStr);
    const vars = (parsed && typeof parsed === "object" && parsed.variables && typeof parsed.variables === "object")
      ? parsed.variables
      : parsed;
    const S = (window.__DOLX__ = window.__DOLX__ || {});
    S.fixtureVars = (vars && typeof vars === "object") ? vars : {};
    return { ok: true, keys: Object.keys(S.fixtureVars).length, bytes: payloadStr.length };
  } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
}
"""


# SugarCube detail that matters: ``State.variables`` is the getter
# ``() => _active.variables`` where ``_active`` is a *clone* of the active
# history entry (momentActivate does ``_active = clone(moment)``). Writing the
# history entry alone therefore does NOT change what the game reads. The
# restore must assign ``State.active.variables`` (and keep the entry in sync).
RESTORE_FIXTURE = r"""
() => {
  const S = window.__DOLX__;
  const SC = window.SugarCube;
  if (!S || !S.fixtureVars) return { ok: false, error: "fixture not loaded" };
  if (!SC || !SC.State || !SC.State.active) return { ok: false, error: "SugarCube.State.active missing" };
  const revive = (v) => {
    if (Array.isArray(v)) return v.map(revive);
    if (v && typeof v === "object") {
      if (v.__dolx_type__ === "Date") return v.iso ? new Date(v.iso) : new Date(NaN);
      if (v.__dolx_type__ === "RegExp") { try { return new RegExp(v.source, v.flags); } catch (e) { return new RegExp("(?:)"); } }
      if (v.__dolx_type__ === "Set") return new Set((v.values || []).map(revive));
      if (v.__dolx_type__ === "Map") return new Map((v.entries || []).map((kv) => [revive(kv[0]), revive(kv[1])]));
      const out = {};
      for (const k of Object.keys(v)) out[k] = revive(v[k]);
      return out;
    }
    return v;
  };
  let vars;
  try {
    vars = structuredClone(S.fixtureVars);
  } catch (e) {
    try { vars = JSON.parse(JSON.stringify(S.fixtureVars)); } catch (e2) { return { ok: false, error: "clone: " + String(e2) }; }
  }
  try { vars = revive(vars); } catch (e) { return { ok: false, error: "revive: " + String(e) }; }
  try {
    const State = SC.State;
    State.active.variables = vars;
    let via = "active";
    try {
      const entry = State.history && State.history[State.activeIndex];
      if (entry) { entry.variables = vars; via = "active+history"; }
    } catch (e) {}
    return { ok: true, via: via };
  } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
}
"""


PLAY_PASSAGE = r"""
(payload) => {
  const S = window.__DOLX__;
  S.reset();
  try {
    window.SugarCube.Engine.play(payload.name);
  } catch (e) {
    S.errors.push({
      kind: "engine.play.throw",
      message: String(e && e.message ? e.message : e),
      source: "Engine.play",
      stack: String(e && e.stack ? e.stack : "").slice(0, 2500),
    });
    S.done = true;
  }
  return true;
}
"""


PROBE = r"""
() => {
  const S = window.__DOLX__ || {};
  let passage = null;
  try { passage = window.SugarCube.State.passage; } catch (_) {}
  // DoL does not render into `#passage`: the live DOM uses `.passage[data-passage]`
  // / `#passage-content` / `#passages .passage`. Probe the union, keep the first hit.
  const candidates = ["#passage", "#passage-content", "#passages .passage", ".passage[data-passage]", "[data-passage]"];
  let node = null, matched = null;
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el) { node = el; matched = sel; break; }
  }
  const text = node ? (node.innerText || node.textContent || "") : "";
  const links = node ? node.querySelectorAll("a, .link-internal, .macro-link").length : 0;
  const children = node ? node.children.length : 0;
  return {
    passage: passage,
    lastPassage: S.lastPassage,
    done: !!S.done,
    renderSeq: S.renderSeq || 0,
    errors: (S.errors || []).slice(),
    textLen: text.trim().length,
    linkCount: links,
    childCount: children,
    hasPassageNode: !!node,
    passageSelector: matched,
    title: document.title
  };
}
"""


# --------------------------------------------------------------------------- #
# Startup gate handling
#
# The gate scripts live in tools/browser_smoke_test.py where they were already
# proven against this build (consent checkbox + labelled controls + modal
# dismissal + the modList.json shim on the local server). Reusing them here
# keeps the two tools from drifting apart.
# --------------------------------------------------------------------------- #

STARTUP_PASSAGES = {"start", "start2", "loading"}


def _ready_js() -> str:
    return (
        "(() => { try { return !!(window.SugarCube && SugarCube.State && "
        "SugarCube.Story && SugarCube.Engine); } catch (e) { return false; } })()"
    )


def _bst() -> Any:
    """Import the sibling smoke-test module (repo-root sys.path is set above)."""
    from tools import browser_smoke_test

    return browser_smoke_test


def _reach_gameplay(page: Any, *, steps: int = 60) -> dict[str, Any]:
    """Click through the age/consent gates until a non-startup passage renders."""
    bst = _bst()
    options = {
        "password": None,
        "modalSelectors": list(bst.MODAL_BLOCKER_SELECTORS),
        "confirmLabels": list(bst.STARTUP_CONFIRM_LABELS),
        "consentLabels": list(bst.STARTUP_CONSENT_LABELS),
    }
    info: dict[str, Any] = {"steps": 0, "passage": None, "actions": []}
    for _ in range(steps):
        try:
            state = page.evaluate(bst._game_ready_script())
        except Exception:
            state = {}
        passage = state.get("passage") if isinstance(state, dict) else None
        info["passage"] = passage
        if passage and str(passage).lower() not in STARTUP_PASSAGES:
            return info
        try:
            action = page.evaluate(bst._startup_interaction_script(), options)
        except Exception as exc:  # noqa: BLE001
            action = {"action": "error", "error": str(exc)[:200]}
        if isinstance(action, dict):
            info["actions"].append(
                {
                    "action": action.get("action"),
                    "clicked": action.get("clicked"),
                    "text": action.get("text") or action.get("label"),
                }
            )
            if len(info["actions"]) > 20:
                del info["actions"][:10]
        page.wait_for_timeout(900)
        info["steps"] += 1
    return info


# --------------------------------------------------------------------------- #
# Sweep
# --------------------------------------------------------------------------- #


@dataclass
class PassageResult:
    name: str
    verdict: str
    detail: str = ""
    errors: list[dict[str, Any]] = field(default_factory=list)
    text_len: int = 0
    link_count: int = 0
    child_count: int = 0
    landed: str | None = None
    elapsed_ms: int = 0


HARD_ERROR_KINDS = {"error", "unhandledrejection", "engine.play.throw"}
FIXTURE_MARKERS = (
    "is not defined",
    "undefined is not a function",
    "cannot read propert",
    "cannot read properties",
    # A debug row may *write* into state the fresh fixture does not have yet
    # (e.g. ``<<set $beast.type to ...>>`` -> "Cannot set properties of
    # undefined"); same fixture-boundary family as the read case above.
    "cannot set propert",
    "cannot set properties",
    "null is not an object",
)


def classify(probe: dict[str, Any], landed_ok: bool, timed_out: bool = False) -> tuple[str, str]:
    errors = probe.get("errors") or []
    hard = [e for e in errors if e.get("kind") in HARD_ERROR_KINDS]
    if hard:
        joined = " | ".join(str(e.get("message", "")) for e in hard)
        low = joined.lower()
        if any(m in low for m in FIXTURE_MARKERS):
            return "fixture_insufficient", joined[:400]
        return "hard_fail", joined[:400]
    if not probe.get("hasPassageNode"):
        return "hard_fail", "no #passage node after render"
    if timed_out and not probe.get("done"):
        return "soft_fail", "did not finish rendering within the per-passage timeout"
    if not probe.get("done"):
        return "soft_fail", "the :passagedisplay hook never fired"
    if probe.get("textLen", 0) == 0 and probe.get("childCount", 0) == 0:
        return "soft_fail", "passage rendered empty"
    return "ok", ""


def _launch_browser(pw: Any, headless: bool) -> Any:
    """Launch a Chromium: prefer the Playwright bundle, fall back to real Chrome/Edge.

    The machine sets PLAYWRIGHT_BROWSERS_PATH to a tree that may not carry the
    exact bundled revision, so a locally installed Chrome is the reliable path.
    """
    errors: list[str] = []
    for kwargs in (
        {},
        {"channel": "chrome"},
        {"channel": "msedge"},
    ):
        try:
            return pw.chromium.launch(headless=headless, **kwargs)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{kwargs or 'bundled'}: {str(exc)[:160]}")
    raise SystemExit("no usable Chromium found:\n  " + "\n  ".join(errors))


def sweep(
    html_path: Path,
    passages: list[Passage],
    *,
    limit: int | None,
    sample: int | None,
    seed: int,
    per_passage_timeout_ms: int,
    headless: bool,
    bootstrap_settle_ms: int,
    fixture_vars: dict[str, Any] | None = None,
    fixture_meta: dict[str, Any] | None = None,
    context: str = "default",
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    bst = _bst()

    selected = passages
    if sample is not None and sample < len(selected):
        rng = random.Random(seed)
        selected = rng.sample(selected, sample)
    if limit is not None:
        selected = selected[:limit]

    report: dict[str, Any] = {
        "target": str(html_path),
        "total_passages": len(passages),
        "swept": len(selected),
        "sample": sample,
        "seed": seed,
        "context": context,
        "fixture": fixture_meta,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": [],
        "bootstrap": {},
        "fixture_bytes": 0,
        "fatal_error": None,
    }

    serve_dir = html_path.parent
    with bst._serve_directory(serve_dir) as server, sync_playwright() as pw:
        url = bst._relative_url(server, serve_dir, html_path)
        browser = _launch_browser(pw, headless)
        context = browser.new_context()
        context.add_init_script(INIT_HARNESS)
        page = context.new_page()
        console: list[str] = []

        def _push_console(line: str) -> None:
            console.append(line[:400])
            if len(console) > 4000:
                del console[:2000]

        page.on("console", lambda m: _push_console(f"{m.type}:{m.text[:300]}"))
        page.on("pageerror", lambda e: _push_console(f"pageerror:{str(e)[:300]}"))
        page.set_default_timeout(per_passage_timeout_ms + 5000)

        page.goto(url, wait_until="load", timeout=180_000)
        page.wait_for_function(_ready_js(), timeout=180_000)

        # Runtime-only overrides: no autosave side effects from a synthetic
        # fixture, and no outgoing-passage transition nodes lingering in the DOM.
        report["runtime_overrides"] = page.evaluate(
            "(() => { try { const C = window.SugarCube.Config;"
            " C.saves.autosave = false; C.passages.transitionOut = undefined;"
            " return { autosave: C.saves.autosave, transitionOut: C.passages.transitionOut }; }"
            " catch (e) { return { error: String(e) }; } })()"
        )

        # Bootstrap: pass the startup gates, then snapshot a genuinely initialized game.
        boot = _reach_gameplay(page, steps=60)
        if not boot.get("passage") or str(boot["passage"]).lower() in STARTUP_PASSAGES:
            raise SystemExit(
                "bootstrap did not reach gameplay; last passage="
                f"{boot.get('passage')!r} after {boot.get('steps')} steps; "
                f"last actions={boot.get('actions')[-4:]}"
            )
        page.wait_for_timeout(bootstrap_settle_ms)
        page.evaluate("(() => { const S = window.__DOLX__; if (S) S.hooked = false; return true; })()")
        hooked = False
        for _ in range(40):
            if page.evaluate(install_passage_hook()):
                hooked = True
                break
            page.wait_for_timeout(250)
        if not hooked:
            raise SystemExit(
                "could not install the :passagedisplay hook; aborting before "
                "every passage would burn the full timeout"
            )

        if fixture_vars is not None:
            # Fixture-file path (tools/fixture_ladder.py capture): reuse the frozen
            # snapshot instead of re-snapshotting the freshly bootstrapped game.
            fixture = fixture_vars
            fixture_json = json.dumps(fixture, ensure_ascii=True, separators=(",", ":"))
            report["bootstrap"] = {
                "source": "fixture-file",
                "steps": boot["steps"],
                "passage": boot["passage"],
                "fixture": fixture_meta,
                "fixture_vars": len(fixture),
            }
            report["fixture_bytes"] = len(fixture_json)
            load_ok = page.evaluate(LOAD_FIXTURE, fixture_json)
            report["bootstrap"]["load_fixture"] = load_ok
            if not load_ok.get("ok"):
                raise SystemExit(f"fixture load failed: {load_ok}")
            first_restore = page.evaluate(RESTORE_FIXTURE)
            report["bootstrap"]["first_restore"] = first_restore
            if not (isinstance(first_restore, dict) and first_restore.get("ok")):
                raise SystemExit(f"fixture restore failed (fail-closed): {first_restore}")
        else:
            snap = json.loads(page.evaluate(FIXTURE_SNAPSHOT))
            fixture = snap.get("variables") if isinstance(snap.get("variables"), dict) else {}
            fixture_json = json.dumps(fixture, ensure_ascii=True, separators=(",", ":"))
            report["bootstrap"] = {
                "source": "bootstrap-snapshot",
                "steps": boot["steps"],
                "passage": boot["passage"],
                "actions": boot.get("actions"),
                "snapshot_ok": snap.get("ok"),
                "snapshot_meta": snap.get("meta"),
                "fixture_vars": len(fixture),
            }
            report["fixture_bytes"] = len(fixture_json)
            load_ok = page.evaluate(LOAD_FIXTURE, fixture_json)
            report["bootstrap"]["load_fixture"] = load_ok
            if not load_ok.get("ok"):
                raise SystemExit(f"fixture load failed: {load_ok}")
            report["bootstrap"]["first_restore"] = page.evaluate(RESTORE_FIXTURE)

        try:
            for idx, p in enumerate(selected, 1):
                t0 = time.time()
                page.evaluate(RESTORE_FIXTURE)
                timed_out = False
                try:
                    page.evaluate(PLAY_PASSAGE, {"name": p.name})
                    try:
                        page.wait_for_function(
                            "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                            timeout=per_passage_timeout_ms,
                        )
                    except Exception:
                        timed_out = True
                except Exception as exc:  # noqa: BLE001
                    page.evaluate(
                        "(() => { const S = window.__DOLX__; if (S) { S.done = true; "
                        "S.errors.push({kind:'error', message:'sweep-driver: ' + "
                        + json.dumps(str(exc)[:200])
                        + ", source:'driver'}); } return true; })()"
                    )
                probe = page.evaluate(PROBE)
                landed = probe.get("passage")
                verdict, detail = classify(probe, landed is not None, timed_out)
                report["results"].append(
                    asdict(
                        PassageResult(
                            name=p.name,
                            verdict=verdict,
                            detail=detail,
                            errors=probe.get("errors") or [],
                            text_len=int(probe.get("textLen") or 0),
                            link_count=int(probe.get("linkCount") or 0),
                            child_count=int(probe.get("childCount") or 0),
                            landed=landed,
                            elapsed_ms=int((time.time() - t0) * 1000),
                        )
                    )
                )
                if idx % 25 == 0:
                    print(f"  ... {idx}/{len(selected)}", flush=True)
        except Exception as exc:  # noqa: BLE001 - keep the partial report
            report["fatal_error"] = f"{type(exc).__name__}: {exc}"[:500]
            print(
                f"[sweep] fatal after {len(report['results'])} passages: {report['fatal_error']}",
                flush=True,
            )

        report["console_tail"] = console[-500:]
        browser.close()

    counts = collections.Counter(r["verdict"] for r in report["results"])
    report["verdict_counts"] = dict(counts)
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return report


# --------------------------------------------------------------------------- #
# Baseline diff + reporting
# --------------------------------------------------------------------------- #


VERDICT_SEVERITY = {"ok": 0, "fixture_insufficient": 1, "soft_fail": 2, "hard_fail": 3}


def diff_against_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    old = {r["name"]: r["verdict"] for r in baseline.get("results", [])}
    new = {r["name"]: r["verdict"] for r in report.get("results", [])}
    regressions, fixed, changed, new_passages = [], [], [], []
    for name, verdict in new.items():
        prev = old.get(name)
        if prev is None:
            new_passages.append({"name": name, "verdict": verdict})
            continue
        if prev == verdict:
            continue
        if prev == "ok":
            regressions.append({"name": name, "was": prev, "now": verdict})
        elif verdict == "ok":
            fixed.append({"name": name, "was": prev, "now": verdict})
        elif VERDICT_SEVERITY.get(verdict, 2) > VERDICT_SEVERITY.get(prev, 2):
            # e.g. fixture_insufficient -> hard_fail: the passage no longer fails
            # only because of missing preconditions, so it must surface.
            regressions.append({"name": name, "was": prev, "now": verdict})
        else:
            changed.append({"name": name, "was": prev, "now": verdict})
    return {
        "regressions": regressions,
        "fixed": fixed,
        "changed": changed,
        "unseen_in_baseline": new_passages,
    }


def _fixture_summary(fixture: dict[str, Any] | None) -> str:
    """Human-readable one-liner for the fixture section of the markdown report."""
    if not fixture:
        return "`bootstrap` (snapshot taken in this run)"
    source = str(fixture.get("source", "?"))
    digest = str(fixture.get("sha256", ""))[:12]
    keys = fixture.get("keys", "?")
    patch = fixture.get("patch")
    extra = f", patch={patch.get('source')} ({len(patch.get('applied', []))} paths)" if patch else ""
    return f"`{source}` keys={keys} sha256={digest}{extra}"


def write_report(report: dict[str, Any], out_dir: Path, diff: dict[str, Any] | None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "passage-sweep.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = report.get("verdict_counts", {})
    lines = [
        "# DOL-X passage sweep report",
        "",
        f"- target: `{report['target']}`",
        f"- swept: **{report['swept']}** of {report['total_passages']} passages",
        f"- context: `{report.get('context', 'default')}`",
        f"- fixture: {_fixture_summary(report.get('fixture'))}",
        f"- bootstrap: {report.get('bootstrap')}",
        f"- fixture bytes: {report.get('fixture_bytes')}",
        "",
        "## verdicts",
        "",
        "| verdict | count |",
        "| --- | --- |",
    ]
    for key in ("ok", "soft_fail", "hard_fail", "fixture_insufficient"):
        lines.append(f"| {key} | {counts.get(key, 0)} |")

    for kind in ("hard_fail", "soft_fail"):
        bad = [r for r in report["results"] if r["verdict"] == kind]
        if not bad:
            continue
        lines += ["", f"## {kind} ({len(bad)})", ""]
        for r in bad[:60]:
            lines.append(f"- `{r['name']}` — {r['detail'][:200]}")
        if len(bad) > 60:
            lines.append(f"- ... and {len(bad) - 60} more")

    if diff is not None:
        lines += ["", "## baseline diff", ""]
        lines.append(f"- regressions (verdict got worse): **{len(diff['regressions'])}**")
        lines.append(f"- fixed: {len(diff['fixed'])}")
        lines.append(f"- changed (non-ok verdict moved): {len(diff.get('changed', []))}")
        lines.append(f"- unseen in baseline: {len(diff['unseen_in_baseline'])}")
        for r in diff["regressions"][:40]:
            lines.append(f"  - `{r['name']}`: {r['was']} -> {r['now']}")
        for r in diff.get("changed", [])[:20]:
            lines.append(f"  - `{r['name']}`: {r['was']} -> {r['now']}")

    md_path = out_dir / "passage-sweep.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DOL-X passage sweep (engine A)")
    p.add_argument("target", type=Path, help="built .html or .zip to sweep")
    p.add_argument("--out", type=Path, default=Path(".local/sweep/out"))
    p.add_argument("--limit", type=int, default=None, help="only sweep the first N passages")
    p.add_argument("--sample", type=int, default=None, help="random sample of N passages")
    p.add_argument("--seed", type=int, default=20261004)
    p.add_argument("--timeout-ms", type=int, default=8000, help="per-passage render timeout")
    p.add_argument("--bootstrap-settle-ms", type=int, default=1500)
    p.add_argument("--headful", action="store_true", help="show the browser window")
    p.add_argument("--baseline", type=Path, default=None, help="sealed baseline json to diff against")
    p.add_argument("--save-baseline", action="store_true", help="write this run's json as the new baseline")
    p.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="fixture json captured by tools/fixture_ladder.py (default: in-run bootstrap snapshot)",
    )
    p.add_argument(
        "--fixture-patch",
        type=Path,
        default=None,
        help='JSON {"dotted.path": value} overlay applied to --fixture before restore',
    )
    p.add_argument(
        "--context",
        type=str,
        default="default",
        help="context label recorded in the report and used in the grouped baseline key",
    )
    p.add_argument(
        "--only-file",
        type=Path,
        default=None,
        help="file with passage names to sweep (one per line, # comments ignored)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    passages, _ = extract_passages(args.target)
    html_path = resolve_html_path(args.target)

    only_meta: dict[str, Any] | None = None
    if args.only_file:
        if not args.only_file.exists():
            raise SystemExit(f"--only-file not found: {args.only_file}")
        names = parse_only_file(args.only_file)
        passages, missing = filter_passages(passages, names)
        only_meta = {
            "source": str(args.only_file),
            "requested": len(names),
            "kept": len(passages),
            "missing": missing,
        }
        if missing:
            print(f"[sweep] WARNING: {len(missing)} requested passage(s) not found: {missing[:8]}")
    print(f"[sweep] target={args.target} passages={len(passages)} html={html_path}")

    fixture_vars: dict[str, Any] | None = None
    fixture_meta: dict[str, Any] | None = None
    if args.fixture_patch and not args.fixture:
        raise SystemExit("--fixture-patch requires --fixture")
    if args.fixture:
        if not args.fixture.exists():
            raise SystemExit(f"fixture not found: {args.fixture}")
        fixture_vars, fixture_meta = load_fixture_file(args.fixture)
        fixture_meta["context"] = args.context
        if args.fixture_patch:
            if not args.fixture_patch.exists():
                raise SystemExit(f"fixture patch not found: {args.fixture_patch}")
            patch_data = json.loads(args.fixture_patch.read_text(encoding="utf-8"))
            if not isinstance(patch_data, dict):
                raise SystemExit("fixture patch must be a JSON object of {dotted.path: value}")
            fixture_vars, applied = apply_fixture_patch(fixture_vars, patch_data)
            fixture_meta["patch"] = {
                "source": str(args.fixture_patch),
                "applied": applied,
            }
            print(f"[sweep] fixture patch applied: {len(applied)} path(s) from {args.fixture_patch}")

    report = sweep(
        html_path,
        passages,
        limit=args.limit,
        sample=args.sample,
        seed=args.seed,
        per_passage_timeout_ms=args.timeout_ms,
        headless=not args.headful,
        bootstrap_settle_ms=args.bootstrap_settle_ms,
        fixture_vars=fixture_vars,
        fixture_meta=fixture_meta,
        context=args.context,
    )
    if only_meta is not None:
        report["only_file"] = only_meta

    diff = None
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        diff = diff_against_baseline(report, baseline)
        report["baseline_diff"] = diff
    md = write_report(report, args.out, diff)

    if args.save_baseline:
        baseline_path = args.out / "passage-sweep-baseline.json"
        baseline_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Grouped copy so baselines are addressable by fixture x context (plan 2026-10-04).
        key = f"{args.fixture.stem if args.fixture else 'bootstrap'}__{args.context}"
        grouped_dir = Path(".local/sweep/baselines")
        grouped_dir.mkdir(parents=True, exist_ok=True)
        grouped_path = grouped_dir / f"{key}.json"
        grouped_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[sweep] baseline sealed -> {baseline_path} ; grouped -> {grouped_path}")

    print(f"[sweep] verdicts={report['verdict_counts']}")
    print(f"[sweep] report -> {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
