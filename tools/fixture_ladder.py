#!/usr/bin/env python3
"""DOL-X fixture ladder (engine A, phase 2).

Fixtures are the *state* half of the automated test stack: a captured
``SugarCube.State.variables`` snapshot plus provenance metadata. They live in
``.local/fixtures/`` (gitignored, never uploaded) together with an ``index.json``
manifest that records source, date, game version and digests.

Subcommands
-----------
capture    boot the built artifact, walk the startup gates, snapshot variables
from-save  load a (discardable) save file, then snapshot; gated behind --allow-real
selftest   serialize a live save, write it locally, then re-import it through the
           from-save path and compare - proves the import path end to end
sanitize   strip absolute paths / personal values from an existing fixture
verify     validate format, required keys and digests of one or more fixtures
list       print the manifest of a fixture directory

Safety
------
* real saves are only accepted with an explicit ``--allow-real``, are always
  sanitized before being written, and never leave ``.local/``;
* :func:`strip_personal` removes Windows/POSIX home paths and user-approved
  literal values / name paths;
* :mod:`tools.save_safety_guard` is the repo-side guard that keeps fixtures out
  of git.

Nothing here touches ``lyra/`` or ``config/``: the whole tool is runtime-only,
so it cannot leak into a release artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import passage_sweep as ps  # noqa: E402

FIXTURE_SCHEMA_VERSION = 1
SOURCE_KINDS = ("synthetic", "real-sanitized", "derived")
DEFAULT_DIR = Path(".local/fixtures")
REDACTED_PATH = "[redacted-path]"
REDACTED_VALUE = "[redacted]"
REDACTED_NAME = "[redacted-name]"

# Personal-path shapes. Anything matching these inside a fixture is treated as
# machine-private provenance and is rewritten by :func:`strip_personal`.
PERSONAL_PATH_PATTERNS = (
    re.compile(
        r"[A-Za-z]:\\(?:Users|Documents and Settings|projects|game)\\[^\"'\r\n\t]*",
        re.IGNORECASE,
    ),
    re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+(?:/[^\"'\r\n\t]*)?"),
    re.compile(r"\\\\[A-Za-z0-9_.-]+\\[^\"'\r\n\t]*"),
)

# Keys whose value is a character name. Deliberately narrow: rewriting an NPC
# display name that the game also uses as a lookup key would corrupt fixtures.
NAME_KEY_RE = re.compile(
    r"^(?:pc|player|mc|hero|char|character)?_?name$|^nickname$|^surname$|^full_?name$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Pure logic (unit-testable without a browser)
# --------------------------------------------------------------------------- #


def fixture_digest(variables: dict[str, Any]) -> str:
    """Stable digest of the payload (key order independent)."""
    canonical = json.dumps(variables, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_paths(node: Any, path: str = "", depth: int = 0) -> Iterable[tuple[str, str, Any]]:
    """Yield ``(path, kind, value)`` for every leaf; ``kind`` is str|num|bool|none."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _walk_paths(value, child, depth + 1)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_paths(value, f"{path}[{index}]", depth + 1)
        return
    if isinstance(node, str):
        yield path, "str", node
    elif isinstance(node, bool):
        yield path, "bool", node
    elif isinstance(node, (int, float)):
        yield path, "num", node
    else:
        yield path, "none", node


def find_personal_paths(node: Any, limit: int = 40) -> list[dict[str, str]]:
    """Return ``{path, preview}`` for every string that looks machine-private."""
    found: list[dict[str, str]] = []
    for path, kind, value in _walk_paths(node):
        if kind != "str" or not value:
            continue
        for pattern in PERSONAL_PATH_PATTERNS:
            match = pattern.search(value)
            if match:
                found.append({"path": path, "preview": match.group(0)[:80]})
                break
        if len(found) >= limit:
            break
    return found


def find_name_candidates(node: Any, *, max_depth: int = 4, limit: int = 40) -> list[dict[str, str]]:
    """Return ``{path, value_length}`` for name-like string leaves.

    Only paths are reported - never the value - so the report can be reviewed
    without leaking data. Measured on the 0.5.11.9 fixture (2026-10-04): all 128
    name-like leaves are wardrobe/garment/NPC-clothing names, and DoL keeps no
    player name in ``State.variables`` at all. Redaction therefore stays opt-in
    (:func:`strip_personal` only touches paths the caller lists); blanket
    ``*.name`` rewriting would corrupt clothing fixtures.
    """
    candidates: list[dict[str, str]] = []

    def walk(current: Any, path: str, depth: int) -> None:
        if len(candidates) >= limit or depth > max_depth:
            return
        if isinstance(current, dict):
            for key, value in current.items():
                child = f"{path}.{key}" if path else str(key)
                if isinstance(value, str) and value.strip() and NAME_KEY_RE.match(str(key)):
                    candidates.append({"path": child, "value_length": str(len(value))})
                walk(value, child, depth + 1)
        elif isinstance(current, list):
            for index, value in enumerate(current[:30]):
                walk(value, f"{path}[{index}]", depth + 1)

    walk(node, "", 0)
    return candidates


def strip_personal(
    node: Any,
    *,
    redact_values: Iterable[str] = (),
    redact_name_paths: Iterable[str] = (),
    redact_names: bool = False,
    path_label: str = "",
) -> tuple[Any, dict[str, int]]:
    """Recursively rewrite machine-private or user-supplied strings.

    Returns ``(clean_node, stats)``. Absolute paths are always rewritten; name
    redaction only happens when ``redact_names`` is true *and* the leaf path was
    listed by the caller, so the game's NPC lookups stay intact.
    """
    literal_blocklist = {value for value in redact_values if value}
    name_paths = set(redact_name_paths)
    stats = {"paths": 0, "values": 0, "names": 0}

    def walk(current: Any, path: str) -> Any:
        if isinstance(current, dict):
            return {
                key: walk(value, f"{path}.{key}" if path else str(key))
                for key, value in current.items()
            }
        if isinstance(current, list):
            return [walk(value, f"{path}[{index}]") for index, value in enumerate(current)]
        if not isinstance(current, str) or not current:
            return current
        if redact_names and path in name_paths:
            stats["names"] += 1
            return REDACTED_NAME
        if current in literal_blocklist:
            stats["values"] += 1
            return REDACTED_VALUE
        cleaned = current
        for pattern in PERSONAL_PATH_PATTERNS:
            cleaned, hits = pattern.subn(REDACTED_PATH, cleaned)
            stats["paths"] += hits
        return cleaned

    return walk(node, path_label), stats


def fixture_stats(variables: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cheap structural stats; keeps ``base`` keys that only capture can know."""
    stats = dict(base or {})
    canonical = json.dumps(variables, ensure_ascii=False)
    stats.update(
        {
            "top_level_keys": len(variables),
            "json_bytes": len(canonical.encode("utf-8")),
            "sha256": fixture_digest(variables),
        }
    )
    return stats


def sanitize_fixture(
    fixture: dict[str, Any],
    *,
    redact_values: Iterable[str] = (),
    redact_name_paths: Iterable[str] = (),
    redact_names: bool = False,
    note: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a sanitized copy of ``fixture`` plus a redaction report."""
    variables, var_stats = strip_personal(
        fixture.get("variables") or {},
        redact_values=redact_values,
        redact_name_paths=redact_name_paths,
        redact_names=redact_names,
    )
    meta, meta_stats = strip_personal(
        dict(fixture.get("meta") or {}),
        redact_values=redact_values,
        path_label="meta",
    )
    clean: dict[str, Any] = {
        "meta": meta,
        "variables": variables,
        "stats": dict(fixture.get("stats") or {}),
    }
    clean["meta"]["schema"] = FIXTURE_SCHEMA_VERSION
    clean["meta"]["sanitized"] = True
    clean["meta"]["sanitized_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    clean["meta"]["sanitize_counts"] = {
        **var_stats,
        "meta_paths": meta_stats.get("paths", 0),
        "meta_values": meta_stats.get("values", 0),
    }
    if note:
        clean["meta"]["sanitize_note"] = note
    clean["meta"]["sha256"] = fixture_digest(clean["variables"])
    clean["stats"] = fixture_stats(clean["variables"], base=clean.get("stats"))
    return clean, clean["meta"]["sanitize_counts"]


def build_fixture(
    variables: dict[str, Any],
    *,
    label: str,
    source: str,
    game_version: str | None,
    snapshot_meta: dict[str, Any] | None = None,
    notes: str | None = None,
    source_save_sha256: str | None = None,
) -> dict[str, Any]:
    """Assemble the on-disk fixture document."""
    if source not in SOURCE_KINDS:
        raise ValueError(f"unknown fixture source: {source!r}")
    fixture: dict[str, Any] = {
        "meta": {
            "schema": FIXTURE_SCHEMA_VERSION,
            "label": label,
            "source": source,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "game_version": game_version or "unknown",
            "tool": "tools/fixture_ladder.py",
            "sanitized": source != "synthetic",
            "name_candidates": find_name_candidates(variables),
            "personal_paths": find_personal_paths(variables, limit=10),
            "notes": notes or "",
        },
        "variables": variables,
        "stats": fixture_stats(variables, base={"snapshot_meta": snapshot_meta or {}}),
    }
    if source_save_sha256:
        fixture["meta"]["source_save_sha256"] = source_save_sha256
    fixture["meta"]["sha256"] = fixture_digest(variables)
    return fixture


def verify_fixture(fixture: Any, *, name: str = "<fixture>") -> dict[str, Any]:
    """Format + integrity check. Returns ``{ok, errors, warnings}``."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(fixture, dict):
        return {"ok": False, "errors": [f"{name}: top level is not an object"], "warnings": []}
    meta = fixture.get("meta")
    variables = fixture.get("variables")
    if not isinstance(meta, dict):
        errors.append("meta is missing or not an object")
        meta = {}
    if not isinstance(variables, dict):
        errors.append("variables is missing or not an object")
        variables = {}
    if not isinstance(fixture.get("stats"), dict):
        warnings.append("stats is missing (regenerated on write)")
    if meta.get("schema") != FIXTURE_SCHEMA_VERSION:
        warnings.append(f"schema={meta.get('schema')!r} (current {FIXTURE_SCHEMA_VERSION})")
    source = meta.get("source")
    if source not in SOURCE_KINDS:
        errors.append(f"meta.source={source!r} not in {SOURCE_KINDS}")
    for key in ("label", "created_at", "game_version"):
        if not str(meta.get(key) or "").strip():
            errors.append(f"meta.{key} is empty")
    if len(variables) < 100:
        errors.append(f"variables has only {len(variables)} top-level keys (looks empty)")
    digest = fixture_digest(variables)
    if not meta.get("sha256"):
        warnings.append("meta.sha256 missing")
    elif meta["sha256"] != digest:
        errors.append(
            f"meta.sha256 mismatch: stored={str(meta['sha256'])[:16]} computed={digest[:16]}"
        )
    leaked = find_personal_paths(variables, limit=5)
    if leaked:
        errors.append(
            "personal paths still present: "
            + ", ".join(f"{item['path']}({item['preview'][:40]})" for item in leaked)
        )
    if source == "real-sanitized" and not meta.get("sanitized"):
        errors.append("real-sanitized fixture is not marked sanitized")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_fixture(fixture: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def update_index(directory: Path, *, entries: list[dict[str, Any]] | None = None) -> Path:
    """Rewrite ``index.json`` from the directory contents (self-healing)."""
    directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = list(entries or [])
    known = {record["file"] for record in records}
    for candidate in sorted(directory.glob("*.json")):
        if candidate.name == "index.json" or candidate.name in known:
            continue
        try:
            fixture = load_fixture(candidate)
        except Exception:  # noqa: BLE001 - unreadable files simply stay unlisted
            continue
        meta = fixture.get("meta") or {}
        variables = fixture.get("variables") if isinstance(fixture.get("variables"), dict) else {}
        records.append(
            {
                "file": candidate.name,
                "label": meta.get("label"),
                "source": meta.get("source"),
                "created_at": meta.get("created_at"),
                "game_version": meta.get("game_version"),
                "sanitized": bool(meta.get("sanitized")),
                "top_level_keys": len(variables),
                "bytes": candidate.stat().st_size,
                "sha256": meta.get("sha256") or fixture_digest(variables),
                "verified": verify_fixture(fixture, name=candidate.name)["ok"],
            }
        )
    index_path = directory / "index.json"
    index_path.write_text(
        json.dumps(
            {"schema": FIXTURE_SCHEMA_VERSION, "fixtures": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return index_path


def default_fixture_name(label: str | None, source: str) -> str:
    stamp = time.strftime("%y%m%d-%H%M%S")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", (label or source)).strip("-") or source
    stem = re.sub(r"\.{2,}", "-", stem) or source
    return f"{stem}-{stamp}.json"


# --------------------------------------------------------------------------- #
# Runtime (browser) side
# --------------------------------------------------------------------------- #

VERSION_PROBE = r"""
() => {
  const out = { version: null, version_source: null, save_api: [], globals: {} };
  const candidates = [
    ["V.version", () => window.V && window.V.version],
    ["setup.version", () => window.setup && setup.version],
    ["V.gameversion", () => window.V && (V.gameversion || V.gameVersion)],
    ["setup.modVersion", () => window.setup && setup.modVersion],
  ];
  for (const [label, getter] of candidates) {
    try {
      const value = getter();
      if (typeof value === "string" && value.trim()) {
        out.version = value.trim();
        out.version_source = label;
        break;
      }
    } catch (_) {}
  }
  try { out.save_api = Object.getOwnPropertyNames(window.SugarCube.Save).sort(); } catch (_) {}
  try {
    out.save_types = {};
    for (const name of out.save_api) out.save_types[name] = typeof window.SugarCube.Save[name];
  } catch (_) {}
  for (const name of ["V", "T", "Time", "Weather", "setup", "Wikifier", "Engine", "State"]) {
    out.globals[name] = typeof window[name];
  }
  try { out.globals.SugarCubeState = typeof window.SugarCube.State; } catch (_) {}
  try {
    out.time = { hour: Time.hour, minute: Time.minute, day: Time.day, month: Time.month, year: Time.year };
    out.weather = (typeof Weather.current === "function") ? Weather.current() : (Weather.current || null);
  } catch (_) {}
  return out;
}
"""

CAPTURE_META = r"""
() => {
  const out = { ok: false, reason: null, passage: null, save_api: [] };
  try {
    const SC = window.SugarCube;
    if (!SC || !SC.State || !SC.State.variables) { out.reason = "State.variables missing"; return out; }
    out.ok = true;
    out.passage = SC.State.passage;
    out.save_api = SC.Save ? Object.getOwnPropertyNames(SC.Save).sort() : [];
    return out;
  } catch (e) { out.reason = String(e && e.message ? e.message : e); return out; }
}
"""

# The game's own export code (verified in the built artifact) is:
#     data = LZString.compressToBase64(JSON.stringify(_marshal(...)))
#     file = data + LZString.compressToBase64(JSON.stringify({[domId]: data.length}))
# ``Save.serialize()`` produces ``data`` alone (the clipboard/share flavour),
# while the on-disk ``.save`` file carries the appended metadata tail.
EXPORT_PAYLOADS = r"""
() => {
  const SC = window.SugarCube;
  const out = { ok: false, errors: [], save_api: [], domId: null };
  if (!SC || !SC.Save || typeof SC.Save.serialize !== "function") {
    out.errors.push("Save.serialize unavailable");
    return out;
  }
  try {
    out.save_api = Object.getOwnPropertyNames(SC.Save).sort();
    out.domId = SC.Story ? SC.Story.domId : null;
    const data = SC.Save.serialize();
    if (typeof data !== "string" || !data) { out.errors.push("serialize returned nothing"); return out; }
    out.single = data;
    if (typeof LZString !== "undefined" && SC.Story) {
      const tail = LZString.compressToBase64(JSON.stringify({ [SC.Story.domId]: data.length }));
      out.disk = data + tail;
      out.disk_tail_bytes = tail.length;
    }
    out.ok = true;
    return out;
  } catch (e) {
    out.errors.push(String(e && e.message ? e.message : e));
    return out;
  }
}
"""

# Import path, measured on the 0.5.11.9 artifact (2026-10-04): the game's own
# ``Save.deserialize`` (which wraps the private ``_unmarshal``) returned ``null``
# for *both* the single-part and the two-part disk payloads, while a faithful
# inline re-implementation of the same steps -- rebuild delta history, validate
# ``id``, ``State.unmarshalForSave``, ``Engine.show`` -- installed both. So the
# inline path is tried first and ``Save.deserialize`` is kept as a fallback for
# other SugarCube builds. Every attempt is reported, never guessed.
LOAD_SAVE_PAYLOAD = r"""
(payloadStr) => {
  const SC = window.SugarCube;
  const out = { ok: false, method: null, errors: [], attempted: [], passage: null, keys: 0 };
  if (!SC || !SC.Save) { out.errors.push("SugarCube.Save missing"); return out; }
  const readState = () => {
    try {
      out.passage = SC.State.passage;
      out.keys = Object.keys(SC.State.variables || {}).length;
    } catch (_) {}
  };
  // Path 1: verified inline re-implementation.
  try {
    out.attempted.push("inline");
    const LZ = window.LZString;
    const jsonstring = (LZ && typeof LZ.decompressFromBase64 === "function")
      ? (LZ.decompressFromBase64(payloadStr) || payloadStr)
      : payloadStr;
    const saveObj = JSON.parse(jsonstring);
    if (!saveObj || !saveObj.state) throw new Error("no state in payload");
    if (!saveObj.state.history) {
      if (saveObj.state.jdelta) delete saveObj.state.jdelta;
      if (saveObj.state.delta) saveObj.state.history = SC.State.deltaDecode(saveObj.state.delta);
      delete saveObj.state.delta;
    }
    if (saveObj.id !== SC.Config.saves.id) throw new Error("save id mismatch: " + saveObj.id);
    saveObj.state.idx = saveObj.idx || "";
    SC.State.unmarshalForSave(saveObj.state);
    if (SC.Engine && typeof SC.Engine.show === "function") SC.Engine.show();
    out.ok = true;
    out.method = "inline unmarshalForSave";
    readState();
    return out;
  } catch (e) {
    out.errors.push("inline: " + String(e && e.message ? e.message : e).slice(0, 240));
  }
  // Path 2: the game's own deserialize, for builds where it accepts the payload.
  try {
    out.attempted.push("Save.deserialize");
    const metadata = SC.Save.deserialize(payloadStr);
    if (metadata !== null && metadata !== undefined) {
      out.ok = true;
      out.method = "Save.deserialize";
      out.metadata = (metadata && typeof metadata === "object")
        ? Object.keys(metadata).slice(0, 10)
        : null;
      readState();
      return out;
    }
    out.errors.push("Save.deserialize returned null");
  } catch (e) {
    out.errors.push("Save.deserialize: " + String(e && e.message ? e.message : e).slice(0, 240));
  }
  return out;
}
"""


def _session(target: Path, *, headless: bool, timeout_ms: int, settle_ms: int):
    """Boot the artifact into gameplay; reuses the phase-1 session plumbing."""
    from tools import sweep_flow_assertions as sfa

    html_path = ps.resolve_html_path(target)
    return html_path, sfa._session(
        html_path, headless=headless, timeout_ms=timeout_ms, bootstrap_settle_ms=settle_ms
    )


def _detect_game_version(html_path: Path) -> str | None:
    """Read the game version from the embedded modList (static, no browser)."""
    try:
        from tools import sweep_flow_assertions as sfa

        inventory = sfa.embedded_mod_inventory(html_path)
        for mod in inventory.get("mods") or []:
            name = str(mod.get("name") or "")
            if "lewdity" in name.lower():
                version = mod.get("version")
                if version:
                    return str(version)
    except Exception:  # noqa: BLE001 - version is a nice-to-have, not a gate
        pass
    return None


def capture(
    target: Path,
    *,
    label: str | None,
    out: Path | None,
    headless: bool,
    timeout_ms: int,
    settle_ms: int,
    game_version: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Snapshot the live bootstrap state into a fixture file."""
    html_path, session = _session(
        target, headless=headless, timeout_ms=timeout_ms, settle_ms=settle_ms
    )
    detected = game_version or _detect_game_version(html_path)
    with session as (page, boot, console):
        info = page.evaluate(CAPTURE_META)
        if not info.get("ok"):
            raise SystemExit(f"capture refused: {info.get('reason')}")
        version_probe = page.evaluate(VERSION_PROBE)
        if not detected:
            detected = version_probe.get("version")
        snapshot = json.loads(page.evaluate(ps.FIXTURE_SNAPSHOT))
        if not snapshot.get("ok"):
            raise SystemExit(f"snapshot failed: {snapshot.get('error')}")
        fixture = build_fixture(
            snapshot.get("variables") or {},
            label=label or "bootstrap",
            source="synthetic",
            game_version=detected,
            snapshot_meta=snapshot.get("meta"),
            notes=f"boot passage={boot.get('passage')} steps={boot.get('steps')}",
        )
        fixture["meta"]["runtime"] = {
            "version_probe": version_probe,
            "save_api": info.get("save_api"),
            "passage": info.get("passage"),
            "console_tail": console[-20:],
        }

    if find_personal_paths(fixture["variables"], limit=1):
        fixture, counts = sanitize_fixture(fixture, note="capture-time path scrub")
        fixture["meta"]["label"] = label or "bootstrap"
        print(f"[fixture] capture-time path scrub: {counts}")
    fixture["meta"]["sha256"] = fixture_digest(fixture["variables"])
    fixture["stats"] = fixture_stats(fixture["variables"], base=fixture.get("stats"))
    path = save_fixture(fixture, out or (DEFAULT_DIR / default_fixture_name(label, "synthetic")))
    update_index(path.parent)
    return path, fixture


def capture_from_save(
    target: Path,
    save_file: Path,
    *,
    label: str | None,
    out: Path | None,
    headless: bool,
    timeout_ms: int,
    settle_ms: int,
    allow_real: bool,
    game_version: str | None = None,
    redact_values: Iterable[str] = (),
    redact_name_paths: Iterable[str] = (),
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Import a save file inside the game, then snapshot the resulting state."""
    if not allow_real:
        raise SystemExit(
            "refusing to import a save file without --allow-real: real saves may "
            "carry personal data, so importing is an explicit decision"
        )
    payload = save_file.read_text(encoding="utf-8", errors="replace").strip()
    if not payload:
        raise SystemExit(f"save file is empty: {save_file}")
    html_path, session = _session(
        target, headless=headless, timeout_ms=timeout_ms, settle_ms=settle_ms
    )
    detected = game_version or _detect_game_version(html_path)
    with session as (page, _boot, _console):
        version_probe = page.evaluate(VERSION_PROBE)
        if not detected:
            detected = version_probe.get("version")
        load = page.evaluate(LOAD_SAVE_PAYLOAD, payload)
        if not load.get("ok"):
            raise SystemExit(f"save import failed: {load}")
        page.wait_for_timeout(1200)
        # Let the imported moment re-render before snapshotting.
        page.evaluate(
            "(() => { try { const p = window.SugarCube.State.passage;"
            " if (p) window.SugarCube.Engine.play(p); return true; } catch (e) { return false; } })()"
        )
        page.wait_for_timeout(max(600, settle_ms // 2))
        snapshot = json.loads(page.evaluate(ps.FIXTURE_SNAPSHOT))
        if not snapshot.get("ok"):
            raise SystemExit(f"snapshot after import failed: {snapshot.get('error')}")
        fixture = build_fixture(
            snapshot.get("variables") or {},
            label=label or f"from-save-{save_file.stem}"[:60],
            source="real-sanitized",
            game_version=detected,
            snapshot_meta=snapshot.get("meta"),
            notes=f"imported {save_file.name} via {load.get('method')}",
            source_save_sha256=file_digest(save_file),
        )
        fixture["meta"]["import"] = {
            "method": load.get("method"),
            "parse": load.get("parse"),
            "errors": load.get("errors"),
            "payload_bytes": len(payload),
        }

    name_like = [item["path"] for item in find_name_candidates(fixture["variables"])]
    names = list(redact_name_paths)
    fixture, counts = sanitize_fixture(
        fixture,
        redact_values=redact_values,
        redact_name_paths=names,
        redact_names=bool(names),
        note=(
            "real-save import: absolute paths scrubbed"
            + ("; explicit name paths redacted" if names else "")
        ),
    )
    fixture["meta"]["label"] = label or f"from-save-{save_file.stem}"[:60]
    fixture["meta"]["name_like_paths"] = name_like[:40]
    fixture["stats"] = fixture_stats(fixture["variables"], base=fixture.get("stats"))
    path = save_fixture(fixture, out or (DEFAULT_DIR / default_fixture_name(label, "from-save")))
    update_index(path.parent)
    return path, fixture, {
        "load": load,
        "counts": counts,
        "name_paths": names,
        "name_like_paths": name_like,
    }


def selftest(
    target: Path,
    *,
    label: str | None,
    out_dir: Path,
    headless: bool,
    timeout_ms: int,
    settle_ms: int,
) -> dict[str, Any]:
    """Round-trip a generated save (both formats) through the from-save importer."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path, session = _session(
        target, headless=headless, timeout_ms=timeout_ms, settle_ms=settle_ms
    )
    report: dict[str, Any] = {"target": str(target), "html_path": str(html_path)}
    with session as (page, boot, _console):
        report["boot"] = {"passage": boot.get("passage"), "steps": boot.get("steps")}
        serialize = page.evaluate(EXPORT_PAYLOADS)
        if not serialize.get("ok"):
            raise SystemExit(f"selftest: Save.serialize failed: {serialize}")
        save_file = out_dir / "selftest-roundtrip.save"
        disk_payload = serialize.get("disk") or serialize["single"]
        save_file.write_text(disk_payload, encoding="utf-8")
        report["serialize"] = {
            "single_bytes": len(serialize["single"]),
            "disk_bytes": len(disk_payload),
            "disk_tail_bytes": serialize.get("disk_tail_bytes"),
            "dom_id": serialize.get("domId"),
            "save_api": serialize.get("save_api"),
            "save_file": str(save_file),
            "sha256": file_digest(save_file),
        }
        before = json.loads(page.evaluate(ps.FIXTURE_SNAPSHOT))
        # Both payload flavours are probed in the *same* page so a failure of one
        # cannot be confused with a flaky boot.
        report["formats"] = {
            "disk": page.evaluate(LOAD_SAVE_PAYLOAD, disk_payload),
            "single": page.evaluate(LOAD_SAVE_PAYLOAD, serialize["single"]),
        }
    report["before_keys"] = len(before.get("variables") or {})

    path, fixture, extra = capture_from_save(
        target,
        save_file,
        label=label or "selftest-roundtrip",
        out=out_dir / "selftest-roundtrip.json",
        headless=headless,
        timeout_ms=timeout_ms,
        settle_ms=settle_ms,
        allow_real=True,
    )
    report["import"] = extra["load"]
    report["after_keys"] = len(fixture["variables"])
    report["fixture"] = str(path)
    report["sanitize_counts"] = extra["counts"]
    report["verification"] = verify_fixture(fixture, name=path.name)
    report["ok"] = bool(
        report["verification"]["ok"]
        and report["import"].get("ok")
        and (report["formats"].get("disk") or {}).get("ok")
        and report["after_keys"] >= max(100, int(report["before_keys"] * 0.6))
    )
    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _add_common_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--headful", action="store_true", help="show the browser window")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--settle-ms", type=int, default=1500)
    parser.add_argument("--game-version", default=None, help="override the detected version")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DOL-X fixture ladder (engine A)")
    sub = parser.add_subparsers(dest="command", required=True)

    capture_p = sub.add_parser("capture", help="snapshot the live bootstrap state")
    capture_p.add_argument("target", type=Path)
    capture_p.add_argument("--out", type=Path, default=None)
    capture_p.add_argument("--label", default=None)
    _add_common_browser_args(capture_p)

    from_p = sub.add_parser("from-save", help="import a discardable save file, then snapshot")
    from_p.add_argument("target", type=Path)
    from_p.add_argument("save_file", type=Path)
    from_p.add_argument("--out", type=Path, default=None)
    from_p.add_argument("--label", default=None)
    from_p.add_argument(
        "--allow-real",
        action="store_true",
        help="required acknowledgement that the save is discardable and personal",
    )
    from_p.add_argument(
        "--redact-value",
        action="append",
        default=[],
        help="exact string value to replace (repeatable)",
    )
    from_p.add_argument(
        "--redact-name-path",
        action="append",
        default=[],
        help="dotted variable path to replace with [redacted-name] (repeatable)",
    )
    _add_common_browser_args(from_p)

    self_p = sub.add_parser("selftest", help="round-trip a generated save through from-save")
    self_p.add_argument("target", type=Path)
    self_p.add_argument("--out", type=Path, default=DEFAULT_DIR)
    self_p.add_argument("--label", default=None)
    _add_common_browser_args(self_p)

    sanitize_p = sub.add_parser("sanitize", help="strip personal data from a fixture")
    sanitize_p.add_argument("fixture", type=Path)
    sanitize_p.add_argument("--out", type=Path, default=None)
    sanitize_p.add_argument("--redact-value", action="append", default=[])
    sanitize_p.add_argument("--redact-name-path", action="append", default=[])
    sanitize_p.add_argument("--redact-names", action="store_true")
    sanitize_p.add_argument("--force", action="store_true", help="allow in-place rewrite")

    verify_p = sub.add_parser("verify", help="validate fixtures")
    verify_p.add_argument("fixture", type=Path, nargs="+")

    list_p = sub.add_parser("list", help="print the fixture manifest")
    list_p.add_argument("--dir", type=Path, default=DEFAULT_DIR)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "capture":
        path, fixture = capture(
            args.target,
            label=args.label,
            out=args.out,
            headless=not args.headful,
            timeout_ms=args.timeout_ms,
            settle_ms=args.settle_ms,
            game_version=args.game_version,
        )
        print(f"[fixture] captured {len(fixture['variables'])} keys -> {path}")
        print(
            f"[fixture] game_version={fixture['meta']['game_version']} "
            f"sha256={fixture['meta']['sha256'][:16]}"
        )
        return 0

    if args.command == "from-save":
        path, fixture, extra = capture_from_save(
            args.target,
            args.save_file,
            label=args.label,
            out=args.out,
            headless=not args.headful,
            timeout_ms=args.timeout_ms,
            settle_ms=args.settle_ms,
            allow_real=args.allow_real,
            game_version=args.game_version,
            redact_values=args.redact_value,
            redact_name_paths=args.redact_name_path,
        )
        print(f"[fixture] imported via {extra['load'].get('method')} -> {path}")
        print(f"[fixture] keys={len(fixture['variables'])} redactions={extra['counts']}")
        if extra.get("name_like_paths"):
            print(
                f"[fixture] {len(extra['name_like_paths'])} name-like leaves seen "
                f"(paths recorded in meta; pass --redact-name-path to rewrite any)"
            )
        return 0

    if args.command == "selftest":
        report = selftest(
            args.target,
            label=args.label,
            out_dir=args.out,
            headless=not args.headful,
            timeout_ms=args.timeout_ms,
            settle_ms=args.settle_ms,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "sanitize":
        fixture = load_fixture(args.fixture)
        names = args.redact_name_path or [
            item["path"] for item in find_name_candidates(fixture.get("variables") or {})
        ]
        clean, counts = sanitize_fixture(
            fixture,
            redact_values=args.redact_value,
            redact_name_paths=names,
            redact_names=args.redact_names,
            note="manual sanitize",
        )
        if args.out:
            target = args.out
        elif args.force:
            target = args.fixture
        else:
            target = args.fixture.with_name(f"{args.fixture.stem}-sanitized.json")
        save_fixture(clean, target)
        update_index(target.parent)
        print(f"[fixture] sanitized -> {target} counts={counts}")
        verdict = verify_fixture(clean, name=target.name)
        print(f"[fixture] verify: {'ok' if verdict['ok'] else 'FAILED'} {verdict['errors']}")
        return 0 if verdict["ok"] else 1

    if args.command == "verify":
        failed = 0
        for path in args.fixture:
            verdict = verify_fixture(load_fixture(path), name=path.name)
            status = "ok" if verdict["ok"] else "FAILED"
            print(f"[{status}] {path}")
            for error in verdict["errors"]:
                print(f"    error: {error}")
            for warning in verdict["warnings"]:
                print(f"    warn:  {warning}")
            failed += 0 if verdict["ok"] else 1
        return 1 if failed else 0

    if args.command == "list":
        index_path = args.dir / "index.json"
        if not index_path.exists():
            update_index(args.dir)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for record in index.get("fixtures", []):
            print(
                f"{record['file']:<44} {str(record.get('source')):<15} "
                f"{str(record.get('game_version')):<12} keys={record.get('top_level_keys')} "
                f"verified={record.get('verified')}"
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
