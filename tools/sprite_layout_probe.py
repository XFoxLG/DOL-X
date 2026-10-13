#!/usr/bin/env python3
"""Sprite layout probe for DOL-X artifacts (engine A).

Answers "which assets were drawn, and where" - the missing half of the
existing pixel smoke tests, which only counted opaque pixels.

How it works:

  * a ``CanvasRenderingContext2D.drawImage`` recorder is injected before the
    game boots, so every image blit is captured together with its source asset
    and its destination rectangle;
  * before each sample point (desk-pet enable, AU face style switch) the log is
    reset, a redraw is triggered, then the log is dumped and aggregated per
    asset: draw count, last destination rect and a normalized geometry
    (0..1 canvas coordinates);
  * the desk-pet canvas is additionally fingerprinted with an 8x8 alpha grid,
    a bounding box and a centroid, so a whole-layer regression shows up even
    when the same assets are still drawn;
  * network failures (HTTP >= 400 and aborted requests) are recorded with
    asset-request flags, which is the direct evidence for "missing texture";
  * a baseline file can be recorded and later compared: missing sprites, moved
    sprites (beyond the tolerance) and grid drift are reported as
    ``layout_drift``.

Reports only carry asset-relative paths and normalized geometry; no save data,
player text or console dumps beyond the standard tail. The tool never touches
``lyra/``, ``config/`` or any build input - it observes a built artifact.

Usage:
    python tools/sprite_layout_probe.py output/DoL-...-au-f-0915.zip \
        --out .local/sweep/sprite-layout/au-f-0915 --update-baseline
    python tools/sprite_layout_probe.py output/DoL-...-au-f-0915.zip \
        --out .local/sweep/sprite-layout/au-f-0915-repeat \
        --baseline .local/sweep/sprite-layout/au-f-0915/sprite-layout-baseline.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import passage_sweep as ps  # noqa: E402
from tools import sweep_flow_assertions as sfa  # noqa: E402


SCHEMA = "dolx.sprite-layout.v1"
TOOL_NAME = "sprite_layout_probe"
DEFAULT_OUT = Path(".local/sweep/sprite-layout")
GRID_SIZE = 8
DEFAULT_POSITION_TOLERANCE = 0.01
DEFAULT_GRID_TOLERANCE = 0.05
MAX_ASSETS_PER_SAMPLE = 600
MAX_RECTS_PER_ASSET = 6
MAX_NETWORK_RECORDS = 300

# Assets that carry the face/body/skin layers the layout questions are about.
# These survive the per-sample cap even when rarer than background sprites.
KEY_ASSET_PATTERN = re.compile(
    r"(blush|tear|eyes|mouth|face|hair|body|head|tattoo|freckle|scar|pubic|arm|leg)",
    re.IGNORECASE,
)
ASSET_EXTENSION_PATTERN = re.compile(
    r"\.(png|jpe?g|webp|gif|svg|bmp|avif)(\?|#|$)", re.IGNORECASE
)
# AU's inner payload asks for legacy ``blush1`` / ``tear3`` names while the
# canonical assets use ``blush-1`` / ``tears-1``; a 404 with this shape is a
# known naming mismatch the game resolves through its fallback chain.
LEGACY_FACE_NAME_PATTERN = re.compile(r"/(blush|tear|tears)(\d+)\.png$", re.IGNORECASE)

# Animated background layers are redrawn on every frame/sample, so their
# destination moves by design. They are excluded from position drift by
# default and reported separately instead (--strict-layout keeps them).
ANIMATED_LAYER_PATTERNS = (
    re.compile(r"^img/misc/sky/", re.IGNORECASE),
    re.compile(r"^img/misc/weather/", re.IGNORECASE),
)


# --------------------------------------------------------------------------- #
# Runtime probes (injected into the live page)
# --------------------------------------------------------------------------- #

DRAW_IMAGE_RECORDER = r"""
(() => {
  const LOG = (window.__DOLX_SPRITE_LOG = window.__DOLX_SPRITE_LOG || {
    entries: [],
    truncated: false,
    limit: 20000,
  });
  const proto = window.CanvasRenderingContext2D && window.CanvasRenderingContext2D.prototype;
  if (!proto || proto.__dolxSpriteRecorder) return false;
  proto.__dolxSpriteRecorder = true;
  const srcOf = (source) => {
    try {
      if (!source) return "unknown";
      if (typeof source === "string") return String(source).slice(0, 400);
      const url = source.currentSrc || source.src;
      if (url) return String(url).slice(0, 400);
      if (source.tagName === "CANVAS") return "canvas:" + (source.id || "anonymous");
      return String((source.constructor && source.constructor.name) || "source");
    } catch (e) {
      return "unknown";
    }
  };
  const numberOrNull = (value) =>
    typeof value === "number" && isFinite(value) ? Math.round(value * 1000) / 1000 : null;
  const push = (ctx, args) => {
    try {
      if (LOG.entries.length >= LOG.limit) {
        LOG.truncated = true;
        return;
      }
      const canvas = ctx.canvas || {};
      const entry = {
        src: srcOf(args[0]),
        canvas: {
          w: canvas.width || 0,
          h: canvas.height || 0,
          id: canvas.id ? String(canvas.id).slice(0, 80) : null,
        },
      };
      if (args.length === 3) {
        entry.dx = numberOrNull(args[1]);
        entry.dy = numberOrNull(args[2]);
        entry.dw = numberOrNull(args[0] && (args[0].naturalWidth || args[0].width));
        entry.dh = numberOrNull(args[0] && (args[0].naturalHeight || args[0].height));
      } else if (args.length === 5) {
        // drawImage(image, dx, dy, dWidth, dHeight) - the five-argument form
        // scales the whole image into a destination rect (no source crop).
        entry.dx = numberOrNull(args[1]);
        entry.dy = numberOrNull(args[2]);
        entry.dw = numberOrNull(args[3]);
        entry.dh = numberOrNull(args[4]);
      } else if (args.length === 9) {
        entry.sx = numberOrNull(args[1]);
        entry.sy = numberOrNull(args[2]);
        entry.sw = numberOrNull(args[3]);
        entry.sh = numberOrNull(args[4]);
        entry.dx = numberOrNull(args[5]);
        entry.dy = numberOrNull(args[6]);
        entry.dw = numberOrNull(args[7]);
        entry.dh = numberOrNull(args[8]);
      }
      LOG.entries.push(entry);
    } catch (e) {
      /* probing must never break rendering */
    }
  };
  const original = proto.drawImage;
  proto.drawImage = function (...args) {
    push(this, args);
    return original.apply(this, args);
  };
  return true;
})();
"""

SPRITE_LOG_RESET = r"""
() => {
  const LOG = window.__DOLX_SPRITE_LOG;
  if (!LOG) return false;
  LOG.entries.length = 0;
  LOG.truncated = false;
  return true;
}
"""

SPRITE_LOG_DUMP = r"""
() => {
  const LOG = window.__DOLX_SPRITE_LOG;
  if (!LOG) return { available: false };
  const maxRects = 6;
  const bySrc = new Map();
  for (const entry of LOG.entries) {
    const src = entry.src || "unknown";
    let record = bySrc.get(src);
    if (!record) {
      record = { src: src, count: 0, rects: [] };
      bySrc.set(src, record);
    }
    record.count += 1;
    if (entry.dx != null || entry.dw != null || entry.sx != null) {
      if (record.rects.length >= maxRects) record.rects.shift();
      record.rects.push({
        sx: entry.sx, sy: entry.sy, sw: entry.sw, sh: entry.sh,
        dx: entry.dx, dy: entry.dy, dw: entry.dw, dh: entry.dh,
        canvasW: entry.canvas ? entry.canvas.w : null,
        canvasH: entry.canvas ? entry.canvas.h : null,
        canvasId: entry.canvas ? entry.canvas.id : null,
      });
    }
  }
  return {
    available: true,
    total_entries: LOG.entries.length,
    truncated: LOG.truncated,
    distinct_sources: bySrc.size,
    assets: Array.from(bySrc.values()),
  };
}
"""

CANVAS_GRID_PROFILE = r"""
(cfg) => {
  const grid = (cfg && cfg.grid) || 8;
  const selector = (cfg && cfg.selector) || "canvas";
  const out = { selector: selector, present: false, canvas: false };
  const host = document.querySelector(selector);
  if (!host) return out;
  out.present = true;
  const canvas = host.tagName === "CANVAS" ? host : host.querySelector("canvas");
  if (!canvas) return out;
  out.canvas = true;
  const w = canvas.width || 0;
  const h = canvas.height || 0;
  out.w = w;
  out.h = h;
  if (!w || !h) return out;
  let data;
  try {
    data = canvas.getContext("2d").getImageData(0, 0, w, h).data;
  } catch (e) {
    out.read_error = String((e && e.message) || e);
    return out;
  }
  const step = w * h > 4000000 ? 2 : 1;
  let opaque = 0;
  let minX = w, minY = h, maxX = -1, maxY = -1;
  let sumX = 0, sumY = 0;
  const cells = [];
  for (let gy = 0; gy < grid; gy += 1) cells.push(new Array(grid).fill(0));
  for (let y = 0; y < h; y += step) {
    for (let x = 0; x < w; x += step) {
      const alpha = data[(y * w + x) * 4 + 3];
      if (alpha <= 0) continue;
      opaque += 1;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      sumX += x;
      sumY += y;
      const gx = Math.min(grid - 1, Math.floor((x * grid) / w));
      const gyi = Math.min(grid - 1, Math.floor((y * grid) / h));
      cells[gyi][gx] += 1;
    }
  }
  out.opaque = opaque;
  out.sampled_step = step;
  if (opaque > 0) {
    out.bbox = {
      x: minX / w,
      y: minY / h,
      w: (maxX - minX + 1) / w,
      h: (maxY - minY + 1) / h,
    };
    out.centroid = { x: sumX / opaque / w, y: sumY / opaque / h };
    out.grid = cells.map((row) => row.map((value) => value / opaque));
  } else {
    out.grid = cells;
  }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------- #

_URL_PREFIX = re.compile(r"^[a-z][a-z0-9+.-]*://[^/]*", re.IGNORECASE)
_URL_SUFFIX = re.compile(r"[?#].*$")


def relativize_src(src: Any) -> str:
    """Normalize an asset URL to a host-relative, query-less path."""
    value = str(src or "").strip()
    if not value:
        return "unknown"
    value = _URL_PREFIX.sub("", value)
    value = _URL_SUFFIX.sub("", value)
    value = value.lstrip("/")
    return value or "unknown"


def classify_network_failure(record: dict[str, Any]) -> str | None:
    """Return a known-pattern tag for a failed asset request, if any."""
    url = str(record.get("url") or "")
    if LEGACY_FACE_NAME_PATTERN.search(url):
        return "legacy_blush_tear_naming"
    return None


def is_animated_layer(src: str) -> bool:
    """Whether an asset path belongs to a known animated/background layer."""
    value = str(src or "")
    return any(pattern.search(value) for pattern in ANIMATED_LAYER_PATTERNS)


def merge_asset_records(
    records: list[dict[str, Any]],
    *,
    cap: int = MAX_ASSETS_PER_SAMPLE,
) -> list[dict[str, Any]]:
    """Merge JS asset records after URL relativization.

    The same file can be reached through absolute and relative URLs; after
    relativization those collapse into one record. Key assets (face/body/skin
    layers) are kept ahead of the cap so a rare but important layer cannot be
    pushed out by background sprites.
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        src = relativize_src(record.get("src"))
        target = merged.get(src)
        if target is None:
            target = {"src": src, "count": 0, "rects": []}
            merged[src] = target
            order.append(src)
        try:
            target["count"] += int(record.get("count") or 0)
        except (TypeError, ValueError):
            pass
        rects = record.get("rects")
        if isinstance(rects, list):
            for rect in rects:
                if not isinstance(rect, dict):
                    continue
                if len(target["rects"]) >= MAX_RECTS_PER_ASSET:
                    break
                target["rects"].append(rect)
    result = [merged[src] for src in order]
    result.sort(key=lambda item: item["count"], reverse=True)
    key_assets = [item for item in result if KEY_ASSET_PATTERN.search(item["src"])]
    others = [item for item in result if not KEY_ASSET_PATTERN.search(item["src"])]
    ordered = key_assets + others
    return ordered[: max(0, cap)]


def normalize_rect(rect: dict[str, Any] | None) -> dict[str, float] | None:
    """Normalize a drawImage destination rect to 0..1 canvas coordinates."""
    if not isinstance(rect, dict):
        return None
    width = rect.get("canvasW")
    height = rect.get("canvasH")
    dx = rect.get("dx")
    dy = rect.get("dy")
    if not width or not height or dx is None or dy is None:
        return None
    try:
        norm_x = float(dx) / float(width)
        norm_y = float(dy) / float(height)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    dw = rect.get("dw")
    dh = rect.get("dh")
    norm_w = None
    norm_h = None
    if dw is not None and dh is not None:
        try:
            norm_w = float(dw) / float(width)
            norm_h = float(dh) / float(height)
        except (TypeError, ValueError, ZeroDivisionError):
            norm_w = None
            norm_h = None
    out: dict[str, float] = {
        "x": round(norm_x, 5),
        "y": round(norm_y, 5),
        "cx": round(norm_x + (norm_w or 0.0) / 2.0, 5),
        "cy": round(norm_y + (norm_h or 0.0) / 2.0, 5),
    }
    if norm_w is not None and norm_h is not None:
        out["w"] = round(norm_w, 5)
        out["h"] = round(norm_h, 5)
    return out


def grid_delta(baseline: Any, current: Any) -> float:
    """L1/2 distance between two normalized grid distributions (0..1)."""
    if not isinstance(baseline, list) or not isinstance(current, list):
        return 0.0
    total = 0.0
    for row_a in baseline:
        if not isinstance(row_a, list):
            return 0.0
    for row_a, row_b in zip(baseline, current):
        if not isinstance(row_a, list) or not isinstance(row_b, list):
            return 0.0
        for value_a, value_b in zip(row_a, row_b):
            try:
                total += abs(float(value_a) - float(value_b))
            except (TypeError, ValueError):
                return 0.0
    return round(total / 2.0, 5)


def _primary_rect(asset: dict[str, Any]) -> dict[str, float] | None:
    """The last normalized destination rect recorded for one asset."""
    last = asset.get("last_norm")
    if isinstance(last, dict):
        return last
    rects = asset.get("rects")
    if isinstance(rects, list) and rects:
        return normalize_rect(rects[-1])
    return None


def compare_sprite_layouts(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    position_tolerance: float = DEFAULT_POSITION_TOLERANCE,
    grid_tolerance: float = DEFAULT_GRID_TOLERANCE,
    ignore_animated_layers: bool = True,
) -> dict[str, Any]:
    """Diff two probe reports sample-by-sample (keyed by sample id)."""
    base_samples = {
        str(sample.get("id")): sample
        for sample in baseline.get("samples", [])
        if isinstance(sample, dict)
    }
    current_samples = {
        str(sample.get("id")): sample
        for sample in current.get("samples", [])
        if isinstance(sample, dict)
    }
    missing: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    ignored_moved: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    grid_drift: list[dict[str, Any]] = []
    for sample_id, base_sample in base_samples.items():
        current_sample = current_samples.get(sample_id)
        if current_sample is None:
            missing.append({"sample": sample_id, "src": None, "reason": "sample_missing"})
            continue
        base_assets = {
            str(asset.get("src")): asset
            for asset in base_sample.get("sprites", [])
            if isinstance(asset, dict)
        }
        current_assets = {
            str(asset.get("src")): asset
            for asset in current_sample.get("sprites", [])
            if isinstance(asset, dict)
        }
        for src, base_asset in base_assets.items():
            current_asset = current_assets.get(src)
            if current_asset is None:
                missing.append({"sample": sample_id, "src": src, "reason": "sprite_missing"})
                continue
            base_rect = _primary_rect(base_asset)
            current_rect = _primary_rect(current_asset)
            if not base_rect or not current_rect:
                continue
            deltas = []
            for key in ("cx", "cy"):
                if key in base_rect and key in current_rect:
                    deltas.append(abs(base_rect[key] - current_rect[key]))
            for key in ("w", "h"):
                if key in base_rect and key in current_rect:
                    deltas.append(abs(base_rect[key] - current_rect[key]))
            if not deltas:
                continue
            delta = max(deltas)
            if delta > position_tolerance:
                entry = {
                    "sample": sample_id,
                    "src": src,
                    "delta": round(delta, 5),
                    "baseline": base_rect,
                    "current": current_rect,
                }
                if ignore_animated_layers and is_animated_layer(src):
                    ignored_moved.append(entry)
                else:
                    moved.append(entry)
        for src in current_assets:
            if src not in base_assets:
                new.append({"sample": sample_id, "src": src})
        base_grid = (base_sample.get("pet_canvas") or {}).get("grid")
        current_grid = (current_sample.get("pet_canvas") or {}).get("grid")
        delta = grid_delta(base_grid, current_grid)
        if delta > grid_tolerance:
            grid_drift.append({"sample": sample_id, "delta": delta})
    drift = bool(missing or moved or grid_drift)
    return {
        "drift": drift,
        "missing": missing,
        "moved": moved,
        "ignored_moved": ignored_moved,
        "new": new,
        "grid_drift": grid_drift,
        "samples_compared": len(base_samples),
        "position_tolerance": position_tolerance,
        "grid_tolerance": grid_tolerance,
        "ignore_animated_layers": ignore_animated_layers,
    }


def build_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    unique: set[str] = set()
    draw_records = 0
    with_pixels = 0
    for sample in samples:
        for asset in sample.get("sprites") or []:
            if isinstance(asset, dict):
                unique.add(str(asset.get("src")))
                draw_records += len(asset.get("rects") or [])
        if (sample.get("pet_canvas") or {}).get("opaque"):
            with_pixels += 1
    return {
        "samples": len(samples),
        "unique_sprites": len(unique),
        "sprite_draw_records": draw_records,
        "pet_canvas_samples_with_pixels": with_pixels,
    }


def highlight_assets(sample: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    """Key face/body assets with their normalized position, for quick review."""
    out: list[dict[str, Any]] = []
    for asset in sample.get("sprites") or []:
        if not isinstance(asset, dict):
            continue
        src = str(asset.get("src") or "")
        if not KEY_ASSET_PATTERN.search(src):
            continue
        rect = _primary_rect(asset)
        if not rect:
            continue
        out.append({"src": src, "count": asset.get("count"), "norm": rect})
        if len(out) >= limit:
            break
    return out


def baseline_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Strip volatile fields so a baseline file stays comparable."""
    return {
        "schema": SCHEMA,
        "target_sha256": report.get("target_sha256"),
        "artifact_variant": report.get("artifact_variant"),
        "samples": report.get("samples", []),
        "summary": report.get("summary", {}),
    }


# --------------------------------------------------------------------------- #
# Session + sampling
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _layout_session(
    html_path: Path,
    *,
    headless: bool,
    timeout_ms: int,
    bootstrap_settle_ms: int,
    console: list[str],
    network: list[dict[str, Any]],
):
    """Boot the artifact into gameplay with the sprite recorder preinstalled."""
    from playwright.sync_api import sync_playwright

    bst = ps._bst()
    serve_dir = html_path.parent

    def _push_console(line: str) -> None:
        console.append(line[:400])
        if len(console) > 4000:
            del console[:2000]

    with bst._serve_directory(serve_dir) as server, sync_playwright() as pw:
        url = bst._relative_url(server, serve_dir, html_path)
        browser = ps._launch_browser(pw, headless)
        context = browser.new_context()
        context.add_init_script(ps.INIT_HARNESS)
        context.add_init_script(DRAW_IMAGE_RECORDER)
        page = context.new_page()
        page.on("console", lambda m: _push_console(f"{m.type}:{m.text[:300]}"))
        page.on("pageerror", lambda e: _push_console(f"pageerror:{str(e)[:300]}"))

        def _on_response(response: Any) -> None:
            try:
                status = int(response.status)
            except Exception:  # noqa: BLE001 - defensive, never break the page.
                return
            if status < 400:
                return
            _record_network(network, url=response.url, status=status, kind="http_error")

        def _on_request_failed(request: Any) -> None:
            failure = None
            try:
                failure = str(request.failure)[:200]
            except Exception:  # noqa: BLE001
                failure = None
            _record_network(
                network,
                url=request.url,
                status=None,
                kind="request_failed",
                failure=failure,
            )

        page.on("response", _on_response)
        page.on("requestfailed", _on_request_failed)
        page.set_default_timeout(timeout_ms)
        try:
            page.goto(url, wait_until="load", timeout=180_000)
            page.wait_for_function(ps._ready_js(), timeout=180_000)
            page.evaluate(
                "(() => { try { const C = window.SugarCube.Config;"
                " C.saves.autosave = false; C.passages.transitionOut = undefined;"
                " return true; } catch (e) { return false; } })()"
            )
            boot = ps._reach_gameplay(page, steps=ps.STARTUP_STEPS)
            page.wait_for_timeout(bootstrap_settle_ms)
            page.evaluate(
                "(() => { const S = window.__DOLX__; if (S) S.hooked = false;"
                " return true; })()"
            )
            for _ in range(40):
                if page.evaluate(ps.install_passage_hook()):
                    break
                page.wait_for_timeout(250)
            yield page, boot
        finally:
            browser.close()


def _record_network(
    sink: list[dict[str, Any]],
    *,
    url: str,
    status: int | None,
    kind: str,
    failure: str | None = None,
) -> None:
    if len(sink) >= MAX_NETWORK_RECORDS:
        return
    relative = relativize_src(url)
    record: dict[str, Any] = {
        "url": relative,
        "status": status,
        "kind": kind,
        "asset": bool(ASSET_EXTENSION_PATTERN.search(relative)),
    }
    hint = classify_network_failure(record)
    if hint:
        record["hint"] = hint
    if failure:
        record["failure"] = failure
    sink.append(record)


def collect_sample(
    page: Any,
    sample_id: str,
    *,
    style: str | None = None,
    variant: str | None = None,
    settle_ms: int = 1600,
) -> dict[str, Any]:
    """Reset the recorder, trigger a redraw, then dump geometry for one state."""
    reset = page.evaluate(SPRITE_LOG_RESET)
    if style is not None:
        set_result = page.evaluate(
            sfa.AU_FACE_SET, {"style": style, "variant": variant}
        )
    else:
        set_result = page.evaluate(sfa.AU_PET_ENABLE)
    page.wait_for_timeout(settle_ms)
    probe = page.evaluate(sfa.AU_PET_PROBE)
    recovered = False
    if not ((probe.get("canvas") or {}).get("opaque")):
        # One reminder of the game's own predecessor macro; recorded, not hidden.
        try:
            page.evaluate(sfa.AU_PET_ENABLE)
            page.wait_for_timeout(900)
            probe = page.evaluate(sfa.AU_PET_PROBE)
            recovered = bool((probe.get("canvas") or {}).get("opaque"))
        except Exception as exc:  # noqa: BLE001
            probe = dict(probe)
            probe["recovery_error"] = str(exc)[:200]
    pet_grid = page.evaluate(
        CANVAS_GRID_PROFILE, {"selector": "#maplebirch-character-pet", "grid": GRID_SIZE}
    )
    sidebar_grid = page.evaluate(
        CANVAS_GRID_PROFILE, {"selector": "#sidebar", "grid": GRID_SIZE}
    )
    dump = page.evaluate(SPRITE_LOG_DUMP)
    assets = merge_asset_records(dump.get("assets") or [])
    for asset in assets:
        rects = asset.get("rects")
        asset["last_norm"] = normalize_rect(rects[-1]) if rects else None
    sample: dict[str, Any] = {
        "id": sample_id,
        "facestyle": style,
        "facevariant": variant,
        "recorder_reset": reset,
        "set": set_result,
        "recovered_via_predecessor": recovered,
        "passage": probe.get("passage"),
        "error_banner": probe.get("errorBanner"),
        "pet_canvas": pet_grid,
        "sidebar": {
            key: sidebar_grid.get(key)
            for key in ("present", "canvas", "w", "h", "opaque", "bbox", "centroid")
        },
        "sprite_log": {
            "available": dump.get("available"),
            "total_entries": dump.get("total_entries"),
            "distinct_sources": dump.get("distinct_sources"),
            "truncated": dump.get("truncated"),
        },
        "sprites": assets,
    }
    sample["highlights"] = highlight_assets(sample)
    return sample


def run(
    target: Path,
    out_dir: Path,
    *,
    headless: bool = True,
    timeout_ms: int = 120_000,
    bootstrap_settle_ms: int = 3_000,
    settle_ms: int = 1_600,
    max_styles: int = 8,
    baseline_path: Path | None = None,
    update_baseline: bool = False,
    strict_layout: bool = False,
) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    report: dict[str, Any] = {
        "tool": TOOL_NAME,
        "schema": SCHEMA,
        "target": str(target),
        "html_path": None,
        "target_sha256": None,
        "artifact_variant": None,
        "inventory": {"list_length": None, "errors": []},
        "boot": None,
        "au_module": None,
        "face_options": None,
        "samples": [],
        "summary": {},
        "network_failures": [],
        "console_tail": [],
        "diff": None,
        "baseline": None,
        "baseline_written": None,
        "verdict": None,
        "started_at": started,
        "finished_at": None,
        "fatal_error": None,
    }

    html_path = ps.resolve_html_path(target)
    report["html_path"] = str(html_path)
    if target.is_file():
        report["target_sha256"] = ps.file_sha256(target)
    try:
        inventory = sfa.embedded_mod_inventory(html_path)
    except Exception as exc:  # noqa: BLE001 - report and keep going.
        inventory = {"list_length": None, "mods": [], "errors": [f"{type(exc).__name__}: {exc}"]}
    report["inventory"] = {
        "list_length": inventory.get("list_length"),
        "errors": list(inventory.get("errors") or []),
    }
    report["artifact_variant"] = sfa.artifact_variant(target, html_path, inventory)

    console: list[str] = []
    network: list[dict[str, Any]] = []
    try:
        with _layout_session(
            html_path,
            headless=headless,
            timeout_ms=timeout_ms,
            bootstrap_settle_ms=bootstrap_settle_ms,
            console=console,
            network=network,
        ) as (page, boot):
            report["boot"] = boot
            se_probe = page.evaluate(sfa.AU_SE_PROBE)
            report["au_module"] = {
                "gaps": sfa.au_se_module_gaps(se_probe),
                "probe": se_probe,
                "probe_stage": "after_boot",
            }
            enable = page.evaluate(sfa.AU_PET_ENABLE)
            page.wait_for_timeout(settle_ms)
            options = page.evaluate(sfa.AU_FACE_OPTIONS)
            styles = [str(item) for item in (options.get("styles") or []) if item][:max_styles]
            report["face_options"] = {
                "style": options.get("style"),
                "styles": styles,
                "current_variant": options.get("current"),
                "enable": enable,
            }
            samples: list[dict[str, Any]] = []
            if len(styles) >= 2:
                by_style = options.get("byStyle") or {}
                for style in styles:
                    variants = [str(item) for item in (by_style.get(style) or []) if item]
                    samples.append(
                        collect_sample(
                            page,
                            f"style:{style}",
                            style=style,
                            variant=variants[0] if variants else None,
                            settle_ms=settle_ms,
                        )
                    )
            else:
                samples.append(collect_sample(page, "default", settle_ms=settle_ms))
            report["samples"] = samples
            # The AU payload registers through ModLoader's lazy/decrypted path,
            # so its passage/widget markers can appear only after the first
            # style interaction. Probing again keeps both moments on record
            # instead of reporting a boot-time gap as a permanent one.
            se_probe_late = page.evaluate(sfa.AU_SE_PROBE)
            report["au_module"]["gaps_after_samples"] = sfa.au_se_module_gaps(
                se_probe_late
            )
            report["au_module"]["probe_after_samples"] = se_probe_late
            report["au_module"]["lazy_note"] = (
                "The AU payload registers through ModLoader's lazy/decrypted "
                "path. Its JS macros and pipeline are live after boot, while "
                "twee markers (SE Widgets / AU_facial_expansion / Widgets "
                "Mirror hook) only appear once a session opens the mod or AU "
                "UI; tools/mod_passage_inventory.py observes them after its "
                "mod-button interaction pass. A pure style-switch session can "
                "legitimately keep them absent."
            )
    except Exception as exc:  # noqa: BLE001 - always emit a report.
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"[:600]

    report["summary"] = build_summary(report["samples"])
    report["network_failures"] = network
    report["network_failure_summary"] = {
        "total": len(network),
        "asset_flagged": sum(1 for item in network if item.get("asset")),
        "legacy_blush_tear_naming": sum(
            1 for item in network if item.get("hint") == "legacy_blush_tear_naming"
        ),
    }
    report["console_tail"] = console[-80:]

    if baseline_path is not None:
        try:
            baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            report["baseline"] = str(baseline_path)
            report["diff"] = {"error": f"{type(exc).__name__}: {exc}", "drift": None}
        else:
            report["baseline"] = str(baseline_path)
            report["diff"] = compare_sprite_layouts(
                baseline, report, ignore_animated_layers=not strict_layout
            )

    if report["fatal_error"] and not report["samples"]:
        report["verdict"] = "insufficient"
    elif report["diff"] is None:
        report["verdict"] = "ok" if report["samples"] else "insufficient"
    elif report["diff"].get("drift") is None:
        report["verdict"] = "insufficient"
    elif report["diff"].get("drift"):
        report["verdict"] = "layout_drift"
    else:
        report["verdict"] = "ok"

    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_report(report, out_dir)
    if update_baseline:
        out_dir.mkdir(parents=True, exist_ok=True)
        baseline_file = out_dir / "sprite-layout-baseline.json"
        baseline_file.write_text(
            json.dumps(baseline_payload(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report["baseline_written"] = str(baseline_file)
    return report


def write_report(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "sprite-layout.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = report.get("summary") or {}
    diff = report.get("diff") or {}
    lines = [
        "# DOL-X sprite layout probe (engine A)",
        "",
        f"- target: `{report.get('target')}`",
        f"- artifact variant: {report.get('artifact_variant')}",
        f"- target sha256: `{report.get('target_sha256')}`",
        f"- verdict: **{report.get('verdict')}**",
        f"- samples: {summary.get('samples')}",
        f"- unique sprites drawn: {summary.get('unique_sprites')}",
        f"- pet canvas samples with pixels: {summary.get('pet_canvas_samples_with_pixels')}",
        "",
    ]
    network_summary = report.get("network_failure_summary") or {}
    if network_summary:
        lines.extend(
            [
                "## network failures",
                "",
                f"- total: {network_summary.get('total')}",
                f"- asset requests: {network_summary.get('asset_flagged')}",
                f"- known legacy blush/tear naming: "
                f"{network_summary.get('legacy_blush_tear_naming')}",
                "",
            ]
        )
    au_module = report.get("au_module") or {}
    if au_module:
        lines.extend(
            [
                "## AU module markers",
                "",
                f"- gaps after boot: {au_module.get('gaps')}",
                f"- gaps after samples: {au_module.get('gaps_after_samples')}",
                "",
            ]
        )
    if report.get("diff") is not None:
        lines.extend(
            [
                "## baseline diff",
                "",
                f"- drift: {diff.get('drift')}",
                f"- missing sprites: {len(diff.get('missing') or [])}",
                f"- moved sprites: {len(diff.get('moved') or [])}",
                f"- animated layers ignored (by design): "
                f"{len(diff.get('ignored_moved') or [])}",
                f"- new sprites: {len(diff.get('new') or [])}",
                f"- grid drift samples: {len(diff.get('grid_drift') or [])}",
                "",
            ]
        )
    for sample in report.get("samples") or []:
        pet = sample.get("pet_canvas") or {}
        lines.append(f"## sample {sample.get('id')}")
        lines.append("")
        lines.append(
            f"- pet canvas: {pet.get('w')}x{pet.get('h')} opaque={pet.get('opaque')} "
            f"bbox={pet.get('bbox')} centroid={pet.get('centroid')}"
        )
        lines.append(
            f"- sprites captured: {len(sample.get('sprites') or [])} "
            f"(log entries={((sample.get('sprite_log') or {}).get('total_entries'))})"
        )
        for item in sample.get("highlights") or []:
            lines.append(f"  - `{item['src']}` at {item['norm']}")
        lines.append("")
    failures = report.get("network_failures") or []
    if failures:
        lines.append("## network failure detail")
        lines.append("")
        for item in failures[:40]:
            hint = f" hint={item['hint']}" if item.get("hint") else ""
            lines.append(
                f"- {item.get('kind')} status={item.get('status')} "
                f"asset={item.get('asset')}{hint} `{item.get('url')}`"
            )
        lines.append("")
    if report.get("fatal_error"):
        lines.extend(["## fatal error", "", f"`{report['fatal_error']}`", ""])
    md_path = out_dir / "sprite-layout.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record which image assets a built DOL-X artifact draws and where, "
            "then optionally diff against a baseline."
        )
    )
    parser.add_argument("target", type=Path, help="built .html or .zip artifact")
    parser.add_argument("--out", type=Path, default=None, help="output directory")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="baseline JSON produced by --update-baseline",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="write sprite-layout-baseline.json into --out after probing",
    )
    parser.add_argument("--max-styles", type=int, default=8)
    parser.add_argument("--settle-ms", type=int, default=1_600)
    parser.add_argument("--bootstrap-settle-ms", type=int, default=3_000)
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument(
        "--strict-layout",
        action="store_true",
        help="do not exclude known animated layers from position drift",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target = args.target
    if not target.exists():
        print(f"target not found: {target}", file=sys.stderr)
        return 2
    out_dir = args.out
    if out_dir is None:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", target.stem)[:80] or "artifact"
        out_dir = DEFAULT_OUT / slug
    report = run(
        target,
        out_dir,
        headless=not args.headed,
        timeout_ms=args.timeout_ms,
        bootstrap_settle_ms=args.bootstrap_settle_ms,
        settle_ms=args.settle_ms,
        max_styles=args.max_styles,
        baseline_path=args.baseline,
        update_baseline=args.update_baseline,
        strict_layout=args.strict_layout,
    )
    summary = report.get("summary") or {}
    print(
        f"[sprite-layout] verdict={report.get('verdict')} "
        f"samples={summary.get('samples')} sprites={summary.get('unique_sprites')} "
        f"diff={report.get('diff')}",
        flush=True,
    )
    return 0 if report.get("verdict") in ("ok", "layout_drift") else 1


if __name__ == "__main__":
    raise SystemExit(main())
