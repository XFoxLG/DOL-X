#!/usr/bin/env python3
"""Automated Android WebView/CDP smoke test for smoke-debug APKs.

This helper is intentionally scoped to the manual baseline candidate gate.  It
installs one release-derived smoke-debug APK on an already running Android
emulator, launches it, attaches to the WebView DevTools endpoint, and reuses the
same runtime checks/report shape as the ZIP browser smoke where practical.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.config_loader import load_build_config
from tools.artifact_inspection import load_html_artifact
from tools.browser_smoke_test import (
    BrowserSmokeReport,
    Issue,
    PROFILES,
    _add_issue,
    _attempt_enter_game,
    _check_required_mods,
    _is_successful_smoke,
    _page_state_script,
    _record_game_ready,
    _run_startup_interactions,
    classify_message,
    collect_ci_context,
    extract_embedded_mods_from_html,
    summarize_report,
    write_outputs,
)


DEFAULT_CDP_PORT = 9222
DEFAULT_PROFILE = "ucb-more-love-custom-spellbook-cheat-extended-maplebirch"
DEFAULT_EXPECTED_PASSAGE = "Orphanage Intro"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _short_text(value: str | bytes | None, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-limit:]
    return value[-limit:]


def _run_command(
    cmd: list[str],
    commands: list[dict[str, Any]],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    entry: dict[str, Any] = {"command": cmd}
    commands.append(entry)
    try:
        result = subprocess.run(cmd, capture_output=True, check=check, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        entry.update(
            {
                "returncode": exc.returncode,
                "stdout": _short_text(exc.stdout),
                "stderr": _short_text(exc.stderr),
            }
        )
        raise
    except subprocess.TimeoutExpired as exc:
        entry.update(
            {
                "returncode": None,
                "timeout_seconds": timeout,
                "stdout": _short_text(exc.stdout),
                "stderr": _short_text(exc.stderr),
            }
        )
        raise

    entry.update(
        {
            "returncode": result.returncode,
            "stdout": _short_text(result.stdout),
            "stderr": _short_text(result.stderr),
        }
    )
    return result


def _apk_slug(apk_path: Path) -> str:
    normalized = apk_path.name.lower().replace("_", "-")
    for slug in ("au-f", "au-m", "au-a"):
        if f"-{slug}-" in normalized:
            return slug
    return "base"


def _default_package_name() -> str:
    return load_build_config().identity_package


def _parse_devtools_sockets(proc_net_unix: str) -> list[str]:
    sockets: list[str] = []
    seen: set[str] = set()
    for line in proc_net_unix.splitlines():
        if "devtools_remote" not in line:
            continue
        raw_name = line.rsplit(maxsplit=1)[-1].strip()
        name = raw_name.lstrip("@").strip("\x00")
        if not name or "devtools_remote" not in name or name in seen:
            continue
        seen.add(name)
        sockets.append(name)
    return sockets


def _select_devtools_socket(sockets: list[str], package_name: str) -> str | None:
    if not sockets:
        return None
    package_tokens = {package_name, package_name.replace(".", "_")}
    for socket in sockets:
        if any(token and token in socket for token in package_tokens):
            return socket
    for socket in sockets:
        if socket.startswith("webview_devtools_remote"):
            return socket
    return sockets[0]


def _fetch_json(url: str, *, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - localhost CDP endpoint.
        return json.loads(response.read().decode("utf-8"))


def _discover_cdp_endpoint(
    adb: str,
    package_name: str,
    commands: list[dict[str, Any]],
    *,
    cdp_port: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, Any]] = []
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            proc_net = _run_command([adb, "shell", "cat", "/proc/net/unix"], commands, timeout=10).stdout
            sockets = _parse_devtools_sockets(proc_net)
            socket = _select_devtools_socket(sockets, package_name)
            attempts.append({"sockets": sockets, "selected_socket": socket})
            if not socket:
                time.sleep(1)
                continue

            _run_command([adb, "forward", "--remove", f"tcp:{cdp_port}"], commands, check=False, timeout=10)
            _run_command([adb, "forward", f"tcp:{cdp_port}", f"localabstract:{socket}"], commands, timeout=10)
            cdp_url = f"http://127.0.0.1:{cdp_port}"
            targets = _fetch_json(f"{cdp_url}/json/list")
            if isinstance(targets, list) and targets:
                return {
                    "success": True,
                    "cdp_url": cdp_url,
                    "socket": socket,
                    "targets": targets,
                    "attempts": attempts,
                }
            last_error = "CDP endpoint returned no targets"
        except (subprocess.SubprocessError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            attempts.append({"error": str(exc)})
        time.sleep(1)

    return {
        "success": False,
        "cdp_url": f"http://127.0.0.1:{cdp_port}",
        "socket": None,
        "targets": [],
        "attempts": attempts,
        "error": last_error or "timed out waiting for Android WebView DevTools target",
    }


def _is_cdp_transport_error(error: BaseException | str | None) -> bool:
    text = str(error or "").lower()
    return "cdp websocket closed" in text or "cdp websocket send failed" in text


def _is_optional_remote_loader_fetch(source: str, message: str, location: dict[str, Any] | None = None) -> bool:
    if source != "console.error" or "TypeError: Failed to fetch" not in message:
        return False
    location_url = str((location or {}).get("url") or "")
    return "RemoteLoader.load" in message or "ModZipReader.ts" in message or "ModZipReader.ts" in location_url


def _is_cordova_android_exec_exception(message: str) -> bool:
    return "Java exception was raised during method invocation" in message and "cordova.js" in message


def _classify_apk_cdp_message(source: str, message: str, location: dict[str, Any] | None = None) -> Issue:
    if _is_optional_remote_loader_fetch(source, message, location):
        return Issue("warning", "optional_remote_mod_list", source, message)
    return classify_message(source, message)


def _classify_apk_cdp_smoke_exception(exc: BaseException) -> Issue:
    if _is_cdp_transport_error(exc):
        return Issue("warning", "apk_cdp_adapter_closed", "runner", str(exc))
    return Issue("high", "apk_cdp_smoke_error", "runner", str(exc))


def _reconnect_cdp_page(report: BrowserSmokeReport, page: Any, phase: str, error: BaseException | str) -> None:
    reconnect = getattr(page, "reconnect", None)
    if not callable(reconnect):
        raise RuntimeError(str(error))
    report.observations.setdefault("apk_cdp_reconnects", []).append({"phase": phase, "error": str(error)})
    reconnect()


def _with_cdp_reconnect(report: BrowserSmokeReport, page: Any, phase: str, operation: Any) -> Any:
    try:
        return operation()
    except Exception as exc:  # noqa: BLE001 - CDP transport close is recoverable once per phase.
        if not _is_cdp_transport_error(exc):
            raise
        _reconnect_cdp_page(report, page, phase, exc)
        return operation()


def _downgrade_ready_cordova_pageerrors(
    report: BrowserSmokeReport,
    final_game_ready: dict[str, Any],
    expected_passage: str,
) -> None:
    if not final_game_ready.get("ready"):
        return
    if expected_passage and final_game_ready.get("passage") != expected_passage:
        return

    pageerror_context = report.observations.get("pageerror_context") or []
    if not isinstance(pageerror_context, list):
        return

    benign_context: list[dict[str, Any]] = []
    retained_context: list[Any] = []
    for entry in pageerror_context:
        message = str(entry.get("message") or "") if isinstance(entry, dict) else str(entry)
        if _is_cordova_android_exec_exception(message):
            benign_context.append(entry if isinstance(entry, dict) else {"message": message})
        else:
            retained_context.append(entry)

    if not benign_context:
        return

    report.observations["pageerror_context"] = retained_context
    report.observations.setdefault("apk_cdp_benign_pageerrors", []).extend(benign_context)
    for issue in report.issues:
        if issue.source == "pageerror" and _is_cordova_android_exec_exception(issue.message):
            issue.severity = "warning"
            issue.kind = "cordova_android_exec_after_ready"


def _attach_page_events(report: BrowserSmokeReport, page: Any) -> None:
    def on_console(message: Any) -> None:
        text = str(message.text)
        entry = {"type": message.type, "text": text, "location": message.location}
        report.console_messages.append(entry)
        if message.type in {"error", "warning"}:
            source = "console.error" if message.type == "error" else "console.warning"
            _add_issue(report, _classify_apk_cdp_message(source, text, message.location), location=message.location)

    def on_page_error(error: Any) -> None:
        text = str(error)
        report.observations.setdefault("pageerror_context", []).append({"message": text, "url": page.url})
        _add_issue(report, _classify_apk_cdp_message("pageerror", text))

    def on_request_failed(request: Any) -> None:
        failure = request.failure or "request failed"
        entry = {
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "failure": failure,
        }
        report.network_failures.append(entry)
        _add_issue(report, classify_message("requestfailed", f"{request.url} {failure}"), url=request.url)

    def on_response(response: Any) -> None:
        if response.status < 400:
            return
        entry = {"url": response.url, "status": response.status, "status_text": response.status_text}
        report.network_failures.append(entry)
        _add_issue(report, classify_message("http_error", f"{response.url} HTTP {response.status}"), url=response.url)

    def on_dialog(dialog: Any) -> None:
        entry = {"type": dialog.type, "message": dialog.message, "accepted": True}
        report.observations.setdefault("dialogs", []).append(entry)
        dialog.accept()

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)
    page.on("dialog", on_dialog)


def _wait_for_cdp_page(browser: Any, timeout_ms: int) -> Any:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        pages = [page for context in browser.contexts for page in context.pages]
        if pages:
            return pages[0]
        time.sleep(0.25)
    raise RuntimeError("CDP connection did not expose a WebView page")


class _CdpObject:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _CdpDialog:
    def __init__(self, page: "_AndroidWebViewCdpPage", dialog_type: str, message: str) -> None:
        self._page = page
        self.type = dialog_type
        self.message = message
        self.accepted = False

    def accept(self) -> None:
        self._page._send_command("Page.handleJavaScriptDialog", {"accept": True})
        self.accepted = True


class _CdpWebSocketSession:
    """Small dependency-free WebSocket client for Android WebView page CDP."""

    _GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, websocket_url: str, timeout_seconds: float) -> None:
        self.websocket_url = websocket_url
        self.timeout_seconds = timeout_seconds
        self._socket = self._connect(websocket_url, timeout_seconds)
        self._next_id = 0
        self._pending: dict[int, dict[str, Any]] = {}
        self._event_callback: Any | None = None

    def set_event_callback(self, callback: Any) -> None:
        self._event_callback = callback

    def send_command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        payload: dict[str, Any] = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

        deadline = time.monotonic() + (timeout_seconds or self.timeout_seconds)
        while time.monotonic() < deadline:
            if message_id in self._pending:
                return self._pop_response(message_id, method)
            remaining = max(0.05, deadline - time.monotonic())
            self._socket.settimeout(min(remaining, 0.5))
            try:
                self._receive_message()
            except socket.timeout:
                continue
        raise RuntimeError(f"timed out waiting for CDP response to {method}")

    def drain_events(self, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            self._socket.settimeout(min(max(remaining, 0.01), 0.25))
            try:
                self._receive_message()
            except socket.timeout:
                continue

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except (OSError, RuntimeError):
            pass
        self._socket.close()

    def _pop_response(self, message_id: int, method: str) -> dict[str, Any]:
        response = self._pending.pop(message_id)
        if error := response.get("error"):
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"CDP {method} failed: {message}")
        result = response.get("result", {})
        return result if isinstance(result, dict) else {"value": result}

    def _receive_message(self) -> None:
        raw = self._receive_text()
        message = json.loads(raw)
        if "id" in message:
            self._pending[int(message["id"])] = message
            return
        if self._event_callback is not None and "method" in message:
            self._event_callback(message)

    def _connect(self, websocket_url: str, timeout_seconds: float) -> socket.socket:
        parsed = urllib.parse.urlparse(websocket_url)
        if parsed.scheme != "ws":
            raise RuntimeError(f"only ws:// CDP endpoints are supported, got {websocket_url!r}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((host, port), timeout=timeout_seconds)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = "\r\n".join(
            [
                f"GET {path} HTTP/1.1",
                f"Host: {host}:{port}",
                "Upgrade: websocket",
                "Connection: Upgrade",
                f"Sec-WebSocket-Key: {key}",
                "Sec-WebSocket-Version: 13",
                "",
                "",
            ]
        )
        sock.sendall(request.encode("ascii"))
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("CDP WebSocket closed during handshake")
            header += chunk
        status_line, _, header_blob = header.partition(b"\r\n")
        if b" 101 " not in status_line:
            raise RuntimeError(f"CDP WebSocket handshake failed: {status_line.decode('ascii', errors='replace')}")
        headers = self._parse_headers(header_blob.decode("ascii", errors="replace"))
        expected_accept = base64.b64encode(hashlib.sha1(f"{key}{self._GUID}".encode("ascii")).digest()).decode(
            "ascii"
        )
        if headers.get("sec-websocket-accept") != expected_accept:
            raise RuntimeError("CDP WebSocket handshake returned an unexpected accept token")
        return sock

    @staticmethod
    def _parse_headers(header_blob: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in header_blob.splitlines():
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        return headers

    def _send_text(self, payload: str) -> None:
        self._send_frame(0x1, payload.encode("utf-8"))

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        length = len(payload)
        if length <= 125:
            header = bytes([0x80 | opcode, 0x80 | length])
        elif length <= 0xFFFF:
            header = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack("!H", length)
        else:
            header = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        try:
            self._socket.sendall(header + mask + masked)
        except OSError as exc:
            raise RuntimeError(f"CDP WebSocket send failed: {exc}") from exc

    def _receive_text(self) -> str:
        payload_parts: list[bytes] = []
        text_opcode_seen = False
        while True:
            first, second = self._read_exact(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

            if opcode == 0x8:
                raise RuntimeError("CDP WebSocket closed")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x1:
                text_opcode_seen = True
                payload_parts.append(payload)
            elif opcode == 0x0 and text_opcode_seen:
                payload_parts.append(payload)
            else:
                continue
            if fin:
                return b"".join(payload_parts).decode("utf-8")

    def _read_exact(self, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise RuntimeError("CDP WebSocket closed while reading frame")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


_NO_EVALUATE_ARG = object()


def _remote_preview_property_text(property_info: dict[str, Any]) -> str:
    if "value" in property_info:
        return str(property_info["value"])
    if "description" in property_info:
        return str(property_info["description"])
    return str(property_info.get("type") or "")


def _remote_object_preview_text(remote_object: dict[str, Any]) -> str | None:
    preview = remote_object.get("preview") if isinstance(remote_object.get("preview"), dict) else None
    if preview is None:
        return None
    properties = preview.get("properties") if isinstance(preview.get("properties"), list) else []
    rendered = [_remote_preview_property_text(prop) for prop in properties if isinstance(prop, dict)]
    if preview.get("subtype") == "array":
        suffix = ", ..." if preview.get("overflow") else ""
        return f"[{', '.join(rendered)}{suffix}]"
    if rendered:
        suffix = ", ..." if preview.get("overflow") else ""
        return "{" + ", ".join(rendered) + suffix + "}"
    return None


def _remote_object_text(remote_object: dict[str, Any]) -> str:
    if "value" in remote_object:
        return str(remote_object["value"])
    if "unserializableValue" in remote_object:
        return str(remote_object["unserializableValue"])
    if preview_text := _remote_object_preview_text(remote_object):
        return preview_text
    if "description" in remote_object:
        return str(remote_object["description"])
    return str(remote_object.get("type") or "")


def _stack_trace_location(stack_trace: dict[str, Any] | None) -> dict[str, Any]:
    call_frames = (stack_trace or {}).get("callFrames") or []
    if not call_frames:
        return {}
    frame = call_frames[0]
    return {
        "url": frame.get("url") or "",
        "lineNumber": frame.get("lineNumber", 0),
        "columnNumber": frame.get("columnNumber", 0),
    }


class _AndroidWebViewCdpPage:
    """Playwright-like page facade backed by a WebView page-target CDP socket."""

    def __init__(
        self,
        websocket_url: str,
        timeout_ms: int,
        target: dict[str, Any],
        *,
        session: _CdpWebSocketSession | None = None,
    ) -> None:
        self.websocket_url = websocket_url
        self.url = str(target.get("url") or "")
        self.setup_errors: list[dict[str, str]] = []
        self._timeout_seconds = max(timeout_ms / 1000, 1)
        self._cdp_url = _cdp_url_from_websocket_url(websocket_url)
        self._handlers: dict[str, list[Any]] = {}
        self._requests: dict[str, dict[str, Any]] = {}
        self._session = session or _CdpWebSocketSession(websocket_url, self._timeout_seconds)
        self._session.set_event_callback(self._handle_event)
        self._enable_domains()

    def _enable_domains(self) -> None:
        for method in ("Runtime.enable", "Page.enable", "Network.enable"):
            try:
                self._send_command(method)
            except RuntimeError as exc:
                self.setup_errors.append({"method": method, "error": str(exc)})

    def __enter__(self) -> "_AndroidWebViewCdpPage":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def on(self, event_name: str, handler: Any) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def evaluate(self, script: str, arg: Any = _NO_EVALUATE_ARG) -> Any:
        expression = f"({script})()" if arg is _NO_EVALUATE_ARG else f"({script})({json.dumps(arg, ensure_ascii=False)})"
        response = self._send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if exception := response.get("exceptionDetails"):
            raise RuntimeError(_format_exception_details(exception))
        remote_result = response.get("result", {})
        if isinstance(remote_result, dict) and "value" in remote_result:
            return remote_result["value"]
        if isinstance(remote_result, dict) and remote_result.get("type") == "undefined":
            return None
        return remote_result.get("description") if isinstance(remote_result, dict) else remote_result

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self._session.drain_events(max(timeout_ms, 0) / 1000)

    def screenshot(self, *, path: str, full_page: bool = False) -> None:
        del full_page
        response = self._send_command("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        data = response.get("data")
        if not isinstance(data, str):
            raise RuntimeError("Page.captureScreenshot did not return image data")
        screenshot_path = Path(path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(base64.b64decode(data))

    def close(self) -> None:
        self._session.close()

    def reconnect(self) -> None:
        self.close()
        self._requests = {}
        targets = _fetch_json(f"{self._cdp_url}/json/list", timeout=self._timeout_seconds)
        target = _select_cdp_page_target(targets if isinstance(targets, list) else [])
        if target is None:
            raise RuntimeError("Android WebView CDP reconnect did not expose a page target")
        self.websocket_url = _target_websocket_url(self._cdp_url, target)
        self.url = str(target.get("url") or self.url)
        self._session = _CdpWebSocketSession(self.websocket_url, self._timeout_seconds)
        self._session.set_event_callback(self._handle_event)
        self._enable_domains()

    def _send_command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._session.send_command(method, params, timeout_seconds=self._timeout_seconds)

    def _emit(self, event_name: str, payload: Any) -> None:
        for handler in self._handlers.get(event_name, []):
            handler(payload)

    def _handle_event(self, message: dict[str, Any]) -> None:
        method = str(message.get("method") or "")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "Runtime.consoleAPICalled":
            args = params.get("args") if isinstance(params.get("args"), list) else []
            text = " ".join(_remote_object_text(arg) for arg in args if isinstance(arg, dict))
            location = _stack_trace_location(params.get("stackTrace"))
            self._emit("console", _CdpObject(type=params.get("type") or "log", text=text, location=location))
        elif method == "Runtime.exceptionThrown":
            self._emit("pageerror", _format_exception_details(params.get("exceptionDetails") or {}))
        elif method == "Network.requestWillBeSent":
            request_id = str(params.get("requestId") or "")
            request = params.get("request") if isinstance(params.get("request"), dict) else {}
            self._requests[request_id] = {
                "url": request.get("url") or "",
                "method": request.get("method") or "GET",
                "resource_type": str(params.get("type") or "other").lower(),
            }
        elif method == "Network.loadingFailed":
            request = self._requests.get(str(params.get("requestId") or ""), {})
            self._emit(
                "requestfailed",
                _CdpObject(
                    url=request.get("url") or "",
                    method=request.get("method") or "GET",
                    resource_type=request.get("resource_type") or "other",
                    failure=params.get("errorText") or "request failed",
                ),
            )
        elif method == "Network.responseReceived":
            response = params.get("response") if isinstance(params.get("response"), dict) else {}
            self._emit(
                "response",
                _CdpObject(
                    url=response.get("url") or "",
                    status=int(response.get("status") or 0),
                    status_text=response.get("statusText") or "",
                ),
            )
        elif method == "Page.frameNavigated":
            frame = params.get("frame") if isinstance(params.get("frame"), dict) else {}
            if not frame.get("parentId") and frame.get("url"):
                self.url = str(frame["url"])
        elif method == "Page.javascriptDialogOpening":
            dialog = _CdpDialog(self, str(params.get("type") or "alert"), str(params.get("message") or ""))
            self._emit("dialog", dialog)
            if not dialog.accepted:
                dialog.accept()


def _format_exception_details(details: dict[str, Any]) -> str:
    exception = details.get("exception") if isinstance(details.get("exception"), dict) else {}
    return str(exception.get("description") or exception.get("value") or details.get("text") or details)


def _select_cdp_page_target(targets: list[Any]) -> dict[str, Any] | None:
    typed_targets = [target for target in targets if isinstance(target, dict)]
    websocket_targets = [target for target in typed_targets if target.get("webSocketDebuggerUrl")]
    page_targets = [target for target in websocket_targets if target.get("type") == "page"]
    candidates = page_targets or websocket_targets
    if not candidates:
        return None

    def score(target: dict[str, Any]) -> tuple[int, int]:
        url = str(target.get("url") or "")
        title = str(target.get("title") or "")
        is_local_game = url.startswith("https://localhost/") or url.startswith("http://localhost/")
        return (0 if is_local_game else 1, 0 if title else 1)

    return sorted(candidates, key=score)[0]


def _target_websocket_url(cdp_url: str, target: dict[str, Any]) -> str:
    raw_url = str(target.get("webSocketDebuggerUrl") or "")
    if raw_url.startswith("ws://"):
        return raw_url
    if not raw_url:
        raise RuntimeError("selected Android WebView CDP target did not expose webSocketDebuggerUrl")
    parsed = urllib.parse.urlparse(cdp_url)
    if not parsed.netloc:
        raise RuntimeError(f"cannot resolve relative CDP WebSocket URL from {cdp_url!r}")
    path = raw_url if raw_url.startswith("/") else f"/{raw_url}"
    return urllib.parse.urlunparse(("ws", parsed.netloc, path, "", "", ""))


def _cdp_url_from_websocket_url(websocket_url: str) -> str:
    parsed = urllib.parse.urlparse(websocket_url)
    if not parsed.netloc:
        raise RuntimeError(f"cannot resolve CDP HTTP URL from {websocket_url!r}")
    return urllib.parse.urlunparse(("http", parsed.netloc, "", "", "", ""))


def _record_apk_identity(report: BrowserSmokeReport, apk_path: Path, profile_name: str) -> None:
    normalized_name = apk_path.name.lower().replace("_", "-")
    required_tokens = ("ucb", "more-love", "custom-spellbook", "cheat-extended", "maplebirch")
    missing_tokens = [token for token in required_tokens if token not in normalized_name]
    identity = {
        "package_slug": apk_path.stem,
        "profile": profile_name,
        "profile_slug_match": not missing_tokens,
        "required_slug_tokens": list(required_tokens),
        "missing_required_slug_tokens": missing_tokens,
        "artifact_kind": "apk-smoke-debug",
    }
    report.observations["package_identity"] = identity
    for token in missing_tokens:
        _add_issue(
            report,
            Issue(
                "warning",
                "package_required_slug_token_missing",
                "identity",
                f"APK slug {apk_path.stem!r} does not include expected token {token!r} for profile {profile_name!r}",
            ),
        )


def _extract_static_embedded_mods(apk_path: Path) -> list[Any]:
    try:
        _, html_content = load_html_artifact(apk_path)
    except Exception:  # noqa: BLE001 - runtime report will still capture CDP status.
        return []
    if html_content is None:
        return []
    return extract_embedded_mods_from_html(html_content)


def _run_webview_browser_smoke(
    apk_path: Path,
    output_dir: Path,
    profile_name: str,
    cdp_url: str,
    expected_passage: str,
    timeout_ms: int,
    settle_ms: int,
    cdp_diagnostics: dict[str, Any],
) -> BrowserSmokeReport:
    profile = PROFILES[profile_name]
    report = BrowserSmokeReport(
        target=str(apk_path),
        profile=profile.name,
        report_only=False,
        ci_context=collect_ci_context(),
    )
    report.observations["apk_cdp"] = cdp_diagnostics
    _record_apk_identity(report, apk_path, profile_name)

    embedded_mods = _extract_static_embedded_mods(apk_path)
    report.observations["embedded_mods"] = [asdict(info) for info in embedded_mods]

    target = _select_cdp_page_target(cdp_diagnostics.get("targets", []))
    if target is None:
        _add_issue(
            report,
            Issue(
                "high",
                "apk_cdp_page_target_missing",
                "runner",
                "Android WebView CDP endpoint did not expose a page target with webSocketDebuggerUrl",
            ),
        )
        return report

    websocket_url = _target_websocket_url(cdp_url, target)
    report.observations["apk_cdp_page_target"] = {
        "id": target.get("id"),
        "type": target.get("type"),
        "title": target.get("title"),
        "url": target.get("url"),
        "webSocketDebuggerUrl": websocket_url,
    }

    try:
        with _AndroidWebViewCdpPage(websocket_url, timeout_ms, target) as page:
            if page.setup_errors:
                report.observations["apk_cdp_setup_errors"] = page.setup_errors
            _attach_page_events(report, page)
            _with_cdp_reconnect(report, page, "settle", lambda: page.wait_for_timeout(settle_ms))
            report.served_url = page.url

            startup_result = _run_startup_interactions(report, page, profile)
            if _is_cdp_transport_error((startup_result or {}).get("error")):
                _reconnect_cdp_page(report, page, "startup_interactions", (startup_result or {}).get("error"))
                _run_startup_interactions(report, page, profile)
            global_names = tuple(
                dict.fromkeys([*profile.required_globals, *profile.warning_globals, *profile.diagnostic_globals])
            )
            page_state = _with_cdp_reconnect(
                report,
                page,
                "page_state",
                lambda: page.evaluate(_page_state_script(global_names), global_names),
            )
            report.observations["page_state"] = page_state
            report.observations["runtime_globals"] = {
                global_name: (page_state.get("globals", {}) or {}).get(global_name)
                for global_name in profile.diagnostic_globals
            }
            report.observations["browser_boot"] = {
                "navigation_ok": True,
                "served_url": page.url,
                "ready_state": page_state.get("readyState"),
                "has_jquery": page_state.get("hasJQuery"),
                "has_sugarcube": page_state.get("hasSugarCube"),
                "has_mod_data_value_zip_list": page_state.get("hasModDataValueZipList"),
                "mod_data_value_zip_list_length": page_state.get("modDataValueZipListLength"),
                "dialog_count": len(report.observations.get("dialogs", [])),
                "popup_count": 0,
                "console_message_count": len(report.console_messages),
                "network_failure_count": len(report.network_failures),
            }
            _with_cdp_reconnect(report, page, "game_ready", lambda: _record_game_ready(report, page))
            _with_cdp_reconnect(report, page, "enter_game", lambda: _attempt_enter_game(report, page))
            enter_result = report.observations.get("enter_game") or {}
            if isinstance(enter_result, dict) and _is_cdp_transport_error(enter_result.get("error")):
                _reconnect_cdp_page(report, page, "enter_game", enter_result.get("error"))
                _attempt_enter_game(report, page)
            final_game_ready = _with_cdp_reconnect(
                report,
                page,
                "final_game_ready",
                lambda: _record_game_ready(report, page, add_issues=False),
            )
            _check_required_mods(report, profile, embedded_mods)
            _downgrade_ready_cordova_pageerrors(report, final_game_ready, expected_passage)

            observed_passage = final_game_ready.get("passage")
            if expected_passage and observed_passage != expected_passage:
                _add_issue(
                    report,
                    Issue(
                        "high",
                        "expected_passage_not_reached",
                        "apk_cdp_smoke",
                        f"expected passage {expected_passage!r}, got {observed_passage!r}",
                    ),
                )

            screenshot_path = output_dir / "browser-smoke-final.png"
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                report.observations["screenshot"] = {"path": str(screenshot_path), "full_page": True}
            except Exception as exc:  # noqa: BLE001 - screenshot is useful but non-blocking.
                _add_issue(report, Issue("warning", "screenshot_failed", "runner", str(exc)))
    except Exception as exc:  # noqa: BLE001 - preserve CDP failures as report artifacts.
        _add_issue(report, _classify_apk_cdp_smoke_exception(exc))

    return report


def _write_logcat(adb: str, output_dir: Path, commands: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    logcat_path = output_dir / "logcat.txt"
    result = _run_command([adb, "logcat", "-d", "-v", "time"], commands, check=False, timeout=30)
    logcat_path.write_text(result.stdout or result.stderr or "", encoding="utf-8", errors="replace")
    return logcat_path


def run_apk_emulator_smoke(args: argparse.Namespace) -> int:
    start = time.monotonic()
    apk_path = Path(args.apk).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []
    errors: list[str] = []
    package_name = args.package or _default_package_name()
    slug = args.slug or _apk_slug(apk_path)
    cdp: dict[str, Any] = {
        "success": False,
        "cdp_url": f"http://127.0.0.1:{args.cdp_port}",
        "socket": None,
        "targets": [],
    }
    browser_report: BrowserSmokeReport | None = None
    setup_completed = False

    try:
        _run_command([args.adb, "devices"], commands, timeout=30)
        _run_command([args.adb, "logcat", "-c"], commands, check=False, timeout=30)
        _run_command([args.adb, "install", "-r", "-d", str(apk_path)], commands, timeout=args.install_timeout_seconds)
        _run_command([args.adb, "shell", "pm", "clear", package_name], commands, check=False, timeout=30)
        _run_command(
            [args.adb, "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
            commands,
            timeout=30,
        )
        time.sleep(args.launch_settle_seconds)
        setup_completed = True

        cdp = _discover_cdp_endpoint(
            args.adb,
            package_name,
            commands,
            cdp_port=args.cdp_port,
            timeout_seconds=args.cdp_timeout_seconds,
        )
        if not cdp.get("success"):
            errors.append(str(cdp.get("error") or "failed to discover Android WebView CDP endpoint"))

        if cdp.get("success"):
            browser_report = _run_webview_browser_smoke(
                apk_path,
                output_dir,
                args.profile,
                str(cdp["cdp_url"]),
                args.expected_passage,
                args.timeout_ms,
                args.settle_ms,
                cdp,
            )
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        errors.append(str(exc))
        cdp["error"] = str(exc)

    if browser_report is None:
        browser_report = BrowserSmokeReport(
            target=str(apk_path),
            profile=args.profile,
            report_only=False,
            ci_context=collect_ci_context(),
        )
        browser_report.observations["apk_cdp"] = cdp
        _record_apk_identity(browser_report, apk_path, args.profile)
        issue_kind = "apk_cdp_endpoint_missing" if setup_completed else "apk_emulator_setup_failed"
        _add_issue(browser_report, Issue("high", issue_kind, "adb", errors[-1] if errors else issue_kind))

    browser_report.elapsed_seconds = time.monotonic() - start
    browser_report.observations["runtime_scope"] = {
        "platform": "Android emulator",
        "webview_cdp": True,
        "manual_phone_testing": False,
        "harmonyos_covered": False,
    }
    browser_report.success = _is_successful_smoke(browser_report)
    write_outputs(browser_report, output_dir)
    browser_summary = summarize_report(browser_report)
    try:
        logcat_path = _write_logcat(args.adb, output_dir, commands)
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"logcat collection failed: {exc}")
        logcat_path = output_dir / "logcat.txt"
        logcat_path.write_text(str(exc), encoding="utf-8", errors="replace")
    try:
        _run_command([args.adb, "forward", "--remove", f"tcp:{args.cdp_port}"], commands, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"CDP forward cleanup failed: {exc}")

    success = browser_report.success and not errors
    payload = {
        "success": success,
        "gate_level": "full_candidate_gate_ready_component",
        "counts_for_phase2_promotion": False,
        "default_matrix_mutated": False,
        "runtime_scope": browser_report.observations["runtime_scope"],
        "target": str(apk_path),
        "slug": slug,
        "package": package_name,
        "profile": args.profile,
        "expected_passage": args.expected_passage,
        "cdp_url": cdp.get("cdp_url"),
        "cdp_socket": cdp.get("socket"),
        "cdp_targets": cdp.get("targets", []),
        "browser_summary": browser_summary,
        "browser_summary_path": str(output_dir / "browser-smoke-summary.json"),
        "browser_report_path": str(output_dir / "browser-smoke-report.json"),
        "markdown_report_path": str(output_dir / "browser-smoke-report.md"),
        "logcat_path": str(logcat_path),
        "screenshot_path": str((browser_summary.get("screenshot") or {}).get("path") or ""),
        "commands": commands,
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - start, 2),
    }
    _write_json(output_dir / "apk-emulator-smoke.json", payload)
    print(json.dumps({"slug": slug, "success": success, "errors": errors}, ensure_ascii=False))
    return 0 if success else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Android emulator WebView/CDP smoke test for a smoke-debug APK")
    parser.add_argument("apk", type=Path, help="Release-derived smoke-debug APK to install and smoke")
    parser.add_argument("--output-dir", type=Path, default=Path("output/apk-emulator-smoke"))
    parser.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE)
    parser.add_argument("--package", help="Android package name; defaults to config/build.toml identity package")
    parser.add_argument("--slug", choices=("base", "au-f", "au-m", "au-a"))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    parser.add_argument("--expected-passage", default=DEFAULT_EXPECTED_PASSAGE)
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--settle-ms", type=int, default=5_000)
    parser.add_argument("--install-timeout-seconds", type=int, default=180)
    parser.add_argument("--launch-settle-seconds", type=int, default=5)
    parser.add_argument("--cdp-timeout-seconds", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_apk_emulator_smoke(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
