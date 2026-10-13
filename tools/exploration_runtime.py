"""Browser-side runtime primitives for the DOL-X gameplay explorer."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tools.passage_sweep import INIT_HARNESS, _launch_browser, install_passage_hook, resolve_html_path
from tools.state_fingerprint import build_fingerprint


RUNTIME_STATE_JS = r"""
(includeAll = false) => {
  const SC = window.SugarCube;
  if (!SC || !SC.State || !SC.Story || !SC.Engine) {
    return JSON.stringify({ ok: false, error: "SugarCube runtime is not ready" });
  }
  try {
    const state = SC.State.marshalForSave();
    const variables =
      SC.State.variables ||
      (state.history && state.history[state.index] ? state.history[state.index].variables : {});
    document.querySelectorAll("[data-dolx-action-index]").forEach((element) => {
      delete element.dataset.dolxActionIndex;
    });
    const storage = (store) => {
      const out = {};
      try {
        for (let i = 0; i < store.length; i++) {
          const key = store.key(i);
          if (key !== null) out[key] = String(store.getItem(key)).slice(0, 100000);
        }
      } catch (e) { out.__error__ = String(e); }
      return out;
    };
    const actions = [];
    const roots = [
      document.body,
      document.querySelector("#passage, #passages, [data-passage]"),
      document.querySelector("#ui-bar"),
    ];
    const seen = new Set();
    let semanticCounter = 0;
    const semanticHash = (value) => {
      let hash = 0x811c9dc5;
      const text = String(value || "");
      for (let i = 0; i < text.length; i++) {
        hash ^= text.charCodeAt(i);
        hash = (hash * 0x01000193) >>> 0;
      }
      return hash.toString(16).padStart(8, "0");
    };
    for (const root of roots) {
      if (!root) continue;
      const candidates = Array.from(root.querySelectorAll(
        "a, button, input[type='button'], input[type='submit'], input[type='checkbox'], input[type='radio'], select, textarea"
      ));
      for (const element of candidates) {
        if (seen.has(element)) continue;
        seen.add(element);
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const outsideViewport = (
          style.display === "none" ||
          style.visibility === "hidden" ||
          style.opacity === "0" ||
          Number(style.opacity) === 0 ||
          rect.width <= 0 ||
          rect.height <= 0 ||
          rect.right <= 0 ||
          rect.bottom <= 0 ||
          rect.left >= window.innerWidth ||
          rect.top >= window.innerHeight
        );
        if (!includeAll && outsideViewport) {
          continue;
        }
        const hit = document.elementFromPoint(
          rect.left + Math.min(rect.width / 2, 1),
          rect.top + Math.min(rect.height / 2, 1)
        );
        const pointerBlocked = Boolean(
          hit && hit !== element && !element.contains(hit) && !hit.contains(element)
        );
        semanticCounter += 1;
        const role = element.getAttribute("role") ||
          (element.tagName === "A" ? "link" :
           element.tagName === "BUTTON" ? "button" :
           element.tagName.toLowerCase());
        const label = element.id ? document.querySelector(`label[for='${CSS.escape(element.id)}']`) : null;
        const text = (
          (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement ? "" : element.innerText) ||
          element.textContent ||
          (label ? label.innerText || label.textContent : "") ||
          element.getAttribute("aria-label") ||
          element.value ||
          ""
        ).trim();
        const semanticKey = (
          element.id ||
          element.getAttribute("name") ||
          element.getAttribute("href") ||
          element.value ||
          text ||
          `index-${semanticCounter}`
        );
        const semanticId = `${SC.State.passage || "unknown"}:${role}:${semanticHash(semanticKey)}`;
        element.dataset.dolxActionIndex = String(semanticCounter);
        actions.push({
          kind: element.tagName === "SELECT" ? "select" :
                element.tagName === "TEXTAREA" || (element.tagName === "INPUT" && ["text", "search"].includes(String(element.type))) ? "text" :
                element.tagName === "INPUT" && ["checkbox", "radio", "button", "submit"].includes(String(element.type)) ? String(element.type) :
                element.tagName === "A" ? "link" : "button",
          semantic_id: semanticId,
          index: semanticCounter,
          scope: element.closest("#passage, #passages, [data-passage]")
            ? "passage"
            : element.closest("#ui-bar")
              ? "ui-bar"
              : "body",
          role: role,
          text: text.slice(0, 300),
          id: element.id || null,
          name: element.getAttribute("name") || null,
          href: element.getAttribute("href") || null,
          scope: element.closest("#passage, #passages, [data-passage]") ? "passage" : element.closest("#ui-bar") ? "ui-bar" : "body",
          overlay: Boolean(element.closest("#customOverlay, #customOverlayContainer, .swal2-container, .ui-dialog, dialog[open], [role='dialog']")),
          visible: !outsideViewport,
          pointer_blocked: pointerBlocked,
          disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
          checked: element instanceof HTMLInputElement ? element.checked : undefined,
          value: element instanceof HTMLInputElement ? element.value : undefined,
        });
      }
    }
    const registry = {
      passage_count: SC.Story.passages ? SC.Story.passages.size : null,
      macro_names: SC.Macro && SC.Macro.get ? null : null,
      modloader_present: Boolean(window.ModLoader),
    };
    return JSON.stringify({
      ok: true,
      passage: SC.State.passage,
      variables: variables,
      marshalForSave: state,
      actions: actions,
      storage: {
        local: storage(window.localStorage),
        session: storage(window.sessionStorage),
      },
      registry: registry,
    });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) });
  }
}
"""


RESTORE_STATE_JS = r"""
(payloadStr) => {
  try {
    const payload = JSON.parse(payloadStr);
    const state = payload && payload.state ? payload.state : payload;
    if (payload && payload.storage) {
      const restoreStore = (store, values) => {
        store.clear();
        for (const [key, value] of Object.entries(values || {})) {
          store.setItem(key, String(value));
        }
      };
      restoreStore(window.localStorage, payload.storage.local);
      restoreStore(window.sessionStorage, payload.storage.session);
    }
    const SC = window.SugarCube;
    if (!SC || !SC.State || !SC.Engine) return JSON.stringify({ ok: false, error: "SugarCube runtime is not ready" });
    SC.State.unmarshalForSave(state);
    SC.Engine.show(SC.State.passage);
    return JSON.stringify({ ok: true, passage: SC.State.passage });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) });
  }
}
"""


@dataclass
class RuntimeSnapshot:
    fingerprint: dict[str, Any]
    actions: list[dict[str, Any]]
    storage: dict[str, Any]
    registry: dict[str, Any]
    marshal_for_save: Any
    observations: list[dict[str, Any]]


def parse_json_response(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise TypeError(f"browser returned {type(raw).__name__}, expected JSON text")


def snapshot_runtime(
    page: Any, observations: list[dict[str, Any]] | None = None
) -> RuntimeSnapshot:
    raw = page.evaluate(RUNTIME_STATE_JS)
    data = parse_json_response(raw)
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "runtime snapshot failed"))
    variables = data.get("variables") or (data.get("marshalForSave") or {}).get("variables") or {}
    fingerprint = build_fingerprint(
        {
            "passage": data.get("passage"),
            "variables": variables,
            "dom": data.get("actions") or [],
            "storage": data.get("storage") or {},
            "mod_registry": data.get("registry") or {},
            "prng": (data.get("marshalForSave") or {}).get("prng"),
            "history": (data.get("marshalForSave") or {}).get("history"),
        }
    )
    return RuntimeSnapshot(
        fingerprint=fingerprint,
        actions=list(data.get("actions") or []),
        storage=data.get("storage") or {},
        registry=data.get("registry") or {},
        marshal_for_save=data.get("marshalForSave") or {},
        observations=list(observations or []),
    )


def reveal_page_actions(page: Any, *, timeout_ms: int = 120) -> None:
    """Scroll the visible game page to the bottom before action discovery.

    Long SugarCube passages can place the next link below the current viewport.
    Scrolling is a real player action and is necessary for ``elementFromPoint``
    to see controls that are otherwise off-screen.
    """
    try:
        page.keyboard.press("End")
        page.wait_for_timeout(timeout_ms)
    except Exception:
        # A scroll failure should not turn into a product failure before the
        # runtime oracle has had a chance to inspect the page.
        pass


def perform_action(page: Any, action: Mapping[str, Any], *, timeout_ms: int = 5000) -> dict[str, Any]:
    index = action.get("index")
    if index is None:
        raise ValueError("runtime action is missing its DOM index")
    selector = f"[data-dolx-action-index='{int(index)}']"
    kind = str(action.get("kind") or "button")
    started_at = time.perf_counter()
    result: dict[str, Any] = {"kind": kind, "semantic_id": action.get("semantic_id"), "selector": selector}
    if kind == "select":
        page.locator(selector).first.select_option(index=0, timeout=timeout_ms)
    elif kind == "text":
        page.locator(selector).first.fill("", timeout=timeout_ms)
    else:
        page.locator(selector).first.click(timeout=timeout_ms)
    result["elapsed_ms"] = int((time.perf_counter() - started_at) * 1000)
    return result


def restore_runtime_state(page: Any, marshal_for_save: Any) -> dict[str, Any]:
    raw = page.evaluate(RESTORE_STATE_JS, json.dumps(marshal_for_save, ensure_ascii=False, separators=(",", ":")))
    result = parse_json_response(raw)
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "runtime restore failed"))
    return result


def restore_checkpoint_payload(page: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Restore state plus browser-local storage from an explorer checkpoint."""
    encoded = json.dumps(
        {
            "state": payload.get("marshalForSave") or {},
            "storage": payload.get("storage") or {},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    raw = page.evaluate(RESTORE_STATE_JS, encoded)
    result = parse_json_response(raw)
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or "checkpoint payload restore failed"))
    return result


class RuntimeSession:
    """A local HTTP + Chromium session with console and error collection."""

    def __init__(self, target: Path, *, headless: bool = True) -> None:
        self.target = Path(target)
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._server = None
        self.console: list[dict[str, Any]] = []
        self.page_errors: list[dict[str, Any]] = []
        self.network_failures: list[dict[str, Any]] = []
        self._observation_cursor = 0

    def __enter__(self) -> "RuntimeSession":
        import contextlib

        from playwright.sync_api import sync_playwright
        from tools.browser_smoke_test import _relative_url, _serve_directory

        self.html_path = resolve_html_path(self.target)
        self._pw = sync_playwright().start()
        self._server_context = _serve_directory(self.html_path.parent)
        self._server = self._server_context.__enter__()
        self._browser = _launch_browser(self._pw, self.headless)
        self._context = self._browser.new_context()
        self._context.add_init_script(INIT_HARNESS)
        self.page = self._context.new_page()
        self.page.on(
            "console",
            lambda message: self.console.append(
                {"kind": message.type, "message": message.text[:2000]}
            ),
        )
        self.page.on(
            "pageerror",
            lambda error: self.page_errors.append(
                {"kind": "pageerror", "message": str(error)[:2000]}
            ),
        )
        self.page.on(
            "requestfailed",
            lambda request: self.network_failures.append(
                {"url": request.url[:1000], "failure": request.failure}
            ),
        )
        self.url = _relative_url(self._server, self.html_path.parent, self.html_path)
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.wait_for_runtime(timeout_s=180)
        # passage_sweep's render hook is registered after SugarCube is live;
        # without it Engine.play() can render correctly while `done` remains
        # false, causing assisted explorers to misclassify healthy passages.
        self.render_hook_installed = bool(self.page.evaluate(install_passage_hook()))
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._server is not None:
            self._server_context.__exit__(exc_type, exc, traceback)
            self._server = None
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    def observations(self) -> list[dict[str, Any]]:
        return [
            *({"kind": "console." + str(item.get("kind")), "message": item.get("message")} for item in self.console if item.get("kind") in ("error", "warning")),
            *self.page_errors,
            *({"kind": "requestfailed", **item} for item in self.network_failures),
        ]

    def wait_for_runtime(self, timeout_s: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                snapshot_runtime(self.page, self.new_observations())
                return
            except RuntimeError as exc:
                last_error = exc
                self.page.wait_for_timeout(500)
        raise TimeoutError(
            f"SugarCube runtime did not become ready within {timeout_s}s: {last_error}"
        )

    def wait_for_mods_stable(self, timeout_s: float = 30.0) -> dict[str, Any]:
        """Wait until the runtime registry stops changing before replay checks."""
        deadline = time.monotonic() + timeout_s
        last_registry: Mapping[str, Any] | None = None
        stable = 0
        while time.monotonic() < deadline:
            snapshot = snapshot_runtime(self.page, self.new_observations())
            registry = snapshot.registry
            if last_registry is not None and json.dumps(last_registry, sort_keys=True) == json.dumps(registry, sort_keys=True):
                stable += 1
                if stable >= 2:
                    return dict(registry)
            else:
                stable = 0
            last_registry = registry
            self.page.wait_for_timeout(500)
        raise TimeoutError(f"runtime Mod registry did not stabilize within {timeout_s}s")

    def new_observations(self) -> list[dict[str, Any]]:
        """Return observations since the previous call, scoped to one action."""
        observations = self.observations()
        fresh = observations[self._observation_cursor :]
        self._observation_cursor = len(observations)
        return fresh

    def bootstrap_natural(
        self, *, max_steps: int = 300, deadline_s: float = 240.0
    ) -> dict[str, Any]:
        """Reach gameplay using only visible controls driven by Playwright."""
        from tools.browser_smoke_test import (
            STARTUP_CONSENT_LABELS,
            STARTUP_CONFIRM_LABELS,
        )

        started = time.monotonic()
        confirm = {str(label).casefold() for label in STARTUP_CONFIRM_LABELS}
        consent = {str(label).casefold() for label in STARTUP_CONSENT_LABELS}
        records: list[dict[str, Any]] = []
        no_progress = 0
        snapshot = snapshot_runtime(self.page, self.new_observations())

        for _step in range(max_steps):
            passage = str(snapshot.fingerprint["coarse"]["passage"] or "")
            if passage and passage.casefold() not in {
                "start",
                "startup",
                "loading",
                "loadingchecker",
                "init",
            }:
                return {
                    "ok": True,
                    "steps": len(records),
                    "passage": passage,
                    "actions": records,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }

            candidates = [
                action
                for action in snapshot.actions
                if not action.get("disabled")
                and action.get("kind") in {"link", "button", "submit", "checkbox"}
                and str(action.get("id") or "") != "ui-bar-toggle"
                and "打开/关闭导航栏" not in str(action.get("text") or "")
            ]
            text_matches = lambda action: any(
                label in str(action.get("text") or "").casefold()
                for label in consent | confirm
            )
            checkboxes = [
                action
                for action in candidates
                if action.get("kind") == "checkbox" and action.get("checked") is False
            ]
            passage_candidates = [
                action for action in candidates if action.get("scope") == "passage"
            ]
            texted = [action for action in candidates if text_matches(action)]
            selected = checkboxes[0] if checkboxes else (texted[0] if texted else (passage_candidates[0] if passage_candidates else (candidates[0] if candidates else None)))

            if selected is None:
                no_progress += 1
                if no_progress >= 40:
                    break
            else:
                no_progress = 0
                try:
                    result = perform_action(self.page, selected)
                    records.append({**selected, "result": result})
                except Exception as exc:  # noqa: BLE001 - bootstrap failures are evidence
                    records.append({**selected, "error": f"{type(exc).__name__}: {exc}"})
                    break
                self.page.wait_for_timeout(150)
                snapshot = snapshot_runtime(self.page, self.new_observations())

            if time.monotonic() - started >= deadline_s:
                break

        return {
            "ok": False,
            "steps": len(records),
            "passage": snapshot.fingerprint["coarse"]["passage"],
            "actions": records,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    def dismiss_runtime_overlays(
        self, *, max_steps: int = 30, deadline_s: float = 60.0
    ) -> dict[str, Any]:
        """Dismiss one-shot startup/mod dialogs through their visible controls."""
        started = time.monotonic()
        records: list[dict[str, Any]] = []
        no_overlay_samples = 0
        reveal_page_actions(self.page)
        snapshot = snapshot_runtime(self.page, self.new_observations())

        for _step in range(max_steps):
            candidates = [
                action
                for action in snapshot.actions
                if action.get("overlay")
                and not action.get("disabled")
                and not action.get("pointer_blocked")
                and action.get("kind") in {"button", "submit", "checkbox", "link"}
            ]
            if not candidates:
                no_overlay_samples += 1
                if no_overlay_samples >= 2:
                    return {
                        "ok": True,
                        "steps": len(records),
                        "actions": records,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                self.page.wait_for_timeout(250)
                reveal_page_actions(self.page)
                snapshot = snapshot_runtime(self.page, self.new_observations())
                continue

            no_overlay_samples = 0
            selected = next(
                (
                    action
                    for action in candidates
                    if action.get("kind") == "checkbox" and action.get("checked") is False
                ),
                next(
                    (
                        action
                        for action in candidates
                        if action.get("kind") in {"button", "submit", "link"}
                    ),
                    candidates[0],
                ),
            )
            try:
                result = perform_action(self.page, selected)
                records.append({**selected, "result": result})
            except Exception as exc:
                records.append({**selected, "error": f"{type(exc).__name__}: {exc}"})
                return {
                    "ok": False,
                    "steps": len(records),
                    "actions": records,
                    "error": str(exc),
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            self.page.wait_for_timeout(150)
            reveal_page_actions(self.page)
            snapshot = snapshot_runtime(self.page, self.new_observations())
            if time.monotonic() - started >= deadline_s:
                break

        return {
            "ok": False,
            "steps": len(records),
            "actions": records,
            "error": "overlay dismissal deadline exceeded",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
