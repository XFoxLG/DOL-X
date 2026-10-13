#!/usr/bin/env python3
"""Semantic replay planning for Android/MuMu DOL-X evidence.

Desktop traces may contain browser-only selectors, but Android WebView replay
must match the same player-visible action by semantic identity.  This module
deliberately keeps device I/O out of the core so the matching rules and privacy
boundary can be unit-tested before a device is attached.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.apk_emulator_smoke_test import (
    _AndroidWebViewCdpPage,
    _default_package_name,
    _discover_cdp_endpoint,
    _run_command,
    _select_cdp_page_target,
    _target_websocket_url,
)
from tools.exploration_runtime import RUNTIME_STATE_JS, parse_json_response
from tools.sweep_ledger import atomic_write_json

PLAN_SCHEMA = "dolx.android-replay-plan.v1"
SUMMARY_SCHEMA = "dolx.android-replay-summary.v1"
EXECUTION_SCHEMA = "dolx.android-replay-execution.v1"
ACTION_EXECUTION_JS = r"""
(index) => {
  const element = document.querySelector(`[data-dolx-action-index='${index}']`);
  if (!element) {
    return JSON.stringify({ok: false, error: "semantic action is no longer present"});
  }
    try {
      element.scrollIntoView({ block: "center", inline: "nearest" });
    if (element instanceof HTMLSelectElement) {
      if (element.options.length > 0) element.selectedIndex = 0;
      element.dispatchEvent(new Event("input", {bubbles: true}));
      element.dispatchEvent(new Event("change", {bubbles: true}));
    } else if (element instanceof HTMLTextAreaElement || (
      element instanceof HTMLInputElement && ["text", "search"].includes(String(element.type))
    )) {
      element.value = "";
      element.dispatchEvent(new Event("input", {bubbles: true}));
      element.dispatchEvent(new Event("change", {bubbles: true}));
    } else {
      element.click();
    }
    return JSON.stringify({
      ok: true,
      passage: window.SugarCube?.State?.passage || null,
    });
  } catch (error) {
    return JSON.stringify({ok: false, error: String(error && error.message ? error.message : error)});
  }
}
"""
PASSAGE_JS = "() => window.SugarCube?.State?.passage || null"
SCROLL_TO_ACTIONS_JS = """
() => {
  try {
    const roots = [document.scrollingElement, document.querySelector("#passage, #passages, [data-passage]")];
    for (const root of roots) {
      if (root && root.scrollHeight > root.clientHeight) {
        root.scrollTop = root.scrollHeight;
      }
    }
    window.scrollTo(0, document.body.scrollHeight);
    return true;
  } catch (error) {
    return false;
  }
}
"""
LOCATOR_POLICY = "semantic_only"
ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|tmp|var|workspace)(?:[\\/]|$))"
)
DESKTOP_ONLY_FIELDS = frozenset({"selector", "css", "xpath", "locator"})
SHORTCUT_PREFIX_RE = re.compile(r"^\s*\(\d+\)\s*")


def text_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def normalize_action_text(value: Any) -> str:
    return SHORTCUT_PREFIX_RE.sub("", str(value or "")).strip()


def normalized_text_hash(value: Any) -> str:
    return text_hash(normalize_action_text(value))


def _planned_normalized_text_hash(step: Mapping[str, Any]) -> str | None:
    existing = step.get("normalized_text_hash")
    if existing:
        return str(existing)
    normalized = normalize_action_text(step.get("text"))
    return text_hash(normalized) if normalized else None


def redact_paths(value: Any) -> Any:
    """Return report-safe data with local filesystem paths replaced."""
    if isinstance(value, str):
        if ABSOLUTE_PATH_RE.search(value):
            return "<redacted-path>"
        return value
    if isinstance(value, Mapping):
        return {str(key): redact_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_paths(item) for item in value]
    if isinstance(value, tuple):
        return [redact_paths(item) for item in value]
    return value


def _identity(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: action.get(key)
        for key in ("id", "name", "href", "value")
        if key in action
    }


def _semantic_id_passage(semantic_id: Any) -> str | None:
    value = str(semantic_id or "")
    parts = value.rsplit(":", 2)
    return parts[0] if len(parts) == 3 and parts[0] else None


def build_plan(report: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a desktop exploration report into an Android-safe plan."""
    actions = report.get("actions")
    if not isinstance(actions, list):
        raise ValueError("exploration report is missing an actions list")
    for action in actions:
        if not isinstance(action, Mapping):
            raise ValueError("exploration action is not an object")
        leaked = sorted(DESKTOP_ONLY_FIELDS.intersection(action))
        if leaked:
            raise ValueError(f"desktop locator fields cannot enter an Android plan: {leaked}")

    bootstrap = report.get("bootstrap") if isinstance(report.get("bootstrap"), Mapping) else {}
    bootstrap_actions = bootstrap.get("actions") if isinstance(bootstrap.get("actions"), list) else []
    bootstrap_end = (
        bootstrap_actions[-1].get("passage_after") or bootstrap.get("passage")
        if bootstrap_actions
        else bootstrap.get("passage")
    )
    prefix_bootstrap = bool(
        bootstrap_actions
        and actions
        and str(actions[0].get("passage_before"))
        == str(bootstrap_end)
    )
    effective_actions = [*bootstrap_actions, *actions] if prefix_bootstrap else actions

    steps: list[dict[str, Any]] = []
    for step_number, action in enumerate(effective_actions, 1):
        semantic_id = action.get("semantic_id")
        if not semantic_id:
            raise ValueError(f"exploration action {action.get('step')} has no semantic_id")
        steps.append(
            {
                "step": step_number,
                "source_step": action.get("step"),
                "semantic_id": str(semantic_id),
                "kind": action.get("kind"),
                "role": action.get("role"),
                "text_hash": str(action.get("text_hash") or text_hash(str(action.get("text") or ""))),
                "normalized_text_hash": _planned_normalized_text_hash(action),
                "expected_passage": action.get("passage_before"),
                "expected_state": {},
                "identity": _identity(action),
                "locator_policy": LOCATOR_POLICY,
            }
        )
    return {
        "schema": PLAN_SCHEMA,
        "source": "natural_semantic_trace_with_bootstrap" if prefix_bootstrap else "natural_semantic_trace",
        "target": {
            "apk_sha256": ((report.get("target_manifest") or {}).get("target") or {}).get("package_sha256"),
            "game_version": ((report.get("target_manifest") or {}).get("target") or {}).get("game_version"),
            "target_tag": ((report.get("target_manifest") or {}).get("target") or {}).get("target_tag"),
        },
        "steps": steps,
    }


def match_actions(
    plan_steps: Iterable[Mapping[str, Any]],
    candidates: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Match planned semantic actions against Android WebView candidates."""
    candidate_list = [dict(candidate) for candidate in candidates]
    results: list[dict[str, Any]] = []
    for step in plan_steps:
        expected_passage = step.get("expected_passage")
        evidence = [
            {
                "index": index,
                "semantic_id": candidate.get("semantic_id"),
                "role": candidate.get("role"),
                "text_hash": str(
                    candidate.get("text_hash")
                    or text_hash(str(candidate.get("text") or ""))
                ),
                "normalized_text_hash": (
                    text_hash(normalize_action_text(candidate.get("text")))
                    if normalize_action_text(candidate.get("text"))
                    else None
                ),
                **_identity(candidate),
            }
            for index, candidate in enumerate(candidate_list)
        ]

        semantic_matches = [
            item for item in evidence if item.get("semantic_id") == step.get("semantic_id")
        ]
        required = {
            key: value
            for key, value in (step.get("identity") or {}).items()
            if value is not None
        }
        if len(semantic_matches) > 1 and required:
            refined = [
                item
                for item in semantic_matches
                if all(item.get(key) == value for key, value in required.items())
            ]
            if refined:
                semantic_matches = refined
        if len(semantic_matches) > 1:
            normalized_digest = _planned_normalized_text_hash(step)
            refined = [
                item
                for item in semantic_matches
                if item.get("normalized_text_hash") == normalized_digest
            ]
            if refined:
                semantic_matches = refined
        if len(semantic_matches) == 1:
            status = "matched"
            matched = semantic_matches
        elif len(semantic_matches) > 1:
            status = "ambiguous"
            matched = semantic_matches
        else:
            identity_matches = []
            if required:
                identity_matches = [
                    item
                    for item in evidence
                    if (
                        not expected_passage
                        or _semantic_id_passage(item.get("semantic_id")) == expected_passage
                    )
                    and all(item.get(key) == value for key, value in required.items())
                ]
            if len(identity_matches) > 1:
                normalized_digest = _planned_normalized_text_hash(step)
                refined_text = [
                    item
                    for item in identity_matches
                    if item.get("normalized_text_hash") == normalized_digest
                ]
                if refined_text:
                    identity_matches = refined_text
            if len(identity_matches) == 1:
                status = "matched"
                matched = identity_matches
            elif len(identity_matches) > 1:
                status = "ambiguous"
                matched = identity_matches
            else:
                role = step.get("role")
                digest = step.get("text_hash")
                normalized_digest = _planned_normalized_text_hash(step)
                text_matches = [
                    item
                    for item in evidence
                    if role is not None
                    and item.get("role") == role
                    and (
                        not expected_passage
                        or _semantic_id_passage(item.get("semantic_id")) == expected_passage
                    )
                    and item.get("text_hash") == digest
                ]
                if not text_matches and normalized_digest:
                    text_matches = [
                        item
                        for item in evidence
                        if role is not None
                        and item.get("role") == role
                        and (
                            not expected_passage
                            or _semantic_id_passage(item.get("semantic_id")) == expected_passage
                        )
                        and item.get("normalized_text_hash") == normalized_digest
                    ]
                if len(text_matches) == 1:
                    status = "matched"
                    matched = text_matches
                elif len(text_matches) > 1:
                    status = "ambiguous"
                    matched = text_matches
                else:
                    status = "unmapped"
                    matched = []
        results.append(
            {
                "step": step.get("step"),
                "semantic_id": step.get("semantic_id"),
                "status": status,
                "evidence": matched,
            }
        )
    return results


def summarize_replay_result(
    entries: Iterable[Mapping[str, Any]],
    *,
    apk_sha256: str | None = None,
    adb_serial: str | None = None,
    android_version: str | None = None,
    webview_version: str | None = None,
    cdp_connected: bool = False,
    logcat_summary: Mapping[str, Any] | None = None,
    page_errors: Iterable[Mapping[str, Any]] | None = None,
    profile_mode: str | None = None,
) -> dict[str, Any]:
    normalized = [dict(entry) for entry in entries]
    statuses = Counter(str(item.get("status") or "unmapped") for item in normalized)
    unmapped = [
        {
            "step": item.get("step"),
            "semantic_id": item.get("semantic_id"),
        }
        for item in normalized
        if item.get("status") != "matched"
    ]
    return redact_paths(
        {
            "schema": SUMMARY_SCHEMA,
            "apk_sha256": apk_sha256,
            "adb_serial": adb_serial,
            "android_version": android_version,
            "webview_version": webview_version,
            "cdp_connected": bool(cdp_connected),
            "profile_mode": profile_mode,
            "logcat_summary": dict(logcat_summary or {}),
            "page_errors": list(page_errors or []),
            "totals": {
                "planned": len(normalized),
                **{key: statuses.get(key, 0) for key in ("matched", "ambiguous", "unmapped")},
            },
            "statuses": {str(item.get("step")): item.get("status") for item in normalized},
            "unmapped": unmapped,
            "completion_claim": "none",
        }
    )


def _attach_page_observers(page: Any) -> dict[str, list[dict[str, Any]]]:
    observations: dict[str, list[dict[str, Any]]] = {
        "console": [],
        "page_errors": [],
        "network_failures": [],
    }
    if hasattr(page, "on"):
        page.on("console", lambda message: observations["console"].append({
            "type": getattr(message, "type", None),
            "text": str(getattr(message, "text", "")),
            "location": getattr(message, "location", None),
        }))
        page.on("pageerror", lambda error: observations["page_errors"].append({"message": str(error)}))
        page.on("requestfailed", lambda request: observations["network_failures"].append({
            "url": str(getattr(request, "url", "")),
            "method": str(getattr(request, "method", "GET")),
            "failure": str(getattr(request, "failure", "request failed")),
        }))
    return observations


def collect_runtime_candidates(page: Any) -> list[dict[str, Any]]:
    data = parse_json_response(page.evaluate(RUNTIME_STATE_JS))
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "Android runtime snapshot failed"))
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise RuntimeError("Android runtime snapshot did not return an actions list")
    return [dict(action) for action in actions if isinstance(action, Mapping)]


def collect_android_runtime_candidates(page: Any) -> list[dict[str, Any]]:
    """Collect semantic actions across the full Android WebView document."""
    data = parse_json_response(page.evaluate(RUNTIME_STATE_JS, True))
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "Android runtime snapshot failed"))
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise RuntimeError("Android runtime snapshot did not return an actions list")
    return [dict(action) for action in actions if isinstance(action, Mapping)]


def _write_page_screenshot(page: Any, path: Path) -> None:
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as exc:  # noqa: BLE001 - screenshot is supporting evidence.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"screenshot failed: {type(exc).__name__}: {exc}\n", encoding="utf-8")


def _current_passage(page: Any) -> str | None:
    try:
        return page.evaluate(PASSAGE_JS)
    except Exception:  # noqa: BLE001 - navigation evidence is useful but not mandatory.
        return None


def execute_replay(
    plan: Mapping[str, Any],
    page: Any,
    output_dir: Path,
    *,
    apk_sha256: str | None = None,
    adb_serial: str | None = None,
    android_version: str | None = None,
    webview_version: str | None = None,
    cdp_connected: bool = True,
    step_delay_ms: int = 200,
    screenshot: bool = True,
    runtime_ready_timeout_ms: int = 30_000,
    profile_mode: str | None = None,
) -> dict[str, Any]:
    """Execute a semantic plan against a live Android WebView page.

    Matching never uses desktop CSS/XPath. Execution uses the runtime's
    temporary semantic action index, assigned to the Android-side candidate that
    matched the plan by semantic identity.
    """
    steps = plan.get("steps")
    if not isinstance(steps, list):
        raise ValueError("semantic plan must contain a steps list")

    output_dir.mkdir(parents=True, exist_ok=True)
    observations = _attach_page_observers(page)
    entries: list[dict[str, Any]] = []
    try:
        _wait_for_replay_runtime(
            page,
            timeout_ms=runtime_ready_timeout_ms,
            expected_passage=_planned_start_passage(steps),
        )
        for planned_step in steps:
            if not isinstance(planned_step, Mapping):
                raise ValueError("semantic plan step is not an object")
            page.evaluate(SCROLL_TO_ACTIONS_JS)
            page.wait_for_timeout(max(step_delay_ms, 50))
            candidates = collect_android_runtime_candidates(page)
            matches = match_actions([planned_step], candidates)
            match = matches[0] if matches else {
                "step": planned_step.get("step"),
                "semantic_id": planned_step.get("semantic_id"),
                "status": "unmapped",
                "evidence": [],
            }
            entry: dict[str, Any] = {
                "step": planned_step.get("step"),
                "semantic_id": planned_step.get("semantic_id"),
                "status": match.get("status"),
                "candidates_seen": len(candidates),
                "evidence": match.get("evidence", []),
            }
            if match.get("status") != "matched":
                if screenshot:
                    _write_page_screenshot(
                        page,
                        output_dir / "screenshots" / f"step-{planned_step.get('step', len(entries) + 1):04d}.png",
                    )
                entries.append(entry)
                continue

            evidence = match.get("evidence") or []
            if not evidence:
                entry["status"] = "unmapped"
                entries.append(entry)
                continue
            candidate = candidates[int(evidence[0].get("index", -1))]
            before_passage = _current_passage(page)
            started = time.perf_counter()
            try:
                if candidate.get("pointer_blocked") or candidate.get("disabled"):
                    page.wait_for_timeout(max(step_delay_ms, 50))
                    entry.update({
                        "action_kind": candidate.get("kind"),
                        "runtime_action_index": candidate.get("index"),
                        "before_passage": before_passage,
                        "after_passage": _current_passage(page),
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "executed": False,
                        "blocked_reason": (
                            "pointer_blocked" if candidate.get("pointer_blocked") else "disabled"
                        ),
                    })
                else:
                    execution = parse_json_response(page.evaluate(ACTION_EXECUTION_JS, int(candidate.get("index"))))
                    if not execution.get("ok"):
                        raise RuntimeError(str(execution.get("error") or "semantic action execution failed"))
                    page.wait_for_timeout(max(step_delay_ms, 50))
                    entry.update({
                        "action_kind": candidate.get("kind"),
                        "runtime_action_index": candidate.get("index"),
                        "before_passage": before_passage,
                        "after_passage": _current_passage(page),
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "executed": True,
                    })
            except Exception as exc:  # noqa: BLE001 - one action must not hide remaining mappings.
                entry["status"] = "action_failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            if screenshot:
                _write_page_screenshot(
                    page,
                    output_dir / "screenshots" / f"step-{planned_step.get('step', len(entries) + 1):04d}.png",
                )
            entries.append(entry)
    finally:
        atomic_write_json(output_dir / "android-replay-execution.json", {
            "schema": EXECUTION_SCHEMA,
            "entries": entries,
            "observations": observations,
        })

    matched_count = sum(item.get("status") == "matched" for item in entries)
    failed_count = sum(item.get("status") == "action_failed" for item in entries)
    if not entries:
        verdict = "failed"
    elif matched_count == len(entries) and failed_count == 0 and not observations["page_errors"]:
        verdict = "ok"
    elif matched_count == 0:
        verdict = "failed"
    else:
        verdict = "partial"
    summary = summarize_replay_result(
        entries,
        apk_sha256=apk_sha256,
        adb_serial=adb_serial,
        android_version=android_version,
        webview_version=webview_version,
        cdp_connected=cdp_connected,
        logcat_summary={"fatal": 0, "anr": 0, "android_runtime": 0},
        page_errors=observations["page_errors"],
        profile_mode=profile_mode,
    )
    summary["verdict"] = verdict
    summary["execution_path"] = "<redacted-path>"
    atomic_write_json(output_dir / "android-replay-summary.json", summary)
    return {"entries": entries, "summary": summary, "observations": observations}


def _planned_start_passage(steps: list[Any]) -> str | None:
    """Return the passage the plan expects before its first action.

    Bootstrap steps carry no ``expected_passage`` because the desktop trace
    started mid-passage, so the semantic id prefix is used as the fallback.
    """
    for step in steps:
        if not isinstance(step, Mapping):
            return None
        explicit = step.get("expected_passage")
        if explicit:
            return str(explicit)
        return _semantic_id_passage(step.get("semantic_id"))
    return None


def _runtime_passage(page: Any) -> Any:
    try:
        return page.evaluate(PASSAGE_JS)
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _runtime_passage_ready(page: Any, expected_passage: str | None) -> bool:
    """Decide whether the booted runtime already sits on the planned passage.

    ModLoader exposes interactive DOM controls while SugarCube is still
    booting. Without the passage check the first planned steps race that boot
    sequence and are reported as unmapped/ambiguous even though the page
    simply had not started the story yet.
    """
    if not expected_passage:
        return True
    return _runtime_passage(page) == expected_passage


def _wait_for_replay_runtime(
    page: Any, *, timeout_ms: int, expected_passage: str | None = None
) -> None:
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            page.evaluate(SCROLL_TO_ACTIONS_JS)
            candidates = collect_android_runtime_candidates(page)
            if not candidates:
                last_error = "runtime exposed no semantic actions"
            elif _runtime_passage_ready(page, expected_passage):
                return
            else:
                passage = _runtime_passage(page)
                last_error = (
                    f"runtime passage {passage!r} does not match the planned "
                    f"starting passage {expected_passage!r}"
                )
        except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        page.wait_for_timeout(500)
    raise RuntimeError(f"Android runtime did not become replayable within {timeout_ms}ms: {last_error}")


def _file_sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _device_versions(
    adb: str,
    serial: str | None,
    commands: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    prefix = [adb, "-s", serial] if serial else [adb]
    android_version: str | None = None
    webview_version: str | None = None
    try:
        result = _run_command(
            [*prefix, "shell", "getprop", "ro.build.version.release"],
            commands,
            check=False,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            android_version = result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        result = _run_command(
            [*prefix, "shell", "dumpsys", "package", "com.google.android.webview"],
            commands,
            check=False,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout:
            match = re.search(r"versionName=([0-9][^\s]+)", result.stdout)
            if match:
                webview_version = match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return android_version, webview_version


def _summarize_logcat(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"collected": False, "fatal": 0, "anr": 0, "android_runtime": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return {
        "collected": True,
        "fatal": sum(" FATAL " in line for line in lines),
        "anr": sum(" ANR " in line for line in lines),
        "android_runtime": sum("AndroidRuntime:" in line for line in lines),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | None, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(encoded, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="build an Android-safe semantic plan")
    plan.add_argument("report", type=Path)
    plan.add_argument("--out", type=Path)

    match = subparsers.add_parser("match", help="match a plan against Android candidates")
    match.add_argument("plan", type=Path)
    match.add_argument("candidates", type=Path)
    match.add_argument("--out", type=Path)

    summary = subparsers.add_parser("report-summary", help="summarize match results")
    summary.add_argument("matches", type=Path)
    summary.add_argument("--apk-sha256")
    summary.add_argument("--adb-serial")
    summary.add_argument("--android-version")
    summary.add_argument("--webview-version")
    summary.add_argument("--cdp-connected", action="store_true")
    summary.add_argument("--out", type=Path)

    execute = subparsers.add_parser("execute", help="execute a semantic plan on Android WebView CDP")
    execute.add_argument("plan", type=Path)
    execute.add_argument("--output-dir", type=Path, default=Path(".local/android-replay"))
    execute.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    execute.add_argument("--adb-serial")
    execute.add_argument("--package", help="Android package name; defaults to config/build.toml identity package")
    execute.add_argument("--apk", type=Path, help="optional APK used to verify target identity")
    execute.add_argument("--cdp-port", type=int, default=9222)
    execute.add_argument("--cdp-timeout-seconds", type=int, default=30)
    execute.add_argument("--timeout-ms", type=int, default=60_000)
    execute.add_argument("--step-delay-ms", type=int, default=200)
    execute.add_argument("--runtime-ready-timeout-ms", type=int, default=60_000)
    execute.add_argument("--launch", action="store_true", help="launch the already installed package before CDP discovery")
    execute.add_argument(
        "--disposable-profile",
        action="store_true",
        help="explicitly allow pm clear; never used for save-migration profiles",
    )
    execute.add_argument(
        "--profile-mode",
        choices=("clean_install", "natural_new_game", "preserved_save", "assisted_save"),
        default=None,
        help=(
            "how the device data was prepared before this replay; recorded in the "
            "summary so clean installs, natural new games, preserved saves and "
            "assisted deep-scene entries are never conflated"
        ),
    )
    execute.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "plan":
        write_json(args.out, build_plan(load_json(args.report)))
    elif args.command == "match":
        plan = load_json(args.plan)
        candidates = load_json(args.candidates)
        steps = plan.get("steps")
        entries = candidates.get("candidates") if isinstance(candidates, Mapping) else candidates
        if not isinstance(steps, list) or not isinstance(entries, list):
            raise ValueError("plan and candidates must contain arrays")
        write_json(args.out, {"schema": "dolx.android-replay-match.v1", "entries": match_actions(steps, entries)})
    elif args.command == "report-summary":
        matches = load_json(args.matches)
        entries = matches.get("entries") if isinstance(matches, Mapping) else matches
        if not isinstance(entries, list):
            raise ValueError("match input must contain an entries array")
        write_json(
            args.out,
            summarize_replay_result(
                entries,
                apk_sha256=args.apk_sha256,
                adb_serial=args.adb_serial,
                android_version=args.android_version,
                webview_version=args.webview_version,
                cdp_connected=args.cdp_connected,
            ),
        )
    elif args.command == "execute":
        from tools.apk_emulator_smoke_test import _write_logcat

        plan = load_json(args.plan)
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        commands: list[dict[str, Any]] = []
        package = args.package or _default_package_name()
        serial = args.adb_serial
        adb_prefix = [args.adb, "-s", serial] if serial else [args.adb]
        try:
            _run_command([*adb_prefix, "devices"], commands, check=True, timeout=30)
            if args.launch:
                _run_command(
                    [*adb_prefix, "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
                    commands,
                    check=True,
                    timeout=30,
                )
            if args.disposable_profile:
                _run_command(
                    [*adb_prefix, "shell", "pm", "clear", package],
                    commands,
                    check=False,
                    timeout=30,
                )
            cdp = _discover_cdp_endpoint(
                args.adb,
                package,
                commands,
                cdp_port=args.cdp_port,
                timeout_seconds=args.cdp_timeout_seconds,
                serial=serial,
            )
            if serial is None:
                devices = _run_command([args.adb, "devices"], commands, check=False, timeout=10).stdout
                connected = [line.split()[0] for line in devices.splitlines() if line.endswith("device")]
                if len(connected) == 1:
                    serial = connected[0]
            android_version, webview_version = _device_versions(args.adb, serial, commands)
            if not cdp.get("success"):
                raise RuntimeError(str(cdp.get("error") or "Android WebView CDP endpoint was not discovered"))
            target = _select_cdp_page_target(cdp.get("targets", []))
            if target is None:
                raise RuntimeError("Android WebView CDP endpoint did not expose a replayable page target")
            websocket_url = _target_websocket_url(str(cdp.get("cdp_url")), target)

            def rediscover() -> dict[str, Any]:
                return _discover_cdp_endpoint(
                    args.adb,
                    package,
                    commands,
                    cdp_port=args.cdp_port,
                    timeout_seconds=10,
                    serial=serial,
                )

            with _AndroidWebViewCdpPage(
                websocket_url,
                args.timeout_ms,
                target,
                reconnect_endpoint=rediscover,
            ) as page:
                result = execute_replay(
                    plan,
                    page,
                    output_dir,
                    apk_sha256=(
                        _file_sha256(args.apk)
                        if args.apk
                        else (plan.get("target") or {}).get("apk_sha256")
                    ),
                    adb_serial=serial,
                    android_version=android_version,
                    webview_version=webview_version,
                    cdp_connected=True,
                    step_delay_ms=args.step_delay_ms,
                    runtime_ready_timeout_ms=args.runtime_ready_timeout_ms,
                    profile_mode=args.profile_mode,
                )
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
            summary = summarize_replay_result(
                [],
                apk_sha256=(
                    _file_sha256(args.apk)
                    if args.apk
                    else (plan.get("target") or {}).get("apk_sha256")
                ),
                adb_serial=serial,
                cdp_connected=False,
                logcat_summary={"collected": False},
                profile_mode=args.profile_mode,
            )
            summary["verdict"] = "infrastructure_fail"
            summary["infrastructure_error"] = f"{type(exc).__name__}: {exc}"
            atomic_write_json(output_dir / "android-replay-summary.json", summary)
            write_json(args.out, summary)
            return 2

        try:
            logcat_path = _write_logcat(args.adb, output_dir, commands)
        except (OSError, subprocess.SubprocessError):
            logcat_path = output_dir / "logcat.txt"
        result["summary"]["logcat_summary"] = {
            **result["summary"].get("logcat_summary", {}),
            **_summarize_logcat(logcat_path),
            "artifact": "<redacted-path>",
        }
        atomic_write_json(output_dir / "android-replay-summary.json", result["summary"])
        write_json(args.out, result["summary"])
        return 0 if result["summary"].get("verdict") == "ok" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
