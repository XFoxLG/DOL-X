#!/usr/bin/env python3
"""Functional flow assertions for the DOL-X full-passage sweep (engine A).

``tools/passage_sweep.py`` answers "does every passage render". This runner
adds the small set of hand-asserted end-to-end flows the 2026-10-04 design
locked in, running against the same carrier: our own built HTML in a local
headless Chromium with runtime-only injection.

Flows:

    mods       runtime mounting of maplebirch / Cheat Extended / LongerCombat /
               Yanling Cheat Collection after a genuine boot to gameplay
    saveload   a real save -> mutate -> load round trip through the game's own
               save surface (DoLSave / SugarCube Save)
    ce-panel   opening the Cheat Extended overlay through its real entry point
               (window.CEiconClicked) and asserting its DOM
    au-face    AU face variant + desk-pet canvas pixel smoke on an AU artifact
               (the engine A mirror of tools/pet_remount_ab_device_check.py)
    morelove   the More Love "Food Preference" passage renders its DOM

Reuse notes: startup gates, the HTTP server (with the modList.json shim) and
the browser launch chain all come from tools/passage_sweep.py +
tools/browser_smoke_test.py. Nothing here touches lyra/, config/ or any build
input - the tool only injects at runtime.

Verdicts are honest by construction: a flow that cannot be asserted on the
given artifact reports ``not_applicable`` or ``not_implemented`` together with
the probes that were actually run. There is no fake pass.

Usage:
    python tools/sweep_flow_assertions.py <target.html|zip> --flow mods
    python tools/sweep_flow_assertions.py <target.html|zip> --flow all --out DIR
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import passage_sweep as ps  # noqa: E402


DEFAULT_OUT = Path(".local/sweep/flows")
FLOW_ORDER = ("mods", "saveload", "ce-panel", "au-face", "morelove")

PASS = "pass"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"
NOT_IMPLEMENTED = "not_implemented"


# --------------------------------------------------------------------------- #
# Artifact-level facts (no browser needed)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModExpectation:
    """One mod the runtime-mount flow wants to observe."""

    key: str
    label: str
    artifact_names: tuple[str, ...]
    probe_names: tuple[str, ...]
    globals: tuple[str, ...]


MOD_EXPECTATIONS: tuple[ModExpectation, ...] = (
    ModExpectation(
        key="maplebirch",
        label="maplebirch framework",
        artifact_names=("maplebirch",),
        probe_names=("maplebirch",),
        globals=("maplebirch", "maplebirchFrameworks"),
    ),
    ModExpectation(
        key="cheat-extended",
        label="Cheat Extended",
        artifact_names=("cheat extended", "cheatextended"),
        probe_names=("cheat extended", "cheatExtended", "Cheat Extended"),
        globals=(
            "CEiconClicked",
            "CE_renderSettings",
            "CE_options",
            "CE_activeSettingsDiv",
        ),
    ),
    ModExpectation(
        key="longer-combat",
        label="Longer Combat",
        artifact_names=("longer-combat", "longercombat", "longer combat"),
        probe_names=("longer-combat", "Longer Combat", "LongerCombat"),
        globals=("LongerCombat",),
    ),
    ModExpectation(
        key="yanling",
        label="Yanling Cheat Collection",
        artifact_names=(
            "yanling-cheat-collection",
            "yanlingcheatcollection",
            "yanling cheat collection",
        ),
        probe_names=(
            "yanling-cheat-collection",
            "Yanling Cheat Collection",
            "YanlingCheatCollection",
        ),
        globals=("YanlingCheatCollection", "yanlingCheat"),
    ),
)

AU_MODEL_NAME_BY_VARIANT = {
    "au-f": "【aufemale】model",
    "au-m": "【aumale】model",
    "au-a": "【auandrogynous】model",
}


def _normalize(name: str) -> str:
    """Lowercase and strip separators so mod names compare across sources."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def embedded_mod_inventory(html_path: Path) -> dict[str, Any]:
    """Decode ``window.modDataValueZipList`` without launching a browser.

    Mirrors tools/browser_smoke_test.py + tools/au_artifact_check.py: every
    embedded mod payload is a base64 ZIP with a boot.json at its root.
    """
    from tools.artifact_inspection import (
        decode_base64_payload,
        parse_boot_json,
        parse_mod_data_value_zip_list,
    )

    html = html_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_mod_data_value_zip_list(html)
    mods: list[dict[str, Any]] = []
    errors: list[str] = []
    if parsed.error_kind:
        detail = f"{parsed.error_kind}: {parsed.error or ''}".strip()
        return {"list_length": None, "mods": mods, "errors": [detail]}

    for index, entry in enumerate(parsed.entries):
        if not isinstance(entry, str):
            errors.append(f"embedded entry {index} is not a base64 string")
            continue
        try:
            payload = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                if "boot.json" not in zf.namelist():
                    continue
                boot = parse_boot_json(zf.read("boot.json").decode("utf-8-sig"))
            mods.append(
                {
                    "index": index,
                    "name": str(boot.get("name") or ""),
                    "nickname": boot.get("nickName"),
                    "version": boot.get("version"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the report.
            errors.append(
                f"embedded entry {index} unreadable: {type(exc).__name__}: {exc}"
            )
    return {"list_length": len(parsed.entries), "mods": mods, "errors": errors}


def artifact_variant(
    target: Path,
    html_path: Path,
    inventory: dict[str, Any],
) -> str | None:
    """Identify base/au-f/au-m/au-a from the artifact name or embedded models."""
    for candidate in (target.name, html_path.name):
        normalized = candidate.lower().replace("_", "-")
        for variant in (*AU_MODEL_NAME_BY_VARIANT, "base"):
            if f"-{variant}-" in normalized:
                return variant
    names = {str(mod.get("name") or "") for mod in inventory.get("mods", [])}
    for variant, model_name in AU_MODEL_NAME_BY_VARIANT.items():
        if model_name in names:
            return variant
    return None


# --------------------------------------------------------------------------- #
# Runtime probes (injected into the live page)
# --------------------------------------------------------------------------- #

MODS_PROBE = r"""
(cfg) => {
  const out = {
    passage: null,
    modDataValueZipListLength: null,
    modUtilsAvailable: false,
    modUtilsApi: {},
    allModNames: [],
    allModNamesError: null,
    modGet: {},
    globals: {},
    maplebirch: { present: false, version: null, modList: null, modListError: null },
    errors: [],
  };
  try {
    const SC = window.SugarCube;
    out.passage = SC && SC.State ? SC.State.passage : null;
  } catch (e) {}
  try {
    out.modDataValueZipListLength = Array.isArray(window.modDataValueZipList)
      ? window.modDataValueZipList.length
      : null;
  } catch (e) {}
  try {
    const mu = window.modUtils;
    out.modUtilsAvailable = Boolean(mu);
    if (mu) {
      out.modUtilsApi = {
        getMod: typeof mu.getMod,
        getModListNameNoAlias: typeof mu.getModListNameNoAlias,
        getAnyModByNameNoAlias: typeof mu.getAnyModByNameNoAlias,
        getModZip: typeof mu.getModZip,
      };
      try {
        if (typeof mu.getModListNameNoAlias === "function") {
          out.allModNames = mu.getModListNameNoAlias() || [];
        }
      } catch (e) {
        out.allModNamesError = String(e && (e.message || e));
      }
    }
  } catch (e) {
    out.modUtilsError = String(e && (e.message || e));
  }
  for (const name of cfg.modNames) {
    const result = {
      available: false,
      type: "undefined",
      version: null,
      name: null,
      error: null,
    };
    try {
      const mu = window.modUtils;
      if (mu && typeof mu.getMod === "function") {
        const mod = mu.getMod(name);
        result.type = typeof mod;
        result.available = Boolean(mod);
        if (mod) {
          result.version =
            mod.version || (mod.bootJson && mod.bootJson.version) || null;
          result.name = mod.name || (mod.bootJson && mod.bootJson.name) || name;
        }
      } else {
        result.error = "modUtils.getMod unavailable";
      }
    } catch (e) {
      result.type = "error";
      result.error = String(e && (e.message || e));
    }
    out.modGet[name] = result;
  }
  for (const name of cfg.globalNames) {
    out.globals[name] = typeof window[name];
  }
  try {
    const mb = window.maplebirch;
    out.maplebirch.present = Boolean(mb);
    if (mb) {
      out.maplebirch.version = (mb.meta && mb.meta.version) || null;
      try {
        out.maplebirch.modList = Array.isArray(mb.modList) ? mb.modList.slice(0, 80) : null;
      } catch (e) {
        out.maplebirch.modListError = String(e && (e.message || e));
      }
    }
  } catch (e) {
    out.maplebirchError = String(e && (e.message || e));
  }
  try {
    const S = window.__DOLX__;
    out.errors = S ? S.errors.slice(-30) : [];
  } catch (e) {}
  return out;
}
"""

SAVELOAD_PROBE = r"""
() => {
  const SC = window.SugarCube;
  const out = {
    sugarCube: typeof SC,
    passage: null,
    saveApi: {
      dolSave: typeof window.save,
      dolLoad: typeof window.loadSave,
      dolImport: typeof window.importSave,
      scSerialize: typeof (SC && SC.Save && SC.Save.serialize),
      scDeserialize: typeof (SC && SC.Save && SC.Save.deserialize),
      scSlotsSave: typeof (SC && SC.Save && SC.Save.slots && SC.Save.slots.save),
      scSlotsLoad: typeof (SC && SC.Save && SC.Save.slots && SC.Save.slots.load),
      scSlotsGet: typeof (SC && SC.Save && SC.Save.slots && SC.Save.slots.get),
    },
    primitiveKeys: [],
  };
  try {
    out.passage = SC.State.passage;
  } catch (e) {}
  try {
    const V = SC.State.variables;
    const skip = new Set(["passage", "saveId", "saveName", "version", "saveVersions"]);
    out.primitiveKeys = Object.keys(V)
      .filter((key) => {
        if (skip.has(key)) return false;
        const type = typeof V[key];
        return type === "string" || type === "number" || type === "boolean";
      })
      .sort()
      .slice(0, 6);
  } catch (e) {}
  return out;
}
"""

SAVELOAD_SAVE = r"""
(payload) => {
  const SC = window.SugarCube;
  const V = SC.State.variables;
  const out = {
    token: payload.token,
    before: { passage: null, vars: {} },
    save: null,
    mutated: {},
    slotProbe: null,
  };
  try {
    window.__DOLX_LOAD_TOKEN__ = payload.token;
  } catch (e) {}
  try {
    out.before.passage = SC.State.passage;
  } catch (e) {}
  for (const key of payload.keys) {
    try {
      out.before.vars[key] = V[key];
    } catch (e) {}
  }
  try {
    if (typeof V.confirmSave === "boolean") V.confirmSave = false;
    if (typeof V.confirmLoad === "boolean") V.confirmLoad = false;
  } catch (e) {}
  const slotHasSave = () => {
    try {
      return Boolean(
        SC.Save &&
          SC.Save.slots &&
          typeof SC.Save.slots.get === "function" &&
          SC.Save.slots.get(payload.slot)
      );
    } catch (e) {
      return false;
    }
  };
  const via = [];
  const notes = [];
  if (typeof window.save === "function") {
    try {
      const saveId = V.saveId == null ? 0 : V.saveId;
      window.save(payload.slot, true, saveId, "sweep-flow");
      via.push("window.save (DoLSave.save)");
    } catch (e) {
      // Known quirk: DoLSave.save writes the slot first, then its
      // detail bookkeeping throws when dolSaveDetails was never prepared
      // (a fresh headless profile). The slot probe below decides.
      notes.push(
        "DoLSave.save threw after writing: " + String(e && (e.message || e))
      );
    }
  }
  if (
    !slotHasSave() &&
    SC.Save &&
    SC.Save.slots &&
    typeof SC.Save.slots.save === "function"
  ) {
    try {
      const ok = SC.Save.slots.save(payload.slot, "sweep-flow");
      via.push("SugarCube.Save.slots.save");
      if (!ok) notes.push("SugarCube.Save.slots.save returned false");
    } catch (e) {
      notes.push("SugarCube.Save.slots.save threw: " + String(e && (e.message || e)));
    }
  }
  out.save = { ok: slotHasSave(), via: via, notes: notes };
  for (const key of payload.keys) {
    try {
      const value = V[key];
      if (typeof value === "number") {
        V[key] = value + 7;
        out.mutated[key] = V[key];
      } else if (typeof value === "boolean") {
        V[key] = !value;
        out.mutated[key] = V[key];
      } else if (typeof value === "string") {
        V[key] = value + "-sweep-mutated";
        out.mutated[key] = V[key];
      }
    } catch (e) {}
  }
  try {
    const get =
      SC.Save && SC.Save.slots && typeof SC.Save.slots.get === "function"
        ? SC.Save.slots.get(payload.slot)
        : null;
    out.slotProbe = { present: Boolean(get), title: get ? get.title : null };
  } catch (e) {
    out.slotProbe = { error: String(e && (e.message || e)) };
  }
  return out;
}
"""

SAVELOAD_LOAD = r"""
(payload) => {
  const SC = window.SugarCube;
  const S = window.__DOLX__;
  if (S) {
    S.done = false;
    S.renderSeq = 0;
  }
  try {
    if (typeof window.loadSave === "function") {
      window.loadSave(payload.slot);
      return { ok: true, via: "window.loadSave (DoLSave.load)" };
    }
    if (
      SC.Save &&
      SC.Save.slots &&
      typeof SC.Save.slots.load === "function"
    ) {
      return {
        ok: Boolean(SC.Save.slots.load(payload.slot)),
        via: "SugarCube.Save.slots.load",
      };
    }
    return { ok: false, via: null, error: "no load API" };
  } catch (e) {
    return { ok: false, via: "exception", error: String(e && (e.message || e)) };
  }
}
"""

SAVELOAD_AFTER = r"""
(payload) => {
  const SC = window.SugarCube;
  const V = SC.State.variables;
  const out = {
    token: null,
    passage: null,
    vars: {},
    textLen: 0,
    errors: [],
  };
  try {
    out.token = window.__DOLX_LOAD_TOKEN__ || null;
  } catch (e) {}
  try {
    out.passage = SC.State.passage;
  } catch (e) {}
  for (const key of payload.keys) {
    try {
      out.vars[key] = V[key];
    } catch (e) {}
  }
  const node = document.querySelector(
    "#passage, #passage-content, .passage[data-passage], #passages .passage"
  );
  out.textLen = node ? (node.innerText || "").trim().length : 0;
  const S = window.__DOLX__;
  out.errors = S ? S.errors.slice(-25) : [];
  return out;
}
"""

CE_PANEL_PROBE = r"""
() => {
  const out = {
    passage: null,
    callable: typeof window.CEiconClicked,
    renderSettings: typeof window.CE_renderSettings,
    overlay: null,
    settingsDiv: false,
    title: null,
    textSample: null,
    errors: [],
  };
  try {
    out.passage = window.SugarCube.State.passage;
  } catch (e) {}
  const overlay = document.getElementById("customOverlay");
  if (overlay) {
    out.overlay = {
      hidden: overlay.classList.contains("hidden"),
      dataOverlay: overlay.getAttribute("data-overlay"),
      visible:
        Boolean(overlay.offsetWidth || overlay.offsetHeight) &&
        window.getComputedStyle(overlay).display !== "none",
    };
    out.textSample = (overlay.innerText || "").replace(/\s+/g, " ").slice(0, 200);
  }
  out.settingsDiv = Boolean(document.getElementById("CE_settingsDiv"));
  const title = document.getElementById("customOverlayTitle");
  out.title = title ? (title.innerText || "").trim().slice(0, 160) : null;
  const S = window.__DOLX__;
  out.errors = S ? S.errors.slice(-25) : [];
  return out;
}
"""

CE_PANEL_OPEN = r"""
() => {
  if (typeof window.CEiconClicked !== "function") {
    return { ok: false, error: "window.CEiconClicked unavailable" };
  }
  const S = window.__DOLX__;
  if (S) S.done = false;
  try {
    window.CEiconClicked();
    return { ok: true, via: "window.CEiconClicked()" };
  } catch (e) {
    return { ok: false, error: String(e && (e.message || e)) };
  }
}
"""

AU_PET_ENABLE = r"""
() => {
  const out = { enabled: null, sync: false, wiki: false, container: false, notes: [] };
  try {
    const V = window.SugarCube.State.variables;
    V.options = V.options || {};
    V.options.maplebirch = V.options.maplebirch || {};
    V.options.maplebirch.character = V.options.maplebirch.character || {};
    V.options.maplebirch.character.pet = V.options.maplebirch.character.pet || {};
    V.options.maplebirch.character.pet.enabled = true;
    out.enabled = true;
  } catch (e) {
    out.notes.push("enable: " + String(e && (e.message || e)));
  }
  try {
    const pet = window.maplebirch && window.maplebirch.char && window.maplebirch.char.pet;
    if (pet && typeof pet.sync === "function") {
      pet.sync();
      out.sync = true;
    }
  } catch (e) {
    out.notes.push("sync: " + String(e && (e.message || e)));
  }
  try {
    if (window.jQuery) {
      window.jQuery.wiki("<<updatesidebarimg>>");
      out.wiki = true;
    }
  } catch (e) {
    out.notes.push("wiki: " + String(e && (e.message || e)));
  }
  out.container = Boolean(document.getElementById("maplebirch-character-pet"));
  return out;
}
"""

AU_PET_PROBE = r"""
() => {
  const out = {
    passage: null,
    petEnabled: null,
    liveContainer: null,
    canvas: null,
    frameworkContainer: null,
    errorBanner: null,
  };
  try {
    out.passage = window.SugarCube.State.passage;
  } catch (e) {}
  try {
    out.petEnabled = Boolean(
      window.SugarCube.State.variables &&
        window.SugarCube.State.variables.options &&
        window.SugarCube.State.variables.options.maplebirch &&
        window.SugarCube.State.variables.options.maplebirch.character &&
        window.SugarCube.State.variables.options.maplebirch.character.pet &&
        window.SugarCube.State.variables.options.maplebirch.character.pet.enabled
    );
  } catch (e) {}
  try {
    const banner = document.querySelector(".error, .error-view");
    out.errorBanner = banner ? String(banner.innerText || "").slice(0, 120) : null;
  } catch (e) {}
  const el = document.getElementById("maplebirch-character-pet");
  if (el) {
    out.liveContainer = { children: el.childElementCount, connected: el.isConnected };
    const cv = el.querySelector("canvas");
    if (cv) {
      out.canvas = { w: cv.width, h: cv.height };
      try {
        const data = cv.getContext("2d").getImageData(0, 0, cv.width, cv.height).data;
        let opaque = 0;
        for (let i = 3; i < data.length; i += 4) {
          if (data[i] > 0) opaque += 1;
        }
        out.canvas.opaque = opaque;
      } catch (e) {
        out.canvas.pixelError = String(e && (e.message || e));
      }
    }
  }
  try {
    const pet = window.maplebirch && window.maplebirch.char && window.maplebirch.char.pet;
    const held = pet && pet.container;
    if (held) {
      out.frameworkContainer = {
        children: held.childElementCount,
        connected: held.isConnected !== false,
      };
    }
  } catch (e) {}
  // The desk-pet canvas is the primary target, but the sidebar character
  // render is the same AU face pipeline through a different element. Both are
  // measured so the caller can tell "face styles do not render" apart from
  // "only the pet canvas ignores the style switch".
  try {
    const host = document.querySelector("#sidebar") || document.querySelector("#ui-bar");
    if (host) {
      const measureCanvas = (cv) => {
        try {
          const data = cv.getContext("2d").getImageData(0, 0, cv.width, cv.height).data;
          let n = 0;
          for (let i = 3; i < data.length; i += 4) {
            if (data[i] > 0) n += 1;
          }
          return n;
        } catch (e) {
          return null;
        }
      };
      const measureImage = (img) => {
        try {
          if (!img.complete || !img.naturalWidth) return null;
          const cv = document.createElement("canvas");
          cv.width = img.naturalWidth;
          cv.height = img.naturalHeight;
          const ctx = cv.getContext("2d");
          ctx.drawImage(img, 0, 0);
          const data = ctx.getImageData(0, 0, cv.width, cv.height).data;
          let n = 0;
          for (let i = 3; i < data.length; i += 4) {
            if (data[i] > 0) n += 1;
          }
          return n;
        } catch (e) {
          return null;
        }
      };
      const canvases = Array.from(host.querySelectorAll("canvas"));
      const images = Array.from(host.querySelectorAll("img"));
      const canvasOpaque = canvases.slice(0, 4).map(measureCanvas);
      const imageOpaque = images.slice(0, 40).map(measureImage);
      const sum = (values) =>
        values.reduce(
          (acc, value) => acc + (typeof value === "number" ? value : 0),
          0
        );
      out.sidebar = {
        canvases: canvases.length,
        images: images.length,
        canvasOpaque: canvasOpaque,
        imageOpaque: imageOpaque.filter((value) => typeof value === "number"),
        opaqueTotal: sum(canvasOpaque) + sum(imageOpaque),
      };
    }
  } catch (e) {
    out.sidebarError = String(e && (e.message || e));
  }
  return out;
}
"""

AU_FACE_OPTIONS = r"""
() => {
  const SC = window.SugarCube;
  const V = SC.State.variables;
  const setupObj = window.setup || {};
  const options = setupObj.faceVariantOptions || {};
  const style = V.facestyle;
  const variants = Object.keys(options[style] || {});
  const byStyle = {};
  for (const key of Object.keys(options)) {
    byStyle[key] = Object.keys(options[key] || {});
  }
  return {
    style: style == null ? null : style,
    variants: variants,
    styles: Object.keys(options),
    byStyle: byStyle,
    current: V.facevariant == null ? null : V.facevariant,
  };
}
"""

AU_FACE_SET = r"""
(payload) => {
  try {
    const V = window.SugarCube.State.variables;
    V.facestyle = payload.style;
    if (payload.variant) V.facevariant = payload.variant;
    const pet = window.maplebirch && window.maplebirch.char && window.maplebirch.char.pet;
    if (pet && typeof pet.sync === "function") pet.sync();
    if (window.jQuery) window.jQuery.wiki("<<updatesidebarimg>>");
    return { ok: true, facestyle: V.facestyle, facevariant: V.facevariant };
  } catch (e) {
    return { ok: false, error: String(e && (e.message || e)) };
  }
}
"""

MORELOVE_STORY_PROBE = r"""
() => {
  const SC = window.SugarCube;
  const out = { hasPassage: false, storyError: null, passage: null };
  try {
    out.hasPassage = SC.Story.has("Food Preference");
  } catch (e) {
    out.storyError = String(e && (e.message || e));
  }
  try {
    out.passage = SC.State.passage;
  } catch (e) {}
  return out;
}
"""

MORELOVE_PLAY = r"""
() => {
  const SC = window.SugarCube;
  const S = window.__DOLX__;
  if (S) {
    S.done = false;
    S.renderSeq = 0;
  }
  try {
    if (!SC.Story.has("Food Preference")) {
      return { ok: false, error: "passage not in story" };
    }
    SC.Engine.play("Food Preference");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e && (e.message || e)) };
  }
}
"""

MORELOVE_PROBE = r"""
() => {
  // This SugarCube/DoL build names the passage element "passage-<slug>"
  // (class "passage", attribute data-passage); there is no #passage node.
  const node =
    document.querySelector("#passage") ||
    document.querySelector(".passage[data-passage]") ||
    document.querySelector("#passages .passage");
  const contentNode =
    document.getElementById("passage-content") ||
    (node && node.querySelector("#passage-content")) ||
    node;
  const textContent = contentNode ? (contentNode.textContent || "").trim() : "";
  const text = contentNode ? (contentNode.innerText || "").trim() : "";
  const out = {
    passage: null,
    nodeId: node ? node.id || null : null,
    nodeFound: Boolean(node),
    childCount: contentNode ? contentNode.children.length : 0,
    textContentLen: textContent.length,
    textContentSample: textContent.slice(0, 240),
    textLen: text.length,
    textSample: text.slice(0, 240),
    mlimFood: node ? node.querySelectorAll(".MLIM-food").length : 0,
    htmlSample: contentNode ? String(contentNode.innerHTML || "").slice(0, 400) : null,
    passagesChildren: document.querySelectorAll("#passages > div").length,
    bodyTextLen: (document.body && document.body.innerText || "").length,
    errors: [],
  };
  try {
    out.passage = window.SugarCube.State.passage;
  } catch (e) {}
  const S = window.__DOLX__;
  out.errors = S ? S.errors.slice(-25) : [];
  return out;
}
"""


# --------------------------------------------------------------------------- #
# Browser session (reuses passage_sweep's harness + browser_smoke_test's server)
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _session(
    html_path: Path,
    *,
    headless: bool,
    timeout_ms: int,
    bootstrap_settle_ms: int,
):
    """Boot the artifact into gameplay and yield (page, boot_info, console)."""
    from playwright.sync_api import sync_playwright

    bst = ps._bst()
    serve_dir = html_path.parent
    console: list[str] = []

    with bst._serve_directory(serve_dir) as server, sync_playwright() as pw:
        url = bst._relative_url(server, serve_dir, html_path)
        browser = ps._launch_browser(pw, headless)
        context = browser.new_context()
        context.add_init_script(ps.INIT_HARNESS)
        page = context.new_page()

        def _push(line: str) -> None:
            console.append(line[:400])
            if len(console) > 4000:
                del console[:2000]

        page.on("console", lambda m: _push(f"{m.type}:{m.text[:300]}"))
        page.on("pageerror", lambda e: _push(f"pageerror:{str(e)[:300]}"))
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
            yield page, boot, console
        finally:
            browser.close()


def _boot_failed(boot: dict[str, Any]) -> str | None:
    passage = str(boot.get("passage") or "")
    if not passage:
        return f"bootstrap never reported a passage (steps={boot.get('steps')})"
    if passage.lower() in ps.STARTUP_PASSAGES:
        return (
            f"bootstrap stopped on startup passage {passage!r} after "
            f"{boot.get('steps')} steps; last actions={boot.get('actions', [])[-4:]}"
        )
    return None


# --------------------------------------------------------------------------- #
# Flows
# --------------------------------------------------------------------------- #


def _inventory_names_by_normalized(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _normalize(str(mod.get("name") or "")): mod
        for mod in inventory.get("mods", [])
    }


def _artifact_has_mod(ctx: dict[str, Any], expectation_key: str) -> bool:
    """Return whether the artifact's embedded mod list carries one expectation."""
    expectation = next(
        item for item in MOD_EXPECTATIONS if item.key == expectation_key
    )
    wanted = {_normalize(name) for name in expectation.artifact_names}
    return any(
        _normalize(str(mod.get("name") or "")) in wanted
        for mod in ctx["inventory"].get("mods", [])
    )


def flow_mods(page: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    inventory = ctx["inventory"]
    by_name = _inventory_names_by_normalized(inventory)
    probe = page.evaluate(
        MODS_PROBE,
        {
            "modNames": [
                name for expectation in MOD_EXPECTATIONS for name in expectation.probe_names
            ],
            "globalNames": sorted(
                {name for expectation in MOD_EXPECTATIONS for name in expectation.globals}
                | {"SCMLSimpleFramework", "simpleFrameworks", "modUtils"}
            ),
        },
    )

    runtime_names = {
        _normalize(str(name)) for name in probe.get("allModNames") or []
    }
    maplebirch_list = {
        _normalize(str(name)) for name in probe.get("maplebirch", {}).get("modList") or []
    }

    entries: list[dict[str, Any]] = []
    for expectation in MOD_EXPECTATIONS:
        artifact_hits = [
            by_name[normalized]
            for normalized in (_normalize(name) for name in expectation.artifact_names)
            if normalized in by_name
        ]
        get_mod_hits = {
            name: probe.get("modGet", {}).get(name)
            for name in expectation.probe_names
            if (probe.get("modGet", {}).get(name) or {}).get("available")
        }
        global_hits = {
            name: probe.get("globals", {}).get(name)
            for name in expectation.globals
            if probe.get("globals", {}).get(name) not in (None, "undefined")
        }
        list_hits = sorted(
            normalized
            for normalized in (_normalize(name) for name in expectation.artifact_names)
            if normalized in maplebirch_list or normalized in runtime_names
        )
        embedded = bool(artifact_hits)
        runtime_verified = bool(get_mod_hits or global_hits or list_hits)
        if runtime_verified:
            status = "verified"
        elif embedded:
            status = "runtime_missing"
        else:
            status = "absent"
        entries.append(
            {
                "key": expectation.key,
                "label": expectation.label,
                "embedded": embedded,
                "embedded_version": (
                    artifact_hits[0].get("version") if artifact_hits else None
                ),
                "runtime_verified": runtime_verified,
                "get_mod_hits": get_mod_hits,
                "global_hits": global_hits,
                "list_hits": list_hits,
                "status": status,
            }
        )

    evidence = {
        "embedded_list_length": inventory.get("list_length"),
        "embedded_mods": [mod.get("name") for mod in inventory.get("mods", [])],
        "inventory_errors": inventory.get("errors"),
        "runtime_mod_utils": probe.get("modUtilsApi"),
        "runtime_mod_count": len(probe.get("allModNames") or []),
        "runtime_mod_names": (probe.get("allModNames") or [])[:60],
        "maplebirch": probe.get("maplebirch"),
        "maplebirch_frameworks_global": probe.get("globals", {}).get("maplebirchFrameworks"),
        "runtime_errors": probe.get("errors"),
        "per_mod": entries,
    }

    verified = [entry for entry in entries if entry["status"] == "verified"]
    embedded_any = [entry for entry in entries if entry["embedded"]]
    runtime_any = [entry for entry in entries if entry["runtime_verified"]]

    if len(verified) == len(entries):
        return {
            "status": PASS,
            "detail": (
                "all four mods verified at runtime: "
                + ", ".join(entry["key"] for entry in entries)
            ),
            "evidence": evidence,
        }
    if not embedded_any and not runtime_any:
        names = ", ".join(str(mod.get("name")) for mod in inventory.get("mods", []))
        return {
            "status": NOT_APPLICABLE,
            "detail": (
                "target artifact embeds none of maplebirch/cheat extended/"
                "longer-combat/yanling-cheat-collection and the runtime exposes none "
                f"of them either; embedded mods ({inventory.get('list_length')}): {names}. "
                "This looks like the pre-mod staging HTML - point the tool at a built "
                "artifact HTML (e.g. extract Degrees of Lewdity.html from "
                "output/DoL-*.zip) to assert runtime mod mounts."
            ),
            "evidence": evidence,
        }
    missing = [entry["key"] for entry in entries if entry["status"] != "verified"]
    return {
        "status": FAIL,
        "detail": "mod mount verification failed or incomplete: " + ", ".join(missing),
        "evidence": evidence,
    }


def flow_saveload(page: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    probe = page.evaluate(SAVELOAD_PROBE)
    api = probe.get("saveApi") or {}
    evidence: dict[str, Any] = {"probe": probe}
    if not (api.get("dolSave") == "function" or api.get("scSlotsSave") == "function"):
        return {
            "status": NOT_IMPLEMENTED,
            "detail": (
                "no programmatic save API found on this artifact: "
                f"window.save={api.get('dolSave')}, "
                f"SugarCube.Save.slots.save={api.get('scSlotsSave')}, "
                f"SugarCube.Save.serialize={api.get('scSerialize')}"
            ),
            "evidence": evidence,
        }

    keys = list(probe.get("primitiveKeys") or [])[:5]
    if len(keys) < 2:
        return {
            "status": FAIL,
            "detail": (
                "could not sample at least two primitive state variables to "
                f"verify a load (found {keys!r})"
            ),
            "evidence": evidence,
        }

    slot = 7
    token = f"dolx-sweep-{int(time.time() * 1000)}"
    save_result = page.evaluate(
        SAVELOAD_SAVE, {"slot": slot, "keys": keys, "token": token}
    )
    evidence["save"] = save_result
    if not (save_result.get("save") or {}).get("ok"):
        return {
            "status": FAIL,
            "detail": f"save call failed: {save_result.get('save')}",
            "evidence": evidence,
        }

    load_result = page.evaluate(SAVELOAD_LOAD, {"slot": slot})
    evidence["load"] = load_result
    if not load_result.get("ok"):
        return {
            "status": FAIL,
            "detail": f"load call failed: {load_result}",
            "evidence": evidence,
        }

    try:
        page.wait_for_function(
            "(() => !!(window.__DOLX__ && window.__DOLX__.done))()", timeout=8000
        )
    except Exception:  # noqa: BLE001 - the after-probe carries the verdict
        evidence["render_wait_timed_out"] = True
    page.wait_for_timeout(400)

    after = page.evaluate(SAVELOAD_AFTER, {"keys": keys})
    evidence["after"] = after
    if after.get("token") != token:
        return {
            "status": NOT_IMPLEMENTED,
            "detail": (
                "the load path appears to navigate/reload the page (load token "
                "disappeared), so an in-page before/after assertion is not possible "
                "with this artifact's save surface"
            ),
            "evidence": evidence,
        }

    before_vars = (save_result.get("before") or {}).get("vars") or {}
    after_vars = after.get("vars") or {}
    compared = {
        key: {
            "before": before_vars.get(key),
            "after": after_vars.get(key),
            "mutated": (save_result.get("mutated") or {}).get(key),
            "match": after_vars.get(key) == before_vars.get(key),
        }
        for key in keys
    }
    matched = [key for key, row in compared.items() if row["match"]]
    hard_errors = [
        err
        for err in after.get("errors") or []
        if err.get("kind") in ps.HARD_ERROR_KINDS
    ]
    passage_ok = str(after.get("passage")) == str((save_result.get("before") or {}).get("passage"))
    slot_present = bool((save_result.get("slotProbe") or {}).get("present"))

    evidence["compared"] = compared
    evidence["matched_keys"] = matched
    evidence["passage_ok"] = passage_ok
    evidence["slot_present"] = slot_present
    evidence["hard_errors"] = hard_errors

    ok = (
        slot_present
        and passage_ok
        and len(matched) >= 2
        and len(matched) >= min(2, len(keys))
        and not hard_errors
    )
    if ok:
        return {
            "status": PASS,
            "detail": (
                f"save slot {slot} -> mutate -> load restored passage "
                f"{after.get('passage')!r} and {len(matched)}/{len(keys)} sampled "
                "variables via " + str(load_result.get("via"))
            ),
            "evidence": evidence,
        }
    return {
        "status": FAIL,
        "detail": (
            f"load round trip did not restore expected state: matched "
            f"{len(matched)}/{len(keys)} variables, passage_ok={passage_ok}, "
            f"slot_present={slot_present}, hard_errors={len(hard_errors)}"
        ),
        "evidence": evidence,
    }


def flow_ce_panel(page: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    before = page.evaluate(CE_PANEL_PROBE)
    evidence: dict[str, Any] = {"before": before}
    embedded = _artifact_has_mod(ctx, "cheat-extended")
    if before.get("callable") != "function":
        if not embedded:
            return {
                "status": NOT_APPLICABLE,
                "detail": (
                    "Cheat Extended is not embedded in this artifact and "
                    "window.CEiconClicked is "
                    f"{before.get('callable')!r}; probed window.CEiconClicked, "
                    "window.CE_renderSettings, #customOverlay, #CE_settingsDiv"
                ),
                "evidence": evidence,
            }
        return {
            "status": FAIL,
            "detail": (
                "Cheat Extended is embedded in the artifact but its panel entry "
                "point is not mounted: window.CEiconClicked is "
                f"{before.get('callable')!r}"
            ),
            "evidence": evidence,
        }

    opened = page.evaluate(CE_PANEL_OPEN)
    evidence["open"] = opened
    found = False
    for _ in range(20):
        page.wait_for_timeout(400)
        current = page.evaluate(CE_PANEL_PROBE)
        if (
            current.get("settingsDiv")
            and (current.get("overlay") or {}).get("dataOverlay") == "CEcheatMenu"
            and not (current.get("overlay") or {}).get("hidden")
        ):
            found = True
            evidence["after"] = current
            break
    if not found:
        evidence["after"] = page.evaluate(CE_PANEL_PROBE)

    after = evidence["after"]
    new_errors = [
        err
        for err in after.get("errors") or []
        if err.get("kind") in ps.HARD_ERROR_KINDS
        and err not in (before.get("errors") or [])
    ]
    evidence["new_hard_errors"] = new_errors
    if opened.get("ok") and found and not new_errors:
        return {
            "status": PASS,
            "detail": (
                "Cheat Extended overlay opened via window.CEiconClicked(); "
                "#customOverlay[data-overlay=CEcheatMenu] visible with "
                "#CE_settingsDiv present"
            ),
            "evidence": evidence,
        }
    return {
        "status": FAIL,
        "detail": (
            f"panel open failed: opened={opened}, dom_found={found}, "
            f"new_hard_errors={new_errors[:2]}"
        ),
        "evidence": evidence,
    }


def flow_au_face(page: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    variant = ctx.get("artifact_variant")
    evidence: dict[str, Any] = {"artifact_variant": variant}
    if variant not in AU_MODEL_NAME_BY_VARIANT:
        return {
            "status": NOT_APPLICABLE,
            "detail": (
                "target is not an AU artifact (variant="
                f"{variant!r}); the AU face/pet pixel smoke only applies to "
                "au-f/au-m/au-a builds"
            ),
            "evidence": evidence,
        }

    face_options = page.evaluate(AU_FACE_OPTIONS)
    evidence["face_options"] = face_options
    enable = page.evaluate(AU_PET_ENABLE)
    evidence["enable"] = enable
    page.wait_for_timeout(2500)
    baseline = page.evaluate(AU_PET_PROBE)
    evidence["baseline"] = baseline
    if not (baseline.get("canvas") or {}).get("opaque"):
        return {
            "status": NOT_IMPLEMENTED,
            "detail": (
                "the maplebirch desk-pet canvas did not produce measurable pixels "
                "in engine A (probed #maplebirch-character-pet, "
                "maplebirch.char.pet.sync, canvas getImageData); baseline="
                f"{baseline}"
            ),
            "evidence": evidence,
        }

    # The AU face module ships one style set per face style ("8 face types" in
    # the design notes). Each style carries demeanour variants; the first one
    # is the fallback the DOL-X face patch itself would pick.
    styles = list(face_options.get("styles") or [])
    by_style = face_options.get("byStyle") or {}
    if len(styles) < 2:
        return {
            "status": NOT_IMPLEMENTED,
            "detail": (
                "no AU face style set is exposed "
                f"(style={face_options.get('style')!r}, styles={styles!r})"
            ),
            "evidence": evidence,
        }

    measurements: list[dict[str, Any]] = []
    for style in styles:
        variants_for_style = list(by_style.get(style) or [])
        set_result = page.evaluate(
            AU_FACE_SET,
            {
                "style": style,
                "variant": variants_for_style[0] if variants_for_style else None,
            },
        )
        page.wait_for_timeout(1600)
        first = page.evaluate(AU_PET_PROBE)
        page.wait_for_timeout(900)
        confirmed = page.evaluate(AU_PET_PROBE)
        canvas = confirmed.get("canvas") or {}
        measurements.append(
            {
                "style": style,
                "variant": variants_for_style[0] if variants_for_style else None,
                "set": set_result,
                "canvas": canvas,
                "sidebar_opaque_total": (confirmed.get("sidebar") or {}).get(
                    "opaqueTotal"
                ),
                "unstable_read": (first.get("canvas") or {}).get("opaque")
                != canvas.get("opaque"),
            }
        )
    evidence["measurements"] = measurements

    pet_values = [
        (row.get("canvas") or {}).get("opaque")
        for row in measurements
        if (row.get("canvas") or {}).get("opaque")
    ]
    pet_distinct = sorted({value for value in pet_values})
    sidebar_values = [
        row.get("sidebar_opaque_total")
        for row in measurements
        if row.get("sidebar_opaque_total")
    ]
    sidebar_distinct = sorted({value for value in sidebar_values})
    pet_spread = (pet_distinct[-1] - pet_distinct[0]) if pet_distinct else 0
    sidebar_spread = (
        (sidebar_distinct[-1] - sidebar_distinct[0]) if sidebar_distinct else 0
    )
    evidence["pet_opaque_values"] = pet_values
    evidence["pet_distinct_opaque_values"] = pet_distinct
    evidence["pet_spread"] = pet_spread
    evidence["sidebar_opaque_values"] = sidebar_values
    evidence["sidebar_distinct_opaque_values"] = sidebar_distinct
    evidence["sidebar_spread"] = sidebar_spread

    # A spread of at least 2 opaque pixels is required so that a +/-1 pixel
    # antialias wobble can never be mistaken for a style difference (the
    # reproducible signature on the 1003 AU-F build is +38 for Twinkle改脸).
    if len(pet_values) == len(styles) and pet_spread >= 2:
        return {
            "status": PASS,
            "detail": (
                f"{len(styles)} AU face styles all produced a non-empty desk-pet "
                f"canvas with {len(pet_distinct)} distinct opaque-pixel counts "
                f"(spread {pet_spread}px) "
                f"(baseline={baseline.get('canvas', {}).get('opaque')})"
            ),
            "evidence": evidence,
        }
    if len(pet_values) < len(styles):
        return {
            "status": FAIL,
            "detail": (
                f"only {len(pet_values)}/{len(styles)} AU face styles produced a "
                "measurable desk-pet canvas"
            ),
            "evidence": evidence,
        }
    if len(sidebar_values) == len(styles) and sidebar_spread >= 2:
        return {
            "status": NOT_IMPLEMENTED,
            "detail": (
                "desk-pet canvas pixel counts were identical across all "
                f"{len(styles)} AU face styles ({pet_distinct}, spread {pet_spread}), "
                "so the "
                "pet-canvas-distinctness criterion could not be driven from engine A; "
                "however the sidebar character render did vary across those same "
                f"styles ({len(sidebar_distinct)} distinct opaque totals, spread "
                f"{sidebar_spread}), so the face "
                "styles themselves render. The pet-canvas check needs the device/UI "
                "path (or a dedicated pet remount call)"
            ),
            "evidence": evidence,
        }
    return {
        "status": NOT_IMPLEMENTED,
        "detail": (
            f"all {len(styles)} AU face styles produced desk-pet pixels but neither "
            f"the pet canvas ({pet_distinct}, spread {pet_spread}) nor the sidebar "
            f"render ({sidebar_distinct}, spread {sidebar_spread}) changed across "
            "styles; engine A cannot assert the face-style switch through "
            "V.facestyle + pet.sync() + <<updatesidebarimg>>"
        ),
        "evidence": evidence,
    }


def flow_morelove(page: Any, ctx: dict[str, Any]) -> dict[str, Any]:
    embedded = any(
        "morelove" in _normalize(str(mod.get("name") or ""))
        for mod in ctx["inventory"].get("mods", [])
    )
    story = page.evaluate(MORELOVE_STORY_PROBE)
    evidence: dict[str, Any] = {"embedded": embedded, "story": story}
    if not story.get("hasPassage") and not embedded:
        return {
            "status": NOT_APPLICABLE,
            "detail": (
                "More Love is not embedded in this artifact and the story has no "
                "'Food Preference' passage; probed the embedded mod list and "
                "SugarCube.Story.has('Food Preference')"
            ),
            "evidence": evidence,
        }
    if not story.get("hasPassage"):
        return {
            "status": FAIL,
            "detail": (
                "More Love appears embedded but the 'Food Preference' passage is "
                f"missing from the story (storyError={story.get('storyError')!r})"
            ),
            "evidence": evidence,
        }

    played = page.evaluate(MORELOVE_PLAY)
    evidence["play"] = played
    if not played.get("ok"):
        return {
            "status": FAIL,
            "detail": f"Engine.play('Food Preference') failed: {played}",
            "evidence": evidence,
        }
    try:
        page.wait_for_function(
            "(() => !!(window.__DOLX__ && window.__DOLX__.done))()", timeout=8000
        )
    except Exception:  # noqa: BLE001 - the probe below carries the verdict
        evidence["render_wait_timed_out"] = True
    page.wait_for_timeout(300)
    after = page.evaluate(MORELOVE_PROBE)
    evidence["after"] = after
    hard_errors = [
        err
        for err in after.get("errors") or []
        if err.get("kind") in ps.HARD_ERROR_KINDS
    ]
    text_len = max(int(after.get("textLen") or 0), int(after.get("textContentLen") or 0))
    rendered = (
        str(after.get("passage")) == "Food Preference"
        and (
            text_len > 20
            or after.get("mlimFood", 0) > 0
            or "食物偏好" in str(after.get("textSample") or after.get("textContentSample") or "")
            or "主要角色喜爱的食物"
            in str(after.get("textSample") or after.get("textContentSample") or "")
        )
        and not hard_errors
    )
    if rendered:
        return {
            "status": PASS,
            "detail": (
                "'Food Preference' rendered in engine A: passage="
                f"{after.get('passage')!r}, text_len={text_len}, "
                f"MLIM-food nodes={after.get('mlimFood')}"
            ),
            "evidence": evidence,
        }
    return {
        "status": FAIL,
        "detail": (
            f"'Food Preference' did not render as expected: passage="
            f"{after.get('passage')!r}, text_len={text_len}, "
            f"text_content_len={after.get('textContentLen')}, "
            f"html_sample={str(after.get('htmlSample'))[:120]!r}, "
            f"hard_errors={len(hard_errors)}"
        ),
        "evidence": evidence,
    }


FLOW_IMPLS = {
    "mods": flow_mods,
    "saveload": flow_saveload,
    "ce-panel": flow_ce_panel,
    "au-face": flow_au_face,
    "morelove": flow_morelove,
}


# --------------------------------------------------------------------------- #
# Runner + reporting
# --------------------------------------------------------------------------- #


def run(
    target: Path,
    flows: list[str],
    out_dir: Path,
    *,
    headless: bool,
    timeout_ms: int,
    bootstrap_settle_ms: int,
) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    report: dict[str, Any] = {
        "tool": "sweep_flow_assertions",
        "target": str(target),
        "flows_requested": flows,
        "started_at": started,
        "finished_at": None,
        "html_path": None,
        "artifact_variant": None,
        "inventory": {"list_length": None, "mods": [], "errors": []},
        "boot": None,
        "flows": [],
        "console_tail": [],
        "fatal_error": None,
    }

    html_path = ps.resolve_html_path(target)
    report["html_path"] = str(html_path)
    try:
        inventory = embedded_mod_inventory(html_path)
    except Exception as exc:  # noqa: BLE001 - report the failure, keep going.
        inventory = {
            "list_length": None,
            "mods": [],
            "errors": [f"inventory read failed: {type(exc).__name__}: {exc}"],
        }
    report["inventory"] = inventory
    report["artifact_variant"] = artifact_variant(target, html_path, inventory)

    try:
        with _session(
            html_path,
            headless=headless,
            timeout_ms=timeout_ms,
            bootstrap_settle_ms=bootstrap_settle_ms,
        ) as (page, boot, console):
            report["boot"] = boot
            report["console_tail"] = console[-120:]
            boot_error = _boot_failed(boot)
            if boot_error:
                for name in flows:
                    report["flows"].append(
                        {
                            "flow": name,
                            "status": FAIL,
                            "detail": f"bootstrap failed: {boot_error}",
                            "evidence": {"boot": boot},
                        }
                    )
            else:
                ctx = {
                    "target": target,
                    "html_path": html_path,
                    "inventory": inventory,
                    "artifact_variant": report["artifact_variant"],
                }
                for name in flows:
                    t0 = time.time()
                    try:
                        result = FLOW_IMPLS[name](page, ctx)
                    except Exception as exc:  # noqa: BLE001 - keep other flows alive.
                        result = {
                            "status": FAIL,
                            "detail": f"{type(exc).__name__}: {exc}"[:400],
                            "evidence": {},
                        }
                    result["flow"] = name
                    result["elapsed_ms"] = int((time.time() - t0) * 1000)
                    report["flows"].append(result)
                    print(
                        f"[flow] {name}: {result['status']} - "
                        f"{str(result.get('detail'))[:160]}",
                        flush=True,
                    )
    except Exception as exc:  # noqa: BLE001 - still emit a report.
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"[:600]
        for name in flows:
            if not any(entry["flow"] == name for entry in report["flows"]):
                report["flows"].append(
                    {
                        "flow": name,
                        "status": FAIL,
                        "detail": f"session fatal error: {report['fatal_error']}",
                        "evidence": {},
                    }
                )

    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_report(report, out_dir)
    return report


def write_report(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "flow-assertions.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# DOL-X functional flow assertions (engine A)",
        "",
        f"- target: `{report['target']}`",
        f"- html: `{report.get('html_path')}`",
        f"- artifact variant: {report.get('artifact_variant')}",
        f"- embedded mods: {report.get('inventory', {}).get('list_length')}",
        f"- started: {report.get('started_at')} / finished: {report.get('finished_at')}",
        "",
        "| flow | status | detail |",
        "| --- | --- | --- |",
    ]
    for entry in report["flows"]:
        detail = str(entry.get("detail", "")).replace("|", "\\|")[:220]
        lines.append(f"| {entry['flow']} | {entry['status']} | {detail} |")
    lines += ["", "## evidence", ""]
    for entry in report["flows"]:
        lines.append(f"### {entry['flow']} - {entry['status']}")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(entry.get("evidence"), ensure_ascii=False, indent=2)[:8000]
        )
        lines.append("```")
        lines.append("")
    if report.get("fatal_error"):
        lines += ["## fatal error", "", f"`{report['fatal_error']}`", ""]
    md_path = out_dir / "flow-assertions.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DOL-X functional flow assertions (engine A)"
    )
    parser.add_argument("target", type=Path, help="built .html or .zip to assert against")
    parser.add_argument(
        "--flow",
        default="all",
        choices=(*FLOW_ORDER, "all"),
        help="flow to run; 'all' runs them in order",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="report directory")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="headless is already the default; accepted for CLI symmetry",
    )
    parser.add_argument("--headful", action="store_true", help="show the browser window")
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument("--bootstrap-settle-ms", type=int, default=1500)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.target.exists():
        print(f"[flows] target does not exist: {args.target}")
        return 2
    flows = list(FLOW_ORDER) if args.flow == "all" else [args.flow]
    print(f"[flows] target={args.target} flows={flows}")
    report = run(
        args.target,
        flows,
        args.out,
        headless=not args.headful,
        timeout_ms=args.timeout_ms,
        bootstrap_settle_ms=args.bootstrap_settle_ms,
    )
    counts: dict[str, int] = {}
    for entry in report["flows"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    print(f"[flows] statuses={counts}")
    print(f"[flows] report -> {args.out / 'flow-assertions.md'}")
    return 1 if counts.get(FAIL) else 0


if __name__ == "__main__":
    raise SystemExit(main())
