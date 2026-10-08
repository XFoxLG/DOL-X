#!/usr/bin/env python3
"""DOL-X scenario sweep (engine A): the story-axis half of the automated test stack.

``tools/passage_sweep.py`` renders every passage of the real artifact.
``tools/sweep_flow_assertions.py`` asserts whole flows (mods, save/load, ...).
This tool walks the game's own **debug-menu scenario list** as a story axis:

    1. the live ``setup.debugMenu.eventList`` is read at runtime and cross-checked
       against the statically embedded copy in the artifact HTML, so a game
       update that adds/removes/renames rows is reported instead of silently
       skipped (the baseline expectation is 363 rows = 331 clickable + 32
       separators, Main 92 / Events 137 / Character 134 / Favourites 0);
    2. every clickable row runs the game's real front-door:
       restore fixture -> ``runWidgetsInsideLink(section, idx)`` -> assert a
       ``<<set $x to v>>``-style prerequisite really landed -> ``Engine.play``
       the resolved target -> assert landing/rendering/no hard errors -> run the
       invariant battery (core numerics finite + in range, ``NPCList`` structure,
       ``Time`` coherence, clothing slots, depth-limited NaN/Infinity scan);
    3. a curated set of 40 real storyline targets (Eden / Kylar / Robin / Avery
       tower / great hawk / prison / hospital / school / temple / forest / sea /
       brothel / estate / asylum ...) adds scene-specific assertions;
    4. an optional ``dayloop`` suite clicks a day through the real UI
       (wake -> wash -> breakfast -> leave -> school -> class -> after school ->
       home -> sleep) and asserts at least one step really ran, time advanced,
       locations switched, the save round trip is consistent and no hard errors
       fired. Fallback navigation hops are recorded but never counted as a
       completed step.

Verdicts stay five-tier and honest: ``ok / soft_fail / hard_fail /
fixture_insufficient / not_applicable``; the baseline diff reports only new
regressions (plus fixes and new scenarios). Nothing here touches ``lyra/``,
``config/`` or any build input: the whole tool is runtime-only.

Usage:
    python tools/scenario_sweep.py <target.html|zip> --suite scenarios --limit 12
    python tools/scenario_sweep.py <target.html|zip> --section Events --limit 40
    python tools/scenario_sweep.py <target.html|zip> --suite all --save-baseline
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import fixture_ladder as fl  # noqa: E402
from tools import passage_sweep as ps  # noqa: E402
from tools import sweep_flow_assertions as sfa  # noqa: E402
from tools import sweep_ledger as sl  # noqa: E402


TOOL = "scenario_sweep"
DEFAULT_OUT_ROOT = Path(".local/sweep")
DEFAULT_BASELINE_DIR = Path(".local/sweep/baselines")
DEFAULT_FIXTURE = Path(".local/fixtures/base-1004.json")
DEFAULT_MANIFEST_OUT = Path(".local/sweep/scenario-manifest.json")
DEFAULT_SUITE = "scenarios"
SUITES = ("scenarios", "dayloop", "all")
# SugarCube/DoLSave slot numbers start at 1; 7 matches the slot that
# tools/sweep_flow_assertions.py already proved works on this artifact.
SLOT = 7

# The 2026-10-04 ground truth measured on the vega-0511-prep artifact. A game
# update that changes these numbers is reported as manifest drift, never
# silently absorbed.
EXPECTED_MANIFEST: dict[str, Any] = {
    "rows": 363,
    "clickable": 331,
    "separators": 32,
    "sections": {"Main": 92, "Events": 137, "Character": 134, "Favourites": 0},
}

VERDICTS = ("ok", "soft_fail", "hard_fail", "fixture_insufficient", "not_applicable")
VERDICT_SEVERITY = {
    "ok": 0,
    "not_applicable": 1,
    "fixture_insufficient": 2,
    "soft_fail": 3,
    "hard_fail": 4,
}


# --------------------------------------------------------------------------- #
# Manifest: runtime extraction + static cross-check
# --------------------------------------------------------------------------- #


MANIFEST_JS = r"""
() => {
  const dm = window.setup && window.setup.debugMenu;
  if (!dm || !dm.eventList) return { ok: false, error: "setup.debugMenu.eventList missing" };
  const SC = window.SugarCube;
  const rows = [];
  const sections = Object.keys(dm.eventList);
  for (const sec of sections) {
    const list = dm.eventList[sec];
    if (!Array.isArray(list)) continue;
    for (let i = 0; i < list.length; i++) {
      const raw = list[i];
      const entry = {
        section: sec,
        index: i,
        kind: "separator",
        label: null,
        target: null,
        widgets: 0,
        label_is_function: false,
        target_is_function: false,
      };
      try {
        if (raw && Array.isArray(raw.link)) {
          entry.kind = "link";
          entry.label_is_function = typeof raw.link[0] === "function";
          entry.target_is_function = typeof raw.link[1] === "function";
          entry.widgets = Array.isArray(raw.widgets) ? raw.widgets.length : 0;
          window.getNameAndPassage(sec, i);
          entry.label = String(SC.State.temporary.link_name);
          entry.target = String(SC.State.temporary.link_passage);
        } else if (raw && typeof raw === "object" && raw.name != null) {
          entry.label = String(raw.name);
        }
      } catch (e) {
        entry.error = String(e && e.message ? e.message : e).slice(0, 300);
      }
      rows.push(entry);
    }
  }
  return { ok: true, sections: sections, rows: rows };
}
"""


def normalize_manifest_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one runtime manifest row into a JSON-safe shallow dict."""
    row = {
        "section": str(raw.get("section") or ""),
        "index": int(raw.get("index") or 0),
        "kind": str(raw.get("kind") or "separator"),
        "label": None if raw.get("label") is None else str(raw.get("label")),
        "target": None if raw.get("target") is None else str(raw.get("target")),
        "widgets": int(raw.get("widgets") or 0),
        "label_is_function": bool(raw.get("label_is_function")),
        "target_is_function": bool(raw.get("target_is_function")),
    }
    if row["kind"] == "unknown":
        row["kind"] = "link" if row["target"] is not None else "separator"
    if raw.get("error"):
        row["error"] = str(raw["error"])[:300]
    if row["kind"] == "link" and not (row["target"] or "").strip():
        row["kind"] = "link"
    return row


def manifest_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counts that the runtime/static cross-check and baseline diff both use."""
    rows = list(rows)
    by_section: dict[str, int] = collections.OrderedDict()
    for row in rows:
        section = str(row.get("section") or "")
        by_section[section] = by_section.get(section, 0) + 1
    clickable = [r for r in rows if r.get("kind") == "link"]
    return {
        "rows": len(rows),
        "clickable": len(clickable),
        "separators": len(rows) - len(clickable),
        "by_section": by_section,
        "by_section_clickable": {
            section: sum(
                1 for r in clickable if str(r.get("section") or "") == section
            )
            for section in by_section
        },
        "by_section_separators": {
            section: sum(
                1
                for r in rows
                if str(r.get("section") or "") == section and r.get("kind") != "link"
            )
            for section in by_section
        },
        "dynamic_targets": sum(1 for r in clickable if r.get("target_is_function")),
        "literal_targets": sum(1 for r in clickable if not r.get("target_is_function")),
    }


class _SourceCursor:
    """Tiny scanner that skips JS strings/comments while matching brackets."""

    def __init__(self, text: str, pos: int = 0) -> None:
        self.text = text
        self.pos = pos

    def __len__(self) -> int:  # pragma: no cover - convenience
        return len(self.text)

    def eof(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.text[index] if 0 <= index < len(self.text) else ""

    def advance(self, count: int = 1) -> None:
        self.pos += count

    def skip_ws_and_comments(self) -> None:
        while not self.eof():
            ch = self.peek()
            if ch in " \t\r\n":
                self.advance()
            elif ch == "/" and self.peek(1) == "/":
                while not self.eof() and self.peek() not in "\r\n":
                    self.advance()
            elif ch == "/" and self.peek(1) == "*":
                self.advance(2)
                while not self.eof() and not (self.peek() == "*" and self.peek(1) == "/"):
                    self.advance()
                self.advance(2)
            else:
                return

    def skip_string(self) -> None:
        quote = self.peek()
        self.advance()
        while not self.eof():
            ch = self.peek()
            if ch == "\\":
                self.advance(2)
                continue
            self.advance()
            if ch == quote:
                return


def _balanced_region(text: str, start: int) -> str:
    """Return the ``{...}`` object literal that starts at/after ``start``."""
    cursor = _SourceCursor(text, start)
    brace = text.find("{", start)
    if brace < 0:
        return ""
    cursor.pos = brace
    depth = 0
    while not cursor.eof():
        ch = cursor.peek()
        if ch in "\"'`":
            cursor.skip_string()
            continue
        if ch == "/" and cursor.peek(1) in ("/", "*"):
            cursor.skip_ws_and_comments()
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                cursor.advance()
                return text[brace : cursor.pos]
        cursor.advance()
    return text[brace:]


def _balanced_bracket_region(text: str, open_index: int) -> str:
    """Return the ``[...]`` slice whose ``[`` sits at ``open_index``."""
    cursor = _SourceCursor(text, open_index)
    depth = 0
    while not cursor.eof():
        ch = cursor.peek()
        if ch in "\"'`":
            cursor.skip_string()
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                cursor.advance()
                return text[open_index : cursor.pos]
        cursor.advance()
    return text[open_index:]


def _split_top_level(inner: str) -> list[str]:
    """Split ``a, b`` at depth 0, skipping nested brackets/strings."""
    parts: list[str] = []
    cursor = _SourceCursor(inner)
    current_start = 0
    depth = 0
    while not cursor.eof():
        ch = cursor.peek()
        if ch in "\"'`":
            cursor.skip_string()
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(inner[current_start : cursor.pos])
            current_start = cursor.pos + 1
        cursor.advance()
    parts.append(inner[current_start:])
    return [p.strip() for p in parts]


_STRING_LITERAL_RE = re.compile(r"^(?:`[^`]*`|'[^']*'|\"[^\"]*\")$", re.DOTALL)


def _literal_text(token: str) -> str | None:
    token = token.strip()
    if not _STRING_LITERAL_RE.match(token):
        return None
    return token[1:-1]


def parse_static_debug_menu(text: str) -> dict[str, Any]:
    """Parse the artifact's embedded ``setup.debugMenu.eventList`` literal.

    Only the *static* copy is read here; labels in the built artifact are the
    upstream (English) ones while the running game may display translations, so
    the cross-check compares structure, order, counts and literal targets.
    """
    marker = "setup.debugMenu.eventList"
    anchor = text.find(marker)
    if anchor < 0:
        return {
            "ok": False,
            "error": "setup.debugMenu.eventList not found in artifact",
            "sections": {},
            "entries": [],
        }
    region = _balanced_region(text, anchor)
    cursor = _SourceCursor(region)
    entries: list[dict[str, Any]] = []
    sections: dict[str, list[dict[str, Any]]] = collections.OrderedDict()
    current_section: str | None = None
    section_re = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\[")
    while not cursor.eof():
        cursor.skip_ws_and_comments()
        if cursor.eof():
            break
        ch = cursor.peek()
        if ch in "\"'`":
            cursor.skip_string()
            continue
        if ch == "[" and current_section is not None:
            close = region.find("]", cursor.pos)
            cursor.pos = close + 1 if close >= 0 else len(region)
            continue
        if ch == "}":
            cursor.advance()
            continue
        match = section_re.match(region, cursor.pos)
        if match and (current_section is None or True):
            current_section = match.group(1)
            sections.setdefault(current_section, [])
            cursor.pos = match.end()
            # Walk this section's rows until its closing bracket.
            depth = 1
            while not cursor.eof() and depth > 0:
                cursor.skip_ws_and_comments()
                if cursor.eof():
                    break
                ch = cursor.peek()
                if ch in "\"'`":
                    cursor.skip_string()
                    continue
                if region.startswith("link", cursor.pos) and (
                    not region[cursor.pos + 4 : cursor.pos + 5].isalnum()
                ):
                    cursor.pos += 4
                    cursor.skip_ws_and_comments()
                    if cursor.peek() != ":":
                        continue
                    cursor.advance()
                    cursor.skip_ws_and_comments()
                    if cursor.peek() != "[":
                        continue
                    link_region = _balanced_bracket_region(region, cursor.pos)
                    if not link_region.endswith("]"):
                        break
                    inner = link_region[1:-1]
                    cursor.pos += len(link_region)
                    parts = _split_top_level(inner)
                    label = _literal_text(parts[0]) if len(parts) > 0 else None
                    target = _literal_text(parts[1]) if len(parts) > 1 else None
                    entry = {
                        "section": current_section,
                        "index": len(sections[current_section]),
                        "label": label,
                        "target": target,
                        "label_is_function": label is None,
                        "target_is_function": target is None,
                    }
                    sections[current_section].append(entry)
                    entries.append(entry)
                    continue
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                cursor.advance()
            continue
        cursor.advance()
    literal = sum(1 for e in entries if not e["target_is_function"])
    dynamic = sum(1 for e in entries if e["target_is_function"])
    return {
        "ok": True,
        "error": None,
        "sections": {name: len(rows) for name, rows in sections.items()},
        "section_entries": sections,
        "entries": entries,
        "rows": len(entries),
        "literal_targets": literal,
        "dynamic_targets": dynamic,
    }


def cross_check_manifest(
    runtime_rows: list[dict[str, Any]],
    static_menu: dict[str, Any] | None,
    *,
    drift_limit: int = 40,
) -> dict[str, Any]:
    """Compare the runtime manifest against the statically parsed copy.

    The contract from the 2026-10-04 design: static literal rows + static
    dynamic rows must equal the runtime rows, section by section. A mismatch is
    a manifest finding (game update / mod rewrite), never a silent skip.
    """
    runtime = [r for r in runtime_rows]
    runtime_summary = manifest_summary(runtime)
    if not static_menu or not static_menu.get("ok"):
        return {
            "ok": False,
            "reason": (static_menu or {}).get("error") or "static parse unavailable",
            "runtime": runtime_summary,
            "static": None,
            "drift": [],
            "counts_match": None,
        }
    static_entries = static_menu.get("entries") or []
    static_summary = {
        "rows": len(static_entries),
        "clickable": len(static_entries),
        "dynamic_targets": static_menu.get("dynamic_targets", 0),
        "literal_targets": static_menu.get("literal_targets", 0),
        "by_section": dict(static_menu.get("sections") or {}),
    }
    drift: list[dict[str, Any]] = []
    counts_match = (
        runtime_summary["clickable"] == static_summary["clickable"]
        and runtime_summary["dynamic_targets"] == static_summary["dynamic_targets"]
        and runtime_summary["literal_targets"] == static_summary["literal_targets"]
    )
    sections = list(
        dict.fromkeys(
            list(runtime_summary["by_section"]) + list(static_summary["by_section"])
        )
    )
    for section in sections:
        runtime_count = runtime_summary["by_section_clickable"].get(section, 0)
        static_count = static_summary["by_section"].get(section, 0)
        if runtime_count != static_count:
            drift.append(
                {
                    "kind": "section_count",
                    "section": section,
                    "static": static_count,
                    "runtime": runtime_count,
                }
            )
    static_by_section: dict[str, list[dict[str, Any]]] = {}
    for entry in static_entries:
        static_by_section.setdefault(str(entry.get("section") or ""), []).append(entry)
    for section, runtime_section in _group_clickable(runtime).items():
        static_section = static_by_section.get(section, [])
        for index, row in enumerate(runtime_section):
            if index >= len(static_section):
                break
            entry = static_section[index]
            if entry.get("target_is_function"):
                continue
            if not row.get("target_is_function") and str(row.get("target")) != str(
                entry.get("target")
            ):
                if len(drift) < drift_limit:
                    drift.append(
                        {
                            "kind": "target_drift",
                            "section": section,
                            "index": index,
                            "static": entry.get("target"),
                            "runtime": row.get("target"),
                        }
                    )
    return {
        "ok": counts_match and not drift,
        "reason": None,
        "runtime": runtime_summary,
        "static": static_summary,
        "counts_match": counts_match,
        "drift": drift[:drift_limit],
        "drift_count": len(drift),
    }


def _group_clickable(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.OrderedDict()
    for row in rows:
        if row.get("kind") != "link":
            continue
        grouped.setdefault(str(row.get("section") or ""), []).append(row)
    return grouped


def manifest_drift(
    summary: dict[str, Any], expected: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Report how the freshly generated manifest differs from the known truth."""
    expected = expected or EXPECTED_MANIFEST
    differences: list[dict[str, Any]] = []
    for key in ("rows", "clickable", "separators"):
        if int(summary.get(key) or 0) != int(expected.get(key) or 0):
            differences.append(
                {
                    "kind": "total",
                    "name": key,
                    "expected": expected.get(key),
                    "actual": summary.get(key),
                }
            )
    for section, count in (expected.get("sections") or {}).items():
        actual = int((summary.get("by_section") or {}).get(section) or 0)
        if actual != int(count):
            differences.append(
                {
                    "kind": "section",
                    "name": section,
                    "expected": count,
                    "actual": actual,
                }
            )
    for section, count in (summary.get("by_section") or {}).items():
        if section not in (expected.get("sections") or {}):
            differences.append(
                {
                    "kind": "section_new",
                    "name": section,
                    "expected": 0,
                    "actual": count,
                }
            )
    return {"ok": not differences, "differences": differences}


# --------------------------------------------------------------------------- #
# Scenario runtime JS
# --------------------------------------------------------------------------- #

# One place for the shallow + one-level state summary. Returned to Python only
# as a JSON string: the game's State.variables is far too deep for CDP.
SUMMARY_HELPER_JS = r"""
  const __dolxType = (v) => {
    if (v === null) return "null";
    if (Array.isArray(v)) return "array";
    return typeof v;
  };
  const __dolxLeaf = (v) => {
    const t = typeof v;
    if (v === null || t === "number" || t === "string" || t === "boolean") {
      let text;
      try { text = String(v); } catch (e) { text = "[unreadable]"; }
      return t + ":" + text.slice(0, 80);
    }
    return null;
  };
  const __dolxSummary = (V) => {
    const out = {};
    let keys = [];
    try { keys = Object.keys(V).sort(); } catch (e) { return out; }
    for (const k of keys) {
      let v;
      try { v = V[k]; } catch (e) { out[k] = "unreadable"; continue; }
      const leaf = __dolxLeaf(v);
      if (leaf !== null) { out[k] = leaf; continue; }
      if (Array.isArray(v)) {
        out[k] = "array:" + v.length;
        for (let i = 0; i < Math.min(v.length, 8); i++) {
          let w;
          try { w = v[i]; } catch (e) { break; }
          const inner = __dolxLeaf(w);
          if (inner !== null) { out[k + "[" + i + "]"] = inner; continue; }
          if (w && typeof w === "object") {
            let wkeys = [];
            try { wkeys = Object.keys(w).slice(0, 8); } catch (e) { wkeys = []; }
            for (const kk of wkeys) {
              let x;
              try { x = w[kk]; } catch (e) { continue; }
              const xleaf = __dolxLeaf(x);
              if (xleaf !== null) out[k + "[" + i + "]." + kk] = xleaf;
            }
          }
        }
      } else if (v && typeof v === "object") {
        let vkeys = [];
        try { vkeys = Object.keys(v); } catch (e) { vkeys = []; }
        out[k] = "object:" + vkeys.length;
        for (const kk of vkeys.slice(0, 8)) {
          let x;
          try { x = v[kk]; } catch (e) { continue; }
          const xleaf = __dolxLeaf(x);
          if (xleaf !== null) out[k + "." + kk] = xleaf;
        }
      } else {
        out[k] = typeof v;
      }
    }
    return out;
  };
  const __dolxDelta = (before, after, limit) => {
    const entries = [];
    let truncated = false;
    const keys = new Set(Object.keys(before).concat(Object.keys(after)));
    const sorted = Array.from(keys).sort();
    for (const k of sorted) {
      if (before[k] === after[k]) continue;
      if (entries.length >= limit) { truncated = true; break; }
      entries.push({
        path: k,
        before: before[k] === undefined ? null : before[k],
        after: after[k] === undefined ? null : after[k],
      });
    }
    return { entries: entries, truncated: truncated };
  };
  // The shallow __dolxSummary above only reaches one nesting level and the
  // first few members of arrays/objects, so a widget writing into
  // ``$museumAntiques.paintings.x`` or deep NPC fields looks like "no delta".
  // __dolxDeepSnapshot walks the whole variable tree (bounded by a node
  // budget) into a flat ``path -> encoded leaf`` map; the delta between two
  // snapshots is the full serialization summary plus targeted diff.
  const __dolxLookupPath = (root, path) => {
    let node = root;
    const parts = String(path || "").split(".");
    for (let i = 0; i < parts.length; i++) {
      let name = parts[i];
      while (name.length) {
        const open = name.indexOf("[");
        if (open < 0) {
          node = node == null ? undefined : node[name];
          break;
        }
        const head = name.slice(0, open);
        if (head) node = node == null ? undefined : node[head];
        const close = name.indexOf("]", open);
        if (close < 0) return undefined;
        node = node == null ? undefined : node[name.slice(open + 1, close)];
        name = name.slice(close + 1);
      }
    }
    return node;
  };
  const __dolxDeepSnapshot = (V, budget) => {
    const map = {};
    const seen = new Set();
    let nodes = 0;
    let truncated = false;
    const walk = (value, path, depth) => {
      if (truncated || nodes >= budget) { truncated = true; return; }
      nodes++;
      let leaf = null;
      try { leaf = __dolxLeaf(value); } catch (e) { map[path] = "unreadable"; return; }
      if (leaf !== null) { map[path] = leaf; return; }
      const t = typeof value;
      if (t === "function") { map[path] = "function"; return; }
      if (t !== "object") { map[path] = t; return; }
      if (depth >= 12) {
        map[path] = Array.isArray(value) ? "array:deep" : "object:deep";
        return;
      }
      let cycle = false;
      try { cycle = seen.has(value); } catch (e) { cycle = false; }
      if (cycle) { map[path] = "cycle"; return; }
      seen.add(value);
      try {
        if (Array.isArray(value)) {
          map[path] = "array:" + value.length;
          const count = Math.min(value.length, 256);
          for (let i = 0; i < count && !truncated; i++) {
            let item;
            try { item = value[i]; } catch (e) {
              map[path + "[" + i + "]"] = "unreadable";
              continue;
            }
            walk(item, path + "[" + i + "]", depth + 1);
          }
        } else {
          let keys = [];
          try { keys = Object.keys(value).sort(); } catch (e) { keys = []; }
          map[path] = "object:" + keys.length;
          for (let i = 0; i < keys.length && !truncated; i++) {
            let item;
            try { item = value[keys[i]]; } catch (e) {
              map[path + "." + keys[i]] = "unreadable";
              continue;
            }
            walk(item, path + "." + keys[i], depth + 1);
          }
        }
      } finally {
        seen.delete(value);
      }
    };
    try { walk(V, "$", 0); } catch (e) { truncated = true; }
    return { map: map, nodes: nodes, truncated: truncated };
  };
  const __dolxDeepDelta = (before, after, limit) => {
    const entries = [];
    let truncated = false;
    const keys = new Set(Object.keys(before.map).concat(Object.keys(after.map)));
    const sorted = Array.from(keys).sort();
    for (const k of sorted) {
      if (before.map[k] === after.map[k]) continue;
      if (entries.length >= limit) { truncated = true; break; }
      entries.push({
        path: k,
        before: before.map[k] === undefined ? null : before.map[k],
        after: after.map[k] === undefined ? null : after.map[k],
      });
    }
    return { entries: entries, truncated: truncated };
  };
  // Parseable ``<<set $path to <literal>>`` / ``<<set $path += 5>>`` widgets
  // get their final value checked against the literal (plus the deep snapshot
  // for compound assignments). Non-literal RHS is reported as unchecked, never
  // guessed: "cannot verify" must not read as "verified".
  const __dolxLiteral = (text) => {
    const s = String(text == null ? "" : text).trim();
    if (/^-?\d+(?:\.\d+)?$/.test(s)) return { kind: "number", value: Number(s) };
    if (s === "true") return { kind: "boolean", value: true };
    if (s === "false") return { kind: "boolean", value: false };
    if (s === "null") return { kind: "null", value: null };
    if (s === "[]") return { kind: "array", value: null };
    if (s === "{}") return { kind: "object", value: null };
    if (/^`[^`]*`$/.test(s) || /^'[^']*'$/.test(s) || /^"[^"]*"$/.test(s)) {
      return { kind: "string", value: s.slice(1, -1) };
    }
    return null;
  };
  const __dolxAssignChecks = (V, widgets, deepBefore, limit) => {
    const checks = [];
    const pathRe = /^\$([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+|\[\d+\])*)\s+(to\s+|=|(?:\+|-|\*|\/)=)\s*([\s\S]+)$/;
    const setRe = /<<\s*set\s+([\s\S]*?)>>/g;
    for (const widget of widgets || []) {
      // Function widgets build their markup at call time (``() => `<<set $x
      // to ` + V.x + `>>` ``). String(fn) is source code, not SugarCube, so
      // parsing it would invent checks that never ran: report the count and
      // stay unchecked instead.
      if (typeof widget === "function") continue;
      const source = String(widget);
      let match;
      setRe.lastIndex = 0;
      while ((match = setRe.exec(source)) !== null) {
        const inner = match[1].trim();
        const parsed = pathRe.exec(inner);
        if (!parsed) continue;
        const path = parsed[1];
        const op = parsed[2].replace(/\s+/g, "");
        const rhs = parsed[3].trim();
        const literal = __dolxLiteral(rhs);
        let actual;
        try { actual = __dolxLookupPath(V, path); } catch (e) { actual = undefined; }
        const shown = actual === undefined
          ? null
          : (typeof actual === "object" && actual !== null
            ? (Array.isArray(actual) ? "array" : "object")
            : actual);
        if (!literal) {
          checks.push({
            path: path, op: op, rhs: rhs.slice(0, 80),
            checked: false, reason: "non-literal rhs", actual: shown,
          });
        } else if (op === "to" || op === "=") {
          let ok = false;
          let expected = literal.value;
          if (literal.kind === "number") ok = actual === literal.value;
          else if (literal.kind === "string") ok = String(actual) === literal.value;
          else if (literal.kind === "boolean") ok = actual === literal.value;
          else if (literal.kind === "null") ok = actual === null || actual === undefined;
          else if (literal.kind === "array") { ok = Array.isArray(actual); expected = "array"; }
          else if (literal.kind === "object") {
            ok = !!actual && typeof actual === "object" && !Array.isArray(actual);
            expected = "object";
          }
          checks.push({
            path: path, op: "to", rhs: rhs.slice(0, 80),
            checked: true, ok: ok, expected: expected, actual: shown,
          });
        } else if (literal.kind !== "number") {
          checks.push({
            path: path, op: op, rhs: rhs.slice(0, 80),
            checked: false, reason: "non-numeric rhs", actual: shown,
          });
        } else {
          const encoded = deepBefore && deepBefore.map ? deepBefore.map["$." + path] : undefined;
          const beforeValue = typeof encoded === "string" && encoded.indexOf("number:") === 0
            ? Number(encoded.slice(7))
            : NaN;
          if (isNaN(beforeValue)) {
            checks.push({
              path: path, op: op, rhs: rhs.slice(0, 80),
              checked: false, reason: "no numeric before value", actual: shown,
            });
          } else {
            let expected = beforeValue;
            if (op === "+=") expected = beforeValue + literal.value;
            else if (op === "-=") expected = beforeValue - literal.value;
            else if (op === "*=") expected = beforeValue * literal.value;
            else if (op === "/=") expected = beforeValue / literal.value;
            const ok = typeof actual === "number" && Math.abs(actual - expected) < 1e-9;
            checks.push({
              path: path, op: op, rhs: rhs.slice(0, 80),
              checked: true, ok: ok, expected: expected, actual: shown,
            });
          }
        }
        if (checks.length >= limit) return checks;
      }
    }
    return checks;
  };
"""


SCENARIO_RUN = (
    r"""
(payload) => {
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  S.reset();
  const SC = window.SugarCube;
  const V = SC.State.variables;
"""
    + SUMMARY_HELPER_JS
    + r"""
  const out = {
    ok: true, section: payload.section, index: payload.index,
    link_name: null, target: null, target_error: null,
    label_is_function: false, target_is_function: false,
    widgets: 0, widgets_list: [], widgets_error: null,
    delta: [], delta_truncated: false, before_keys: 0, after_keys: 0, fixture_keys: 0,
    passage_before: null, deep_delta: [], deep_delta_truncated: false,
    deep_nodes: 0, assignment_checks: [], location_before: null,
    function_widgets: 0,
  };
  let widgetsRaw = [];
  try {
    const list = (window.setup && window.setup.debugMenu && window.setup.debugMenu.eventList) || null;
    const row = list && list[payload.section] && list[payload.section][payload.index];
    if (!row) { out.ok = false; out.error = "row not found"; return JSON.stringify(out); }
    out.label_is_function = typeof row.link[0] === "function";
    out.target_is_function = typeof row.link[1] === "function";
    out.widgets = Array.isArray(row.widgets) ? row.widgets.length : 0;
    widgetsRaw = Array.isArray(row.widgets) ? row.widgets : [];
    // The widget source text is what the invariant battery uses to tell an
    // intentional debug cheat ("$awareness -= 200") from real corruption.
    out.widgets_list = widgetsRaw.slice(0, 24).map((w) => String(w).slice(0, 300));
  } catch (e) {
    out.ok = false; out.error = "row probe: " + String(e && e.message ? e.message : e);
    return JSON.stringify(out);
  }
  try { out.passage_before = String(SC.State.passage || ""); } catch (e) { out.passage_before = null; }
  try { out.location_before = String(V.passage || ""); } catch (e) { out.location_before = null; }
  try {
    window.getNameAndPassage(payload.section, payload.index);
    out.link_name = String(SC.State.temporary.link_name);
    out.target = String(SC.State.temporary.link_passage);
    out.link_passage = out.target;
  } catch (e) {
    out.target_error = String(e && e.message ? e.message : e).slice(0, 400);
  }
  const before = __dolxSummary(V);
  let deepBefore = null;
  try { deepBefore = __dolxDeepSnapshot(V, 150000); } catch (e) { deepBefore = null; }
  try {
    window.runWidgetsInsideLink(payload.section, payload.index);
  } catch (e) {
    out.widgets_error = String(e && e.message ? e.message : e).slice(0, 600);
  }
  const after = __dolxSummary(V);
  const delta = __dolxDelta(before, after, 40);
  out.delta = delta.entries;
  out.delta_truncated = delta.truncated;
  out.before_keys = Object.keys(before).length;
  out.after_keys = Object.keys(after).length;
  if (deepBefore) out.deep_nodes = deepBefore.nodes;
  if (delta.entries.length === 0 && deepBefore && !deepBefore.truncated) {
    try {
      const deepAfter = __dolxDeepSnapshot(V, 150000);
      if (deepAfter.truncated) {
        out.deep_delta_truncated = true;
      } else {
        const deep = __dolxDeepDelta(deepBefore, deepAfter, 40);
        out.deep_delta = deep.entries;
        out.deep_delta_truncated = deep.truncated;
      }
    } catch (e) {
      out.deep_delta_truncated = true;
    }
  }
  try {
    out.assignment_checks = __dolxAssignChecks(V, widgetsRaw, deepBefore, 40);
  } catch (e) {
    out.assignment_checks = [];
  }
  try {
    out.function_widgets = widgetsRaw.filter((w) => typeof w === "function").length;
  } catch (e) { out.function_widgets = 0; }
  try { out.fixture_keys = S.fixtureVars ? Object.keys(S.fixtureVars).length : 0; } catch (e) { out.fixture_keys = 0; }
  return JSON.stringify(out);
}
"""
)


# Core numeric variables with generous sanity bounds: only corruption (NaN,
# Infinity, negative pain, absurd magnitudes) trips them. Verified present as
# numbers in .local/fixtures/base-1004.json.
CORE_NUMERIC_BOUNDS: tuple[tuple[str, float, float], ...] = (
    ("money", -1_000_000_000, 1_000_000_000_000),
    ("pain", 0, 1_000_000),
    ("arousal", 0, 1_000_000),
    ("arousalmax", 0, 1_000_000_000),
    ("stress", 0, 1_000_000),
    ("trauma", 0, 1_000_000),
    ("awareness", 0, 1_000_000),
    ("physique", 0, 1_000_000_000),
    ("tiredness", 0, 1_000_000),
    ("hunger", 0, 1_000_000),
    ("thirst", 0, 1_000_000),
    ("control", 0, 1_000_000_000),
    ("allure", 0, 1_000_000_000),
    ("beauty", 0, 1_000_000_000),
    ("attractiveness", 0, 1_000_000_000),
    ("promiscuity", 0, 1_000_000),
    ("exhibitionism", 0, 1_000_000),
    ("deviancy", 0, 1_000_000),
    ("willpower", 0, 1_000_000_000),
    ("purity", 0, 1_000_000_000),
    ("attention", 0, 1_000_000),
)

REQUIRED_CORE_KEYS: tuple[str, ...] = (
    "money",
    "pain",
    "arousal",
    "stress",
    "trauma",
    "awareness",
    "physique",
    "worn",
    "NPCList",
    "NPCName",
    "player",
)

WEAR_SLOTS: tuple[str, ...] = (
    "over_upper",
    "over_lower",
    "upper",
    "lower",
    "under_upper",
    "under_lower",
    "over_head",
    "head",
    "face",
    "neck",
    "hands",
    "handheld",
    "legs",
    "feet",
    "genitals",
)

INVARIANT_BATTERY = (
    r"""
(payload) => {
  const SC = window.SugarCube;
  const V = SC.State.variables;
  const checks = [];
  const violations = [];
  const notes = [];
  const rowWidgets = (payload && payload.widgets) || [];
  const stats = { nodes: 0, truncated: false, nan: 0, infinity: 0 };
  const push = (name, ok, detail) => checks.push({ name: name, ok: !!ok, detail: String(detail || "").slice(0, 300) });
  const violate = (text) => { if (violations.length < 40) violations.push(String(text).slice(0, 200)); };
  const note = (text) => { if (notes.length < 40) notes.push(String(text).slice(0, 200)); };
  // A debug-menu row that writes an out-of-range value itself ("$awareness -=
  // 200", "Damage Chastity") is exercising the cheat on purpose. Such values
  // are recorded as notes, never as corruption violations.
  const intended = (needle) => {
    for (const w of rowWidgets) { if (String(w).indexOf(needle) >= 0) return true; }
    return false;
  };

  const required = __REQUIRED_KEYS__;
  const missing = required.filter((k) => { try { return !(k in V); } catch (e) { return true; } });
  push("required_core_keys", missing.length === 0, missing.length ? "missing: " + missing.join(",") : "all present");
  for (const k of missing) violate("required key missing: " + k);

  const bounds = __CORE_BOUNDS__;
  const bound_bad = [];
  const bound_note = [];
  for (const item of bounds) {
    const k = item[0], lo = item[1], hi = item[2];
    let v;
    try { if (!(k in V)) continue; v = V[k]; } catch (e) { bound_bad.push(k + ":unreadable"); continue; }
    if (typeof v !== "number" || !Number.isFinite(v)) {
      bound_bad.push(k + "=" + String(v));
      continue;
    }
    if (v < lo || v > hi) {
      const text = k + "=" + String(v);
      if (intended("$" + k)) bound_note.push(text + " (written by this debug row)");
      else bound_bad.push(text);
    }
  }
  push("core_numeric_bounds", bound_bad.length === 0, bound_bad.length ? bound_bad.join("; ") : (bound_note.length ? "in range; " + bound_note.length + " intentional debug value(s)" : "in range"));
  for (const item of bound_bad) violate("core numeric out of range: " + item);
  for (const item of bound_note) note("intentional out-of-range: " + item);

  let player_ok = false;
  try { player_ok = !!V.player && typeof V.player === "object" && "gender" in V.player; } catch (e) {}
  push("player_struct", player_ok, player_ok ? "player.gender present" : "player/gender missing");
  if (!player_ok) violate("player struct broken");

  const npc_bad = [];
  try {
    if (!Array.isArray(V.NPCList)) npc_bad.push("NPCList is not an array");
    else {
      for (let i = 0; i < Math.min(V.NPCList.length, 200); i++) {
        const npc = V.NPCList[i];
        if (!npc || typeof npc !== "object") { npc_bad.push("NPCList[" + i + "] not an object"); continue; }
        if ("chastity" in npc && (!npc.chastity || typeof npc.chastity !== "object")) npc_bad.push("NPCList[" + i + "].chastity");
        if ("location" in npc && (!npc.location || typeof npc.location !== "object")) npc_bad.push("NPCList[" + i + "].location");
        if ("skills" in npc && (!npc.skills || typeof npc.skills !== "object")) npc_bad.push("NPCList[" + i + "].skills");
        if ("traits" in npc && !Array.isArray(npc.traits)) npc_bad.push("NPCList[" + i + "].traits");
      }
    }
  } catch (e) { npc_bad.push("NPCList unreadable: " + String(e && e.message ? e.message : e)); }
  push("npc_list_struct", npc_bad.length === 0, npc_bad.length ? npc_bad.slice(0, 6).join("; ") : "array of objects");
  for (const item of npc_bad.slice(0, 6)) violate("NPCList: " + item);

  let npcname_ok = false;
  let npcname_detail = "NPCName[1].type missing";
  try {
    if (Array.isArray(V.NPCName) && V.NPCName.length >= 2 && V.NPCName[1] && typeof V.NPCName[1] === "object") {
      npcname_ok = typeof V.NPCName[1].type === "string";
      if (npcname_ok) npcname_detail = "NPCName[1].type=" + V.NPCName[1].type;
    }
  } catch (e) { npcname_detail = "NPCName unreadable"; }
  push("npc_name_struct", npcname_ok, npcname_detail);
  if (!npcname_ok) violate("NPCName struct broken: " + npcname_detail);

  const slots = __WEAR_SLOTS__;
  const worn_bad = [];
  const worn_note = [];
  try {
    if (!V.worn || typeof V.worn !== "object") worn_bad.push("worn missing");
    else {
      for (const slot of slots) {
        const item = V.worn[slot];
        if (!item || typeof item !== "object") { worn_bad.push(slot + " missing"); continue; }
        if ("slot" in item && item.slot !== slot) worn_bad.push(slot + ".slot=" + String(item.slot));
        const slot_intended = intended("$worn." + slot + ".");
        const flag = (field, value) => {
          const numeric_finite = typeof value === "number" && Number.isFinite(value);
          if (numeric_finite && value >= 0) return;
          const text = slot + "." + field + "=" + String(value);
          if (numeric_finite && slot_intended) worn_note.push(text + " (written by this debug row)");
          else worn_bad.push(text);
        };
        if ("integrity" in item) flag("integrity", item.integrity);
        if ("reveal" in item) flag("reveal", item.reveal);
      }
    }
  } catch (e) { worn_bad.push("worn unreadable"); }
  push("clothing_slots", worn_bad.length === 0, worn_bad.length ? worn_bad.slice(0, 6).join("; ") : slots.length + " slots ok");
  for (const item of worn_bad.slice(0, 6)) violate("worn: " + item);
  for (const item of worn_note.slice(0, 6)) note("intentional debug wear value: " + item);

  const time_bad = [];
  let time_seen = false;
  try {
    const T = window.Time;
    if (!T || typeof T !== "object") time_bad.push("window.Time missing");
    else {
      time_seen = true;
      const int = (v) => typeof v === "number" && Number.isFinite(v) && Math.floor(v) === v;
      if (!int(T.hour) || T.hour < 0 || T.hour > 23) time_bad.push("hour=" + String(T.hour));
      if (!int(T.minute) || T.minute < 0 || T.minute > 59) time_bad.push("minute=" + String(T.minute));
      if (!int(T.month) || T.month < 0 || T.month > 12) time_bad.push("month=" + String(T.month));
      // DoL runs on a fictional calendar (year 361 in 0.5.11.9); only
      // non-integer / absurd years count as corruption.
      if (!int(T.year) || T.year < 1 || T.year > 9999) time_bad.push("year=" + String(T.year));
      if (typeof T.season !== "string" || !T.season) time_bad.push("season=" + String(T.season));
    }
  } catch (e) { time_bad.push("Time unreadable: " + String(e && e.message ? e.message : e)); }
  push("time_coherent", time_bad.length === 0, time_bad.length ? time_bad.join("; ") : (time_seen ? "hour/minute/month/year/season coherent" : "not evaluated"));
  for (const item of time_bad) violate("Time: " + item);

  const MAX_DEPTH = 4;
  const MAX_NODES = 20000;
  const see = new Set();
  const walk = (node, path, depth) => {
    if (stats.nodes >= MAX_NODES) { stats.truncated = true; return; }
    stats.nodes += 1;
    if (node === null || node === undefined) return;
    const t = typeof node;
    if (t === "number") {
      if (Number.isNaN(node)) { stats.nan += 1; violate("NaN at " + (path || "<root>")); }
      else if (!Number.isFinite(node)) { stats.infinity += 1; violate("Infinity at " + (path || "<root>")); }
      return;
    }
    if (t !== "object") return;
    if (see.has(node)) return;
    see.add(node);
    if (depth >= MAX_DEPTH) return;
    if (Array.isArray(node)) {
      const n = Math.min(node.length, 500);
      for (let i = 0; i < n; i++) { let v; try { v = node[i]; } catch (e) { continue; } walk(v, path + "[" + i + "]", depth + 1); if (stats.nodes >= MAX_NODES) break; }
      return;
    }
    let keys = [];
    try { keys = Object.keys(node); } catch (e) { return; }
    for (const k of keys.slice(0, 200)) {
      let v;
      try { v = node[k]; } catch (e) { continue; }
      walk(v, path ? path + "." + k : k, depth + 1);
      if (stats.nodes >= MAX_NODES) break;
    }
  };
  try { walk(V, "", 0); } catch (e) { violate("deep scan failed: " + String(e && e.message ? e.message : e)); }
  push(
    "deep_numeric_scan",
    stats.nan === 0 && stats.infinity === 0,
    "nodes=" + stats.nodes + (stats.truncated ? " (truncated)" : "") + " nan=" + stats.nan + " inf=" + stats.infinity
  );

  const failed = checks.filter((c) => !c.ok);
  return JSON.stringify({
    ok: failed.length === 0 && violations.length === 0,
    checks: checks,
    violations: violations,
    notes: notes,
    stats: stats,
  });
}
"""
    .replace("__REQUIRED_KEYS__", json.dumps(list(REQUIRED_CORE_KEYS)))
    .replace("__CORE_BOUNDS__", json.dumps([list(item) for item in CORE_NUMERIC_BOUNDS]))
    .replace("__WEAR_SLOTS__", json.dumps(list(WEAR_SLOTS)))
)


SCENARIO_CHECKS_JS = r"""
(payload) => {
  const SC = window.SugarCube;
  const V = SC.State.variables;
  const S = window.__DOLX__ || {};
  const T = SC.State.temporary;
  const out = { globals: [], keys: [], changed: [], exprs: [], eval_error: null };
  for (const name of payload.globals || []) {
    let type = "undefined";
    try { type = typeof window[name]; } catch (e) { type = "error"; }
    out.globals.push({ name: name, type: type, ok: type !== "undefined" });
  }
  for (const name of payload.keys || []) {
    let present = false, type = "undefined";
    try { present = name in V || name in window; type = present ? typeof V[name] : "undefined"; if (!present && name in window) type = typeof window[name]; } catch (e) { type = "error"; }
    out.keys.push({ name: name, type: type, ok: present });
  }
  for (const name of payload.changed || []) {
    let changed = false, detail = "";
    try {
      const base = S.fixtureVars || {};
      const has = Object.prototype.hasOwnProperty.call(base, name);
      const baseStr = has ? JSON.stringify(base[name]) : null;
      const nowStr = JSON.stringify(V[name]);
      changed = !has || baseStr !== nowStr;
      detail = (has ? baseStr : "absent") + " -> " + nowStr;
    } catch (e) { detail = "compare failed: " + String(e && e.message ? e.message : e); }
    out.changed.push({ name: name, changed: changed, detail: String(detail).slice(0, 200) });
  }
  for (const check of payload.exprs || []) {
    try {
      const runner = new Function("V", "S", "Time", "window", "SugarCube", "T", "return (" + check.expr + ");");
      let value;
      try { value = runner(V, S, window.Time, window, SC, T); } catch (e) { throw e; }
      let shown;
      try { shown = typeof value === "object" ? JSON.stringify(value).slice(0, 160) : String(value).slice(0, 160); } catch (e) { shown = "[unserializable]"; }
      out.exprs.push({ name: check.name, ok: !!value, value: shown });
    } catch (e) {
      if (out.eval_error === null) out.eval_error = String(e && e.message ? e.message : e).slice(0, 300);
      out.exprs.push({ name: check.name, ok: false, error: String(e && e.message ? e.message : e).slice(0, 200) });
    }
  }
  return JSON.stringify(out);
}
"""


# --------------------------------------------------------------------------- #
# Scenario-specific assertions (>= 20 real targets, all present in the manifest)
#
# Every entry was calibrated against a real run of this artifact with
# .local/fixtures/base-1004.json (see the 2026-10-04 session evidence): the
# changed_keys were observed to move, the checks were observed to hold on a
# healthy build. That is what makes them able to fail on a broken one.
# --------------------------------------------------------------------------- #


def _spec(
    *,
    keys: tuple[str, ...] = (),
    changed: tuple[str, ...] = (),
    checks: tuple[tuple[str, str, str], ...] = (),
    globals_: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "required_globals": list(globals_),
        "required_keys": list(keys),
        "changed_keys": list(changed),
        "checks": [
            {"name": name, "expr": expr, "severity": severity}
            for name, expr, severity in checks
        ],
    }


SCENARIO_SPECS: dict[str, dict[str, Any]] = {
    # Eden
    "Eden Cabin": _spec(
        keys=("edengarden", "edenSeen"),
        changed=("edengarden", "edenSeen", "location"),
        checks=(("location_cabin", 'V.location === "cabin"', "hard"),),
    ),
    "Forest Hunter Intro": _spec(
        keys=("area",),
        changed=("area", "location"),
        checks=(("location_cabin", 'V.location === "cabin"', "hard"),),
    ),
    # Kylar
    "Kylar Basement Rape": _spec(
        changed=("combat", "askAction", "anusWetness"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_man", 'V.enemytype === "man"', "hard"),
        ),
    ),
    "Street Kylar Sex": _spec(
        changed=("combat", "askAction", "anusWetness"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_man", 'V.enemytype === "man"', "hard"),
            ("location_town", 'V.location === "town"', "hard"),
        ),
    ),
    # Robin
    "Bed Robin Sex": _spec(
        changed=("enemytrust", "anusstate", "arousal"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_man", 'V.enemytype === "man"', "hard"),
            ("enemytrust_high", "typeof V.enemytrust === \"number\" && V.enemytrust >= 100", "hard"),
        ),
    ),
    "Robin Pillory Watch": _spec(
        keys=("robinPillory", "robinLastPunishment"),
        changed=("robinPillory", "robinmissing", "robinTraumaMultiplier"),
        checks=(("robin_pillory_key", '"robinPillory" in V', "hard"),),
    ),
    "Orphanage": _spec(
        keys=("baileypaychain",),
        changed=("baileypaychain", "robinfirstrentfight", "robinpaid", "robinromance"),
        checks=(("bailey_chain", '"baileypaychain" in V', "hard"),),
    ),
    "Underground Intro": _spec(
        changed=("location", "combatWetBoost"),
        checks=(("location_underground", 'V.location === "underground"', "hard"),),
    ),
    # Avery (tower/mansion storyline)
    "Domus Street": _spec(
        keys=("averydate",),
        changed=("averydate", "location"),
        checks=(
            ("averydate_key", '"averydate" in V', "hard"),
            ("location_town", 'V.location === "town"', "hard"),
        ),
    ),
    "Test": _spec(
        keys=("avery_tower",),
        changed=("avery_tower", "avery_mansion", "avery_antiques", "location"),
        checks=(("avery_mansion", 'V.location === "avery_mansion"', "hard"),),
    ),
    # Great hawk
    "Moor": _spec(
        keys=("moor", "moor_hunt"),
        changed=("beastname", "moor", "moor_hunt"),
        checks=(("great_hawk", 'V.beastname === "greathawk"', "hard"),),
    ),
    # Prison / police
    "Police Cell": _spec(
        changed=("location", "badEndStats", "attractiveness"),
        checks=(("location_police", 'V.location === "police_station"', "hard"),),
    ),
    "Police Prison Intro Bailey": _spec(
        changed=("npcnum", "npcrow", "enemyno", "monster"),
        checks=(
            (
                "npc_row_prepared",
                "V.npcnum !== S.fixtureVars.npcnum || V.npcrow !== S.fixtureVars.npcrow",
                "hard",
            ),
        ),
    ),
    "Police Pillory Start": _spec(
        changed=("location", "tiredness", "timeSinceArousal"),
        checks=(("location_town", 'V.location === "town"', "hard"),),
    ),
    "Street Police Extreme": _spec(
        keys=("controlled",),
        changed=("controlled", "controlstart", "averyseen"),
        checks=(("controlled_key", '"controlled" in V', "hard"),),
    ),
    # Hospital / asylum
    "Hospital Foyer": _spec(
        changed=("location", "timeStamp"),
        checks=(("location_hospital", 'V.location === "hospital"', "hard"),),
    ),
    "Hospital Bed": _spec(
        keys=("harperSeen",),
        changed=("harperSeen", "hallucinations", "trauma", "location"),
        checks=(
            ("location_hospital", 'V.location === "hospital"', "hard"),
            ("harper_key", '"harperSeen" in V', "hard"),
        ),
    ),
    "Ambulance rescue": _spec(
        changed=("hoursGoneFromHome", "timeSinceArousal", "wolfevent", "tiredness"),
        checks=(
            (
                "time_or_trauma_moved",
                "V.hoursGoneFromHome !== S.fixtureVars.hoursGoneFromHome || V.tiredness !== S.fixtureVars.tiredness",
                "hard",
            ),
        ),
    ),
    "Asylum Intro": _spec(
        keys=("asylumstate", "asylumkeycard", "asylumstatus"),
        changed=("asylumstate", "asylumstatus", "asylumkeycard", "dissociation"),
        checks=(("location_asylum", 'V.location === "asylum"', "hard"),),
    ),
    # Estate / farm / livestock
    "Estate": _spec(
        changed=("location", "estate", "outside"),
        checks=(("location_estate", 'V.location === "estate"', "hard"),),
    ),
    "Livestock Intro": _spec(
        keys=("remySeen",),
        changed=("livestock", "remySeen", "pain"),
        checks=(("remy_key", '"remySeen" in V', "hard"),),
    ),
    # School
    "School Detention": _spec(
        keys=("changingroomstate",),
        changed=("changingroomstate", "location"),
        checks=(("location_school", 'V.location === "school"', "hard"),),
    ),
    "History Lesson Pillory": _spec(
        changed=("schoollesson", "schoolstate", "changingroomstate"),
        checks=(
            ("location_school", 'V.location === "school"', "hard"),
            ("lesson_key", '"schoollesson" in V', "hard"),
        ),
    ),
    "Maths Lesson Gang Bang": _spec(
        changed=("audiencepresent", "audiencemember", "combat"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_man", 'V.enemytype === "man"', "hard"),
            ("audience_present", "V.audiencepresent >= 1", "hard"),
        ),
    ),
    # Temple / museum
    "Temple": _spec(
        keys=("temple_rank", "temple_event", "grace"),
        changed=("temple_rank", "temple_event", "grace", "temple_garden"),
        checks=(("location_temple", 'V.location === "temple"', "hard"),),
    ),
    "Museum": _spec(
        changed=("location",),
        checks=(("location_museum", 'V.location === "museum"', "hard"),),
    ),
    # Forest / beasts (the combat battery)
    "Forest": _spec(
        changed=("location", "forest", "forestmove", "sublocation"),
        checks=(
            ("location_forest", 'V.location === "forest"', "hard"),
            ("forest_meter", "typeof V.forest === \"number\" && V.forest > 0", "hard"),
        ),
    ),
    "Forest Wolf Molestation": _spec(
        changed=("beastname", "combat", "enemytype", "enemytrust"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_beast", 'V.enemytype === "beast"', "hard"),
            ("black_wolf", 'V.beastname === "blackwolf"', "hard"),
        ),
    ),
    "Forest Bear Molestation": _spec(
        changed=("combat", "enemytype", "enemytrust", "canRescue"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_beast", 'V.enemytype === "beast"', "hard"),
        ),
    ),
    "Forest Boar Rape": _spec(
        changed=("combat", "enemytype", "canRescue"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_beast", 'V.enemytype === "beast"', "hard"),
        ),
    ),
    "Street Dogs": _spec(
        changed=("combat", "enemytype", "location"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_beast", 'V.enemytype === "beast"', "hard"),
            ("location_town", 'V.location === "town"', "hard"),
        ),
    ),
    "Meadow Cave Sex": _spec(
        changed=("combat", "enemytype", "anusWetness"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_beast", 'V.enemytype === "beast"', "hard"),
        ),
    ),
    # Sea
    "Beach Cave": _spec(
        keys=("cave", "pursuit"),
        changed=("cave", "pursuit", "exposed", "stress"),
        checks=(("cave_key", '"cave" in V', "hard"),),
    ),
    "Sea Tentacles": _spec(
        changed=("combat", "enemytype", "tentacles", "area"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_tentacles", 'V.enemytype === "tentacles"', "hard"),
            ("location_sea", 'V.location === "sea"', "hard"),
        ),
    ),
    "Monster Test": _spec(
        changed=("combat", "enemytype", "area", "tentacles"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_tentacles", 'V.enemytype === "tentacles"', "hard"),
            ("location_sea", 'V.location === "sea"', "hard"),
        ),
    ),
    # Wraith / possession
    "Wraith Test Start": _spec(
        changed=("wraith", "abomination"),
        checks=(
            ("wraith_state_grew", "Object.keys(V.wraith || {}).length >= 3", "hard"),
        ),
    ),
    "Possessed Fight Test": _spec(
        keys=("possessed",),
        changed=("possessed", "wraith", "control"),
        checks=(("possessed_key", '"possessed" in V', "hard"),),
    ),
    # Brothel / group scenes
    "Brothel Dance": _spec(
        keys=("dance_place",),
        changed=("dancing", "dance_place", "dancelocation"),
        checks=(("dance_place_key", '"dance_place" in V', "hard"),),
    ),
    "The Pod": _spec(
        changed=("audiencepresent", "audiencemember", "combat"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_man", 'V.enemytype === "man"', "hard"),
            ("audience_present", "V.audiencepresent >= 1", "hard"),
        ),
    ),
    "Struggle": _spec(
        changed=("combat", "enemytype", "anusstate"),
        checks=(
            ("combat_on", "V.combat === 1", "hard"),
            ("enemy_struggle", 'V.enemytype === "struggle"', "hard"),
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Pure evaluation helpers (unit-testable without a browser)
# --------------------------------------------------------------------------- #


def parse_name_and_passage_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the shape of ``getNameAndPassage``'s observable result.

    The game writes ``T.link_name`` / ``T.link_passage``; the injected wrapper
    reports them as strings. Anything else (missing, null, empty, non-string)
    is a real failure and must not be papered over.
    """
    if not isinstance(payload, dict) or payload.get("ok") is False:
        error = (payload or {}).get("error") or (payload or {}).get("target_error")
        return {"ok": False, "error": str(error or "unreadable result")[:300]}
    name = payload.get("link_name")
    target = payload.get("link_passage")
    if not isinstance(name, str) or not name.strip():
        return {"ok": False, "error": "link_name missing/empty", "link_name": name}
    if not isinstance(target, str) or not target.strip():
        return {"ok": False, "error": "link_passage missing/empty", "link_passage": target}
    if payload.get("target_error"):
        return {"ok": False, "error": str(payload["target_error"])[:300]}
    return {"ok": True, "link_name": name.strip(), "link_passage": target.strip()}


def classify_unresolvable(error: str) -> str:
    """Verdict for a row whose target could not be resolved at all.

    An undefined-variable style failure means the fixture cannot drive this
    entry (``fixture_insufficient``); a genuinely empty target means there is
    nothing to play (``not_applicable``); anything else is a real break.
    """
    text = str(error or "").strip()
    low = text.lower()
    if not text:
        return "not_applicable"
    if any(marker in low for marker in ps.FIXTURE_MARKERS):
        return "fixture_insufficient"
    if "missing" in low and "empty" in low:
        return "not_applicable"
    if "empty target" in low:
        return "not_applicable"
    return "hard_fail"


def evaluate_invariants(battery: dict[str, Any] | None) -> dict[str, Any]:
    """Aggregate the JS invariant battery into a Python-side verdict input."""
    battery = battery or {}
    checks = battery.get("checks") or []
    violations = [str(v) for v in (battery.get("violations") or [])]
    notes = [str(v) for v in (battery.get("notes") or [])]
    failed = [
        {"name": str(c.get("name")), "detail": str(c.get("detail") or "")[:200]}
        for c in checks
        if isinstance(c, dict) and not c.get("ok")
    ]
    ok = bool(checks) and not failed and not violations
    detail_parts = [f"{c['name']}: {c['detail']}" for c in failed[:5]]
    detail_parts += violations[:5]
    return {
        "ok": ok,
        "failed_checks": failed,
        "violations": violations[:20],
        "notes": notes[:20],
        "stats": battery.get("stats") or {},
        "detail": "; ".join(detail_parts)[:600],
    }


def scan_variables(
    variables: dict[str, Any],
    *,
    depth_limit: int = 4,
    node_limit: int = 20000,
    violation_limit: int = 20,
) -> dict[str, Any]:
    """Python mirror of the depth-limited NaN/Infinity scan (fixture sanity)."""
    violations: list[str] = []
    stats = {"nodes": 0, "nan": 0, "infinity": 0, "truncated": False}
    seen: set[int] = set()
    stack: list[tuple[Any, str, int]] = [(variables, "", 0)]
    while stack:
        node, path, depth = stack.pop()
        if stats["nodes"] >= node_limit:
            stats["truncated"] = True
            break
        stats["nodes"] += 1
        if isinstance(node, bool) or node is None:
            continue
        if isinstance(node, float):
            if node != node:  # NaN
                stats["nan"] += 1
                if len(violations) < violation_limit:
                    violations.append(f"NaN at {path or '<root>'}")
            elif node in (float("inf"), float("-inf")):
                stats["infinity"] += 1
                if len(violations) < violation_limit:
                    violations.append(f"Infinity at {path or '<root>'}")
            continue
        if isinstance(node, int):
            continue
        if not isinstance(node, (dict, list)):
            continue
        marker = id(node)
        if marker in seen:
            continue
        seen.add(marker)
        if depth >= depth_limit:
            continue
        if isinstance(node, dict):
            for key, value in node.items():
                stack.append((value, f"{path}.{key}" if path else str(key), depth + 1))
        else:
            for index, value in enumerate(node):
                stack.append((value, f"{path}[{index}]", depth + 1))
    return {"ok": not violations, "violations": violations, "stats": stats}


def evaluate_spec_report(raw: dict[str, Any] | None, spec: dict[str, Any]) -> dict[str, Any]:
    """Turn the injected scenario-check payload into hard/soft failures."""
    raw = raw or {}
    hard: list[str] = []
    soft: list[str] = []
    evidence: dict[str, Any] = {
        "globals": [],
        "keys": [],
        "changed": [],
        "exprs": [],
    }
    for item in raw.get("globals") or []:
        record = {
            "name": str(item.get("name")),
            "type": str(item.get("type")),
            "ok": bool(item.get("ok")),
        }
        evidence["globals"].append(record)
        if not record["ok"]:
            hard.append(f"global missing: {record['name']}")
    for item in raw.get("keys") or []:
        record = {
            "name": str(item.get("name")),
            "type": str(item.get("type")),
            "ok": bool(item.get("ok")),
        }
        evidence["keys"].append(record)
        if not record["ok"]:
            hard.append(f"key missing: {record['name']}")
    changed_records = raw.get("changed") or []
    for item in changed_records:
        evidence["changed"].append(
            {
                "name": str(item.get("name")),
                "changed": bool(item.get("changed")),
                "detail": str(item.get("detail") or "")[:200],
            }
        )
    if changed_records and not any(item.get("changed") for item in changed_records):
        names = ", ".join(str(item.get("name")) for item in changed_records[:6])
        soft.append(f"no observed state change in: {names}")
    severity_by_name = {
        str(check.get("name")): str(check.get("severity") or "hard")
        for check in spec.get("checks") or []
    }
    for item in raw.get("exprs") or []:
        record = {
            "name": str(item.get("name")),
            "ok": bool(item.get("ok")),
            "value": item.get("value"),
            "error": item.get("error"),
        }
        evidence["exprs"].append(record)
        if record["ok"]:
            continue
        detail = f"{record['name']}: {record.get('error') or record.get('value') or 'false'}"
        if severity_by_name.get(record["name"], "hard") == "soft":
            soft.append(detail[:200])
        else:
            hard.append(detail[:200])
    if raw.get("eval_error"):
        hard.append(f"check evaluation failed: {raw['eval_error']}")
    return {
        "ok": not hard and not soft,
        "hard_failures": hard[:10],
        "soft_failures": soft[:10],
        "evidence": evidence,
        "detail": "; ".join((hard + soft)[:6])[:600],
    }


_UNREGISTERED_MACRO_RE = re.compile(
    r"macro\s*<<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>>\s*does not exist", re.IGNORECASE
)


def is_unregistered_debug_macro(widget_error: str, widget_list: list[Any]) -> bool:
    """True when the row's own widget text calls a macro this build lacks.

    In 0.5.11.9 the debug menu's "Pregnancy Progress Day/Week" rows call
    ``<<parasiteProgressDay>>`` while the game only defines a plain JS function
    of that name, so the row throws "macro <<parasiteProgressDay>> does not
    exist". That is an upstream debug-menu defect: it must be reported, but it
    is neither a render failure nor a DOL-X regression.
    """
    match = _UNREGISTERED_MACRO_RE.search(str(widget_error))
    if not match:
        return False
    name = match.group(1)
    return any(f"<<{name}" in str(widget) for widget in widget_list)


INTERACTIONS = ("scene", "state", "display")


def classify_interaction(
    *,
    location_before: Any,
    target: Any,
    target_is_function: bool = False,
    widgets_list: Iterable[Any] | None = None,
) -> str:
    """Classify one clickable debug row by what the click actually does.

    * ``display`` -- every widget source is blank (or there are none), so the
      click only navigates/renders (viewer pages such as ``Wardrobe`` /
      ``NNPC Parade``); no state delta is expected at all.
    * ``state`` -- the target is a function (in this build every one of the
      212 dynamic targets is ``stayOnPassageFn``, ``() => V.passage``) and it
      resolved to the current game location: an in-place operation whose
      effect, if any, lives in the variable tree.
    * ``scene`` -- the click navigates to a passage; widget code ran as a
      pre-jump step and is not required to leave a delta.

    Unknowns stay ``scene`` (the sweep already verifies the landing passage
    for every row), so a missing signal never silently upgrades a row.
    """
    sources = [str(w) for w in (widgets_list or [])]
    if not sources or all(not s.strip() for s in sources):
        return "display"
    location = None if location_before is None else str(location_before)
    resolved = None if target is None else str(target)
    if target_is_function and location is not None and resolved == location:
        return "state"
    return "scene"


def summarize_assignment_checks(
    checks: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Aggregate the JS ``__dolxAssignChecks`` payload for the verdict layer."""
    items = [c for c in (checks or []) if isinstance(c, dict)]
    checked = [c for c in items if c.get("checked")]
    failed = [
        {
            "path": str(c.get("path")),
            "op": str(c.get("op")),
            "expected": c.get("expected"),
            "actual": c.get("actual"),
        }
        for c in checked
        if not c.get("ok")
    ]
    unchecked = [
        {
            "path": str(c.get("path")),
            "op": str(c.get("op")),
            "reason": str(c.get("reason") or ""),
        }
        for c in items
        if not c.get("checked")
    ]
    return {
        "total": len(items),
        "checked": len(checked),
        "failed": failed,
        "unchecked": unchecked,
    }


def aggregate_scenario_verdict(
    *,
    probe: dict[str, Any] | None,
    target: str,
    timed_out: bool = False,
    row_report: dict[str, Any] | None = None,
    invariant_report: dict[str, Any] | None = None,
    spec_report: dict[str, Any] | None = None,
    not_applicable: str | None = None,
    interaction: str | None = None,
) -> tuple[str, str]:
    """Combine every per-row signal into the five-tier verdict + a detail string.

    Precedence: a fixture-blocked row stays ``fixture_insufficient`` unless a
    *real* corruption shows up (numeric/structural/landing), which is always a
    ``hard_fail``. Soft signals only downgrade a clean row.
    """
    probe = probe or {}
    row_report = row_report or {}
    invariant_report = invariant_report or {}
    spec_report = spec_report or {}
    details: list[str] = []

    if not_applicable:
        return "not_applicable", not_applicable[:400]

    landed = probe.get("passage")
    base_verdict, base_detail = ps.classify(probe, landed is not None, timed_out)
    if base_detail:
        details.append(base_detail)

    if target and landed is not None and str(landed) != str(target):
        return "hard_fail", (
            f"landed on {landed!r} instead of {target!r}"
            + ("; " + "; ".join(details) if details else "")
        )[:600]

    hard_items: list[str] = []
    soft_items: list[str] = []
    fixture_items: list[str] = []
    notes: list[str] = []

    if row_report.get("target_error"):
        target_error = str(row_report["target_error"])
        if classify_unresolvable(target_error) == "fixture_insufficient":
            fixture_items.append(f"getNameAndPassage: {target_error}")
        else:
            hard_items.append(f"getNameAndPassage: {target_error}")
    widget_error = row_report.get("widgets_error")
    if widget_error:
        low = str(widget_error).lower()
        if any(marker in low for marker in ps.FIXTURE_MARKERS):
            fixture_items.append(f"runWidgetsInsideLink: {widget_error}")
        elif is_unregistered_debug_macro(
            str(widget_error), list(row_report.get("widgets_list") or [])
        ):
            # Reported verbatim, but the row itself is broken in this build —
            # not a passage render failure and not a DOL-X regression.
            soft_items.append(
                f"upstream debug-menu defect (unregistered macro): {widget_error}"
            )
        else:
            hard_items.append(f"runWidgetsInsideLink threw: {widget_error}")
    elif int(row_report.get("widgets") or 0) > 0 and not (row_report.get("delta") or []):
        # The shallow summary misses nested writes; the deep snapshot + targeted
        # diff is the real evidence layer. Absence of any delta is a note, not a
        # failure: a debug click is not required to move a variable (RNG
        # rerolls, idempotent <<set>> writes, viewer pages). Parseable
        # assignments are still checked against their literal below.
        deep_delta = list(row_report.get("deep_delta") or [])
        if deep_delta:
            notes.append(
                f"delta visible only in deep snapshot ({len(deep_delta)} nested change(s))"
            )
        elif row_report.get("deep_delta_truncated"):
            notes.append("deep snapshot truncated; delta cannot be fully attributed")
        elif int(row_report.get("function_widgets") or 0) > 0:
            notes.append(
                f"{int(row_report.get('function_widgets'))} function widget(s) are not statically checkable"
            )
        elif interaction == "state":
            notes.append("state operation left no observable variable delta")
        elif interaction == "display":
            notes.append("display-only row (no executable widget source)")
        else:
            notes.append("pre-jump widgets left no observable variable delta")

    assignment = summarize_assignment_checks(row_report.get("assignment_checks"))
    for item in assignment["failed"][:4]:
        soft_items.append(
            "assignment check failed: ${path} ({op}) expected {expected!r} got {actual!r}".format(
                path=item["path"], op=item["op"], expected=item["expected"], actual=item["actual"]
            )
        )

    if invariant_report and not invariant_report.get("ok"):
        hard_items.append(f"invariant battery: {invariant_report.get('detail') or 'failed'}")
    if spec_report.get("hard_failures"):
        hard_items.append("scenario asserts: " + "; ".join(spec_report["hard_failures"][:4]))
    if spec_report.get("soft_failures"):
        soft_items.append("scenario asserts: " + "; ".join(spec_report["soft_failures"][:4]))

    if hard_items:
        return "hard_fail", "; ".join(details + hard_items)[:600]

    if fixture_items:
        return "fixture_insufficient", "; ".join(details + fixture_items)[:600]

    if base_verdict == "fixture_insufficient":
        return base_verdict, "; ".join(details)[:600] or "fixture insufficient"
    if base_verdict == "hard_fail":
        return base_verdict, "; ".join(details)[:600]

    if soft_items:
        return "soft_fail", "; ".join(details + notes + soft_items)[:600]
    if base_verdict == "soft_fail":
        return "soft_fail", "; ".join(details + notes)[:600]
    return "ok", "; ".join(details + notes)[:600]


def diff_scenarios(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Baseline diff keyed by (section, index) so duplicate targets still work."""
    def _key(entry: dict[str, Any]) -> str:
        return f"{entry.get('section')}#{entry.get('index')}"

    old = {_key(r): r for r in baseline.get("results", [])}
    new = {_key(r): r for r in report.get("results", [])}
    new_regressions: list[dict[str, Any]] = []
    fixed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    new_scenarios: list[dict[str, Any]] = []
    for key, entry in new.items():
        previous = old.get(key)
        record = {
            "key": key,
            "section": entry.get("section"),
            "index": entry.get("index"),
            "target": entry.get("target"),
        }
        if previous is None:
            new_scenarios.append({**record, "verdict": entry.get("verdict")})
            continue
        was = str(previous.get("verdict"))
        now = str(entry.get("verdict"))
        if was == now:
            continue
        was_sev = VERDICT_SEVERITY.get(was, 2)
        now_sev = VERDICT_SEVERITY.get(now, 2)
        if now_sev > was_sev:
            new_regressions.append({**record, "was": was, "now": now})
        elif now == "ok":
            fixed.append({**record, "was": was, "now": now})
        else:
            changed.append({**record, "was": was, "now": now})
    baseline_manifest = baseline.get("manifest") or {}
    report_manifest = report.get("manifest") or {}
    manifest_diff = {
        "rows": {
            "baseline": baseline_manifest.get("summary", {}).get("rows"),
            "current": report_manifest.get("summary", {}).get("rows"),
        },
        "clickable": {
            "baseline": baseline_manifest.get("summary", {}).get("clickable"),
            "current": report_manifest.get("summary", {}).get("clickable"),
        },
    }
    manifest_diff["changed"] = any(
        item["baseline"] != item["current"] for item in manifest_diff.values()
    )
    return {
        "new_regressions": new_regressions,
        "fixed": fixed,
        "changed": changed,
        "new_scenarios": new_scenarios,
        "manifest": manifest_diff,
    }


def default_out_dir(suite: str, day: str | None = None) -> Path:
    """``.local/sweep/<suite>-<date>/`` as promised by the design."""
    stamp = day or time.strftime("%Y%m%d")
    return DEFAULT_OUT_ROOT / f"{suite}-{stamp}"


def baseline_path(fixture: Path | None, suite: str) -> Path:
    stem = Path(fixture).stem if fixture else "nofx"
    name = "scenario-sweep" if suite in ("scenarios", "all") else "dayloop"
    return DEFAULT_BASELINE_DIR / f"{name}-{stem}.json"


def manifest_baseline_path(fixture: Path | None) -> Path:
    stem = Path(fixture).stem if fixture else "nofx"
    return DEFAULT_BASELINE_DIR / f"scenario-manifest-{stem}.json"


# --------------------------------------------------------------------------- #
# Dayloop
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class DayloopStep:
    """One step of the real-UI day.

    ``target_passages`` is the structured goal: navigation prefers a link whose
    ``data-passage`` names it and only falls back to the label text. A
    ``completion="effect"`` step is *not* finished by arriving -- it needs one
    more click that matches ``action_keywords`` and consumes at least
    ``min_minutes`` of in-game clock, so "entered the bathroom" can never be
    reported as "washed".
    """

    name: str
    keywords: tuple[str, ...]
    target_passages: tuple[str, ...] = ()
    waypoints: tuple[str, ...] = ()
    action_keywords: tuple[str, ...] = ()
    min_minutes: int = 0
    completion: str = "passage"


# 2026-10-08 rewrite. The old table was pure keyword matching, so the day
# "completed" on entering the bathroom and then died at the first step whose
# label the current passage did not carry (7:00 Sunday start, 0.03h advanced).
# Targets now come from the artifact's own passage names (verified in the
# 0.5.11.9 build: Orphanage Intro -> Bedroom -> Bathroom -> ...
# -> Leave orphanage -> Domus Street -> Harvest Street -> School Front
# Courtyard -> ... -> Bedroom -> Sleep).
DAYLOOP_STEPS: tuple[DayloopStep, ...] = (
    DayloopStep(
        "起床",
        ("继续", "起床", "醒来", "wake", "get up", "continue"),
        target_passages=("Bedroom",),
    ),
    DayloopStep(
        "洗漱",
        ("浴室", "洗漱", "洗澡", "bathroom", "wash", "shower"),
        target_passages=("Bathroom",),
        action_keywords=(
            "洗澡", "沐浴", "淋浴", "洗脸", "刷牙", "洗个",
            "shower", "wash", "bathe", "brush",
        ),
        min_minutes=1,
        completion="effect",
    ),
    DayloopStep(
        "早餐",
        ("厨房", "早餐", "吃点", "kitchen", "breakfast", "食堂", "canteen"),
        target_passages=("Kitchen", "Canteen"),
        action_keywords=(
            "吃", "早餐", "进食", "面包", "麦片", "烹饪", "做点",
            "eat", "breakfast", "cereal", "toast", "cook", "meal",
            "买", "购买", "餐", "buy", "purchase",
        ),
        min_minutes=1,
        completion="effect",
    ),
    DayloopStep(
        "出门",
        ("离开", "出门", "离开孤儿院", "leave", "domus street", "出门去"),
        target_passages=("Domus Street",),
        # Verified 2026-10-08 (probe_dayloop_ui): the orphanage hall shows a
        # random event first; the leave link lives in Bedroom, and the hall
        # link lives in Kitchen. The waypoints let the driver walk the
        # Kitchen -> Orphanage -> Bedroom -> street chain when the current
        # room has no direct street link.
        waypoints=("Orphanage", "Bedroom"),
    ),
    DayloopStep(
        "上学",
        ("学校", "上学", "school"),
        target_passages=("School Front Courtyard", "School"),
        waypoints=("Barb Street", "Oxford Street"),
    ),
    DayloopStep(
        "上课",
        ("上课", "课程", "lesson", "class", "教室"),
        target_passages=("Hallways", "School Front Courtyard"),
        action_keywords=(
            "上课", "课程", "课时", "教室", "lesson", "class", "attend",
            "科学", "数学", "语文", "历史", "家务", "Science", "Maths",
            "English", "History", "Housekeeping",
        ),
        min_minutes=15,
        completion="effect",
    ),
    DayloopStep(
        "放学",
        ("放学", "离开学校", "leave school", "after school", "go home"),
        target_passages=("Domus Street",),
        waypoints=("School Front Courtyard", "Oxford Street", "Barb Street"),
    ),
    DayloopStep(
        "回家",
        ("孤儿院", "回家", "家", "orphanage", "home", "卧室", "bedroom", "大厅"),
        target_passages=("Bedroom",),
        waypoints=("Orphanage",),
    ),
    DayloopStep(
        "睡觉",
        ("睡觉", "爬上床", "床", "sleep", "bed"),
        # Verified 2026-10-08: "睡8小时" lives in the ``Bed`` passage, so the
        # step must reach the bed first and then spend the night.
        target_passages=("Bed",),
        waypoints=("Bedroom",),
        action_keywords=("睡觉", "睡", "sleep", "bed", "上床"),
        min_minutes=60,
        completion="effect",
    ),
)

# Only used when a step's own keywords are absent: walk one hop back inside the
# current location (e.g. Bathroom -> Bedroom) so a step is not declared
# unreachable just because the previous step left the player in a side room.
# Fallback hops are recorded but never count as step completion, and the set
# deliberately excludes a generic "继续/continue": a self-looping passage (the
# combat Tutorial) would otherwise masquerade as a finished step.
DAYLOOP_FALLBACK_KEYWORDS: tuple[str, ...] = (
    "返回",
    "回到",
    "back",
    "return",
    # The unkeyed orphanage exits and street connectors in the 0.5.11.9 build
    # (verified 2026-10-08): "安全返回" / "后退".
    "安全返回",
    "后退",
)

# Keys whose values are expected to move across a save/load round trip (save
# bookkeeping, render counters, RNG bookkeeping). The round trip verdict is the
# *core* comparison; the exact comparison is still recorded.
ROUNDTRIP_VOLATILE_KEYS: tuple[str, ...] = (
    "timeStamp",
    "saveId",
    "saveName",
    "passageCount",
    "passageChangesCount",
    "passagePrev",
    "orgasmdown",
    "rng",
    "lastgenerated",
    "index",
    "event",
)

# A save round trip must preserve these; the artifact's own load path re-runs
# mod bootstrap (which can legitimately *add* keys like mod option caches), so
# the assertion samples stable state instead of demanding a byte-identical set.
ROUNDTRIP_CORE_KEYS: tuple[str, ...] = (
    "money",
    "pain",
    "arousal",
    "stress",
    "trauma",
    "awareness",
    "physique",
    "tiredness",
    "hunger",
    "thirst",
    "purity",
    "willpower",
    "worn",
    "player",
    "location",
)

# Variables the dayloop preparation itself changes (Time.timeTravel sets the
# calendar, options.combatControls is normalised to the string form). A click
# never legitimately rewinds the clock, so a negative minute delta is treated
# as a state rewind by the effect phase.
DAYLOOP_REWIND_MINUTES = 0.0


def dayloop_match(link_text: str, keywords: Iterable[str]) -> str | None:
    """Return the first keyword contained in the link text (case-insensitive)."""
    haystack = str(link_text or "").lower()
    for keyword in keywords:
        if str(keyword).lower() in haystack:
            return str(keyword)
    return None


def dayloop_pick(links: list[dict[str, Any]], keywords: Iterable[str]) -> dict[str, Any] | None:
    """Pick the first *visible* clickable link whose text matches a keyword."""
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        matched = dayloop_match(str(link.get("text") or ""), keywords)
        if matched:
            return {
                "index": index,
                "text": str(link.get("text") or ""),
                "matched": matched,
                "data_passage": link.get("data"),
            }
    return None


DAYLOOP_LINK_RE = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
DAYLOOP_COST_RE = re.compile(r"\((\d+):([0-5]\d)\)")


def dayloop_cost_minutes(text: str) -> int | None:
    """Minutes stated in a DoL link label such as ``Bathroom (0:01)``."""
    match = DAYLOOP_COST_RE.search(str(text or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def dayloop_pick_target(
    links: list[dict[str, Any]], targets: Iterable[str]
) -> dict[str, Any] | None:
    """Pick a visible link whose ``data-passage`` is one of ``targets``.

    This is the structured navigation channel: it does not care what the link
    is called in the current locale.
    """
    wanted = [str(target) for target in targets if target]
    if not wanted:
        return None
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        data = str(link.get("data") or "").strip()
        if data and data in wanted:
            return {
                "index": index,
                "text": str(link.get("text") or ""),
                "matched": data,
                "data_passage": data,
                "structured": True,
            }
    return None


def dayloop_pick_effect(
    links: list[dict[str, Any]], keywords: Iterable[str]
) -> dict[str, Any] | None:
    """Pick the matching effect link that costs the most in-game time.

    ``Sleep for 8 hours`` must win over ``Sleep for 1 hour`` so the day really
    advances; the stated ``(H:MM)`` cost is the only ordering signal needed.
    """
    keywords = tuple(keywords)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        text = str(link.get("text") or "")
        matched = dayloop_match(text, keywords)
        if not matched:
            continue
        cost = dayloop_cost_minutes(text) or 0
        picked = dict(link)
        picked.update(
            {
                "index": index,
                "text": text,
                "matched": matched,
                "data_passage": link.get("data"),
                "cost_minutes": cost,
            }
        )
        candidates.append((-cost, index, picked))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2]


def dayloop_resolve_pick(
    links: list[dict[str, Any]],
    current_passage: str,
    static_links: Mapping[str, Sequence[str]],
) -> dict[str, Any] | None:
    """Pick an on-screen event whose passage leads back to the current one.

    Verified 2026-10-08 (probe_kitchen): the orphanage hall renders a random
    event ("Home Orphan Poster") whose links leave and then return, and the
    real hall exits only appear afterwards. Resolving such an event is
    navigation, so the caller records it as a fallback, never as step
    completion. Round-trip events are preferred; if none is provable the first
    visible passage link that is not the current passage is offered instead
    (still recorded, still bounded by the step's click budget).
    """
    if not current_passage:
        return None
    fallback: dict[str, Any] | None = None
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        data = str(link.get("data") or "").strip()
        if not data or data == current_passage:
            continue
        pick = {
            "index": index,
            "text": str(link.get("text") or ""),
            "matched": data,
            "data_passage": data,
        }
        targets = [str(item) for item in (static_links.get(data) or [])]
        if current_passage in targets:
            pick["event_roundtrip"] = True
            return pick
        if fallback is None:
            fallback = pick
    return fallback


DAYLOOP_WINDOW_TOKENS: tuple[str, ...] = (
    "属性", "特质", "社交", "日志", "统计", "成就", "选项", "存档", "设置",
    "衣柜", "态度", "人物", "保存", "加载", "游戏设置", "昵称", "调色",
    "换装", "重生", "导出", "作弊", "言灵", "特质",
    # Tutorial-only links (verified 2026-10-08): the scripted continuation is
    # labelled "下一段" and must be clicked through to finish the tutorial.
    "下一段",
)


def dayloop_window_pick(
    current_passage: str,
    step: "DayloopStep",
    links: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick a chrome/window link that is known not to advance the clock.

    Verified 2026-10-08 (probe_kitchen): ``Orphanage`` renders a random event
    first and the real hall exits only appear afterwards; some of those exits
    are entry doors that need a key and are dead ends without one. This helper
    therefore only ever offers chrome links (clothing/options/attitude/...)
    that the game itself opens as replacement panels -- they are recorded as
    fallback navigation and never as step completion.
    """
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        text = str(link.get("text") or "")
        data = str(link.get("data") or "").strip()
        if data == current_passage or not text:
            continue
        if any(token and token in text for token in DAYLOOP_WINDOW_TOKENS):
            return {
                "index": index,
                "text": text,
                "matched": text,
                "data_passage": data or None,
                "window": True,
            }
    return None


DAYLOOP_EXIT_KEYWORDS: tuple[str, ...] = (
    "离开孤儿院", "离开", "出门", "leave", "exit",
)


def dayloop_exit_pick(links: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the orphanage's own exit link regardless of its current label."""
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        text = str(link.get("text") or "")
        matched = dayloop_match(text, DAYLOOP_EXIT_KEYWORDS)
        if matched:
            return {
                "index": index,
                "text": text,
                "matched": matched,
                "data_passage": link.get("data"),
            }
    return None


DAYLOOP_TUTORIAL_ADVANCE: tuple[str, ...] = ("结束教程", "Finish", "结束", "完成")


def dayloop_tutorial_advance_pick(links: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the tutorial's own continuation link.

    Verified 2026-10-08 (``Tutorial`` body + ``Tutorial Finish`` body): the
    first scripted page shows the text with no action radios; the only way
    forward is its ``"<Tutorial Finish|Tutorial>"`` continuation link, and the
    next page exits through ``$tutorialExit``. This helper is only consulted
    while ``$tutorial`` is still 0 (the caller gates on the probe's combat
    flag), so it can never touch an ordinary combat turn.
    """
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        text = str(link.get("text") or "")
        data = str(link.get("data") or "")
        matched = dayloop_match(text, DAYLOOP_TUTORIAL_ADVANCE)
        if matched or data == "Tutorial Finish":
            return {
                "index": index,
                "text": text,
                "matched": matched or data,
                "data_passage": data or None,
                "tutorial": True,
            }
    return None


DAYLOOP_SCRIPTED_PASSAGES: tuple[str, ...] = (
    "Tutorial Finish",
    "Tutorial Flirt",
    "Tutorial Thank",
)


def dayloop_scripted_pick(
    passage: str, links: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Pick the scripted Tutorial continuation after its combat has ended.

    Verified 2026-10-08 (``Tutorial Finish`` / ``Tutorial Flirt`` bodies): the
    chain is ``Tutorial`` (combat) -> ``Tutorial Finish`` -> ``Tutorial Flirt``
    or ``Tutorial Thank`` -> ``$tutorialExit`` (Domus Street). Only consulted
    for the named scripted passages while ``combat`` is 0, so ordinary combat
    turns and the stuck-Tutorial regression case are never touched.
    """
    if str(passage) not in DAYLOOP_SCRIPTED_PASSAGES:
        return None
    fallback: dict[str, Any] | None = None
    for index, link in enumerate(links):
        if not link.get("visible", True):
            continue
        data = str(link.get("data") or "").strip()
        text = str(link.get("text") or "")
        if not data or data == passage:
            continue
        pick = {
            "index": index,
            "text": text,
            "matched": data,
            "data_passage": data,
            "scripted": True,
        }
        if data.startswith("Tutorial"):
            return pick
        if fallback is None:
            fallback = pick
    return fallback


# Action preference for an automatic combat turn: escape first (the scripted
# Tutorial rescues the player on a scream), then plain attacks, then whatever
# the game offers. The label is matched case-insensitively on either locale.
DAYLOOP_COMBAT_PREFERENCE: tuple[str, ...] = (
    "尖叫",
    "呼救",
    "scream",
    "shout",
    "攻击",
    "击退",
    "attack",
    "fight",
)

# Hard bound for one encounter; a real combat turn is ~1-3 s of wall clock, so
# 40 rounds cannot mask a stuck fight as progress.
DAYLOOP_COMBAT_MAX_ROUNDS = 40


def dayloop_combat_choice(
    options: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Choose one offered combat action radio, preferring escape over attack."""
    usable = [opt for opt in options if str(opt.get("id") or "")]
    for token in DAYLOOP_COMBAT_PREFERENCE:
        lowered = token.lower()
        for opt in usable:
            if lowered in str(opt.get("label") or "").lower():
                return opt
    return usable[0] if usable else None


def dayloop_minutes_between(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> float | None:
    """In-game minutes between two probe clocks (None when unmeasurable)."""
    before = before or {}
    after = after or {}
    old_ms = before.get("dateMs")
    new_ms = after.get("dateMs")
    if isinstance(old_ms, (int, float)) and isinstance(new_ms, (int, float)):
        return (float(new_ms) - float(old_ms)) / 60000.0
    old_day = before.get("dayOfYear")
    new_day = after.get("dayOfYear")
    old_sec = before.get("secondsSinceMidnight")
    new_sec = after.get("secondsSinceMidnight")
    if all(
        isinstance(value, (int, float))
        for value in (old_day, new_day, old_sec, new_sec)
    ):
        day_delta = (float(new_day) - float(old_day)) % 365 if new_day != old_day else 0.0
        return (day_delta * 86400.0 + (float(new_sec) - float(old_sec))) / 60.0
    return None


def dayloop_link_targets(body: str) -> list[str]:
    """Passage names a body links to, in document order (``[[label|Target]]``)."""
    targets: list[str] = []
    for match in DAYLOOP_LINK_RE.finditer(str(body or "")):
        target = str(match.group(2) or match.group(1) or "").strip()
        if target and target not in targets:
            targets.append(target)
    return targets


def dayloop_static_links(passages: Mapping[str, str]) -> dict[str, list[str]]:
    return {
        str(name): dayloop_link_targets(body) for name, body in passages.items()
    }


def dayloop_path(
    start: str,
    goal: str,
    links: Mapping[str, Sequence[str]],
    *,
    max_depth: int = 6,
) -> list[str]:
    """Shortest passage path from ``start`` to ``goal`` (goal excluded start)."""
    if not start or not goal or start == goal:
        return []
    queue: collections.deque[tuple[str, list[str]]] = collections.deque([(start, [])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for nxt in links.get(node) or []:
            if nxt in seen:
                continue
            if nxt == goal:
                return path + [nxt]
            seen.add(nxt)
            queue.append((nxt, path + [nxt]))
    return []


# Verdict vocabulary for a single dayloop click. ``ok`` is the only status that
# counts as step completion; ``fallback``/``stalled``/``not_applicable`` are
# honest non-completions and ``soft_fail`` means the click itself did not land.
DAYLOOP_CLICK_STATUSES: tuple[str, ...] = (
    "ok",
    "fallback",
    "stalled",
    "progress",
    "unknown",
    "soft_fail",
    "not_applicable",
)


def dayloop_click_status(
    *,
    clicked_ok: bool,
    waited: bool,
    fallback: bool,
    moved: bool,
) -> str:
    """Classify one dayloop click without ever turning movement into a pass.

    ``ok`` requires the step's *own* keyword to have matched, the passage
    display hook to have fired, and the game to have actually progressed
    (passage change or in-game clock advance). A fallback hop is navigation
    only, and an own-keyword click that changes nothing is ``stalled``.
    """
    if not clicked_ok or not waited:
        return "soft_fail"
    if fallback:
        return "fallback"
    if not moved:
        return "stalled"
    return "ok"


def dayloop_clock_moved(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> bool:
    """True when any in-game clock basis moved between two probes."""
    before = before or {}
    after = after or {}
    for key in ("dateMs", "dayOfYear", "secondsSinceMidnight"):
        old = before.get(key)
        new = after.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != new:
            return True
    return False


def dayloop_missing_step_record(
    step_name: str,
    keywords: Iterable[str],
    passage: str,
    *,
    step_index: int = 0,
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    """The honest record for a step whose entry link was not reachable."""
    keyword_list = [str(keyword) for keyword in keywords]
    return {
        "step": step_name,
        "step_index": step_index,
        "click_index": 0,
        "keyword_hits": [],
        "keywords": keyword_list,
        "passage_before": str(passage or ""),
        "passage_after": str(passage or ""),
        "clicked_text": None,
        "matched_link": None,
        "data_passage": None,
        "elapsed_ms": int(elapsed_ms),
        "status": "not_applicable",
        "detail": (
            f"当前 passage={passage}，未找到匹配 "
            + "/".join(keyword_list[:4])
            + " 的链接"
        ),
    }


def dayloop_time_advance(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compute hours advanced from the Time getters (monotonic, honest)."""
    def _num(mapping: dict[str, Any], key: str) -> float | None:
        value = (mapping or {}).get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    start_ms = _num(before, "dateMs")
    end_ms = _num(after, "dateMs")
    if start_ms is not None and end_ms is not None:
        return {
            "ok": True,
            "hours": (end_ms - start_ms) / 3_600_000.0,
            "method": "Time.date.getTime()",
        }
    start_day = _num(before, "dayOfYear")
    end_day = _num(after, "dayOfYear")
    start_sec = _num(before, "secondsSinceMidnight")
    end_sec = _num(after, "secondsSinceMidnight")
    if None not in (start_day, end_day, start_sec, end_sec):
        delta = (end_day - start_day) * 86400.0 + (end_sec - start_sec)
        if delta < 0:
            delta += 365 * 86400.0
        return {"ok": True, "hours": delta / 3600.0, "method": "dayOfYear+secondsSinceMidnight"}
    return {
        "ok": False,
        "hours": None,
        "method": None,
        "error": "Time.date/dayOfYear/secondsSinceMidnight unavailable",
    }


def roundtrip_digest_diff(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    volatile_keys: Iterable[str] = ROUNDTRIP_VOLATILE_KEYS,
    sample_keys: Iterable[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Compare two State.variables summaries after a save/load round trip."""
    before = before or {}
    after = after or {}
    volatile = set(volatile_keys)
    sample = set(sample_keys or [])
    differences: list[dict[str, Any]] = []
    core_differences: list[str] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old == new:
            continue
        if len(differences) < limit:
            differences.append({"path": key, "before": old, "after": new})
        in_sample = key in sample or (sample and key.split(".", 1)[0].split("[", 1)[0] in sample)
        if sample:
            if in_sample:
                core_differences.append(key)
        elif key not in volatile:
            core_differences.append(key)
    return {
        "exact_equal": not differences,
        "core_equal": not core_differences,
        "sample_keys": sorted(sample),
        "core_differences": core_differences[:limit],
        "differences": differences,
    }


TIME_HELPER_JS = r"""
  const __dolxTime = () => {
    const out = {};
    const num = (fn) => {
      try { const v = fn(); return typeof v === "number" && isFinite(v) ? v : null; } catch (e) { return null; }
    };
    try {
      const T = window.Time;
      if (T) {
        out.hour = num(() => T.hour);
        out.minute = num(() => T.minute);
        out.month = num(() => T.month);
        out.year = num(() => T.year);
        out.dayOfYear = num(() => T.dayOfYear);
        out.secondsSinceMidnight = num(() => T.secondsSinceMidnight);
        out.dateMs = num(() => T.date.getTime());
        try { out.weekDayName = String(T.weekDayName); } catch (e) {}
        try { out.schoolDay = Boolean(T.schoolDay); } catch (e) {}
      }
    } catch (e) { out.error = String(e && e.message ? e.message : e).slice(0, 200); }
    return out;
  };
"""


DAYLOOP_PROBE = (
    r"""
() => {
  const SC = window.SugarCube;
  const S = window.__DOLX__ || {};
  const out = { passage: null, time: {}, links: [], node: null, errors: [] };
  try { out.passage = SC.State.passage; } catch (e) {}
  try { out.combat = Number(SC.State.variables.combat) || 0; } catch (e) { out.combat = null; }
"""
    + TIME_HELPER_JS
    + r"""
  out.time = __dolxTime();
  const selectors = ["#passage-content", "#passage", ".passage[data-passage]", "#passages .passage"];
  let node = null;
  for (const sel of selectors) { const el = document.querySelector(sel); if (el) { node = el; out.node = sel; break; } }
  if (node) {
    const clickable = node.querySelectorAll("a, .link-internal, .macro-link, button");
    for (const el of Array.from(clickable).slice(0, 120)) {
      out.links.push({
        text: (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
        data: el.getAttribute ? String(el.getAttribute("data-passage") || "") : "",
        cls: String(el.className || "").slice(0, 80),
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      });
    }
  }
  try { out.errors = (S.errors || []).slice(-50); } catch (e) { out.errors = []; }
  return out;
}
"""
)


DAYLOOP_CLICK = r"""
(payload) => {
  const SC = window.SugarCube;
  const S = window.__DOLX__ || {};
  const out = { ok: false, text: null, passage_before: null, error: null };
  try { out.passage_before = SC.State.passage; } catch (e) {}
  const selectors = ["#passage-content", "#passage", ".passage[data-passage]", "#passages .passage"];
  let node = null;
  for (const sel of selectors) { const el = document.querySelector(sel); if (el) { node = el; break; } }
  if (!node) { out.error = "no passage node"; return out; }
  const clickable = Array.from(node.querySelectorAll("a, .link-internal, .macro-link, button"));
  const el = clickable[payload.index];
  if (!el) { out.error = "link index out of range: " + payload.index + " of " + clickable.length; return out; }
  out.text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120);
  S.done = false;
  S.renderSeq = 0;
  try { el.click(); out.ok = true; } catch (e) { out.error = "click threw: " + String(e && e.message ? e.message : e).slice(0, 200); }
  return out;
}
"""


# The Tutorial and random street encounters are real combat turns: the actions
# are ``input.macro-radiobutton`` elements inside ``#listContainer`` and the
# confirm control is the ``#next`` link (``<<nexttext>>``). ``combatControls``
# is a *string* control-type name ("radio", "columnRadio", "lists",
# "limitedLists"), never a number: writing a number breaks
# ``$options.combatControls.includes(...)`` and the whole action list renders as
# an ``error-view`` box instead of radios (verified 2026-10-08).
DAYLOOP_COMBAT_OPTIONS = r"""
() => {
  const out = { passage: null, combat: null, options: [], next: null, errors: [] };
  const SC = window.SugarCube;
  try { out.passage = SC.State.passage; } catch (e) {}
  try { out.combat = Number(SC.State.variables.combat) || 0; } catch (e) { out.combat = null; }
  try {
    const radios = Array.from(document.querySelectorAll("#listContainer input.macro-radiobutton"));
    out.options = radios.map((el) => {
      const label = el.closest ? el.closest("label") : null;
      return {
        id: String(el.id || ""),
        label: ((label && label.innerText) || el.value || "").replace(/\s+/g, " ").trim().slice(0, 100),
        checked: !!el.checked,
      };
    });
  } catch (e) { out.errors.push("options: " + String(e && e.message ? e.message : e).slice(0, 160)); }
  const next = document.querySelector("#next a") || document.querySelector("#next .link-internal");
  out.next = next ? (next.innerText || "").replace(/\s+/g, " ").trim().slice(0, 60) : null;
  return out;
}
"""


DAYLOOP_COMBAT_CLICK = r"""
(payload) => {
  const out = { ok: false, id: payload.id, radio_clicked: false, next_clicked: false, text: null, error: null };
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  let el = null;
  try { el = document.getElementById(payload.id); } catch (e) { el = null; }
  if (!el) { out.error = "action radio missing: " + payload.id; return out; }
  try {
    el.click();
    out.radio_clicked = true;
    const label = el.closest ? el.closest("label") : null;
    out.text = ((label && label.innerText) || "").replace(/\s+/g, " ").trim().slice(0, 100);
  } catch (e) { out.error = "radio click threw: " + String(e && e.message ? e.message : e).slice(0, 160); return out; }
  try {
    const next = document.querySelector("#next a") || document.querySelector("#next .link-internal");
    if (!next) { out.error = "no #next control to confirm the turn"; return out; }
    S.done = false;
    S.renderSeq = 0;
    next.click();
    out.next_clicked = true;
  } catch (e) { out.error = "next click threw: " + String(e && e.message ? e.message : e).slice(0, 160); return out; }
  out.ok = out.radio_clicked && out.next_clicked;
  return out;
}
"""


# Preparation for the day loop. The base artifact boots on a Sunday morning and
# Domus Street immediately starts the combat Tutorial; a lesson needs a school
# day and the street graph is only reachable after the Tutorial. Both are done
# through the game's own surfaces: ``$debug=1`` uses the debug menu's own
# "Next School" entry (``Time.timeTravel``), and the Tutorial's scripted
# continuation links are clicked in the real UI. The whole preparation runs in
# debug mode, the debug flag is cleared afterwards, and ``start_time`` is only
# captured once it finishes, so the clock jump can never inflate
# ``time_advance>=16h`` and the nine recorded steps are never debug traffic.
DAYLOOP_PREP = r"""
(payload) => {
  const out = { ok: false, via: null, before: null, after: null, logout_pending: false, errors: [] };
  const SC = window.SugarCube;
  const T = window.Time;
  const DT = (typeof DateTime !== "undefined") ? DateTime : window.DateTime;
  const num = (fn) => { try { const v = fn(); return typeof v === "number" && isFinite(v) ? v : null; } catch (e) { return null; } };
  const read = () => ({
    year: num(() => T.year), month: num(() => T.month), day: num(() => T.date.day),
    hour: num(() => T.hour), minute: num(() => T.minute),
    weekDayName: (() => { try { return String(T.weekDayName); } catch (e) { return null; } })(),
    schoolDay: (() => { try { return Boolean(T.schoolDay); } catch (e) { return null; } })(),
  });
  if (!T || !DT || !SC || !SC.State) { out.errors.push("Time/DateTime/SugarCube missing"); return out; }
  const V = SC.State.variables;
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  try {
    const debugBefore = num(() => V.debug);
    V.debug = 1;
    if (typeof T.set === "function") T.set();
    out.before = read();
    if (out.before.schoolDay === true && out.before.hour !== null && out.before.hour >= 5) {
      out.via = "already a school day";
    } else {
      let target = null;
      if (typeof T.getNextSchoolTermStartDate === "function") {
        const d = T.getNextSchoolTermStartDate();
        if (d && num(() => d.year) !== null) {
          target = new DT(d.year, d.month, d.day, payload.hour || 7, 0);
        }
      }
      if (!target) { out.errors.push("getNextSchoolTermStartDate unavailable"); }
      else {
        T.timeTravel(target);
        out.via = "Time.timeTravel(next school term start)";
      }
    }
    // The debug menu's own reset form sets the control mode while it is open;
    // leaving the mode at "Radio" keeps the school walk from opening a full
    // four-mode chooser on the way. The value is a control-type *string*: the
    // game calls ``$options.combatControls.includes(...)`` and a number makes
    // every combat action widget render an error box instead of radios.
    try { if (V.options) V.options.combatControls = "radio"; } catch (e) {}
    try { if ("combatControls" in V) V.combatControls = "radio"; } catch (e) {}
    // Rewind to the opening passage so the scripted tutorial continuation can
    // be clicked exactly like a player would (the street links only appear
    // after ``Tutorial Finish``).
    if (SC.State.passage === "Domus Street") {
      SC.Engine.play("Orphanage Intro");
      out.logout_pending = true;
    }
    out.after = read();
    out.ok = out.after.schoolDay === true;
    if (!out.ok) out.errors.push("schoolDay is still false after timeTravel");
    V.debug = debugBefore == null ? 0 : debugBefore;
  } catch (e) {
    out.errors.push(String(e && e.message ? e.message : e));
    try { if (SC.State.variables) SC.State.variables.debug = 0; } catch (e2) {}
  }
  return out;
}
"""


DAYLOOP_DIGEST = (
    r"""
() => {
  const SC = window.SugarCube;
  const V = SC.State.variables;
"""
    + SUMMARY_HELPER_JS
    + TIME_HELPER_JS
    + r"""
  const out = { passage: null, summary: null, time: null, error: null };
  try { out.passage = SC.State.passage; } catch (e) {}
  try { out.summary = __dolxSummary(V); } catch (e) { out.error = String(e && e.message ? e.message : e); }
  out.time = __dolxTime();
  return JSON.stringify(out);
}
"""
)


DAYLOOP_SAVE = r"""
(payload) => {
  const SC = window.SugarCube;
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  const out = { ok: false, via: null, error: null, serialized: null, slot_present: null, notes: [] };
  // Always stash a serialized snapshot: this is the explicit in-memory fallback
  // the design allows when the artifact's slot surface refuses to reload.
  try {
    if (SC.Save && typeof SC.Save.serialize === "function") {
      S.dayloopSaveJson = SC.Save.serialize();
      out.serialized = String(S.dayloopSaveJson).length;
    }
  } catch (e) { out.notes.push("serialize: " + String(e && e.message ? e.message : e).slice(0, 160)); }
  if (SC.Save && SC.Save.slots && typeof SC.Save.slots.save === "function") {
    try {
      const ok = SC.Save.slots.save(payload.slot, payload.title || "DOL-X dayloop");
      if (ok) { out.ok = true; out.via = "SC.Save.slots.save"; return out; }
      out.error = "SC.Save.slots.save returned false";
    } catch (e) { out.error = "SC.Save.slots.save threw: " + String(e && e.message ? e.message : e).slice(0, 200); }
  }
  if (typeof window.save === "function") {
    try {
      const V = SC.State.variables;
      const saveId = V.saveId == null ? 0 : V.saveId;
      if (typeof V.confirmSave === "boolean") V.confirmSave = false;
      window.save(payload.slot, true, saveId, payload.title || "DOL-X dayloop");
      try {
        out.slot_present = Boolean(SC.Save.slots.get && SC.Save.slots.get(payload.slot));
      } catch (e) { out.slot_present = null; }
      out.ok = out.slot_present !== false;
      out.via = "window.save (DoLSave)";
      if (!out.ok) out.error = "window.save did not leave a slot behind";
      return out;
    } catch (e) {
      // Known quirk: DoLSave.save can throw in its detail bookkeeping after the
      // slot has actually been written - probe the slot before giving up.
      out.notes.push("window.save threw: " + String(e && e.message ? e.message : e).slice(0, 200));
      try {
        const present = Boolean(SC.Save.slots.get && SC.Save.slots.get(payload.slot));
        if (present) { out.ok = true; out.slot_present = true; out.via = "window.save (slot present after throw)"; return out; }
      } catch (e2) {}
    }
  }
  if (typeof S.dayloopSaveJson === "string") {
    out.ok = true;
    out.via = "SC.Save.serialize (in-memory fallback)";
  }
  return out;
}
"""


DAYLOOP_LOAD = r"""
(payload) => {
  const SC = window.SugarCube;
  const S = window.__DOLX__ || {};
  const out = { ok: false, via: null, error: null };
  S.done = false;
  S.renderSeq = 0;
  if (typeof window.loadSave === "function") {
    try {
      if (typeof SC.State.variables.confirmLoad === "boolean") SC.State.variables.confirmLoad = false;
      window.loadSave(payload.slot);
      out.ok = true;
      out.via = "window.loadSave (DoLSave)";
      return out;
    } catch (e) { out.error = "window.loadSave threw: " + String(e && e.message ? e.message : e).slice(0, 200); }
  }
  if (SC.Save && SC.Save.slots && typeof SC.Save.slots.load === "function") {
    try {
      const ok = SC.Save.slots.load(payload.slot);
      if (ok) { out.ok = true; out.via = "SC.Save.slots.load"; return out; }
      out.error = "SC.Save.slots.load returned false";
    } catch (e) { out.error = "SC.Save.slots.load threw: " + String(e && e.message ? e.message : e).slice(0, 200); }
  }
  try {
    if (typeof S.dayloopSaveJson === "string" && SC.Save && typeof SC.Save.deserialize === "function") {
      SC.Save.deserialize(S.dayloopSaveJson);
      out.ok = true;
      out.via = "SC.Save.deserialize (in-memory fallback)";
      return out;
    }
  } catch (e) { out.error = (out.error ? out.error + "; " : "") + "deserialize threw: " + String(e && e.message ? e.message : e).slice(0, 200); }
  return out;
}
"""


def run_dayloop(
    page: Any,
    *,
    slot: Any = SLOT,
    max_clicks_per_step: int = 3,
    timeout_ms: int = 8000,
    settle_ms: int = 250,
    passages: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Click through one in-game day on the real UI; never fake a pass.

    Each step is a three-phase state machine:

    * **encounters** -- a live combat turn (the scripted street Tutorial or a
      random encounter) is played with a real action radio and the game's own
      ``#next`` confirm until ``$combat`` drops; the scripted ``Tutorial
      Finish`` / ``Tutorial Flirt`` / ``Tutorial Thank`` pages are clicked by
      their ``data-passage``. Encounter rounds are recorded but never counted
      as step completion.

    * **navigation** -- click real links until the probe reports the step's
      target passage. Structured navigation (``data-passage``) wins over label
      text, and the static passage map (``passages``) supplies the next hop
      when the target is more than one passage away. Navigation by itself is
      recorded as ``fallback`` and never completes a step.
    * **effect** -- for ``completion="effect"`` steps, click the action that
      costs in-game time (``洗澡 (1:00)``, ``Sleep for 8 hours``, ...) and
      require the clock to advance by at least ``min_minutes``. Arriving in the
      bathroom is never reported as having washed.

    Nothing here writes game state or jumps the clock: the only writes are
    clicks on real passage links.
    """
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    first = page.evaluate(DAYLOOP_PROBE)
    static_links = dayloop_static_links(passages or {})
    records: list[dict[str, Any]] = []
    visited: list[str] = [str(first.get("passage") or "")]
    save_report: dict[str, Any] | None = None
    saved_digest: dict[str, Any] | None = None
    save_at_passage: str | None = None
    hard_errors: list[dict[str, Any]] = []

    def probe(step_name: str) -> dict[str, Any]:
        data = page.evaluate(DAYLOOP_PROBE)
        for error in data.get("errors") or []:
            if error.get("kind") in ps.HARD_ERROR_KINDS:
                hard_errors.append(
                    {
                        "step": step_name,
                        "kind": error.get("kind"),
                        "message": str(error.get("message"))[:300],
                    }
                )
        return data

    def click_once(
        pick: dict[str, Any], *, fallback: bool, step_name: str
    ) -> dict[str, Any]:
        before = probe(step_name)
        passage_before = str(before.get("passage") or "")
        clicked = page.evaluate(DAYLOOP_CLICK, {"index": pick["index"]})
        waited = False
        if clicked.get("ok"):
            try:
                page.wait_for_function(
                    "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                    timeout=timeout_ms,
                )
                waited = True
            except Exception:  # noqa: BLE001 - a slow render is recorded, not fatal
                waited = False
        page.wait_for_timeout(settle_ms)
        after = page.evaluate(DAYLOOP_PROBE)
        passage_after = str(after.get("passage") or "")
        if passage_after and passage_after != passage_before:
            visited.append(passage_after)
        moved = passage_after != passage_before
        if not moved:
            moved = dayloop_clock_moved(before.get("time"), after.get("time"))
        return {
            "passage_before": passage_before,
            "passage_after": passage_after,
            "moved": moved,
            "minutes": dayloop_minutes_between(before.get("time"), after.get("time")),
            "clicked_ok": bool(clicked.get("ok")),
            "click_error": None if clicked.get("ok") else str(clicked.get("error"))[:200],
            "clicked_text": str(clicked.get("text") or pick.get("text") or "")[:120],
            "waited": waited,
            "click_status": dayloop_click_status(
                clicked_ok=bool(clicked.get("ok")),
                waited=waited,
                fallback=fallback,
                moved=moved,
            ),
        }

    def add_record(
        step: DayloopStep,
        step_index: int,
        step_started: float,
        click_index: int,
        pick: dict[str, Any],
        outcome: dict[str, Any],
        *,
        phase: str,
        status: str,
        detail: str,
    ) -> dict[str, Any]:
        record = {
            "step": step.name,
            "step_index": step_index,
            "click_index": click_index,
            "phase": phase,
            "keyword_hits": [pick.get("matched")],
            "keywords": list(step.keywords),
            "fallback_navigation": phase == "fallback",
            "passage_before": outcome["passage_before"],
            "passage_after": outcome["passage_after"],
            "clicked_text": outcome["clicked_text"],
            "matched_link": str(pick.get("text") or "")[:120],
            "data_passage": pick.get("data_passage"),
            "minutes_advanced": outcome["minutes"],
            "elapsed_ms": int((time.time() - step_started) * 1000),
            "status": status,
            "detail": detail,
        }
        records.append(record)
        return record

    # --- recorded preparation (debug pass) ----------------------------------- #
    # The artifact boots on a Sunday and Domus Street starts the combat
    # Tutorial; a lesson needs a school day and the Tutorial must be resolved
    # before the street graph opens.
    prep: dict[str, Any] = {
        "ran": False,
        "ok": None,
        "via": None,
        "before": None,
        "after": None,
        "logout_pending": None,
        "errors": [],
    }
    if (first.get("time") or {}).get("schoolDay") is False:
        prep["ran"] = True
        # The prep script flips ``$debug`` itself and restores the previous
        # value before it returns. The driver must not pre-set ``$debug``:
        # the street Tutorial only fires while ``$debug is 0``, so a leftover
        # 1 would silently skip the encounter and strand the whole day on
        # Domus Street (regression captured 2026-10-08).
        raw = page.evaluate(DAYLOOP_PREP, {"hour": 7})
        if isinstance(raw, dict):
            prep["ok"] = raw.get("ok")
            prep["via"] = raw.get("via")
            prep["before"] = raw.get("before")
            prep["after"] = raw.get("after")
            prep["logout_pending"] = raw.get("logout_pending")
            prep["errors"] = [str(item)[:200] for item in (raw.get("errors") or [])]
            if raw.get("logout_pending"):
                try:
                    page.wait_for_function(
                        "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                        timeout=timeout_ms,
                    )
                except Exception:  # noqa: BLE001 - the reprobe below records reality
                    pass
        else:
            prep["ok"] = False
            prep["errors"] = ["prep script returned no object"]
        first = page.evaluate(DAYLOOP_PROBE)
        prep["ok"] = bool(prep.get("ok")) and (
            (first.get("time") or {}).get("schoolDay") is True
        )
    start_time = dict(first.get("time") or {})
    visited[0] = str(first.get("passage") or "")

    for step_index, step in enumerate(DAYLOOP_STEPS):
        step_started = time.time()
        step_records: list[dict[str, Any]] = []
        current = probe(step.name)
        current_passage = str(current.get("passage") or "")

        # --- phase 0: live combat / scripted Tutorial continuation -------- #
        # The first street visit starts the scripted Tutorial (a real combat
        # passage) and streets can also throw random encounters. Leaving one
        # half-played would strand every later step, so each turn is played
        # with a real action radio + the game's own ``#next`` confirm, and the
        # scripted follow-up pages are clicked by their ``data-passage``.
        for _ in range(DAYLOOP_COMBAT_MAX_ROUNDS):
            combat = int(current.get("combat") or 0)
            if combat:
                options = page.evaluate(DAYLOOP_COMBAT_OPTIONS) or {}
                choice = dayloop_combat_choice(list(options.get("options") or []))
                if choice is None:
                    step_records.append(
                        add_record(
                            step,
                            step_index,
                            step_started,
                            len(step_records),
                            {
                                "index": -1,
                                "text": "",
                                "matched": None,
                                "data_passage": None,
                            },
                            {
                                "passage_before": current_passage,
                                "passage_after": current_passage,
                                "minutes": None,
                                "clicked_text": "",
                                "click_status": "not_applicable",
                            },
                            phase="combat",
                            status="not_applicable",
                            detail=(
                                f"combat turn in {current_passage} offered no action "
                                f"radios; next control={options.get('next')!r}"
                            )[:600],
                        )
                    )
                    pick = dayloop_tutorial_advance_pick(
                        list(current.get("links") or [])
                    )
                    if pick is None:
                        break
                else:
                    before = probe(step.name)
                    clicked = page.evaluate(
                        DAYLOOP_COMBAT_CLICK, {"id": choice.get("id")}
                    )
                    waited = False
                    if clicked.get("ok"):
                        try:
                            page.wait_for_function(
                                "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                                timeout=timeout_ms,
                            )
                            waited = True
                        except Exception:  # noqa: BLE001 - a slow turn is recorded, not fatal
                            waited = False
                    page.wait_for_timeout(settle_ms)
                    after = probe(step.name)
                    passage_before = str(before.get("passage") or "")
                    passage_after = str(after.get("passage") or "")
                    if passage_after and passage_after != passage_before:
                        visited.append(passage_after)
                    moved = passage_after != passage_before
                    if not moved:
                        moved = dayloop_clock_moved(
                            before.get("time"), after.get("time")
                        )
                    status = (
                        "progress"
                        if clicked.get("ok") and moved
                        else "stalled"
                    )
                    detail = (
                        f"combat action {str(choice.get('label'))!r}: "
                        f"{passage_before} -> {passage_after} (settled={waited})"
                        if clicked.get("ok")
                        else f"combat action failed: {str(clicked.get('error'))[:140]}"
                    )
                    step_records.append(
                        add_record(
                            step,
                            step_index,
                            step_started,
                            len(step_records),
                            {
                                "index": -1,
                                "text": str(choice.get("label") or ""),
                                "matched": str(choice.get("label") or ""),
                                "data_passage": None,
                            },
                            {
                                "passage_before": passage_before,
                                "passage_after": passage_after,
                                "minutes": dayloop_minutes_between(
                                    before.get("time"), after.get("time")
                                ),
                                "clicked_text": str(clicked.get("text") or ""),
                                "click_status": status,
                            },
                            phase="combat",
                            status=status,
                            detail=detail[:600],
                        )
                    )
                    current = after
                    current_passage = passage_after
                    if status == "stalled":
                        break
                    continue
            pick = dayloop_scripted_pick(
                current_passage, list(current.get("links") or [])
            )
            if pick is None:
                break
            outcome = click_once(pick, fallback=False, step_name=step.name)
            step_records.append(
                add_record(
                    step,
                    step_index,
                    step_started,
                    len(step_records),
                    pick,
                    outcome,
                    phase="tutorial",
                    status=(
                        "stalled"
                        if outcome["click_status"] == "stalled"
                        else "progress"
                    ),
                    detail=(
                        f"scripted tutorial continuation via {pick['matched']!r}: "
                        f"{outcome['passage_before']} -> {outcome['passage_after']}; "
                        "movement only, not counted as step completion"
                    )[:600],
                )
            )
            current = probe(step.name)
            current_passage = str(current.get("passage") or "")
            if outcome["click_status"] == "stalled":
                break
        if int(current.get("combat") or 0):
            step_records.append(
                add_record(
                    step,
                    step_index,
                    step_started,
                    len(step_records),
                    {
                        "index": -1,
                        "text": "",
                        "matched": None,
                        "data_passage": None,
                    },
                    {
                        "passage_before": current_passage,
                        "passage_after": current_passage,
                        "minutes": None,
                        "clicked_text": "",
                        "click_status": "stalled",
                    },
                    phase="combat",
                    status="stalled",
                    detail=(
                        f"combat still live in {current_passage} after "
                        f"{DAYLOOP_COMBAT_MAX_ROUNDS} recorded rounds"
                    ),
                )
            )

        navigated = (not step.target_passages) or current_passage in step.target_passages

        # --- phase 1: navigation ------------------------------------------ #
        if step.target_passages and not navigated:
            for _ in range(max_clicks_per_step):
                links = list(current.get("links") or [])
                pick = dayloop_pick_target(links, step.target_passages)
                if pick is None:
                    hop = ""
                    for target in step.target_passages:
                        path = dayloop_path(current_passage, target, static_links)
                        if path:
                            hop = path[0]
                            break
                    if hop:
                        pick = dayloop_pick_target(links, (hop,))
                if pick is None:
                    pick = dayloop_pick(links, step.keywords)
                if (
                    pick is None
                    and step.completion == "effect"
                    and step.name != "睡觉"
                ):
                    # School lessons are one-shot passages: the classroom entry
                    # itself is the effect link ("上课 (1:00)"), and the lesson
                    # is then finished from wherever that click lands. The bed
                    # action is the opposite case (Bedroom -> Bed must happen
                    # first), so it keeps the play-then-sleep order.
                    pick = dayloop_pick_effect(links, step.action_keywords or step.keywords)
                if pick is None:
                    pick = dayloop_window_pick(current_passage, step, links)
                if pick is None:
                    pick = dayloop_resolve_pick(links, current_passage, static_links)
                if pick is None and step.name == "出门":
                    pick = dayloop_exit_pick(links)
                if pick is None:
                    break
                outcome = click_once(pick, fallback=False, step_name=step.name)
                landed = str(outcome["passage_after"]) in step.target_passages
                navigated_now = str(outcome["passage_after"]) in (step.waypoints or ())
                effect_minutes = outcome["minutes"]
                if (
                    step.completion == "effect"
                    and effect_minutes is not None
                    and effect_minutes >= step.min_minutes
                ):
                    status = "ok"
                    detail = (
                        f"{pick['matched']!r} advanced {effect_minutes:.0f} min "
                        f"(required >= {step.min_minutes}); class entry "
                        f"{outcome['passage_before']} -> {outcome['passage_after']}"
                    )
                    step_records.append(
                        add_record(
                            step,
                            step_index,
                            step_started,
                            len(step_records),
                            pick,
                            outcome,
                            phase="effect",
                            status=status,
                            detail=detail,
                        )
                    )
                    current = probe(step.name)
                    break
                phase = "navigate"
                if pick.get("window") or pick.get("event_roundtrip"):
                    phase = "fallback"
                if outcome["click_status"] == "stalled":
                    status = "stalled"
                    detail = "click landed but neither the passage nor the in-game clock moved"
                elif landed and step.completion == "passage" and phase == "navigate":
                    status = "ok"
                    detail = f"reached {outcome['passage_after']}"
                elif navigated_now:
                    status = "fallback"
                    detail = (
                        f"waypoint navigation via {pick['matched']!r}: "
                        f"{outcome['passage_before']} -> {outcome['passage_after']}; "
                        "movement only, not counted as step completion"
                    )
                elif pick.get("window"):
                    status = "fallback"
                    detail = (
                        f"window link via {pick['matched']!r}: "
                        f"{outcome['passage_before']} -> {outcome['passage_after']}; "
                        "this game action did not advance the in-game clock"
                    )
                elif pick.get("event_roundtrip"):
                    status = "fallback"
                    detail = (
                        f"resolved an event via {pick['matched']!r}: "
                        f"{outcome['passage_before']} -> {outcome['passage_after']}; "
                        "navigation only, not counted as step completion"
                    )
                else:
                    status = "fallback"
                    detail = (
                        f"navigation only: {outcome['passage_before']} -> "
                        f"{outcome['passage_after']} (step target "
                        f"{list(step.target_passages)})"
                    )
                step_records.append(
                    add_record(
                        step,
                        step_index,
                        step_started,
                        len(step_records),
                        pick,
                        outcome,
                        phase=phase,
                        status=status,
                        detail=detail,
                    )
                )
                current = probe(step.name)
                current_passage = str(current.get("passage") or "")
                if landed and phase == "navigate":
                    navigated = True
                    break
                if status == "stalled":
                    break
            if not navigated:
                # One hop back inside the current location (e.g. Bathroom ->
                # Bedroom) so a side room cannot end the day. Recorded as
                # fallback: movement only, never step completion.
                pick = dayloop_pick(list(current.get("links") or []), DAYLOOP_FALLBACK_KEYWORDS)
                if pick is not None:
                    outcome = click_once(pick, fallback=True, step_name=step.name)
                    step_records.append(
                        add_record(
                            step,
                            step_index,
                            step_started,
                            len(step_records),
                            pick,
                            outcome,
                            phase="fallback",
                            status="fallback",
                            detail=(
                                f"fallback navigation via {pick['matched']!r}: "
                                "movement only, not counted as step completion"
                            ),
                        )
                    )
                    current = probe(step.name)
                    current_passage = str(current.get("passage") or "")
                    navigated = current_passage in step.target_passages

        # --- phase 2: effect ---------------------------------------------- #
        if step.completion == "effect" and navigated:
            effect_keywords = step.action_keywords or step.keywords
            for _ in range(max_clicks_per_step):
                links = list(current.get("links") or [])
                pick = dayloop_pick_effect(links, effect_keywords)
                if pick is None:
                    if not step_records:
                        step_records.append(
                            add_record(
                                step,
                                step_index,
                                step_started,
                                len(step_records),
                                {
                                    "index": -1,
                                    "text": "",
                                    "matched": None,
                                    "data_passage": None,
                                },
                                {
                                    "passage_before": current_passage,
                                    "passage_after": current_passage,
                                    "minutes": None,
                                    "clicked_text": "",
                                },
                                phase="effect",
                                status="not_applicable",
                                detail=(
                                    f"reached {current_passage} but no action matched "
                                    f"{list(effect_keywords)}; offered: "
                                    + ", ".join(
                                        str(link.get('text'))[:40]
                                        for link in links[:12]
                                    )
                                )[:600],
                            )
                        )
                    break
                outcome = click_once(pick, fallback=False, step_name=step.name)
                minutes = outcome["minutes"]
                if minutes is not None and minutes < DAYLOOP_REWIND_MINUTES:
                    # The click landed but the clock went backwards (a state
                    # rewind); never credit it as progress toward a step.
                    status = "stalled"
                    detail = (
                        f"{pick['matched']!r} moved the clock backwards "
                        f"({minutes:.0f} min); not counted as progress"
                    )
                    step_records.append(
                        add_record(
                            step,
                            step_index,
                            step_started,
                            len(step_records),
                            pick,
                            outcome,
                            phase="effect",
                            status=status,
                            detail=detail,
                        )
                    )
                    current = probe(step.name)
                    current_passage = str(current.get("passage") or "")
                    break
                advanced = minutes is not None and minutes >= step.min_minutes
                if advanced:
                    status = "ok"
                    detail = (
                        f"{pick['matched']!r} advanced {minutes:.0f} min "
                        f"(required >= {step.min_minutes})"
                    )
                elif outcome["click_status"] == "stalled":
                    status = "stalled"
                    detail = "effect click landed but nothing moved"
                else:
                    # ``None`` means the clock basis was missing, not that the
                    # action did nothing; an explicit 0 that fails the minimum
                    # is a genuine partial effect (e.g. one lesson of a longer
                    # block), which a later click in the same step can top up.
                    status = "progress" if minutes is not None else "unknown"
                    detail = (
                        f"{pick['matched']!r} advanced "
                        f"{'unknown' if minutes is None else f'{minutes:.0f}'} min "
                        f"(required >= {step.min_minutes})"
                    )
                step_records.append(
                    add_record(
                        step,
                        step_index,
                        step_started,
                        len(step_records),
                        pick,
                        outcome,
                        phase="effect",
                        status=status,
                        detail=detail,
                    )
                )
                current = probe(step.name)
                current_passage = str(current.get("passage") or "")
                if status == "ok":
                    break
                if status == "stalled":
                    break

        if not step_records and not navigated:
            records.append(
                dayloop_missing_step_record(
                    step.name,
                    step.keywords,
                    str(current.get("passage") or ""),
                    step_index=step_index,
                    elapsed_ms=int((time.time() - step_started) * 1000),
                )
            )
        if (
            save_report is None
            and step.name == "出门"
            and any(r["status"] == "ok" for r in step_records)
        ):
            digest = json.loads(page.evaluate(DAYLOOP_DIGEST))
            save_report = page.evaluate(DAYLOOP_SAVE, {"slot": slot, "title": "DOL-X dayloop"})
            saved_digest = digest
            save_at_passage = digest.get("passage")

    end_time = dict(page.evaluate(DAYLOOP_PROBE).get("time") or {})

    roundtrip: dict[str, Any] = {
        "attempted": False,
        "ok": False,
        "method": None,
        "error": "save point was never reached (出门 step did not land)",
        "before": None,
        "after": None,
    }
    if save_report and save_report.get("ok") and saved_digest is not None:
        load = page.evaluate(DAYLOOP_LOAD, {"slot": slot})
        loaded = False
        if load.get("ok"):
            try:
                page.wait_for_function(
                    "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                    timeout=timeout_ms,
                )
                loaded = True
            except Exception:
                loaded = False
        page.wait_for_timeout(settle_ms)
        after = json.loads(page.evaluate(DAYLOOP_DIGEST))
        same_passage = str(after.get("passage")) == str(save_at_passage)
        saved_time = dict((saved_digest or {}).get("time") or {})
        after_time = dict(after.get("time") or {})
        same_time = saved_time == after_time
        digest_diff = roundtrip_digest_diff(
            saved_digest.get("summary"),
            after.get("summary"),
            sample_keys=ROUNDTRIP_CORE_KEYS,
        )
        roundtrip = {
            "attempted": True,
            "ok": bool(
                load.get("ok")
                and loaded
                and same_passage
                and same_time
                and digest_diff["core_equal"]
            ),
            "method": load.get("via") or save_report.get("via"),
            "save_via": save_report.get("via"),
            "load_via": load.get("via"),
            "error": None if load.get("ok") else str(load.get("error"))[:300],
            "before": {"passage": save_at_passage},
            "after": {"passage": after.get("passage")},
            "same_passage": same_passage,
            "same_time": same_time,
            "time_before": saved_time,
            "time_after": after_time,
            "exact_equal": digest_diff["exact_equal"],
            "core_equal": digest_diff["core_equal"],
            "core_differences": digest_diff["core_differences"],
            "differences": digest_diff["differences"],
            "sample_keys": digest_diff["sample_keys"],
            "volatile_keys_ignored": list(ROUNDTRIP_VOLATILE_KEYS),
            "note": (
                "core comparison covers stable variables + Time; the artifact's "
                "load path re-runs mod bootstrap, which may add keys, so exact "
                "set equality is recorded but not required"
            ),
        }

    advance = dayloop_time_advance(start_time, end_time)
    switches = sum(1 for a, b in zip(visited, visited[1:]) if a != b)
    completed_steps = [r for r in records if r["status"] == "ok"]
    fallback_clicks = [r for r in records if r["status"] == "fallback"]
    stalled_clicks = [r for r in records if r["status"] == "stalled"]
    not_applicable_steps = [r for r in records if r["status"] == "not_applicable"]
    assertions = [
        {
            "name": "steps_completed>=1",
            "ok": bool(completed_steps),
            "detail": (
                f"{len(completed_steps)} ok, {len(fallback_clicks)} fallback, "
                f"{len(stalled_clicks)} stalled, {len(not_applicable_steps)} not applicable"
            ),
        },
        {
            "name": "time_advance>=16h",
            "ok": bool(advance.get("ok")) and float(advance.get("hours") or 0) >= 16.0,
            "detail": (
                f"{advance.get('hours'):.2f}h via {advance.get('method')}"
                if advance.get("ok")
                else str(advance.get("error"))
            ),
        },
        {
            "name": "location_switches>=3",
            "ok": switches >= 3,
            "detail": f"{switches} switches over {len(visited)} passages",
        },
        {
            "name": "save_roundtrip",
            "ok": bool(roundtrip.get("ok")),
            "detail": (
                f"method={roundtrip.get('method')}; passage={roundtrip.get('same_passage')}; "
                f"time={roundtrip.get('same_time')}; core={roundtrip.get('core_equal')}; "
                + (
                    "diff=" + ",".join(roundtrip.get("core_differences") or [])[:160]
                    if roundtrip.get("core_differences")
                    else "diff=none"
                )
                + (f"; error={roundtrip.get('error')}" if roundtrip.get("error") else "")
            ),
        },
        {
            "name": "no_hard_errors",
            "ok": not hard_errors,
            "detail": f"{len(hard_errors)} hard errors",
        },
    ]
    if hard_errors:
        verdict = "hard_fail"
    elif not records or all(r["status"] == "not_applicable" for r in records):
        verdict = "not_applicable"
    elif all(item["ok"] for item in assertions):
        verdict = "ok"
    else:
        verdict = "soft_fail"
    failed = [a for a in assertions if not a["ok"]]
    return {
        "verdict": verdict,
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "slot": slot,
        "steps_requested": [step.name for step in DAYLOOP_STEPS],
        "prep": prep,
        "records": records,
        "clicks": len(records),
        "ok_clicks": len(completed_steps),
        "fallback_clicks": len(fallback_clicks),
        "stalled_clicks": len(stalled_clicks),
        "click_statuses": list(DAYLOOP_CLICK_STATUSES),
        "not_applicable": len(not_applicable_steps),
        "visited_passages": visited,
        "location_switches": switches,
        "time_start": start_time,
        "time_end": end_time,
        "time_advance_hours": advance.get("hours"),
        "time_method": advance.get("method"),
        "save_roundtrip": roundtrip,
        "hard_errors": hard_errors[:20],
        "assertions": assertions,
        "detail": "; ".join(f"{a['name']}: {a['detail']}" for a in failed)[:600],
    }


def _hard_error_count(errors: list[dict[str, Any]]) -> int:
    return len(errors)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def select_rows(
    rows: list[dict[str, Any]],
    *,
    sections: list[str] | None = None,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 20261004,
) -> list[dict[str, Any]]:
    wanted = {s for s in (sections or []) if s}
    pool = [
        row
        for row in rows
        if row.get("kind") == "link" and (not wanted or row.get("section") in wanted)
    ]
    if sample is not None and 0 <= sample < len(pool):
        pool = random.Random(seed).sample(pool, sample)
        pool.sort(key=lambda row: (str(row.get("section")), int(row.get("index") or 0)))
    if limit is not None:
        pool = pool[: max(0, limit)]
    return pool


def generate_manifest(page: Any) -> dict[str, Any]:
    raw = page.evaluate(MANIFEST_JS)
    if not raw or not raw.get("ok"):
        return {
            "ok": False,
            "error": (raw or {}).get("error") or "runtime manifest read failed",
            "rows": [],
            "sections": [],
        }
    rows = [normalize_manifest_row(item) for item in raw.get("rows") or []]
    return {
        "ok": True,
        "error": None,
        "sections": [str(s) for s in raw.get("sections") or []],
        "rows": rows,
        "summary": manifest_summary(rows),
    }


def load_fixture_payload(fixture_path: Path) -> tuple[dict[str, Any], str]:
    fixture = fl.load_fixture(fixture_path)
    variables = fixture.get("variables") if isinstance(fixture, dict) else None
    if not isinstance(variables, dict) or not variables:
        raise SystemExit(f"fixture has no 'variables' object: {fixture_path}")
    payload = json.dumps(fixture, ensure_ascii=False, separators=(",", ":"))
    return fixture, payload


def fixture_digest(variables: dict[str, Any]) -> str:
    canonical = json.dumps(variables, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_scenarios(
    page: Any,
    rows: list[dict[str, Any]],
    *,
    fixture: dict[str, Any],
    timeout_ms: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for position, row in enumerate(rows, 1):
        section = str(row.get("section"))
        index = int(row.get("index") or 0)
        label = row.get("label")
        expected_target = row.get("target")
        t0 = time.time()
        restore = page.evaluate(ps.RESTORE_FIXTURE)
        if not (isinstance(restore, dict) and restore.get("ok")):
            results.append(
                {
                    "section": section,
                    "index": index,
                    "label": label,
                    "target": expected_target,
                    "verdict": "hard_fail",
                    "detail": f"fixture restore failed: {restore}",
                    "widgets": row.get("widgets"),
                    "interaction": None,
                    "state_delta": [],
                    "deep_delta": [],
                    "deep_delta_truncated": False,
                    "assignment_checks": [],
                    "assignment_summary": None,
                    "invariants": None,
                    "spec": None,
                    "landed": None,
                    "errors": [],
                    "text_len": 0,
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }
            )
            continue
        run_raw = page.evaluate(
            SCENARIO_RUN, {"section": section, "index": index}
        )
        try:
            row_report = json.loads(run_raw) if isinstance(run_raw, str) else (run_raw or {})
        except Exception as exc:  # noqa: BLE001 - report, keep sweeping
            row_report = {"ok": False, "error": f"scenario run payload unreadable: {exc}"}
        target_check = parse_name_and_passage_result(row_report)
        target = target_check.get("link_passage") if target_check.get("ok") else None

        timed_out = False
        probe: dict[str, Any] = {}
        interaction: str | None = None
        assignment_summary: dict[str, Any] | None = None
        invariant_report: dict[str, Any] | None = None
        spec_report: dict[str, Any] | None = None
        not_applicable: str | None = None

        if not row_report.get("ok"):
            verdict, detail = "hard_fail", str(
                row_report.get("error") or "scenario run failed"
            )[:400]
        elif not target_check.get("ok"):
            error = str(target_check.get("error") or "")
            verdict = classify_unresolvable(error)
            detail = f"target not resolvable ({verdict}): {error}"
        elif not target:
            verdict, detail = "not_applicable", "row resolves to an empty target passage"
        else:
            page.evaluate(ps.PLAY_PASSAGE, {"name": target})
            try:
                page.wait_for_function(
                    "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                    timeout=timeout_ms,
                )
            except Exception:
                timed_out = True
            probe = page.evaluate(ps.PROBE) or {}
            interaction = classify_interaction(
                location_before=row_report.get("location_before"),
                target=target,
                target_is_function=bool(row_report.get("target_is_function")),
                widgets_list=row_report.get("widgets_list"),
            )
            assignment_summary = summarize_assignment_checks(
                row_report.get("assignment_checks")
            )
            try:
                invariant_report = json.loads(
                    page.evaluate(
                        INVARIANT_BATTERY,
                        {"widgets": list(row_report.get("widgets_list") or [])},
                    )
                )
            except Exception as exc:  # noqa: BLE001 - a broken battery is a hard fail
                invariant_report = {
                    "checks": [{"name": "battery_unreadable", "ok": False, "detail": str(exc)[:200]}],
                    "violations": [f"battery unreadable: {str(exc)[:200]}"],
                    "stats": {},
                }
            invariant_eval = evaluate_invariants(invariant_report)
            spec = SCENARIO_SPECS.get(str(target))
            if spec:
                try:
                    spec_raw = page.evaluate(
                        SCENARIO_CHECKS_JS,
                        {
                            "globals": spec.get("required_globals") or [],
                            "keys": spec.get("required_keys") or [],
                            "changed": spec.get("changed_keys") or [],
                            "exprs": [
                                {"name": c["name"], "expr": c["expr"]}
                                for c in spec.get("checks") or []
                            ],
                        },
                    )
                    spec_payload = json.loads(spec_raw) if isinstance(spec_raw, str) else spec_raw
                except Exception as exc:  # noqa: BLE001
                    spec_payload = {"eval_error": f"spec payload unreadable: {exc}"}
                spec_report = evaluate_spec_report(spec_payload, spec)
            verdict, detail = aggregate_scenario_verdict(
                probe=probe,
                target=str(target),
                timed_out=timed_out,
                row_report=row_report,
                invariant_report=invariant_eval,
                spec_report=spec_report,
                not_applicable=not_applicable,
                interaction=interaction,
            )
            invariant_report = {
                "ok": invariant_eval["ok"],
                "failed_checks": invariant_eval["failed_checks"],
                "violations": invariant_eval["violations"],
                "notes": invariant_eval.get("notes") or [],
                "stats": invariant_eval["stats"],
                "detail": invariant_eval["detail"],
            }
        results.append(
            {
                "section": section,
                "index": index,
                "label": label,
                "target": expected_target,
                "resolved_target": target,
                "verdict": verdict,
                "detail": detail[:600],
                "widgets": int(row_report.get("widgets") or row.get("widgets") or 0),
                "widgets_error": row_report.get("widgets_error"),
                "target_is_function": bool(row_report.get("target_is_function")),
                "interaction": interaction,
                "location_before": row_report.get("location_before"),
                "state_delta": row_report.get("delta") or [],
                "state_delta_truncated": bool(row_report.get("delta_truncated")),
                "deep_delta": (row_report.get("deep_delta") or [])[:20],
                "deep_delta_truncated": bool(row_report.get("deep_delta_truncated")),
                "assignment_checks": (row_report.get("assignment_checks") or [])[:20],
                "assignment_summary": assignment_summary or None,
                "invariants": invariant_report,
                "spec": (
                    {
                        "ok": spec_report.get("ok"),
                        "hard_failures": spec_report.get("hard_failures"),
                        "soft_failures": spec_report.get("soft_failures"),
                        "evidence": spec_report.get("evidence"),
                    }
                    if spec_report
                    else None
                ),
                "landed": probe.get("passage"),
                "errors": (probe.get("errors") or [])[:20],
                "text_len": int(probe.get("textLen") or 0),
                "link_count": int(probe.get("linkCount") or 0),
                "timed_out": timed_out,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
        )
        if position % 10 == 0:
            print(f"  ... {position}/{len(rows)}", flush=True)
    return results


def run(
    target: Path,
    *,
    suite: str = DEFAULT_SUITE,
    fixture_path: Path = DEFAULT_FIXTURE,
    out_dir: Path | None = None,
    sections: list[str] | None = None,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 20261004,
    timeout_ms: int = 20000,
    bootstrap_settle_ms: int = 1500,
    headless: bool = True,
    static_check: bool = True,
    manifest_out: Path | None = None,
    baseline_path_in: Path | None = None,
    save_baseline: bool = False,
    dayloop_max_clicks: int = 3,
) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    html_path = ps.resolve_html_path(target)
    fixture, fixture_json = load_fixture_payload(fixture_path)
    variables = fixture.get("variables") or {}
    fixture_scan = scan_variables(variables)
    report: dict[str, Any] = {
        "tool": TOOL,
        "target": str(target),
        "html_path": str(html_path),
        "suite": suite,
        "fixture": {
            "path": str(fixture_path),
            "top_level_keys": len(variables),
            "digest": fixture_digest(variables),
            "scan": fixture_scan,
        },
        "started_at": started,
        "finished_at": None,
        "manifest": None,
        "results": [],
        "verdict_counts": {},
        "dayloop": None,
        "baseline": {"path": str(baseline_path_in) if baseline_path_in else None},
        "baseline_diff": None,
        "console_tail": [],
        "fatal_error": None,
    }
    planned_keys: list[str] = []
    strategy = {
        "kind": "scenario_sweep",
        "suite": suite,
        "sections": sections,
        "limit": limit,
        "sample": sample,
        "seed": seed,
        "static_check": static_check,
    }
    identity = sl.run_identity(
        TOOL,
        html_sha256=ps.file_sha256(html_path),
        fixture_digest=fixture_digest(variables),
        tool_version="scenario-sweep-v2",
        plan_digest=sl.plan_digest(planned_keys, strategy),
        strategy=strategy,
    )
    report["ledger"] = {"identity": identity, "planned_keys": planned_keys, "plan_digest": identity["plan_digest"]}

    static_menu: dict[str, Any] | None = None
    if static_check:
        try:
            html_text = html_path.read_text(encoding="utf-8", errors="replace")
            static_menu = parse_static_debug_menu(html_text)
        except Exception as exc:  # noqa: BLE001
            static_menu = {
                "ok": False,
                "error": f"static parse failed: {type(exc).__name__}: {exc}"[:300],
                "entries": [],
            }

    try:
        with sfa._session(
            html_path,
            headless=headless,
            timeout_ms=timeout_ms,
            bootstrap_settle_ms=bootstrap_settle_ms,
        ) as (page, boot, console):
            boot_error = sfa._boot_failed(boot)
            report["boot"] = boot
            report["console_tail"] = console[-120:]
            if boot_error:
                report["fatal_error"] = f"bootstrap failed: {boot_error}"
            else:
                load_ok = page.evaluate(ps.LOAD_FIXTURE, fixture_json)
                report["fixture"]["load"] = load_ok
                manifest = generate_manifest(page) if suite in ("scenarios", "all") else {
                    "ok": True,
                    "rows": [],
                    "sections": [],
                    "summary": None,
                }
                if manifest.get("ok") and manifest.get("rows"):
                    manifest["cross_check"] = cross_check_manifest(
                        manifest["rows"], static_menu
                    )
                    manifest["drift"] = manifest_drift(manifest["summary"])
                report["manifest"] = {
                    "ok": bool(manifest.get("ok")),
                    "error": manifest.get("error"),
                    "summary": manifest.get("summary"),
                    "cross_check": manifest.get("cross_check"),
                    "drift": manifest.get("drift"),
                    "expected": EXPECTED_MANIFEST,
                    "sections": manifest.get("sections"),
                }
                if manifest_out is not None and manifest.get("rows"):
                    manifest_out.parent.mkdir(parents=True, exist_ok=True)
                    manifest_out.write_text(
                        json.dumps(
                            {
                                "tool": TOOL,
                                "target": str(target),
                                "html_path": str(html_path),
                                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "summary": manifest.get("summary"),
                                "expected": EXPECTED_MANIFEST,
                                "drift": report["manifest"]["drift"],
                                "cross_check": report["manifest"]["cross_check"],
                                "static": (
                                    {
                                        "rows": (static_menu or {}).get("rows"),
                                        "literal_targets": (static_menu or {}).get(
                                            "literal_targets"
                                        ),
                                        "dynamic_targets": (static_menu or {}).get(
                                            "dynamic_targets"
                                        ),
                                        "sections": (static_menu or {}).get("sections"),
                                        "ok": (static_menu or {}).get("ok"),
                                        "error": (static_menu or {}).get("error"),
                                    }
                                ),
                                "rows": manifest.get("rows"),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    report["manifest"]["path"] = str(manifest_out)
                if suite in ("scenarios", "all") and manifest.get("rows"):
                    selected = select_rows(
                        manifest["rows"],
                        sections=sections,
                        limit=limit,
                        sample=sample,
                        seed=seed,
                    )
                    planned_keys = [
                        f"{row.get('section')}#{row.get('index')}" for row in selected
                    ]
                    identity["plan_digest"] = sl.plan_digest(planned_keys, strategy)
                    report["ledger"]["planned_keys"] = list(planned_keys)
                    report["ledger"]["plan_digest"] = identity["plan_digest"]
                    report["selection"] = {
                        "sections": sections,
                        "limit": limit,
                        "sample": sample,
                        "seed": seed,
                        "count": len(selected),
                    }
                    print(
                        f"[scenario] sweeping {len(selected)} debug-menu rows "
                        f"(sections={sections or 'all'})",
                        flush=True,
                    )
                    report["results"] = run_scenarios(
                        page,
                        selected,
                        fixture=variables,
                        timeout_ms=timeout_ms,
                    )
                if suite in ("dayloop", "all"):
                    print("[scenario] dayloop: walking one in-game day", flush=True)
                    # The static passage graph lets the walk resolve multi-hop
                    # routes (Bathroom -> Kitchen, Domus Street -> Harvest
                    # Street) even though only the current passage's links are
                    # clickable at any moment.
                    try:
                        dayloop_passages = {
                            passage.name: passage.body
                            for passage in ps.extract_passages(html_path)[0]
                        }
                        report["dayloop_passages"] = {
                            "ok": True,
                            "count": len(dayloop_passages),
                        }
                    except Exception as exc:  # noqa: BLE001 - record and continue
                        dayloop_passages = {}
                        report["dayloop_passages"] = {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}"[:300],
                        }
                    report["dayloop"] = run_dayloop(
                        page,
                        max_clicks_per_step=dayloop_max_clicks,
                        timeout_ms=min(timeout_ms, 15000),
                        passages=dayloop_passages,
                    )
    except Exception as exc:  # noqa: BLE001 - always emit a report
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"[:600]

    counts = collections.Counter(r["verdict"] for r in report["results"])
    report["verdict_counts"] = {key: counts.get(key, 0) for key in VERDICTS}
    if report.get("dayloop"):
        report["verdict_counts"]["dayloop:" + report["dayloop"]["verdict"]] = 1
    complete, completeness_diagnostics, completeness = sl.validate_complete(
        planned_keys, report["results"]
    )
    if suite in ("dayloop", "all"):
        dayloop = report.get("dayloop")
        if not isinstance(dayloop, dict):
            complete = False
            completeness_diagnostics.append("dayloop result is missing")
        elif dayloop.get("verdict") != "ok":
            complete = False
            completeness_diagnostics.append(
                f"dayloop verdict is {dayloop.get('verdict')!r}, expected 'ok'"
            )
    report["completeness"] = {
        "ok": complete,
        "diagnostics": completeness_diagnostics,
        "summary": {**completeness, "status": "complete" if complete else "incomplete"},
        "expected_keys": len(planned_keys),
        "actual_results": len(report["results"]),
    }
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    if baseline_path_in and baseline_path_in.exists():
        try:
            baseline = json.loads(baseline_path_in.read_text(encoding="utf-8"))
            report["baseline_diff"] = diff_scenarios(report, baseline)
        except Exception as exc:  # noqa: BLE001
            report["baseline_diff"] = {"error": f"baseline unreadable: {exc}"}

    out = out_dir or default_out_dir(suite)
    write_report(report, out, report.get("baseline_diff"))
    if save_baseline:
        target_path = baseline_path_in or baseline_path(fixture_path, suite)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if report.get("manifest") and report["manifest"].get("summary"):
            manifest_baseline_path(fixture_path).write_text(
                json.dumps(
                    {
                        "tool": TOOL,
                        "target": str(target),
                        "fixture": str(fixture_path),
                        "saved_at": report["finished_at"],
                        "summary": report["manifest"]["summary"],
                        "expected": EXPECTED_MANIFEST,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        print(f"[scenario] baseline sealed -> {target_path}", flush=True)
    return report


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def write_report(
    report: dict[str, Any], out_dir: Path, diff: dict[str, Any] | None
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "scenario-sweep.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = report.get("verdict_counts") or {}
    manifest = report.get("manifest") or {}
    summary = manifest.get("summary") or {}
    lines = [
        "# DOL-X scenario sweep report",
        "",
        f"- target: `{report.get('target')}`",
        f"- html: `{report.get('html_path')}`",
        f"- suite: {report.get('suite')} / fixture: `{(report.get('fixture') or {}).get('path')}`",
        (
            f"- manifest: {summary.get('rows', 0)} rows = "
            f"{summary.get('clickable', 0)} clickable + {summary.get('separators', 0)} separators"
        ),
        f"- started: {report.get('started_at')} / finished: {report.get('finished_at')}",
        "",
        "## verdicts",
        "",
        "| verdict | count |",
        "| --- | --- |",
    ]
    for key in VERDICTS:
        lines.append(f"| {key} | {counts.get(key, 0)} |")
    interaction_counts: dict[str, int] = {name: 0 for name in INTERACTIONS}
    interaction_verdicts: dict[str, collections.Counter[str]] = {
        name: collections.Counter() for name in INTERACTIONS
    }
    for item in report.get("results") or []:
        name = str(item.get("interaction") or "")
        if name in interaction_counts:
            interaction_counts[name] += 1
            interaction_verdicts[name][str(item.get("verdict"))] += 1
    lines += [
        "",
        "## row interactions (scene jump / state op / display-only)",
        "",
        "| interaction | count | verdicts |",
        "| --- | --- | --- |",
    ]
    for name in INTERACTIONS:
        verdict_text = " ".join(
            f"{key}={value}" for key, value in sorted(interaction_verdicts[name].items())
        ) or "-"
        lines.append(f"| {name} | {interaction_counts[name]} | {verdict_text} |")
    noted = [
        item
        for item in report.get("results") or []
        if item.get("verdict") == "ok" and item.get("detail")
    ]
    if noted:
        lines += ["", f"## ok rows with notes ({len(noted)})", ""]
        for item in noted[:60]:
            lines.append(
                f"- `{item.get('section')}#{item.get('index')}` {item.get('label')} -> "
                f"`{item.get('resolved_target') or item.get('target')}`: "
                f"{str(item.get('detail') or '')[:200]}"
            )
    dayloop = report.get("dayloop")
    if dayloop:
        lines += [
            "",
            f"## dayloop - {dayloop.get('verdict')}",
            "",
            f"- clicks: {dayloop.get('clicks')} (ok={dayloop.get('ok_clicks')}, "
            f"fallback={dayloop.get('fallback_clicks', 0)}, "
            f"stalled={dayloop.get('stalled_clicks', 0)}, "
            f"n/a={dayloop.get('not_applicable')})",
            f"- time advance: {dayloop.get('time_advance_hours')} h "
            f"via {dayloop.get('time_method')}",
            f"- location switches: {dayloop.get('location_switches')}",
            f"- save round trip: {dayloop.get('save_roundtrip', {}).get('ok')} "
            f"({dayloop.get('save_roundtrip', {}).get('method')})",
            "",
            "| step | passage before | passage after | clicked | status |",
            "| --- | --- | --- | --- | --- |",
        ]
        for record in (dayloop.get("records") or [])[:80]:
            clicked = str(record.get("clicked_text") or "").replace("|", "\\|")[:40]
            before = str(record.get("passage_before") or "").replace("|", "\\|")[:30]
            after = str(record.get("passage_after") or "").replace("|", "\\|")[:30]
            lines.append(
                f"| {record.get('step')} | {before} | {after} | {clicked} | {record.get('status')} |"
            )
        lines.append("")
        for assertion in dayloop.get("assertions") or []:
            mark = "PASS" if assertion.get("ok") else "FAIL"
            lines.append(f"- [{mark}] {assertion.get('name')}: {assertion.get('detail')}")

    cross = manifest.get("cross_check") or {}
    if cross:
        lines += ["", "## manifest cross-check", ""]
        lines.append(f"- runtime vs static ok: **{cross.get('ok')}**")
        lines.append(f"- counts match: {cross.get('counts_match')}")
        lines.append(f"- drift entries: {cross.get('drift_count', len(cross.get('drift') or []))}")
        for item in (cross.get("drift") or [])[:20]:
            lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
    drift = manifest.get("drift") or {}
    if drift.get("differences"):
        lines += ["", "## manifest drift vs known truth (2026-10-04)", ""]
        for item in drift["differences"][:20]:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")

    for kind in ("hard_fail", "soft_fail", "fixture_insufficient", "not_applicable"):
        bad = [r for r in report.get("results") or [] if r.get("verdict") == kind]
        if not bad:
            continue
        title = {"hard_fail": "hard failures", "soft_fail": "soft failures"}.get(kind, kind)
        lines += ["", f"## {title} ({len(bad)})", ""]
        for item in bad[:60]:
            lines.append(
                f"- `{item.get('section')}#{item.get('index')}` {item.get('label')} -> "
                f"`{item.get('resolved_target') or item.get('target')}`: "
                f"{str(item.get('detail') or '')[:220]}"
            )
        if len(bad) > 60:
            lines.append(f"- ... and {len(bad) - 60} more")

    specced = [r for r in report.get("results") or [] if r.get("spec")]
    if specced:
        lines += ["", f"## scenario specs ({len(specced)})", ""]
        for item in specced[:60]:
            mark = "ok" if item.get("spec", {}).get("ok") else "FAIL"
            lines.append(
                f"- [{mark}] `{item.get('resolved_target') or item.get('target')}` "
                f"({item.get('verdict')})"
            )

    if diff:
        lines += ["", "## baseline diff", ""]
        lines.append(f"- new regressions: **{len(diff.get('new_regressions') or [])}**")
        lines.append(f"- fixed: {len(diff.get('fixed') or [])}")
        lines.append(f"- changed (non-regression): {len(diff.get('changed') or [])}")
        lines.append(f"- new scenarios: {len(diff.get('new_scenarios') or [])}")
        for item in (diff.get("new_regressions") or [])[:40]:
            lines.append(
                f"  - `{item.get('key')}` {item.get('target')}: {item.get('was')} -> {item.get('now')}"
            )
        for item in (diff.get("fixed") or [])[:20]:
            lines.append(f"  - fixed `{item.get('key')}`: {item.get('was')} -> ok")
        for item in (diff.get("new_scenarios") or [])[:20]:
            lines.append(f"  - new `{item.get('key')}`: {item.get('verdict')}")
        manifest_diff = diff.get("manifest")
        if manifest_diff:
            lines.append(f"- manifest diff: {json.dumps(manifest_diff, ensure_ascii=False)}")
    if report.get("fatal_error"):
        lines += ["", "## fatal error", "", f"`{report['fatal_error']}`", ""]

    md_path = out_dir / "scenario-sweep.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DOL-X scenario sweep (debug-menu story axis, engine A)"
    )
    parser.add_argument("target", type=Path, help="built .html or .zip to sweep")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="report directory (default .local/sweep/<suite>-<date>)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="fixture json (default .local/fixtures/base-1004.json)",
    )
    parser.add_argument("--suite", choices=SUITES, default=DEFAULT_SUITE)
    parser.add_argument(
        "--section",
        action="append",
        default=None,
        help="only sweep this debug-menu section (repeatable)",
    )
    parser.add_argument("--limit", type=int, default=None, help="first N clickable rows")
    parser.add_argument("--sample", type=int, default=None, help="random N clickable rows")
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument("--bootstrap-settle-ms", type=int, default=1500)
    parser.add_argument("--headful", action="store_true", help="show the browser window")
    parser.add_argument("--baseline", type=Path, default=None, help="baseline json to diff")
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="seal this run as the baseline (default .local/sweep/baselines/)",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=DEFAULT_MANIFEST_OUT,
        help="where the freshly generated manifest json is written",
    )
    parser.add_argument(
        "--static-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="cross-check the runtime manifest against the static HTML copy",
    )
    parser.add_argument(
        "--dayloop-max-clicks",
        type=int,
        default=8,
        help="max clicks per dayloop step",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.target.exists():
        print(f"[scenario] target does not exist: {args.target}")
        return 2
    if not args.fixture.exists():
        print(f"[scenario] fixture does not exist: {args.fixture}")
        return 2
    report = run(
        args.target,
        suite=args.suite,
        fixture_path=args.fixture,
        out_dir=args.out,
        sections=args.section,
        limit=args.limit,
        sample=args.sample,
        seed=args.seed,
        timeout_ms=args.timeout_ms,
        bootstrap_settle_ms=args.bootstrap_settle_ms,
        headless=not args.headful,
        static_check=args.static_check,
        manifest_out=args.manifest_out,
        baseline_path_in=args.baseline,
        save_baseline=args.save_baseline,
        dayloop_max_clicks=args.dayloop_max_clicks,
    )
    print(f"[scenario] verdicts={report['verdict_counts']}")
    manifest = report.get("manifest") or {}
    cross = manifest.get("cross_check") or {}
    print(
        f"[scenario] manifest: {json.dumps((manifest.get('summary') or {}), ensure_ascii=False)} "
        f"cross_check_ok={cross.get('ok')}"
    )
    out_dir = args.out or default_out_dir(args.suite)
    print(f"[scenario] report -> {out_dir / 'scenario-sweep.md'}")
    hard = int((report.get("verdict_counts") or {}).get("hard_fail") or 0)
    if report.get("fatal_error"):
        return 1
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
