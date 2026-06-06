#!/usr/bin/env python3
"""Phase 4: browser smoke test for built DoL packages.

This tool intentionally stays outside the Lyra build pipeline.  It opens a
built ZIP/HTML package through a local HTTP server, captures browser runtime
evidence, and writes report-only artifacts that can later be promoted to a
strict CI gate.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.artifact_inspection import (
    collect_string_values,
    decode_base64_payload,
    parse_mod_data_value_zip_list,
)


@dataclass(frozen=True)
class SmokeProfile:
    """Mod-specific browser checks layered on top of generic smoke checks."""

    name: str
    required_mod_names: tuple[str, ...] = ()
    required_globals: tuple[str, ...] = ()
    warning_globals: tuple[str, ...] = ()
    diagnostic_globals: tuple[str, ...] = ()
    diagnostic_mod_names: tuple[str, ...] = ()
    click_selectors: tuple[str, ...] = ()
    dialog_password: str | None = None


CHEAT_EXTENDED_RUNTIME_GLOBALS: tuple[str, ...] = (
    "maplebirchFrameworks",
    "CE_options",
    "SCMLSimpleFramework",
)

CHEAT_EXTENDED_RUNTIME_MOD_PROBES: tuple[str, ...] = (
    "maplebirch",
    "Simple Frameworks",
)


PROFILES: dict[str, SmokeProfile] = {
    "ucb-more-love-custom-spellbook": SmokeProfile(
        name="ucb-more-love-custom-spellbook",
        required_mod_names=(
            "ModLoaderGui",
            "ModI18N",
            "More Love Interests Mod",
            "Custom-Spellbook",
            "Lyra",
        ),
        warning_globals=("spellBookMobileClicked",),
        click_selectors=('[onclick*="spellBookMobileClicked"]',),
        dialog_password="DOL-Custom-Spellbook-Mod",
    ),
    "ucb-cheat-extended-maplebirch": SmokeProfile(
        name="ucb-cheat-extended-maplebirch",
        required_mod_names=(
            "ModLoaderGui",
            "ModI18N",
            "maplebirch",
            "cheatExtended",
            "Lyra",
        ),
        diagnostic_globals=CHEAT_EXTENDED_RUNTIME_GLOBALS,
        diagnostic_mod_names=CHEAT_EXTENDED_RUNTIME_MOD_PROBES,
    ),
    "ucb-more-love-custom-spellbook-cheat-extended-maplebirch": SmokeProfile(
        name="ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
        required_mod_names=(
            "ModLoaderGui",
            "ModI18N",
            "maplebirch",
            "cheatExtended",
            "More Love Interests Mod",
            "Custom-Spellbook",
            "Lyra",
        ),
        warning_globals=("spellBookMobileClicked",),
        diagnostic_globals=CHEAT_EXTENDED_RUNTIME_GLOBALS,
        diagnostic_mod_names=CHEAT_EXTENDED_RUNTIME_MOD_PROBES,
        click_selectors=('[onclick*="spellBookMobileClicked"]',),
        dialog_password="DOL-Custom-Spellbook-Mod",
    ),
    "none": SmokeProfile(name="none"),
}


@dataclass
class Issue:
    """One classified browser smoke finding."""

    severity: str
    kind: str
    source: str
    message: str
    url: str | None = None
    location: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrowserSmokeReport:
    """Serializable browser smoke report."""

    target: str
    profile: str
    report_only: bool
    ci_context: dict[str, str] = field(default_factory=dict)
    success: bool = False
    html_path: str | None = None
    served_url: str | None = None
    elapsed_seconds: float = 0.0
    issues: list[Issue] = field(default_factory=list)
    console_messages: list[dict[str, Any]] = field(default_factory=list)
    network_failures: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddedModInfo:
    """Minimal metadata extracted from an embedded ModLoader ZIP payload."""

    index: int
    names: list[str] = field(default_factory=list)
    boot_json_found: bool = False
    error: str | None = None
    search_text: str = ""


def collect_ci_context() -> dict[str, str]:
    """Collect optional GitHub Actions metadata for report traceability."""
    env_map = {
        "workflow_run_id": "DOLX_WORKFLOW_RUN_ID",
        "workflow_head_branch": "DOLX_WORKFLOW_HEAD_BRANCH",
        "workflow_head_sha": "DOLX_WORKFLOW_HEAD_SHA",
        "github_sha": "DOLX_GITHUB_SHA",
        "artifact_name": "DOLX_ARTIFACT_NAME",
    }
    return {key: value for key, env_name in env_map.items() if (value := os.environ.get(env_name))}


ALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "usettings_inactive_normal",
        re.compile(r"usettings\.js not active, this is normal", re.IGNORECASE),
    ),
)

WARNING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "optional_remote_mod_list",
        re.compile(r"modList\.json", re.IGNORECASE),
    ),
    (
        "more_love_optional_dependency",
        re.compile(r"Remy Love Mod|NPC Avatars Mod", re.IGNORECASE),
    ),
    (
        "spellbook_external_asset",
        re.compile(r"style\.css|img/misc/banner\.png|banner\.png", re.IGNORECASE),
    ),
    (
        "usettings_optional_asset",
        re.compile(r"usettings\.js", re.IGNORECASE),
    ),
    (
        "simple_frameworks_optional_lookup",
        re.compile(
            r"ModOrderContainer getByNameOne\(\) cannot find name\. \[Simple Frameworks, ModOrderContainer\]",
            re.IGNORECASE,
        ),
    ),
)

HIGH_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "image_layer_load_failed",
        re.compile(r"Failed to load image\s+\S+\s+for layer\s+\w+", re.IGNORECASE),
    ),
    (
        "face_image_asset_missing",
        re.compile(
            r"img/face/[^\s]+\.(?:png|jpe?g|webp|gif).*(?:HTTP 4\d\d|ERR_FILE_NOT_FOUND|ERR_FAILED|failed|not found)",
            re.IGNORECASE,
        ),
    ),
    (
        "spellbook_missing_click_handler",
        re.compile(r"spellBookMobileClicked.*not defined", re.IGNORECASE),
    ),
    (
        "prevent_default_type_error",
        re.compile(r"ev\.preventDefault is not a function", re.IGNORECASE),
    ),
    (
        "maplebirch_framework_missing",
        re.compile(r"maplebirchFrameworks.*not defined", re.IGNORECASE),
    ),
    (
        "skin_colour_fallback_missing",
        re.compile(r"skinColourFullback|skincolourtext.*not defined", re.IGNORECASE),
    ),
    (
        "tw_user_script_error",
        re.compile(r"Error \[tw-user-script-[^\]]*\]", re.IGNORECASE),
    ),
    ("reference_error", re.compile(r"\bReferenceError\b", re.IGNORECASE)),
    ("type_error", re.compile(r"\bTypeError\b", re.IGNORECASE)),
    ("uncaught_error", re.compile(r"\bUncaught\b", re.IGNORECASE)),
)


PROFILE_SLUG_EXPECTATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "ucb-more-love-custom-spellbook": {
        "required": ("ucb", "more-love", "custom-spellbook"),
        "forbidden": ("cheat-extended", "maplebirch"),
    },
    "ucb-cheat-extended-maplebirch": {
        "required": ("ucb", "cheat-extended", "maplebirch"),
        "forbidden": ("more-love", "custom-spellbook"),
    },
    "ucb-more-love-custom-spellbook-cheat-extended-maplebirch": {
        "required": ("ucb", "more-love", "custom-spellbook", "cheat-extended", "maplebirch"),
        "forbidden": (),
    },
}


BRANCH_PROFILE_EXPECTATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^vega$", re.IGNORECASE), "ucb-more-love-custom-spellbook"),
    (
        re.compile(r"^experiment/cheat-extended-maplebirch$", re.IGNORECASE),
        "ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
    ),
)


ARTIFACT_PROFILE_EXPECTATIONS: dict[str, str] = {
    "dol-builds-cheat-canary-zip": "ucb-cheat-extended-maplebirch",
    "baseline-candidate-zip-artifacts": "ucb-more-love-custom-spellbook-cheat-extended-maplebirch",
}


def extract_embedded_mods_from_html(content: str) -> list[EmbeddedModInfo]:
    """Extract best-effort embedded mod metadata from a built HTML file."""
    parsed_mods = parse_mod_data_value_zip_list(content)
    if parsed_mods.error_kind:
        return []

    embedded_mods: list[EmbeddedModInfo] = []
    for index, entry in enumerate(parsed_mods.entries):
        info = EmbeddedModInfo(index=index)
        embedded_mods.append(info)

        if not isinstance(entry, str):
            info.error = "modDataValueZipList entry is not a string"
            continue

        try:
            payload = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
                boot_names = [name for name in zf.namelist() if name.lower().endswith("boot.json")]
                if not boot_names:
                    info.error = "boot.json not found"
                    continue

                info.boot_json_found = True
                boot_text = zf.read(boot_names[0]).decode("utf-8", errors="replace")
                info.search_text = boot_text
                try:
                    boot_json = json.loads(boot_text)
                    strings = list(collect_string_values(boot_json))
                    preferred_keys = ("name", "modName", "id", "nickName")
                    if isinstance(boot_json, dict):
                        for key in preferred_keys:
                            value = boot_json.get(key)
                            if isinstance(value, str):
                                info.names.append(value)
                    for value in strings:
                        if value not in info.names:
                            info.names.append(value)
                except json.JSONDecodeError:
                    info.names.append(boot_text[:120])
        except Exception as exc:  # noqa: BLE001 - report malformed embedded entries.
            info.error = str(exc)

    return embedded_mods


def classify_message(source: str, message: str) -> Issue:
    """Classify a browser message into allowed, warning, or high-risk."""
    for kind, pattern in ALLOWED_PATTERNS:
        if pattern.search(message):
            return Issue("allowed", kind, source, message)

    for kind, pattern in HIGH_RISK_PATTERNS:
        if pattern.search(message):
            return Issue("high", kind, source, message)

    for kind, pattern in WARNING_PATTERNS:
        if pattern.search(message):
            return Issue("warning", kind, source, message)

    if source in {"console.error", "pageerror"}:
        return Issue("high", "unexpected_browser_error", source, message)

    if source in {"requestfailed", "http_error"}:
        return Issue("warning", "network_failure", source, message)

    return Issue("warning", "browser_warning", source, message)


def _artifact_path_preference(path: Path) -> tuple[bool, bool, str]:
    normalized_path = str(path).lower().replace("_", "-")
    normalized_name = path.name.lower().replace("_", "-")
    # When an artifact directory contains multiple builds, smoke the smallest
    # dependency surface first. AU variants get a dedicated pass after base boot.
    return (
        "-au-" in normalized_path,
        "dol-" not in normalized_name and "degrees of lewdity" not in normalized_name,
        normalized_path,
    )


def _find_preferred_html(root: Path) -> Path | None:
    candidates = sorted(root.rglob("*.html"), key=lambda item: str(item).lower())
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: ("degrees of lewdity" not in item.name.lower(), *_artifact_path_preference(item)),
    )[0]


def _zip_preference(zip_path: Path) -> tuple[bool, bool, str]:
    return _artifact_path_preference(zip_path)


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = (destination / member.filename).resolve()
            try:
                member_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"unsafe ZIP member path: {member.filename}") from exc
        zf.extractall(destination)


def _resolve_target(target: Path, temp_root: Path) -> tuple[Path, Path]:
    target = target.resolve()
    if not target.exists():
        raise FileNotFoundError(f"target does not exist: {target}")

    if target.is_file() and target.suffix.lower() == ".html":
        return target.parent, target

    if target.is_file() and target.suffix.lower() == ".zip":
        extract_dir = temp_root / target.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(target, extract_dir)
        html_path = _find_preferred_html(extract_dir)
        if html_path is None:
            raise FileNotFoundError(f"ZIP target has no HTML file: {target}")
        return extract_dir, html_path

    if target.is_dir():
        html_path = _find_preferred_html(target)
        if html_path is not None:
            return target, html_path

        zip_candidates = sorted(target.rglob("*.zip"), key=_zip_preference)
        if zip_candidates:
            return _resolve_target(zip_candidates[0], temp_root)

    raise FileNotFoundError(f"target is not an HTML, ZIP, or artifact directory: {target}")


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that keeps CI logs focused on smoke findings."""

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP verb hook.
        request_path = self.path.split("?", 1)[0].split("#", 1)[0]
        if request_path == "/modList.json" and not Path(self.translate_path(self.path)).exists():
            payload = b"[]\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - inherited name.
        return


@contextlib.contextmanager
def _serve_directory(directory: Path):
    handler = functools.partial(QuietHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _relative_url(server: http.server.ThreadingHTTPServer, serve_dir: Path, html_path: Path) -> str:
    relative = html_path.relative_to(serve_dir).as_posix()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/{quote(relative)}"


def _add_issue(report: BrowserSmokeReport, issue: Issue, **updates: Any) -> None:
    for key, value in updates.items():
        setattr(issue, key, value)
    report.issues.append(issue)


def _package_slug_from_paths(target: Path, html_path: Path) -> str:
    candidates = [html_path.parent.name]
    if target.suffix.lower() == ".zip":
        candidates.append(target.stem)
    candidates.extend([target.name, target.stem])

    for candidate in candidates:
        if candidate and any(marker in candidate.lower() for marker in ("dol-", "xfox", "ucb", "lyra")):
            return candidate
    return next((candidate for candidate in candidates if candidate), "")


def _expected_profile_for_branch(branch: str | None) -> str | None:
    if not branch:
        return None
    for pattern, profile_name in BRANCH_PROFILE_EXPECTATIONS:
        if pattern.search(branch):
            return profile_name
    return None


def _expected_profile_for_artifact(artifact_name: str | None) -> str | None:
    if not artifact_name:
        return None
    return ARTIFACT_PROFILE_EXPECTATIONS.get(artifact_name)


def _record_package_identity(
    report: BrowserSmokeReport,
    profile: SmokeProfile,
    target: Path,
    html_path: Path,
) -> dict[str, Any]:
    package_slug = _package_slug_from_paths(target, html_path)
    normalized_slug = package_slug.lower().replace("_", "-")
    branch = report.ci_context.get("workflow_head_branch")
    artifact_name = report.ci_context.get("artifact_name")
    expected_profile_for_branch = _expected_profile_for_branch(branch)
    expected_profile_for_artifact = _expected_profile_for_artifact(artifact_name)
    expected_profile = expected_profile_for_artifact or expected_profile_for_branch
    expected_profile_source = "artifact" if expected_profile_for_artifact else "branch" if expected_profile_for_branch else None
    slug_expectations = PROFILE_SLUG_EXPECTATIONS.get(profile.name, {"required": (), "forbidden": ()})
    required_tokens = slug_expectations.get("required", ())
    forbidden_tokens = slug_expectations.get("forbidden", ())
    missing_required = [token for token in required_tokens if token not in normalized_slug]
    forbidden_present = [token for token in forbidden_tokens if token in normalized_slug]
    branch_profile_match = expected_profile is None or expected_profile == profile.name
    profile_slug_match = not missing_required and not forbidden_present

    identity = {
        "package_slug": package_slug,
        "profile": profile.name,
        "workflow_head_branch": branch,
        "artifact_name": artifact_name,
        "expected_profile": expected_profile,
        "expected_profile_for_branch": expected_profile_for_branch,
        "expected_profile_for_artifact": expected_profile_for_artifact,
        "expected_profile_source": expected_profile_source,
        "branch_profile_match": branch_profile_match,
        "required_slug_tokens": list(required_tokens),
        "missing_required_slug_tokens": missing_required,
        "forbidden_slug_tokens": list(forbidden_tokens),
        "forbidden_slug_tokens_present": forbidden_present,
        "profile_slug_match": profile_slug_match,
    }
    report.observations["package_identity"] = identity

    if expected_profile is not None and expected_profile != profile.name:
        _add_issue(
            report,
            Issue(
                "high",
                "branch_profile_mismatch",
                "identity",
                f"branch {branch!r} should use profile {expected_profile!r}, got {profile.name!r}",
            ),
        )
    for token in missing_required:
        _add_issue(
            report,
            Issue(
                "warning",
                "package_required_slug_token_missing",
                "identity",
                f"package slug {package_slug!r} does not include expected token {token!r} for profile {profile.name!r}",
            ),
        )
    for token in forbidden_present:
        _add_issue(
            report,
            Issue(
                "high",
                "package_forbidden_slug_token_present",
                "identity",
                f"package slug {package_slug!r} includes experiment token {token!r} while using profile {profile.name!r}",
            ),
        )

    return identity


def _relative_sample_paths(root: Path, candidates: list[Path], limit: int = 20) -> list[str]:
    samples = []
    for candidate in candidates[:limit]:
        with contextlib.suppress(ValueError):
            samples.append(candidate.relative_to(root).as_posix())
    return samples


def _record_static_asset_audit(report: BrowserSmokeReport, package_root: Path) -> dict[str, Any]:
    face_dir = package_root / "img" / "face"
    blush1_path = face_dir / "default" / "default" / "blush1.png"
    face_pngs = sorted(face_dir.rglob("*.png"), key=lambda item: str(item).lower()) if face_dir.exists() else []
    blush_pngs = sorted(package_root.rglob("*blush*.png"), key=lambda item: str(item).lower())

    audit = {
        "package_root": str(package_root),
        "face_dir_exists": face_dir.exists(),
        "face_png_count": len(face_pngs),
        "face_png_samples": _relative_sample_paths(package_root, face_pngs),
        "blush_png_count": len(blush_pngs),
        "blush_png_samples": _relative_sample_paths(package_root, blush_pngs),
        "required_face_assets": [
            {
                "path": "img/face/default/default/blush1.png",
                "exists": blush1_path.exists(),
            }
        ],
    }
    report.observations["static_asset_audit"] = audit

    if not face_dir.exists():
        _add_issue(
            report,
            Issue(
                "warning",
                "face_asset_directory_missing",
                "asset_audit",
                "package does not contain img/face; AU/BeautySelector face layers may rely on embedded or missing assets",
            ),
        )

    if not blush1_path.exists():
        _add_issue(
            report,
            Issue(
                "warning",
                "face_blush_asset_not_packaged",
                "asset_audit",
                "expected face layer asset is not packaged: img/face/default/default/blush1.png",
            ),
        )

    return audit


def _check_required_mods(
    report: BrowserSmokeReport,
    profile: SmokeProfile,
    embedded_mods: list[EmbeddedModInfo],
) -> None:
    search_text = "\n".join(
        [json.dumps(asdict(info), ensure_ascii=False) for info in embedded_mods]
        + [message.get("text", "") for message in report.console_messages]
    ).lower()
    required_results: dict[str, bool] = {}

    for mod_name in profile.required_mod_names:
        found = mod_name.lower() in search_text
        required_results[mod_name] = found
        if not found:
            _add_issue(
                report,
                Issue(
                    severity="high",
                    kind="required_mod_not_observed",
                    source="profile",
                    message=f"required mod was not observed: {mod_name}",
                ),
            )

    report.observations["required_mods"] = required_results


def _page_state_script(global_names: tuple[str, ...]) -> str:
    return """
    (probeConfig) => {
      const globalNames = Array.isArray(probeConfig) ? probeConfig : (probeConfig.globalNames || []);
      const modNames = Array.isArray(probeConfig) ? [] : (probeConfig.modNames || []);
      const globals = {};
      for (const name of globalNames) {
        globals[name] = typeof window[name];
      }
      const modUtilsAvailable = Boolean(
        window.modUtils && typeof window.modUtils.getMod === 'function'
      );
      const modProbeResults = {};
      for (const name of modNames) {
        const result = {
          available: false,
          type: 'undefined',
          error: null,
          name: null,
          version: null,
        };
        try {
          if (!modUtilsAvailable) {
            result.error = 'window.modUtils.getMod unavailable';
          } else {
            const mod = window.modUtils.getMod(name);
            result.type = typeof mod;
            result.available = Boolean(mod);
            if (mod && typeof mod === 'object') {
              const info = mod.modInfo || mod.bootJson || mod.bootJsonCache || mod;
              if (info && typeof info === 'object') {
                result.name = info.name || info.modName || info.id || null;
                result.version = info.version || null;
              }
            }
          }
        } catch (error) {
          result.type = 'error';
          result.error = String(error && (error.message || error));
        }
        modProbeResults[name] = result;
      }
      return {
        title: document.title,
        readyState: document.readyState,
        bodyTextSample: (document.body && document.body.innerText || '').slice(0, 500),
        hasJQuery: typeof window.jQuery !== 'undefined',
        hasSugarCube: typeof window.SugarCube !== 'undefined',
        hasModDataValueZipList: Array.isArray(window.modDataValueZipList),
        modDataValueZipListLength: Array.isArray(window.modDataValueZipList)
          ? window.modDataValueZipList.length
          : null,
        globals,
        modProbes: {
          modUtilsAvailable,
          results: modProbeResults,
        },
      };
    }
    """


ENTER_GAME_LABELS: tuple[str, ...] = (
    "(1) 开始游戏！",
    "(1) 开始游戏!",
    "开始游戏！",
    "开始游戏!",
    "Start",
    "New Game",
    "Begin",
    "Play",
    "Enter Game",
    "Enter",
    "Next",
    "Continue",
    "Proceed",
    "Confirm",
    "开始",
    "开始游戏",
    "进入游戏",
    "新游戏",
    "下一步",
    "继续",
    "确认",
    "完成",
)


STARTUP_PASSAGES: frozenset[str] = frozenset({"start", "start2", "loading"})


MODAL_BLOCKER_SELECTORS: tuple[str, ...] = (
    "dialog[open]",
    ".swal2-container",
    ".swal2-popup",
    "[role='dialog']",
    "[aria-modal='true']",
    ".modal",
    ".popup",
    ".overlay",
)


BLOCKER_CONFIRM_LABELS: tuple[str, ...] = (
    "OK",
    "Ok",
    "Confirm",
    "Continue",
    "Close",
    "I agree",
    "Yes",
    "确定",
    "确认",
    "继续",
    "关闭",
    "同意",
    "是",
)


STARTUP_INTERACTION_MAX_STEPS = 45


STARTUP_CONSENT_LABELS: tuple[str, ...] = (
    "我确定我已年满十八岁",
    "我已阅读并理解上述说明",
    "I confirm I am at least 18",
    "I have read and understand",
)


STARTUP_CONFIRM_LABELS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            *BLOCKER_CONFIRM_LABELS,
            *ENTER_GAME_LABELS,
            "Enter Game",
            "Enter",
            "I understand",
            "I have read",
            "进入游戏",
            "开始游戏",
            "我已知晓",
            "我知道了",
        ]
    )
)


def _game_ready_script() -> str:
    return """
    () => {
      const bodyText = (document.body && document.body.innerText || '').trim();
      const sugarCube = window.SugarCube;
      const state = sugarCube && sugarCube.State;
      const engine = sugarCube && sugarCube.Engine;
      const story = sugarCube && sugarCube.Story;
      const passageElement = document.querySelector('.passage, [data-passage], #passages > div');
      const passage =
        (state && (state.passage || (state.active && state.active.title))) ||
        (passageElement && (passageElement.getAttribute('data-passage') || passageElement.id)) ||
        null;
      const loadingLike = /loading|please wait|加载|载入|初始化/i.test(bodyText) && bodyText.length < 1000;
      const interactiveElements = Array.from(
        document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"], .link-internal')
      ).filter((element) => Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length));

      const hasJQuery = typeof window.jQuery !== 'undefined';
      const hasSugarCube = typeof sugarCube !== 'undefined';
      const hasSugarCubeState = Boolean(state);
      const hasSugarCubeEngine = Boolean(engine);
      const hasSugarCubeStory = Boolean(story);
      const readyState = document.readyState;
      const ready = Boolean(
        hasJQuery &&
        hasSugarCube &&
        hasSugarCubeState &&
        hasSugarCubeEngine &&
        hasSugarCubeStory &&
        readyState !== 'loading' &&
        !loadingLike
      );

      return {
        ready,
        title: document.title,
        readyState,
        hasJQuery,
        hasSugarCube,
        hasSugarCubeState,
        hasSugarCubeEngine,
        hasSugarCubeStory,
        passage,
        passageElementId: passageElement ? passageElement.id || null : null,
        passageElementData: passageElement ? passageElement.getAttribute('data-passage') : null,
        bodyTextSample: bodyText.slice(0, 500),
        bodyTextLength: bodyText.length,
        loadingLike,
        interactiveElementCount: interactiveElements.length,
      };
    }
    """


def _enter_game_click_script() -> str:
    return """
    (labels) => {
      const normalizedLabels = labels.map((label) => String(label).toLowerCase());
      const isIgnoredChrome = (element) => Boolean(
        element && (
          element.id === 'ui-bar-toggle' ||
          element.closest('#ui-bar, #ui-bar-toggle, #story-caption, #menu, nav, header')
        )
      );
      const elements = Array.from(
        document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"], .link-internal')
      );
      const candidates = elements
        .filter((element) => Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length))
        .filter((element) => !isIgnoredChrome(element))
        .map((element) => {
          const text = (element.innerText || element.textContent || element.value || element.title || element.getAttribute('aria-label') || '').trim();
          return {
            element,
            text,
            tag: element.tagName,
            id: element.id || null,
            className: typeof element.className === 'string' ? element.className : null,
          };
        })
        .filter((candidate) => candidate.text.length > 0);

      const matched = candidates.find((candidate) => {
        const text = candidate.text.toLowerCase();
        return normalizedLabels.some((label) => text === label || text.includes(label));
      });

      if (!matched) {
        return {
          clicked: false,
          reason: 'no_candidate',
          candidates: candidates.slice(0, 20).map(({ text, tag, id, className }) => ({ text, tag, id, className })),
        };
      }

      matched.element.click();
      return {
        clicked: true,
        text: matched.text,
        tag: matched.tag,
        id: matched.id,
        className: matched.className,
      };
    }
    """


def _modal_blocker_script() -> str:
    return r"""
    (selectors) => {
      const visible = (element) => Boolean(
        element &&
        (element.offsetWidth || element.offsetHeight || element.getClientRects().length) &&
        window.getComputedStyle(element).visibility !== 'hidden' &&
        window.getComputedStyle(element).display !== 'none'
      );
      const simpleSelector = (element) => {
        if (!element) return null;
        if (element.id) return `${element.tagName.toLowerCase()}#${element.id}`;
        const classes = typeof element.className === 'string'
          ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).join('.')
          : '';
        return classes ? `${element.tagName.toLowerCase()}.${classes}` : element.tagName.toLowerCase();
      };
      const unique = [];
      const seen = new Set();
      for (const selector of selectors) {
        for (const element of Array.from(document.querySelectorAll(selector))) {
          if (seen.has(element) || !visible(element)) continue;
          seen.add(element);
          unique.push({ selector, element });
        }
      }
      const items = unique.slice(0, 10).map(({ selector, element }) => {
        const style = window.getComputedStyle(element);
        const text = (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim();
        const buttons = Array.from(
          element.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"]')
        )
          .filter(visible)
          .map((button) => (
            button.innerText || button.textContent || button.value || button.title || button.getAttribute('aria-label') || ''
          ).replace(/\s+/g, ' ').trim())
          .filter(Boolean)
          .slice(0, 12);
        return {
          selector,
          simpleSelector: simpleSelector(element),
          tag: element.tagName,
          id: element.id || null,
          className: typeof element.className === 'string' ? element.className : null,
          role: element.getAttribute('role'),
          ariaModal: element.getAttribute('aria-modal'),
          zIndex: style.zIndex,
          textSample: text.slice(0, 500),
          buttonTexts: buttons,
        };
      });
      return { count: items.length, items };
    }
    """


def _dismiss_blocker_script() -> str:
    return r"""
    (options) => {
      const labels = options.labels.map((label) => String(label).trim().toLowerCase());
      const selectors = options.selectors;
      const allowGlobal = Boolean(options.allowGlobal);
      const visible = (element) => Boolean(
        element &&
        (element.offsetWidth || element.offsetHeight || element.getClientRects().length) &&
        window.getComputedStyle(element).visibility !== 'hidden' &&
        window.getComputedStyle(element).display !== 'none'
      );
      const textOf = (element) => (
        element.innerText || element.textContent || element.value || element.title || element.getAttribute('aria-label') || ''
      ).replace(/\s+/g, ' ').trim();
      const matches = (text) => {
        const normalized = text.trim().toLowerCase();
        return labels.some((label) => normalized === label || normalized.includes(label));
      };
      const roots = [];
      const seenRoots = new Set();
      for (const selector of selectors) {
        for (const element of Array.from(document.querySelectorAll(selector))) {
          if (seenRoots.has(element) || !visible(element)) continue;
          seenRoots.add(element);
          roots.push({ selector, element });
        }
      }
      if (allowGlobal && roots.length === 0) {
        roots.push({ selector: 'document', element: document });
      }
      const candidates = [];
      for (const root of roots) {
        for (const element of Array.from(
          root.element.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"]')
        )) {
          if (!visible(element)) continue;
          const text = textOf(element);
          if (!text) continue;
          candidates.push({ rootSelector: root.selector, element, text });
        }
      }
      const matched = candidates.find((candidate) => matches(candidate.text));
      if (!matched) {
        return {
          clicked: false,
          reason: candidates.length ? 'no_matching_label' : 'no_candidate',
          blockerCount: roots.length,
          candidates: candidates.slice(0, 20).map(({ rootSelector, text }) => ({ rootSelector, text })),
        };
      }
      matched.element.click();
      return {
        clicked: true,
        text: matched.text,
        rootSelector: matched.rootSelector,
        blockerCount: roots.length,
      };
    }
    """


def _startup_gate_status_script() -> str:
    return r"""
    (options) => {
      const modalSelectors = options.modalSelectors || [];
      const consentLabels = (options.consentLabels || []).map((label) => String(label).trim()).filter(Boolean);
      const visible = (element) => Boolean(
        element &&
        (element.offsetWidth || element.offsetHeight || element.getClientRects().length) &&
        window.getComputedStyle(element).visibility !== 'hidden' &&
        window.getComputedStyle(element).display !== 'none'
      );
      const textOf = (element) => (
        element.innerText || element.textContent || element.value || element.title || element.getAttribute('aria-label') || ''
      ).replace(/\s+/g, ' ').trim();
      const bodyText = textOf(document.body || document.documentElement);
      const consentLabel = consentLabels.find((label) => bodyText.includes(label));
      if (consentLabel) {
        return {
          has_gate: true,
          reason: 'consent_label_visible',
          consent_label: consentLabel,
          text_sample: bodyText.slice(0, 500),
        };
      }

      const swal = Array.from(document.querySelectorAll('.swal2-container, .swal2-popup')).find(visible);
      if (swal) {
        const text = textOf(swal);
        if (/Custom-Spellbook|Spellbook|密码|password/i.test(text)) {
          return {
            has_gate: true,
            reason: 'custom_spellbook_sweetalert',
            text_sample: text.slice(0, 500),
          };
        }
      }

      for (const selector of modalSelectors) {
        for (const element of Array.from(document.querySelectorAll(selector))) {
          if (!visible(element)) continue;
          const text = textOf(element);
          if (consentLabels.some((label) => text.includes(label)) || /年满十八岁|我已阅读|进入游戏|我已知晓/i.test(text)) {
            return {
              has_gate: true,
              reason: 'startup_modal_visible',
              selector,
              text_sample: text.slice(0, 500),
            };
          }
        }
      }

      return {
        has_gate: false,
        reason: 'no_startup_gate',
        text_sample: bodyText.slice(0, 500),
      };
    }
    """


def _startup_interaction_script() -> str:
    return r"""
    (options) => {
      const password = options.password || '';
      const modalSelectors = options.modalSelectors || [];
      const confirmLabels = (options.confirmLabels || []).map((label) => String(label).trim().toLowerCase());
      const consentLabels = (options.consentLabels || []).map((label) => String(label).trim());
      const visible = (element) => Boolean(
        element &&
        (element.offsetWidth || element.offsetHeight || element.getClientRects().length) &&
        window.getComputedStyle(element).visibility !== 'hidden' &&
        window.getComputedStyle(element).display !== 'none'
      );
      const textOf = (element) => (
        element.innerText || element.textContent || element.value || element.title || element.getAttribute('aria-label') || ''
      ).replace(/\s+/g, ' ').trim();
      const bodyText = textOf(document.body || document.documentElement);
      const simpleSelector = (element) => {
        if (!element) return null;
        if (element.id) return `${element.tagName.toLowerCase()}#${element.id}`;
        const classes = typeof element.className === 'string'
          ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).join('.')
          : '';
        return classes ? `${element.tagName.toLowerCase()}.${classes}` : element.tagName.toLowerCase();
      };
      const isIgnoredChrome = (element) => Boolean(
        element && (
          element.id === 'ui-bar-toggle' ||
          element.closest('#ui-bar, #ui-bar-toggle, #story-caption, #menu, nav, header')
        )
      );
      const matchesLabel = (text, labels = confirmLabels) => {
        const normalized = String(text || '').trim().toLowerCase();
        return labels.some((label) => normalized === label || normalized.includes(label));
      };
      const controlsIn = (root) => Array.from(
        root.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"], .link-internal')
      )
        .filter((element) => visible(element) && !isIgnoredChrome(element))
        .map((element) => ({
          element,
          text: textOf(element),
          tag: element.tagName,
          id: element.id || null,
          className: typeof element.className === 'string' ? element.className : null,
        }))
        .filter((candidate) => candidate.text.length > 0);
      const clickMatchingControl = (root, labels = confirmLabels) => {
        const candidates = controlsIn(root);
        const matched = candidates.find((candidate) => matchesLabel(candidate.text, labels));
        if (!matched) {
          return {
            clicked: false,
            reason: candidates.length ? 'no_matching_label' : 'no_candidate',
            candidates: candidates.slice(0, 20).map(({ text, tag, id, className }) => ({ text, tag, id, className })),
          };
        }
        if ('disabled' in matched.element && matched.element.disabled) {
          matched.element.disabled = false;
          matched.element.removeAttribute('disabled');
        }
        matched.element.click();
        return {
          clicked: true,
          text: matched.text,
          tag: matched.tag,
          id: matched.id,
          className: matched.className,
        };
      };
      const firstVisibleModalWithText = (needle) => {
        for (const selector of modalSelectors) {
          const root = Array.from(document.querySelectorAll(selector))
            .find((element) => visible(element) && textOf(element).includes(needle));
          if (root) return root;
        }
        return document;
      };
      const setCheckboxChecked = (checkbox, labelElement = null) => {
        if (!checkbox) return false;
        if (!checkbox.checked) {
          try {
            checkbox.click();
          } catch (_error) {
            // Hidden custom-styled checkboxes can throw on click; setting checked still exercises listeners below.
          }
        }
        if (!checkbox.checked && labelElement) {
          try {
            labelElement.click();
          } catch (_error) {
            // Ignore click failures and fall back to direct property updates.
          }
        }
        if (!checkbox.checked) checkbox.checked = true;
        checkbox.setAttribute('checked', 'checked');
        checkbox.dispatchEvent(new Event('input', { bubbles: true }));
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        checkbox.dispatchEvent(new Event('click', { bubbles: true }));
        return Boolean(checkbox.checked);
      };

      const swal = Array.from(document.querySelectorAll('.swal2-container, .swal2-popup')).find(visible);
      if (swal) {
        const swalText = textOf(swal);
        const passwordInput = swal.querySelector('input.swal2-input, input[type="password"], input[type="text"], textarea');
        if (passwordInput && password && /Custom-Spellbook|Spellbook|密码|password/i.test(swalText)) {
          passwordInput.focus();
          passwordInput.value = password;
          passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
          passwordInput.dispatchEvent(new Event('change', { bubbles: true }));
          const confirmButton = swal.querySelector('.swal2-confirm') || swal.querySelector('button, input[type="button"], input[type="submit"], [role="button"]');
          const click = confirmButton && visible(confirmButton)
            ? (() => {
                const text = textOf(confirmButton) || 'swal2-confirm';
                confirmButton.click();
                return { clicked: true, text, tag: confirmButton.tagName, id: confirmButton.id || null };
              })()
            : clickMatchingControl(swal);
          return {
            action: 'fill_custom_spellbook_password',
            clicked: Boolean(click.clicked),
            password_supplied: true,
            button_text: click.text || null,
            root_selector: simpleSelector(swal),
            text_sample: swalText.slice(0, 500),
            click,
          };
        }

        const click = clickMatchingControl(swal);
        if (click.clicked) {
          return {
            action: 'dismiss_sweetalert',
            clicked: true,
            button_text: click.text || null,
            root_selector: simpleSelector(swal),
            text_sample: swalText.slice(0, 500),
            click,
          };
        }
      }

      for (const consentLabel of consentLabels) {
        if (!consentLabel || !bodyText.includes(consentLabel)) continue;
        const gateRoot = firstVisibleModalWithText(consentLabel);
        const rootText = textOf(gateRoot === document ? document.body || document.documentElement : gateRoot);
        const labels = Array.from(gateRoot.querySelectorAll('label'))
          .filter((label) => visible(label) || textOf(label).includes(consentLabel));
        const labelElement = labels.find((label) => textOf(label).includes(consentLabel));
        let checkbox = null;
        if (labelElement) {
          checkbox = labelElement.control || labelElement.querySelector('input[type="checkbox"]');
          const forId = labelElement.getAttribute('for');
          if (!checkbox && forId) checkbox = document.getElementById(forId);
        }
        if (!checkbox) {
          const checkboxes = Array.from(gateRoot.querySelectorAll('input[type="checkbox"]'));
          checkbox = checkboxes.find((input) => {
            const root = input.closest('label, p, div, li, section, article, form, [role="dialog"], dialog') || input.parentElement;
            return (root && textOf(root).includes(consentLabel)) || rootText.includes(consentLabel);
          }) || checkboxes[0] || Array.from(document.querySelectorAll('input[type="checkbox"]'))[0] || null;
        }
        const checkboxChecked = setCheckboxChecked(checkbox, labelElement);

        let click = clickMatchingControl(gateRoot, confirmLabels);
        if (!click.clicked && gateRoot !== document) click = clickMatchingControl(document, confirmLabels);
        return {
          action: 'accept_consent_gate',
          clicked: Boolean(click.clicked),
          checkbox_checked: checkboxChecked,
          consent_label: consentLabel,
          button_text: click.text || null,
          root_selector: simpleSelector(gateRoot === document ? document.body || document.documentElement : gateRoot),
          text_sample: bodyText.slice(0, 500),
          click,
        };
      }

      const modalRoots = [];
      const seenRoots = new Set();
      for (const selector of modalSelectors) {
        for (const element of Array.from(document.querySelectorAll(selector))) {
          if (seenRoots.has(element) || !visible(element)) continue;
          seenRoots.add(element);
          modalRoots.push({ selector, element });
        }
      }
      for (const root of modalRoots) {
        const click = clickMatchingControl(root.element);
        if (click.clicked) {
          return {
            action: 'dismiss_modal',
            clicked: true,
            button_text: click.text || null,
            root_selector: root.selector,
            simple_selector: simpleSelector(root.element),
            text_sample: textOf(root.element).slice(0, 500),
            click,
          };
        }
      }

      const pageClick = clickMatchingControl(document, confirmLabels);
      if (pageClick.clicked) {
        return {
          action: 'click_startup_control',
          clicked: true,
          button_text: pageClick.text || null,
          text_sample: bodyText.slice(0, 500),
          click: pageClick,
        };
      }

      return {
        action: 'no_action',
        clicked: false,
        reason: pageClick.reason || 'no_candidate',
        text_sample: bodyText.slice(0, 500),
        candidates: pageClick.candidates || [],
      };
    }
    """


def _looks_playable(game_ready: dict[str, Any]) -> bool:
    passage = str(game_ready.get("passage") or "").strip().lower()
    if not game_ready.get("ready") or game_ready.get("loadingLike"):
        return False
    if passage in STARTUP_PASSAGES:
        return False
    if passage:
        return True
    return bool(game_ready.get("interactiveElementCount", 0) > 0 and game_ready.get("bodyTextLength", 0) > 500)


def _add_game_ready_issues(report: BrowserSmokeReport, game_ready: dict[str, Any]) -> None:
    if not game_ready.get("hasSugarCube"):
        _add_issue(
            report,
            Issue("high", "game_runtime_missing", "game_ready", "window.SugarCube was not available after startup"),
        )
    elif game_ready.get("loadingLike"):
        _add_issue(
            report,
            Issue("high", "game_stuck_loading", "game_ready", "page still looked like a loading screen after startup"),
        )
    elif not game_ready.get("ready"):
        _add_issue(
            report,
            Issue("warning", "game_ready_incomplete", "game_ready", "game runtime was observed but not fully ready"),
        )

    if not game_ready.get("hasJQuery"):
        _add_issue(
            report,
            Issue("warning", "jquery_missing", "game_ready", "window.jQuery was not available after startup"),
        )


def _record_game_ready(report: BrowserSmokeReport, page: Any, *, add_issues: bool = True) -> dict[str, Any]:
    game_ready = page.evaluate(_game_ready_script())
    report.observations["game_ready"] = game_ready

    if add_issues:
        _add_game_ready_issues(report, game_ready)

    return game_ready


def _startup_instability_triggers(
    report: BrowserSmokeReport,
    navigation_events: list[dict[str, Any]],
    extra_messages: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Summarize navigation/context symptoms that justify one stable re-read."""
    issue_text = "\n".join([issue.message for issue in report.issues] + list(extra_messages)).lower()
    context_destroyed = "execution context was destroyed" in issue_text or "most likely because of a navigation" in issue_text
    document_abort = any(
        event.get("type") == "document_request_failed"
        and (
            "err_aborted" in str(event.get("failure") or "").lower()
            or "aborted" in str(event.get("failure") or "").lower()
        )
        for event in navigation_events
    )
    main_frame_navigations = [
        event for event in navigation_events if event.get("type") == "framenavigated" and event.get("main_frame")
    ]
    extra_navigation = len(main_frame_navigations) > 1
    return {
        "context_destroyed": context_destroyed,
        "document_abort": document_abort,
        "extra_navigation": extra_navigation,
        "main_frame_navigation_count": len(main_frame_navigations),
        "should_retry": context_destroyed or document_abort or extra_navigation,
    }


def _startup_diagnostic_console_tail(report: BrowserSmokeReport, limit: int = 50) -> list[str]:
    keywords = ("modloader", "maplebirch", "custom-spellbook", "cheat extended", "sugarcube")
    matches: list[str] = []
    for message in report.console_messages:
        text = str(message.get("text") or "")
        if any(keyword in text.lower() for keyword in keywords):
            matches.append(f"[{message.get('type', 'log')}] {text}")
    return matches[-limit:]


def _run_startup_interactions(report: BrowserSmokeReport, page: Any, profile: SmokeProfile) -> dict[str, Any]:
    """Replay the real startup gates observed in a clean browser session."""
    result: dict[str, Any] = {
        "attempted": True,
        "success": False,
        "max_steps": STARTUP_INTERACTION_MAX_STEPS,
        "steps": [],
    }
    options = {
        "password": profile.dialog_password,
        "modalSelectors": list(MODAL_BLOCKER_SELECTORS),
        "confirmLabels": list(STARTUP_CONFIRM_LABELS),
        "consentLabels": list(STARTUP_CONSENT_LABELS),
    }

    try:
        consecutive_no_action = 0
        state_after: dict[str, Any] = {}
        for step_index in range(STARTUP_INTERACTION_MAX_STEPS):
            state_before = page.evaluate(_game_ready_script())
            gate_before = page.evaluate(_startup_gate_status_script(), options)
            step: dict[str, Any] = {
                "step": step_index + 1,
                "passage_before": state_before.get("passage"),
                "ready_before": state_before.get("ready"),
                "playable_before": _looks_playable(state_before),
                "gate_before": gate_before,
            }
            if _looks_playable(state_before) and not gate_before.get("has_gate"):
                result.update(
                    {
                        "success": True,
                        "reason": "already_playable_no_startup_gate",
                        "final_passage": state_before.get("passage"),
                        "state_after": state_before,
                        "startup_gate_after": gate_before,
                    }
                )
                break

            action = page.evaluate(_startup_interaction_script(), options)
            if not isinstance(action, dict):
                action = {"action": "unexpected_result", "clicked": False, "raw": action}
            step["action"] = action
            result["steps"].append(step)

            if not action.get("clicked") and action.get("action") == "no_action":
                consecutive_no_action += 1
                step["consecutive_no_action"] = consecutive_no_action
                page.wait_for_timeout(1_500)
            else:
                consecutive_no_action = 0
                step["consecutive_no_action"] = consecutive_no_action
                page.wait_for_timeout(1_000)

            state_after = page.evaluate(_game_ready_script())
            gate_after = page.evaluate(_startup_gate_status_script(), options)
            step["passage_after"] = state_after.get("passage")
            step["ready_after"] = state_after.get("ready")
            step["playable_after"] = _looks_playable(state_after)
            step["gate_after"] = gate_after
            if _looks_playable(state_after) and not gate_after.get("has_gate"):
                result.update(
                    {
                        "success": True,
                        "reason": "playable_state_observed_no_startup_gate",
                        "final_passage": state_after.get("passage"),
                        "state_after": state_after,
                        "startup_gate_after": gate_after,
                    }
                )
                break
        else:
            result["reason"] = "max_steps_reached"

        if not result.get("success"):
            final_state = state_after or page.evaluate(_game_ready_script())
            result.setdefault("reason", "not_playable_after_startup_interactions")
            result["final_passage"] = final_state.get("passage")
            result["state_after"] = final_state
            result["startup_gate_after"] = page.evaluate(_startup_gate_status_script(), options)
            result["last_visible_text_sample"] = final_state.get("bodyTextSample")
            result["last_visible_text_length"] = final_state.get("bodyTextLength")
            result["recent_modloader_logs"] = _startup_diagnostic_console_tail(report)
    except Exception as exc:  # noqa: BLE001 - keep CI report artifacts even if the page is mid-navigation.
        result["error"] = str(exc)
        result.setdefault("reason", "startup_interaction_error")
        _add_issue(report, Issue("warning", "startup_interaction_error", "startup_interactions", str(exc)))

    steps = result.get("steps", [])
    result["step_count"] = len(steps)
    result["clicked_count"] = sum(1 for step in steps if (step.get("action") or {}).get("clicked"))
    result["password_supplied"] = any((step.get("action") or {}).get("password_supplied") for step in steps)
    result["consent_accepted_count"] = sum(
        1 for step in steps if (step.get("action") or {}).get("action") == "accept_consent_gate"
    )
    result["last_action"] = (steps[-1].get("action") or {}).get("action") if steps else None
    report.observations["startup_interactions"] = result
    return result


def _attempt_enter_game(report: BrowserSmokeReport, page: Any) -> None:
    issue_start = len(report.issues)
    enter_result: dict[str, Any] = {
        "attempted": False,
        "success": False,
        "steps": [],
        "new_high_risk_errors": [],
    }

    try:
        options = {
            "modalSelectors": list(MODAL_BLOCKER_SELECTORS),
            "consentLabels": list(STARTUP_CONSENT_LABELS),
        }
        before = page.evaluate(_game_ready_script())
        gate_before = page.evaluate(_startup_gate_status_script(), options)
        enter_result["passage_before"] = before.get("passage")
        enter_result["state_before"] = before
        enter_result["startup_gate_before"] = gate_before

        if _looks_playable(before) and not gate_before.get("has_gate"):
            enter_result.update(
                {
                    "success": True,
                    "reason": "already_playable_no_startup_gate",
                    "passage_after": before.get("passage"),
                    "state_after": before,
                }
            )
            report.observations["enter_game"] = enter_result
            return

        if not before.get("ready"):
            enter_result["reason"] = "game_not_ready"
            report.observations["enter_game"] = enter_result
            _add_issue(
                report,
                Issue("warning", "enter_game_not_attempted", "enter_game", "game was not ready enough to attempt entry"),
            )
            return

        enter_result["attempted"] = True
        after = before
        for _ in range(5):
            step = page.evaluate(_enter_game_click_script(), list(ENTER_GAME_LABELS))
            enter_result["steps"].append(step)
            if not step.get("clicked"):
                enter_result["reason"] = step.get("reason", "no_candidate")
                break

            page.wait_for_timeout(1_000)
            after = page.evaluate(_game_ready_script())
            gate_after = page.evaluate(_startup_gate_status_script(), options)
            step["passage_after"] = after.get("passage")
            step["startup_gate_after"] = gate_after
            if _looks_playable(after) and not gate_after.get("has_gate"):
                enter_result["success"] = True
                enter_result["reason"] = "playable_state_observed_no_startup_gate"
                break

        enter_result["passage_after"] = after.get("passage")
        enter_result["state_after"] = after
        enter_result["startup_gate_after"] = page.evaluate(_startup_gate_status_script(), options)
    except Exception as exc:  # noqa: BLE001 - CI report should capture Playwright/runtime setup failures.
        enter_result["error"] = str(exc)
        _add_issue(report, Issue("warning", "enter_game_error", "enter_game", str(exc)))

    new_high = [issue for issue in report.issues[issue_start:] if issue.severity == "high"]
    enter_result["new_high_risk_errors"] = [asdict(issue) for issue in new_high]
    if new_high:
        enter_result["success"] = False

    if not enter_result.get("success"):
        _add_issue(
            report,
            Issue(
                "warning",
                "enter_game_not_confirmed",
                "enter_game",
                f"could not confirm playable passage; reason={enter_result.get('reason', 'unknown')}",
            ),
        )

    report.observations["enter_game"] = enter_result


def _candidate_browser_paths() -> list[Path]:
    candidates: list[Path] = []
    if configured := os.environ.get("DOLX_BROWSER_EXECUTABLE"):
        candidates.append(Path(configured))

    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    for root, relative in (
        (local_app_data, r"Microsoft\Edge\Application\msedge.exe"),
        (program_files_x86, r"Microsoft\Edge\Application\msedge.exe"),
        (program_files, r"Microsoft\Edge\Application\msedge.exe"),
        (local_app_data, r"Google\Chrome\Application\chrome.exe"),
        (program_files, r"Google\Chrome\Application\chrome.exe"),
        (program_files_x86, r"Google\Chrome\Application\chrome.exe"),
    ):
        if root:
            candidates.append(Path(root) / relative)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _launch_chromium_browser(
    playwright: Any,
    report: BrowserSmokeReport,
    playwright_error_type: type[BaseException],
) -> Any | None:
    try:
        browser = playwright.chromium.launch(headless=True)
        report.observations["browser_executable"] = {"source": "playwright-bundled"}
        return browser
    except playwright_error_type as exc:
        bundled_error = str(exc)

    fallback_errors: list[dict[str, str]] = []
    for channel in ("msedge", "chrome"):
        try:
            browser = playwright.chromium.launch(headless=True, channel=channel)
            report.observations["browser_executable"] = {
                "source": "system-channel",
                "channel": channel,
                "bundled_error": bundled_error,
            }
            _add_issue(
                report,
                Issue(
                    "warning",
                    "playwright_browser_fallback",
                    "runner",
                    f"Playwright bundled Chromium unavailable; using system browser channel {channel!r}",
                ),
            )
            return browser
        except playwright_error_type as exc:
            fallback_errors.append({"channel": channel, "error": str(exc)})

    for candidate in _candidate_browser_paths():
        if not candidate.exists():
            continue
        try:
            browser = playwright.chromium.launch(headless=True, executable_path=str(candidate))
            report.observations["browser_executable"] = {
                "source": "system-path",
                "path": str(candidate),
                "bundled_error": bundled_error,
            }
            _add_issue(
                report,
                Issue(
                    "warning",
                    "playwright_browser_fallback",
                    "runner",
                    f"Playwright bundled Chromium unavailable; using system browser at {candidate}",
                ),
            )
            return browser
        except playwright_error_type as exc:
            fallback_errors.append({"path": str(candidate), "error": str(exc)})

    report.observations["browser_executable"] = {
        "source": None,
        "bundled_error": bundled_error,
        "fallback_errors": fallback_errors,
    }
    _add_issue(
        report,
        Issue(
            "high",
            "playwright_browser_missing",
            "runner",
            "Playwright is installed but no bundled or system Chromium browser could be launched",
        ),
    )
    return None


def _run_playwright(
    report: BrowserSmokeReport,
    profile: SmokeProfile,
    url: str,
    timeout_ms: int,
    settle_ms: int,
    screenshot_dir: Path | None = None,
) -> None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        _add_issue(
            report,
            Issue(
                severity="high",
                kind="playwright_missing",
                source="runner",
                message=f"Playwright is not installed: {exc}",
            ),
        )
        return

    page_errors: list[str] = []
    dialogs: list[dict[str, Any]] = []
    browser_popups: list[dict[str, Any]] = []
    navigation_events: list[dict[str, Any]] = []
    pageerror_context: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = _launch_chromium_browser(playwright, report, PlaywrightError)
        if browser is None:
            return
        context = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = context.new_page()
        seen_popup_ids: set[int] = {id(page)}

        def safe_ready_state() -> str | None:
            try:
                return page.evaluate("() => document.readyState")
            except PlaywrightError:
                return None

        def safe_page_state(global_names: tuple[str, ...], mod_names: tuple[str, ...] = ()) -> dict[str, Any]:
            try:
                return page.evaluate(
                    _page_state_script(global_names),
                    {"globalNames": list(global_names), "modNames": list(mod_names)},
                )
            except PlaywrightError as exc:
                return {"error": str(exc), "url": page.url}

        def record_browser_popup(popup: Any, source: str) -> None:
            popup_id = id(popup)
            if popup_id in seen_popup_ids:
                return
            seen_popup_ids.add(popup_id)
            entry: dict[str, Any] = {
                "source": source,
                "url": None,
                "title": None,
                "body_text_sample": None,
                "closed": None,
            }
            try:
                entry["url"] = popup.url
                entry["closed"] = popup.is_closed()
                if not entry["closed"]:
                    with contextlib.suppress(PlaywrightTimeoutError, PlaywrightError):
                        popup.wait_for_load_state("domcontentloaded", timeout=3_000)
                    entry["url"] = popup.url
                    entry["closed"] = popup.is_closed()
                    if not entry["closed"]:
                        with contextlib.suppress(PlaywrightError):
                            entry["title"] = popup.title()
                        with contextlib.suppress(PlaywrightError):
                            entry["body_text_sample"] = popup.evaluate(
                                "(document.body && document.body.innerText || '').slice(0, 500)"
                            )
            except PlaywrightError as exc:
                entry["error"] = str(exc)
            browser_popups.append(entry)

        def observe_modal_blockers(stage: str) -> dict[str, Any]:
            try:
                result = page.evaluate(_modal_blocker_script(), list(MODAL_BLOCKER_SELECTORS))
                if not isinstance(result, dict):
                    result = {"count": 0, "items": [], "raw": result}
                result["stage"] = stage
                return result
            except PlaywrightError as exc:
                entry = {"stage": stage, "count": None, "items": [], "error": str(exc)}
                _add_issue(report, Issue("warning", "modal_blocker_probe_failed", "runner", f"{stage}: {exc}"))
                return entry

        def dismiss_modal_blockers(initial_blockers: dict[str, Any]) -> dict[str, Any]:
            dismissal: dict[str, Any] = {
                "initial_count": initial_blockers.get("count"),
                "final_count": initial_blockers.get("count"),
                "attempts": [],
            }
            blockers_before = initial_blockers
            for attempt_index in range(3):
                if not blockers_before.get("count"):
                    break

                step: dict[str, Any] = {
                    "attempt": attempt_index + 1,
                    "blockers_before": blockers_before,
                }
                try:
                    click = page.evaluate(
                        _dismiss_blocker_script(),
                        {
                            "labels": list(BLOCKER_CONFIRM_LABELS),
                            "selectors": list(MODAL_BLOCKER_SELECTORS),
                            "allowGlobal": False,
                        },
                    )
                    if not isinstance(click, dict):
                        click = {"clicked": False, "reason": "unexpected_result", "raw": click}
                except PlaywrightError as exc:
                    click = {"clicked": False, "reason": "dismiss_error", "error": str(exc)}
                    _add_issue(report, Issue("warning", "modal_blocker_dismiss_failed", "runner", str(exc)))

                step["click"] = click
                if not click.get("clicked"):
                    dismissal["attempts"].append(step)
                    break

                page.wait_for_timeout(1_000)
                blockers_after = observe_modal_blockers(f"after_dismissal_attempt_{attempt_index + 1}")
                step["blockers_after"] = blockers_after
                game_ready_after: dict[str, Any] = {}
                with contextlib.suppress(PlaywrightError):
                    game_ready_after = page.evaluate(_game_ready_script())
                    step["game_ready_after"] = game_ready_after
                dismissal["attempts"].append(step)
                blockers_before = blockers_after
                dismissal["final_count"] = blockers_after.get("count")
                if game_ready_after.get("ready") or _looks_playable(game_ready_after):
                    break

            dismissal["clicked_count"] = sum(
                1 for step in dismissal["attempts"] if (step.get("click") or {}).get("clicked")
            )
            dismissal["clicked"] = dismissal["clicked_count"] > 0
            return dismissal

        def on_dialog(dialog: Any) -> None:
            default_value = getattr(dialog, "default_value", None)
            if callable(default_value):
                default_value = default_value()
            message = str(dialog.message or "")
            entry = {
                "type": dialog.type,
                "message": message,
                "default_value": default_value,
                "accepted": True,
                "password_supplied": False,
            }
            dialog_issue = classify_message("browser_dialog", message)
            if dialog_issue.severity == "high":
                _add_issue(report, dialog_issue)
            try:
                if dialog.type == "prompt" and profile.dialog_password is not None:
                    dialog.accept(profile.dialog_password)
                    entry["password_supplied"] = True
                else:
                    dialog.accept()
            except PlaywrightError as exc:
                entry["accepted"] = False
                entry["error"] = str(exc)
                _add_issue(report, Issue("high", "dialog_handling_failed", "runner", str(exc)))
            dialogs.append(entry)

        def on_console(message: Any) -> None:
            location = message.location or {}
            text = str(message.text or "")
            url = location.get("url") if isinstance(location, dict) else None
            classified_text = f"{url} {text}" if url and "Failed to load resource" in text else text
            entry = {
                "type": message.type,
                "text": text,
                "location": location,
            }
            report.console_messages.append(entry)
            if message.type in {"error", "warning"}:
                source = "console.error" if message.type == "error" else "console.warning"
                issue = classify_message(source, classified_text)
                _add_issue(report, issue, location=location)

        def on_page_error(error: Any) -> None:
            text = str(error)
            stack = str(getattr(error, "stack", "") or "")
            context_entry = {
                "message": text,
                "stack": stack or None,
                "url": page.url,
                "ready_state": safe_ready_state(),
                "recent_navigation_events": navigation_events[-5:],
            }
            pageerror_context.append(context_entry)
            page_errors.append(text)
            _add_issue(report, classify_message("pageerror", text))

        def on_frame_navigated(frame: Any) -> None:
            navigation_events.append(
                {
                    "type": "framenavigated",
                    "url": frame.url,
                    "name": frame.name,
                    "main_frame": frame == page.main_frame,
                }
            )

        def on_request_failed(request: Any) -> None:
            failure = request.failure or "request failed"
            entry = {
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "failure": failure,
            }
            report.network_failures.append(entry)
            if request.resource_type == "document":
                navigation_events.append(
                    {
                        "type": "document_request_failed",
                        "url": request.url,
                        "method": request.method,
                        "failure": failure,
                        "is_navigation_request": request.is_navigation_request(),
                    }
                )
            issue = classify_message("requestfailed", f"{request.url} {failure}")
            _add_issue(report, issue, url=request.url)

        def on_response(response: Any) -> None:
            if response.status < 400:
                return
            entry = {
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text,
            }
            report.network_failures.append(entry)
            issue = classify_message("http_error", f"{response.url} HTTP {response.status}")
            _add_issue(report, issue, url=response.url)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("framenavigated", on_frame_navigated)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)
        page.on("dialog", on_dialog)
        page.on("popup", lambda popup: record_browser_popup(popup, "page.popup"))
        context.on("page", lambda new_page: record_browser_popup(new_page, "context.page"))
        report.observations["dialog_password_configured"] = profile.dialog_password is not None
        global_names = tuple(
            dict.fromkeys([*profile.required_globals, *profile.warning_globals, *profile.diagnostic_globals])
        )
        mod_probe_names = tuple(profile.diagnostic_mod_names)

        navigation_ok = False
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            navigation_ok = True
            with contextlib.suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15_000))
            page.wait_for_timeout(settle_ms)
        except PlaywrightTimeoutError as exc:
            _add_issue(
                report,
                Issue("high", "navigation_timeout", "runner", f"navigation timed out: {exc}"),
            )
        except PlaywrightError as exc:
            _add_issue(report, Issue("high", "browser_navigation_error", "runner", str(exc)))

        try:
            _run_startup_interactions(report, page, profile)
        except PlaywrightError as exc:
            _add_issue(report, Issue("warning", "startup_interaction_check_error", "runner", str(exc)))

        try:
            page_state = safe_page_state(global_names, mod_probe_names)
            report.observations["page_state"] = page_state
            if "error" in page_state:
                raise PlaywrightError(page_state["error"])
            global_types = page_state.get("globals", {}) or {}
            report.observations["runtime_globals"] = {
                global_name: global_types.get(global_name) for global_name in profile.diagnostic_globals
            }
            report.observations["runtime_mod_probes"] = page_state.get("modProbes", {}) or {}
            for global_name, global_type in global_types.items():
                if global_type == "function":
                    continue
                if global_name in profile.required_globals:
                    _add_issue(
                        report,
                        Issue(
                            "high",
                            "required_global_missing",
                            "profile",
                            f"window.{global_name} expected function, got {global_type}",
                        ),
                    )
                elif global_name in profile.warning_globals:
                    _add_issue(
                        report,
                        Issue(
                            "warning",
                            "warning_global_missing",
                            "profile",
                            f"window.{global_name} expected function when reachable, got {global_type}",
                        ),
                    )
        except PlaywrightError as exc:
            _add_issue(report, Issue("high", "page_state_error", "runner", str(exc)))

        report.observations["dialogs"] = dialogs
        page_state = report.observations.get("page_state", {})
        report.observations["browser_boot"] = {
            "navigation_ok": navigation_ok,
            "served_url": url,
            "ready_state": page_state.get("readyState"),
            "has_jquery": page_state.get("hasJQuery"),
            "has_sugarcube": page_state.get("hasSugarCube"),
            "has_mod_data_value_zip_list": page_state.get("hasModDataValueZipList"),
            "mod_data_value_zip_list_length": page_state.get("modDataValueZipListLength"),
            "dialog_count": len(dialogs),
            "popup_count": len(browser_popups),
            "console_message_count": len(report.console_messages),
            "network_failure_count": len(report.network_failures),
        }

        blockers_before_ready = observe_modal_blockers("before_game_ready")
        report.observations["modal_blockers_before_ready"] = blockers_before_ready
        report.observations["blocker_dismissal"] = dismiss_modal_blockers(blockers_before_ready)

        stability_retry: dict[str, Any] = {
            "attempted": False,
            "trigger": {},
            "initial_ready": None,
            "initial_has_sugarcube": None,
        }
        initial_game_ready: dict[str, Any] | None = None
        try:
            initial_game_ready = _record_game_ready(report, page, add_issues=False)
            stability_retry["initial_ready"] = initial_game_ready.get("ready")
            stability_retry["initial_has_sugarcube"] = initial_game_ready.get("hasSugarCube")
            trigger_messages: tuple[str, ...] = ()
        except PlaywrightError as exc:
            trigger_messages = (str(exc),)
            stability_retry["initial_error"] = str(exc)

        stability_retry["trigger"] = _startup_instability_triggers(
            report,
            navigation_events,
            extra_messages=trigger_messages,
        )
        if (initial_game_ready is None or not initial_game_ready.get("ready")) and stability_retry["trigger"].get(
            "should_retry"
        ):
            stability_retry["attempted"] = True
            try:
                page.wait_for_timeout(2_000)
                with contextlib.suppress(PlaywrightTimeoutError):
                    page.wait_for_load_state("domcontentloaded", timeout=3_000)
                reread_state = safe_page_state(global_names, mod_probe_names)
                stability_retry["page_state_after_wait"] = reread_state
                if "error" not in reread_state:
                    report.observations["page_state"] = reread_state
                    report.observations["runtime_globals"] = {
                        global_name: (reread_state.get("globals", {}) or {}).get(global_name)
                        for global_name in profile.diagnostic_globals
                    }
                    report.observations["runtime_mod_probes"] = reread_state.get("modProbes", {}) or {}
                try:
                    reread_game_ready = page.evaluate(_game_ready_script())
                except PlaywrightError as exc:
                    stability_retry["game_ready_after_wait_error"] = str(exc)
                else:
                    stability_retry["game_ready_after_wait"] = reread_game_ready
                    report.observations["game_ready"] = reread_game_ready
            except PlaywrightError as exc:
                stability_retry["retry_error"] = str(exc)

        final_game_ready = report.observations.get("game_ready")
        if final_game_ready:
            _add_game_ready_issues(report, final_game_ready)
        else:
            _add_issue(
                report,
                Issue(
                    "high",
                    "game_ready_check_error",
                    "runner",
                    str(stability_retry.get("initial_error") or "game_ready evaluation did not return a result"),
                ),
            )
        report.observations["game_ready_stability_retry"] = stability_retry

        report.observations["navigation_events"] = navigation_events
        report.observations["pageerror_context"] = pageerror_context
        report.observations["startup_instability"] = stability_retry.get("trigger") or _startup_instability_triggers(
            report, navigation_events
        )

        modal_blockers_after_ready = observe_modal_blockers("after_game_ready")
        report.observations["modal_blockers"] = modal_blockers_after_ready

        if "game_ready" in report.observations:
            _attempt_enter_game(report, page)

        click_results: dict[str, dict[str, Any]] = {}
        for selector in profile.click_selectors:
            result: dict[str, Any] = {
                "selector": selector,
                "found": 0,
                "visible": False,
                "clicked": False,
                "errors_after_click": [],
            }
            click_results[selector] = result
            try:
                locator = page.locator(selector)
                count = locator.count()
                result["found"] = count
                if count == 0:
                    _add_issue(
                        report,
                        Issue(
                            "warning",
                            "click_selector_not_found",
                            "profile",
                            f"selector not found; may require navigation: {selector}",
                        ),
                    )
                    continue

                first = locator.first
                result["visible"] = first.is_visible()
                if not result["visible"]:
                    _add_issue(
                        report,
                        Issue(
                            "warning",
                            "click_selector_not_visible",
                            "profile",
                            f"selector found but not visible; may require a specific UI state: {selector}",
                        ),
                    )
                    continue

                before_errors = len(page_errors)
                first.click(timeout=3_000)
                page.wait_for_timeout(1_000)
                result["clicked"] = True
                result["errors_after_click"] = page_errors[before_errors:]
            except PlaywrightError as exc:
                enter_game = report.observations.get("enter_game") or {}
                game_ready = report.observations.get("game_ready") or {}
                non_blocking = bool(enter_game.get("success")) or _looks_playable(game_ready)
                _add_issue(
                    report,
                    Issue(
                        "warning" if non_blocking else "high",
                        "profile_click_failed_non_blocking" if non_blocking else "profile_click_failed",
                        "profile",
                        f"{selector}: {exc}",
                    ),
                )
        report.observations["click_results"] = click_results
        report.observations["browser_popups"] = browser_popups
        report.observations["final_page_state"] = safe_page_state(global_names, mod_probe_names)

        if screenshot_dir is not None:
            screenshot_path = screenshot_dir / "browser-smoke-final.png"
            try:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                report.observations["screenshot"] = {
                    "path": str(screenshot_path),
                    "full_page": True,
                }
            except PlaywrightError as exc:
                _add_issue(report, Issue("warning", "screenshot_failed", "runner", str(exc)))

        context.close()
        browser.close()


def _write_console_log(report: BrowserSmokeReport, output_dir: Path) -> None:
    lines = []
    for message in report.console_messages:
        location = message.get("location") or {}
        suffix = ""
        if location.get("url"):
            suffix = f" ({location.get('url')}:{location.get('lineNumber', '')})"
        lines.append(f"[{message.get('type')}] {message.get('text')}{suffix}")
    (output_dir / "console.log").write_text("\n".join(lines), encoding="utf-8")


def _is_successful_smoke(report: BrowserSmokeReport) -> bool:
    if any(issue.severity == "high" for issue in report.issues):
        return False

    browser_boot = report.observations.get("browser_boot") or {}
    if not browser_boot.get("navigation_ok") or not browser_boot.get("has_sugarcube"):
        return False

    enter_game = report.observations.get("enter_game") or {}
    if enter_game.get("success"):
        return True

    game_ready = report.observations.get("game_ready") or {}
    return _looks_playable(game_ready)


def summarize_report(report: BrowserSmokeReport, top_limit: int = 5) -> dict[str, Any]:
    """Return a compact summary for CI step summaries and quick artifact checks."""
    high = [issue for issue in report.issues if issue.severity == "high"]
    warnings = [issue for issue in report.issues if issue.severity == "warning"]
    allowed = [issue for issue in report.issues if issue.severity == "allowed"]
    status = "pass" if report.success else "report_only_with_findings" if report.report_only else "fail"
    browser_boot = report.observations.get("browser_boot", {})
    game_ready = report.observations.get("game_ready", {})
    enter_game = report.observations.get("enter_game", {})
    startup_interactions = report.observations.get("startup_interactions", {}) or {}
    package_identity = report.observations.get("package_identity", {})
    static_asset_audit = report.observations.get("static_asset_audit", {})
    modal_blockers = report.observations.get("modal_blockers", {}) or {}
    blocker_dismissal = report.observations.get("blocker_dismissal", {}) or {}
    browser_popups = report.observations.get("browser_popups", []) or []
    navigation_events = report.observations.get("navigation_events", []) or []
    pageerror_context = report.observations.get("pageerror_context", []) or []
    stability_retry = report.observations.get("game_ready_stability_retry", {}) or {}
    startup_instability = report.observations.get("startup_instability", {}) or {}
    final_page_state = report.observations.get("final_page_state", {}) or {}
    runtime_globals = report.observations.get("runtime_globals")
    if runtime_globals is None:
        runtime_globals = (report.observations.get("page_state") or {}).get("globals", {})
    dismissal_attempts = blocker_dismissal.get("attempts", []) or []
    blocker_samples = [
        {
            "selector": item.get("selector"),
            "simple_selector": item.get("simpleSelector"),
            "text_sample": item.get("textSample"),
            "button_texts": item.get("buttonTexts", []),
        }
        for item in (modal_blockers.get("items") or [])[:3]
    ]

    return {
        "status": status,
        "success": report.success,
        "report_only": report.report_only,
        "target": report.target,
        "profile": report.profile,
        "ci_context": report.ci_context,
        "html_path": report.html_path,
        "served_url": report.served_url,
        "elapsed_seconds": round(report.elapsed_seconds, 2),
        "screenshot": report.observations.get("screenshot"),
        "static_asset_audit": {
            "face_dir_exists": static_asset_audit.get("face_dir_exists"),
            "face_png_count": static_asset_audit.get("face_png_count"),
            "blush_png_count": static_asset_audit.get("blush_png_count"),
            "required_face_assets": static_asset_audit.get("required_face_assets", []),
        },
        "package_identity": {
            "package_slug": package_identity.get("package_slug"),
            "workflow_head_branch": package_identity.get("workflow_head_branch"),
            "expected_profile_for_branch": package_identity.get("expected_profile_for_branch"),
            "branch_profile_match": package_identity.get("branch_profile_match"),
            "profile_slug_match": package_identity.get("profile_slug_match"),
            "forbidden_slug_tokens_present": package_identity.get("forbidden_slug_tokens_present", []),
        },
        "runtime_globals": runtime_globals or {},
        "browser_boot": {
            "navigation_ok": browser_boot.get("navigation_ok"),
            "has_sugarcube": browser_boot.get("has_sugarcube"),
            "has_mod_data_value_zip_list": browser_boot.get("has_mod_data_value_zip_list"),
            "dialog_count": browser_boot.get("dialog_count", 0),
        },
        "browser_diagnostics": {
            "navigation_event_count": len(navigation_events),
            "document_abort_count": sum(
                1
                for event in navigation_events
                if event.get("type") == "document_request_failed"
                and "abort" in str(event.get("failure") or "").lower()
            ),
            "main_frame_navigation_count": sum(
                1 for event in navigation_events if event.get("type") == "framenavigated" and event.get("main_frame")
            ),
            "pageerror_count": len(pageerror_context),
            "pageerror_samples": pageerror_context[:3],
            "startup_instability": startup_instability,
            "stability_retry_attempted": stability_retry.get("attempted", False),
            "stability_retry_ready_after_wait": (stability_retry.get("game_ready_after_wait") or {}).get("ready"),
            "stability_retry_has_sugarcube_after_wait": (stability_retry.get("game_ready_after_wait") or {}).get(
                "hasSugarCube"
            ),
            "final_ready_state": final_page_state.get("readyState"),
            "final_has_sugarcube": final_page_state.get("hasSugarCube"),
        },
        "game_ready": {
            "ready": game_ready.get("ready"),
            "has_jquery": game_ready.get("hasJQuery"),
            "has_sugarcube": game_ready.get("hasSugarCube"),
            "passage": game_ready.get("passage"),
            "loading_like": game_ready.get("loadingLike"),
            "interactive_element_count": game_ready.get("interactiveElementCount"),
        },
        "enter_game": {
            "attempted": enter_game.get("attempted"),
            "success": enter_game.get("success"),
            "reason": enter_game.get("reason"),
            "passage_before": enter_game.get("passage_before"),
            "passage_after": enter_game.get("passage_after"),
            "new_high_risk_count": len(enter_game.get("new_high_risk_errors", [])),
        },
        "startup_interactions": {
            "attempted": startup_interactions.get("attempted", False),
            "success": startup_interactions.get("success", False),
            "reason": startup_interactions.get("reason"),
            "step_count": startup_interactions.get("step_count", 0),
            "clicked_count": startup_interactions.get("clicked_count", 0),
            "browser_dialogs": report.observations.get("dialogs", [])[:20],
            "password_supplied": startup_interactions.get("password_supplied", False),
            "consent_accepted_count": startup_interactions.get("consent_accepted_count", 0),
            "final_passage": startup_interactions.get("final_passage"),
            "last_action": startup_interactions.get("last_action"),
            "startup_gate_after": startup_interactions.get("startup_gate_after"),
            "last_visible_text_sample": startup_interactions.get("last_visible_text_sample"),
            "last_visible_text_length": startup_interactions.get("last_visible_text_length"),
            "recent_modloader_logs": startup_interactions.get("recent_modloader_logs", [])[-50:],
            "steps": [
                {
                    "step": step.get("step"),
                    "action": (step.get("action") or {}).get("action"),
                    "clicked": (step.get("action") or {}).get("clicked"),
                    "button_text": (step.get("action") or {}).get("button_text"),
                    "consent_label": (step.get("action") or {}).get("consent_label"),
                    "passage_before": step.get("passage_before"),
                    "passage_after": step.get("passage_after"),
                    "playable_after": step.get("playable_after"),
                    "gate_before_has_gate": (step.get("gate_before") or {}).get("has_gate"),
                    "gate_before_reason": (step.get("gate_before") or {}).get("reason"),
                    "gate_before_consent_label": (step.get("gate_before") or {}).get("consent_label"),
                    "gate_after_has_gate": (step.get("gate_after") or {}).get("has_gate"),
                    "gate_after_reason": (step.get("gate_after") or {}).get("reason"),
                    "gate_after_consent_label": (step.get("gate_after") or {}).get("consent_label"),
                }
                for step in startup_interactions.get("steps", [])[:20]
            ],
        },
        "blockers": {
            "modal_count": modal_blockers.get("count", 0),
            "modal_samples": blocker_samples,
            "popup_count": len(browser_popups),
            "popup_samples": browser_popups[:3],
            "dismissal_attempts": len(dismissal_attempts),
            "dismissal_clicked": any((attempt.get("click") or {}).get("clicked") for attempt in dismissal_attempts),
            "dismissal_clicked_count": blocker_dismissal.get("clicked_count", 0),
            "dismissal_initial_count": blocker_dismissal.get("initial_count"),
            "dismissal_final_count": blocker_dismissal.get("final_count"),
        },
        "issue_counts": {
            "high": len(high),
            "warning": len(warnings),
            "allowed": len(allowed),
            "total": len(report.issues),
        },
        "dialog_observations": report.observations.get("dialogs", []),
        "top_high_risk": [asdict(issue) for issue in high[:top_limit]],
    }


def _write_markdown_report(report: BrowserSmokeReport, output_dir: Path) -> None:
    summary = summarize_report(report)
    high = [issue for issue in report.issues if issue.severity == "high"]
    warnings = [issue for issue in report.issues if issue.severity == "warning"]
    allowed = [issue for issue in report.issues if issue.severity == "allowed"]
    status = "PASS" if report.success else "REPORT ONLY - HIGH RISK FOUND" if report.report_only else "FAIL"
    counts = summary["issue_counts"]

    lines = [
        "# DoL-X Phase 4 Browser Smoke Report",
        "",
        f"- Status: `{status}`",
        f"- Success: `{report.success}`",
        f"- Report-only mode: `{report.report_only}`",
        f"- Target: `{report.target}`",
        f"- Profile: `{report.profile}`",
        f"- Package slug: `{summary['package_identity']['package_slug']}`",
        f"- Branch/profile match: `{summary['package_identity']['branch_profile_match']}`",
        f"- Profile/package slug match: `{summary['package_identity']['profile_slug_match']}`",
        f"- HTML: `{report.html_path}`",
        f"- URL: `{report.served_url}`",
        f"- Screenshot: `{(summary['screenshot'] or {}).get('path')}`",
        f"- Elapsed seconds: `{report.elapsed_seconds:.2f}`",
        f"- Browser navigation OK: `{summary['browser_boot']['navigation_ok']}`",
        f"- Browser navigation events: `{summary['browser_diagnostics']['navigation_event_count']}`",
        f"- Browser document aborts: `{summary['browser_diagnostics']['document_abort_count']}`",
        f"- Browser pageerrors captured: `{summary['browser_diagnostics']['pageerror_count']}`",
        f"- Startup stability retry attempted: `{summary['browser_diagnostics']['stability_retry_attempted']}`",
        f"- Startup stability retry ready after wait: `{summary['browser_diagnostics']['stability_retry_ready_after_wait']}`",
        f"- Final page readyState: `{summary['browser_diagnostics']['final_ready_state']}`",
        f"- Final page has SugarCube: `{summary['browser_diagnostics']['final_has_sugarcube']}`",
        f"- Runtime globals observed: `{summary['runtime_globals']}`",
        f"- SugarCube ready: `{summary['game_ready']['ready']}`",
        f"- Current passage: `{summary['game_ready']['passage']}`",
        f"- Entered playable scene: `{summary['enter_game']['success']}`",
        f"- Enter-game reason: `{summary['enter_game']['reason']}`",
        f"- Startup interaction steps: `{summary['startup_interactions']['step_count']}`",
        f"- Startup interaction clicked: `{summary['startup_interactions']['clicked_count']}`",
        f"- Startup password supplied: `{summary['startup_interactions']['password_supplied']}`",
        f"- Startup consent accepted: `{summary['startup_interactions']['consent_accepted_count']}`",
        f"- Startup final passage: `{summary['startup_interactions']['final_passage']}`",
        f"- Startup gate after: `{(summary['startup_interactions'].get('startup_gate_after') or {}).get('reason')}`",
        f"- Startup last visible text length: `{summary['startup_interactions']['last_visible_text_length']}`",
        f"- Startup recent ModLoader log lines: `{len(summary['startup_interactions']['recent_modloader_logs'])}`",
        f"- Browser popups observed: `{summary['blockers']['popup_count']}`",
        f"- Modal blockers observed: `{summary['blockers']['modal_count']}`",
        f"- Blocker dismissal clicked: `{summary['blockers']['dismissal_clicked']}`",
        f"- Face asset dir exists: `{summary['static_asset_audit']['face_dir_exists']}`",
        f"- Face PNG count: `{summary['static_asset_audit']['face_png_count']}`",
        f"- Blush PNG count: `{summary['static_asset_audit']['blush_png_count']}`",
        f"- High risk issues: `{counts['high']}`",
        f"- Warnings: `{counts['warning']}`",
        f"- Allowed findings: `{counts['allowed']}`",
        f"- Total findings: `{counts['total']}`",
        "",
    ]

    if report.ci_context:
        lines.extend(["## CI context", ""])
        for key, value in report.ci_context.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    browser_diagnostics = summary["browser_diagnostics"]
    if browser_diagnostics.get("navigation_event_count") or browser_diagnostics.get("pageerror_count"):
        lines.extend(["## Browser startup diagnostics", ""])
        lines.append(f"- Navigation events: `{browser_diagnostics['navigation_event_count']}`")
        lines.append(f"- Document aborts: `{browser_diagnostics['document_abort_count']}`")
        lines.append(f"- Pageerrors captured: `{browser_diagnostics['pageerror_count']}`")
        lines.append(f"- Stability retry attempted: `{browser_diagnostics['stability_retry_attempted']}`")
        lines.append(f"- Startup instability: `{browser_diagnostics['startup_instability']}`")
        for pageerror in browser_diagnostics.get("pageerror_samples", []):
            message = str(pageerror.get("message") or "").replace("\n", " ")[:300]
            lines.append(
                "- "
                f"pageerror url=`{pageerror.get('url')}`, ready_state=`{pageerror.get('ready_state')}`, "
                f"message=`{message}`"
            )
        lines.append("")

    startup_steps = summary["startup_interactions"].get("steps", [])
    if startup_steps:
        lines.extend(["## Startup interactions", ""])
        for step in startup_steps:
            lines.append(
                "- "
                f"Step `{step.get('step')}`: action=`{step.get('action')}`, "
                f"clicked=`{step.get('clicked')}`, button=`{step.get('button_text')}`, "
                f"consent=`{step.get('consent_label')}`, "
                f"passage=`{step.get('passage_before')}` -> `{step.get('passage_after')}`, "
                f"gate=`{step.get('gate_before_reason')}` -> `{step.get('gate_after_reason')}`"
            )
        lines.append("")

    startup_dialogs = summary["startup_interactions"].get("browser_dialogs", [])
    if startup_dialogs:
        lines.extend(["## Startup browser dialogs", ""])
        for dialog in startup_dialogs:
            message = str(dialog.get("message") or "").replace("\n", " ")[:300]
            lines.append(
                "- "
                f"type=`{dialog.get('type')}`, accepted=`{dialog.get('accepted')}`, "
                f"password_supplied=`{dialog.get('password_supplied')}`, message=`{message}`"
            )
        lines.append("")

    startup_text_sample = summary["startup_interactions"].get("last_visible_text_sample")
    if startup_text_sample:
        lines.extend(["## Startup final visible text sample", "", "```text"])
        lines.append(startup_text_sample)
        lines.extend(["```", ""])

    startup_log_tail = summary["startup_interactions"].get("recent_modloader_logs") or []
    if startup_log_tail:
        lines.extend(["## Startup recent ModLoader logs", "", "```text"])
        lines.extend(startup_log_tail)
        lines.extend(["```", ""])

    if report.report_only and high:
        lines.extend(
            [
                "> This job is currently report-only: high-risk runtime findings are recorded but do not fail CI.",
                "",
            ]
        )

    if high:
        lines.extend(["## Top high-risk findings", ""])
        for issue in high[:5]:
            lines.append(f"- `{issue.kind}` from `{issue.source}`: {issue.message}")
        lines.append("")

    def add_issue_section(title: str, issues: list[Issue]) -> None:
        lines.extend([f"## {title}", ""])
        if not issues:
            lines.extend(["None.", ""])
            return
        for issue in issues:
            lines.append(f"- `{issue.kind}` from `{issue.source}`: {issue.message}")
            if issue.url:
                lines.append(f"  - URL: `{issue.url}`")
        lines.append("")

    add_issue_section("High risk issues", high)
    add_issue_section("Warnings", warnings)
    add_issue_section("Allowed findings", allowed)

    lines.extend(["## Observations", "", "```json"])
    lines.append(json.dumps(report.observations, ensure_ascii=False, indent=2))
    lines.extend(["```", ""])

    (output_dir / "browser-smoke-report.md").write_text("\n".join(lines), encoding="utf-8")


def write_outputs(report: BrowserSmokeReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report.success = _is_successful_smoke(report)
    summary = summarize_report(report)
    (output_dir / "browser-smoke-report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "browser-smoke-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "network-failures.json").write_text(
        json.dumps(report.network_failures, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_console_log(report, output_dir)
    _write_markdown_report(report, output_dir)


def run_browser_smoke(args: argparse.Namespace) -> BrowserSmokeReport:
    start = time.monotonic()
    profile = PROFILES[args.profile]
    report = BrowserSmokeReport(
        target=str(args.target),
        profile=profile.name,
        report_only=args.report_only,
        ci_context=collect_ci_context(),
    )

    try:
        with tempfile.TemporaryDirectory(prefix="dolx-browser-smoke-") as temp_dir_name:
            serve_dir, html_path = _resolve_target(Path(args.target), Path(temp_dir_name))
            report.html_path = str(html_path)

            html_content = html_path.read_text(encoding="utf-8", errors="replace")
            embedded_mods = extract_embedded_mods_from_html(html_content)
            report.observations["embedded_mods"] = [asdict(info) for info in embedded_mods]
            _record_package_identity(report, profile, Path(args.target), html_path)
            _record_static_asset_audit(report, serve_dir)

            with _serve_directory(serve_dir) as server:
                url = _relative_url(server, serve_dir, html_path)
                report.served_url = url
                _run_playwright(report, profile, url, args.timeout_ms, args.settle_ms, Path(args.output_dir))

            _check_required_mods(report, profile, embedded_mods)
    except Exception as exc:  # noqa: BLE001 - CI report must capture setup failures.
        _add_issue(report, Issue("high", "browser_smoke_setup_error", "runner", str(exc)))
    finally:
        report.elapsed_seconds = time.monotonic() - start

    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DoL-X Phase 4 browser smoke test")
    parser.add_argument("target", type=Path, help="Built ZIP, extracted package directory, or HTML file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/browser-smoke"),
        help="Directory for browser smoke reports",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="ucb-more-love-custom-spellbook",
        help="Mod-specific smoke profile",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Write high-risk findings but exit 0 so CI remains non-blocking",
    )
    parser.add_argument("--timeout-ms", type=int, default=60_000, help="Browser navigation timeout")
    parser.add_argument("--settle-ms", type=int, default=5_000, help="Wait after initial page load")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = run_browser_smoke(args)
    write_outputs(report, args.output_dir)

    high_count = sum(1 for issue in report.issues if issue.severity == "high")
    warning_count = sum(1 for issue in report.issues if issue.severity == "warning")
    print(
        f"Phase 4 browser smoke: success={report.success} "
        f"high={high_count} warnings={warning_count} report_only={report.report_only}"
    )
    print(f"Report: {args.output_dir / 'browser-smoke-report.md'}")

    if args.report_only:
        return 0
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
