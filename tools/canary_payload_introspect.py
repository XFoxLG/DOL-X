#!/usr/bin/env python3
"""Inspect cheatExtended/maplebirch canary payloads and smoke evidence.

This helper is intentionally offline-first.  It can inspect locally cached
upstream payload files and correlate them with already downloaded HTML/browser
smoke reports, so canary triage does not require repeated workflow dispatches.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


KEYWORDS: tuple[str, ...] = (
    "maplebirchFrameworks",
    "CE_options",
    "SCMLSimpleFramework",
    "Simple Frameworks",
    "TimeEvent",
    "addto",
    "maplebirch",
    "cheatExtended",
    "cheat extended",
)

TEXT_SUFFIXES: tuple[str, ...] = (
    ".json",
    ".js",
    ".ts",
    ".twee",
    ".tw",
    ".txt",
    ".md",
    ".html",
    ".css",
)

MOD_INIT_PATTERN = re.compile(
    r"ModZipReader init\(\) modInfo \{name: (?P<name>[^,}]+).*?version: (?P<version>[^,}]+)",
    re.IGNORECASE,
)


@dataclass
class Snippet:
    """Short source excerpt for one contract-relevant match."""

    path: str
    keyword: str
    line: int
    text: str


@dataclass
class BootJsonSummary:
    """Summary of one boot.json file inside a ModLoader payload."""

    path: str
    parse_error: str | None = None
    name: str | None = None
    version: str | None = None
    aliases: list[str] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    addon_plugins: list[str] = field(default_factory=list)


@dataclass
class PayloadInspection:
    """Static inspection result for one cached upstream payload."""

    path: str
    exists: bool = False
    size_bytes: int = 0
    sha256: str | None = None
    kind: str = "missing"
    error: str | None = None
    zip_member_count: int = 0
    sample_files: list[str] = field(default_factory=list)
    boot_jsons: list[BootJsonSummary] = field(default_factory=list)
    keyword_hits: dict[str, int] = field(default_factory=dict)
    keyword_files: dict[str, list[str]] = field(default_factory=dict)
    snippets: list[Snippet] = field(default_factory=list)
    ce_options_definitions: list[Snippet] = field(default_factory=list)
    ce_options_reads: list[Snippet] = field(default_factory=list)
    ce_options_widget_definitions: list[Snippet] = field(default_factory=list)
    ce_options_slot_registrations: list[Snippet] = field(default_factory=list)
    mod_order_lookups: list[Snippet] = field(default_factory=list)
    maplebirch_framework_accesses: list[Snippet] = field(default_factory=list)
    defines_maplebirch_frameworks: bool = False
    references_maplebirch_frameworks: bool = False
    references_ce_options: bool = False


@dataclass
class SmokeEvidenceSummary:
    """Correlated evidence from existing HTML and browser smoke reports."""

    html_mod_count: int = 0
    html_valid_zip_count: int = 0
    html_non_zip_indices: list[int] = field(default_factory=list)
    browser_mod_order: list[dict[str, Any]] = field(default_factory=list)
    maplebirch_index: int | None = None
    cheat_extended_index: int | None = None
    load_order_ok: bool | None = None
    runtime_globals: dict[str, str] = field(default_factory=dict)
    runtime_mod_probes: dict[str, dict[str, Any]] = field(default_factory=dict)
    maplebirch_getmod_available: bool | None = None
    simple_framework_getmod_available: bool | None = None
    simple_framework_getmod_error: str | None = None
    maplebirch_framework_missing_issue_count: int = 0
    simple_framework_lookup_issue_count: int = 0
    high_risk_messages: list[str] = field(default_factory=list)
    high_risk_issue_kinds: list[str] = field(default_factory=list)
    high_risk_issue_sources: list[str] = field(default_factory=list)
    browser_success: bool | None = None
    game_ready: bool | None = None
    playable_passage: str | None = None
    enter_game_success: bool | None = None
    ce_options_observed: bool = False
    maplebirch_framework_global_observed: bool = False


@dataclass
class CanaryPayloadIntrospectionReport:
    """Full report emitted by this helper."""

    payloads: list[PayloadInspection]
    smoke_evidence: SmokeEvidenceSummary | None = None
    root_cause_classification: str = "insufficient_evidence"
    notes: list[str] = field(default_factory=list)
    framework_contract_conclusions: list[str] = field(default_factory=list)
    recommended_canary_fix: str | None = None
    single_validation_plan: list[str] = field(default_factory=list)


def _safe_decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _collect_string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _collect_string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _collect_string_values(item)


def _scan_keywords(text: str) -> dict[str, int]:
    return {keyword: text.count(keyword) for keyword in KEYWORDS if keyword in text}


def _merge_hits(target: dict[str, int], source: dict[str, int]) -> None:
    for keyword, count in source.items():
        target[keyword] = target.get(keyword, 0) + count


def _record_keyword_files(target: dict[str, list[str]], file_name: str, hits: dict[str, int]) -> None:
    for keyword, count in hits.items():
        if count <= 0:
            continue
        target.setdefault(keyword, [])
        if file_name not in target[keyword]:
            target[keyword].append(file_name)


def _looks_like_definition(text: str) -> bool:
    return bool(
        re.search(
            r"(?:window\.|globalThis\.)?maplebirchFrameworks\s*=",
            text,
        )
    )


def _shorten(text: str, limit: int = 260) -> str:
    normalized = " ".join(text.strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _make_snippet(path: str, lines: list[str], keyword: str, index: int, context: int = 1) -> Snippet:
    start = max(0, index - context)
    end = min(len(lines), index + context + 1)
    return Snippet(
        path=path,
        keyword=keyword,
        line=index + 1,
        text=_shorten("\n".join(lines[start:end])),
    )


def _line_snippets(path: str, text: str, keyword: str, context: int = 1) -> list[Snippet]:
    lines = text.splitlines()
    return [
        _make_snippet(path, lines, keyword, index, context)
        for index, line in enumerate(lines)
        if keyword in line
    ]


def _is_ce_options_definition(line: str) -> bool:
    return bool(re.search(r"(?:window\.|globalThis\.|State\.variables\.)CE_options\s*=", line))


def _is_ce_options_read(line: str) -> bool:
    return bool(re.search(r"(?:window\.|globalThis\.|State\.variables\.)CE_options\b", line)) and not _is_ce_options_definition(line)


def _is_ce_options_widget_definition(line: str) -> bool:
    return bool(re.search(r"<<widget\s+[\"']CE_options[\"']", line))


def _is_ce_options_slot_registration(line: str) -> bool:
    return "addto" in line and "CE_options" in line


def _collect_contract_snippets(result: PayloadInspection, file_name: str, text: str) -> None:
    lines = text.splitlines()
    for keyword in KEYWORDS:
        result.snippets.extend(_line_snippets(file_name, text, keyword))

    for index, line in enumerate(lines):
        if "CE_options" in line:
            snippet = _make_snippet(file_name, lines, "CE_options", index)
            if _is_ce_options_definition(line):
                result.ce_options_definitions.append(snippet)
            if _is_ce_options_read(line):
                result.ce_options_reads.append(snippet)
            if _is_ce_options_widget_definition(line):
                result.ce_options_widget_definitions.append(snippet)
            if _is_ce_options_slot_registration(line):
                result.ce_options_slot_registrations.append(snippet)

        if "maplebirchFrameworks" in line:
            result.maplebirch_framework_accesses.append(
                _make_snippet(file_name, lines, "maplebirchFrameworks", index)
            )
        if "SCMLSimpleFramework" in line:
            result.maplebirch_framework_accesses.append(
                _make_snippet(file_name, lines, "SCMLSimpleFramework", index)
            )

        if "getByNameOne" in line or "Simple Frameworks" in line:
            snippet = _make_snippet(file_name, lines, "Simple Frameworks", index)
            if "ModOrderContainer" in snippet.text or "getByNameOne" in snippet.text or "Simple Frameworks" in line:
                result.mod_order_lookups.append(snippet)


def _record_text_scan(result: PayloadInspection, file_name: str, text: str) -> None:
    hits = _scan_keywords(text)
    _merge_hits(result.keyword_hits, hits)
    _record_keyword_files(result.keyword_files, file_name, hits)
    _collect_contract_snippets(result, file_name, text)


def _summarize_boot_json(path: str, content: str) -> BootJsonSummary:
    summary = BootJsonSummary(path=path)
    try:
        boot = json.loads(content)
    except json.JSONDecodeError as exc:
        summary.parse_error = str(exc)
        return summary

    if not isinstance(boot, dict):
        summary.parse_error = "boot.json root is not an object"
        return summary

    for key in ("name", "modName", "id"):
        value = boot.get(key)
        if isinstance(value, str):
            summary.name = value
            break

    value = boot.get("version")
    if isinstance(value, str):
        summary.version = value

    alias = boot.get("alias")
    if isinstance(alias, list):
        summary.aliases = [item for item in alias if isinstance(item, str)]

    dependencies = boot.get("dependenceInfo") or boot.get("dependencies") or []
    if isinstance(dependencies, list):
        summary.dependencies = [item for item in dependencies if isinstance(item, dict)]

    plugins = boot.get("addonPlugin") or []
    if isinstance(plugins, list):
        for plugin in plugins:
            if isinstance(plugin, dict) and isinstance(plugin.get("modName"), str):
                summary.addon_plugins.append(plugin["modName"])

    return summary


def inspect_payload(path: Path) -> PayloadInspection:
    """Inspect one cached upstream payload."""
    path = Path(path)
    result = PayloadInspection(path=str(path))
    if not path.exists():
        result.error = "payload does not exist"
        return result

    result.exists = True
    data = path.read_bytes()
    result.size_bytes = len(data)
    result.sha256 = hashlib.sha256(data).hexdigest()
    raw_hits = _scan_keywords(_safe_decode(data))
    _merge_hits(result.keyword_hits, raw_hits)
    _record_keyword_files(result.keyword_files, "<raw-payload>", raw_hits)

    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            result.kind = "zip"
            names = zf.namelist()
            result.zip_member_count = len(names)
            result.sample_files = names[:30]

            for name in names:
                lower_name = name.lower()
                if lower_name.endswith("boot.json"):
                    text = zf.read(name).decode("utf-8", errors="replace")
                    result.boot_jsons.append(_summarize_boot_json(name, text))
                    _record_text_scan(result, name, text)
                elif lower_name.endswith(TEXT_SUFFIXES):
                    with zf.open(name) as file_obj:
                        text = file_obj.read(2_000_000).decode("utf-8", errors="replace")
                    _record_text_scan(result, name, text)
                    result.defines_maplebirch_frameworks = (
                        result.defines_maplebirch_frameworks or _looks_like_definition(text)
                    )
    except zipfile.BadZipFile as exc:
        result.kind = "non_zip"
        result.error = str(exc)
    except Exception as exc:  # noqa: BLE001 - preserve diagnostics for canary triage.
        result.kind = "zip_error"
        result.error = str(exc)

    result.references_maplebirch_frameworks = result.keyword_hits.get("maplebirchFrameworks", 0) > 0
    result.references_ce_options = result.keyword_hits.get("CE_options", 0) > 0
    return result


def _load_first_result(report_path: Path) -> dict[str, Any] | None:
    if not report_path or not report_path.exists():
        return None
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    results = payload.get("results")
    if isinstance(results, list) and results:
        return results[0]
    return None


def _iter_browser_text(browser_report: dict[str, Any]) -> Iterable[str]:
    for message in browser_report.get("console_messages", []):
        if isinstance(message, dict) and isinstance(message.get("text"), str):
            yield message["text"]

    observations = browser_report.get("observations", {})
    if isinstance(observations, dict):
        startup = observations.get("startup_interactions", {})
        if isinstance(startup, dict):
            for line in startup.get("recent_modloader_logs", []):
                if isinstance(line, str):
                    yield line

    startup = browser_report.get("startup_interactions", {})
    if isinstance(startup, dict):
        for line in startup.get("recent_modloader_logs", []):
            if isinstance(line, str):
                yield line


def _browser_runtime_globals(browser_report: dict[str, Any]) -> dict[str, str]:
    observations = browser_report.get("observations", {})
    if not isinstance(observations, dict):
        return {}

    runtime_globals = observations.get("runtime_globals")
    if isinstance(runtime_globals, dict):
        return {str(name): str(global_type) for name, global_type in runtime_globals.items()}

    page_state = observations.get("page_state", {})
    if isinstance(page_state, dict) and isinstance(page_state.get("globals"), dict):
        return {str(name): str(global_type) for name, global_type in page_state["globals"].items()}

    return {}


def _browser_runtime_mod_probes(browser_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observations = browser_report.get("observations", {})
    if not isinstance(observations, dict):
        return {}

    runtime_mod_probes = observations.get("runtime_mod_probes")
    if isinstance(runtime_mod_probes, dict):
        results = runtime_mod_probes.get("results", runtime_mod_probes)
        if isinstance(results, dict):
            return {str(name): dict(value) for name, value in results.items() if isinstance(value, dict)}

    for state_key in ("page_state", "final_page_state"):
        page_state = observations.get(state_key, {})
        if not isinstance(page_state, dict):
            continue
        mod_probes = page_state.get("modProbes", {})
        if not isinstance(mod_probes, dict):
            continue
        results = mod_probes.get("results", {})
        if isinstance(results, dict):
            return {str(name): dict(value) for name, value in results.items() if isinstance(value, dict)}

    return {}


def summarize_smoke_evidence(
    html_smoke_report: Path | None = None,
    browser_smoke_report: Path | None = None,
) -> SmokeEvidenceSummary | None:
    """Summarize already downloaded canary smoke evidence."""
    if not html_smoke_report and not browser_smoke_report:
        return None

    summary = SmokeEvidenceSummary()

    if html_smoke_report:
        first_result = _load_first_result(Path(html_smoke_report))
        if first_result:
            summary.html_mod_count = int(first_result.get("mod_count") or 0)
            summary.html_valid_zip_count = int(first_result.get("valid_zip_count") or 0)
            payloads = first_result.get("payloads") or []
            if isinstance(payloads, list):
                summary.html_non_zip_indices = [
                    int(item.get("index"))
                    for item in payloads
                    if isinstance(item, dict) and item.get("kind") == "non_zip"
                ]

    if browser_smoke_report and Path(browser_smoke_report).exists():
        browser_report = json.loads(Path(browser_smoke_report).read_text(encoding="utf-8"))
        if isinstance(browser_report.get("success"), bool):
            summary.browser_success = bool(browser_report.get("success"))

        for issue in browser_report.get("issues", []):
            if not isinstance(issue, dict):
                continue

            message = str(issue.get("message") or "")
            if issue.get("severity") == "high":
                summary.high_risk_messages.append(message)
                summary.high_risk_issue_kinds.append(str(issue.get("kind") or ""))
                summary.high_risk_issue_sources.append(str(issue.get("source") or ""))
            if issue.get("kind") == "maplebirch_framework_missing":
                summary.maplebirch_framework_missing_issue_count += 1
            if "Simple Frameworks" in message and (
                "getByNameOne" in message or "ModOrderContainer" in message
            ):
                summary.simple_framework_lookup_issue_count += 1

        runtime_globals = _browser_runtime_globals(browser_report)
        summary.runtime_globals = runtime_globals
        summary.ce_options_observed = runtime_globals.get("CE_options") not in {None, "undefined"}
        summary.maplebirch_framework_global_observed = runtime_globals.get("maplebirchFrameworks") not in {
            None,
            "undefined",
        }

        runtime_mod_probes = _browser_runtime_mod_probes(browser_report)
        summary.runtime_mod_probes = runtime_mod_probes
        maplebirch_probe = runtime_mod_probes.get("maplebirch") or {}
        simple_framework_probe = runtime_mod_probes.get("Simple Frameworks") or {}
        if maplebirch_probe:
            summary.maplebirch_getmod_available = bool(maplebirch_probe.get("available"))
        if simple_framework_probe:
            summary.simple_framework_getmod_available = bool(simple_framework_probe.get("available"))
            if simple_framework_probe.get("error") is not None:
                summary.simple_framework_getmod_error = str(simple_framework_probe.get("error"))

        observations = browser_report.get("observations", {})
        if isinstance(observations, dict):
            game_ready = observations.get("game_ready", {})
            if isinstance(game_ready, dict):
                if isinstance(game_ready.get("ready"), bool):
                    summary.game_ready = bool(game_ready.get("ready"))
                passage = game_ready.get("passage")
                if isinstance(passage, str) and passage:
                    summary.playable_passage = passage

            enter_game = observations.get("enter_game", {})
            if isinstance(enter_game, dict):
                if isinstance(enter_game.get("success"), bool):
                    summary.enter_game_success = bool(enter_game.get("success"))
                passage_after = enter_game.get("passage_after")
                if isinstance(passage_after, str) and passage_after:
                    summary.playable_passage = passage_after

        for text in _iter_browser_text(browser_report):
            if "CE_options" in text:
                summary.ce_options_observed = True
            if "maplebirchFrameworks" in text and "not defined" not in text:
                summary.maplebirch_framework_global_observed = True

            match = MOD_INIT_PATTERN.search(text)
            if not match:
                continue
            entry = {
                "index": len(summary.browser_mod_order),
                "name": match.group("name").strip(),
                "version": match.group("version").strip(),
            }
            summary.browser_mod_order.append(entry)

        for entry in summary.browser_mod_order:
            normalized_name = str(entry["name"]).lower()
            if normalized_name == "maplebirch":
                summary.maplebirch_index = int(entry["index"])
            if normalized_name in {"cheat extended", "cheatextended"}:
                summary.cheat_extended_index = int(entry["index"])

        if summary.maplebirch_index is not None and summary.cheat_extended_index is not None:
            summary.load_order_ok = summary.maplebirch_index < summary.cheat_extended_index

    return summary


def classify_root_cause(
    payloads: list[PayloadInspection],
    smoke_evidence: SmokeEvidenceSummary | None,
) -> tuple[str, list[str]]:
    """Classify the most likely root cause from static and smoke evidence."""
    notes: list[str] = []
    by_name = {Path(payload.path).name.lower(): payload for payload in payloads}
    maplebirch_payload = next(
        (payload for name, payload in by_name.items() if "maplebirch" in name),
        None,
    )
    cheat_payload = next(
        (payload for name, payload in by_name.items() if "cheat" in name),
        None,
    )

    if maplebirch_payload and maplebirch_payload.kind == "non_zip":
        notes.append("maplebirch upstream asset is not a normal ZIP; HTML smoke will report it as non_zip.")

    if smoke_evidence and smoke_evidence.load_order_ok is False:
        return "load_order", notes + ["browser logs show cheatExtended before maplebirch"]

    if smoke_evidence and smoke_evidence.maplebirch_index is not None:
        notes.append("browser logs show maplebirch is loaded by ModLoader.")

    if smoke_evidence and smoke_evidence.load_order_ok is True:
        notes.append("browser logs show maplebirch loads before cheatExtended.")

    if cheat_payload and cheat_payload.references_maplebirch_frameworks:
        notes.append("cheatExtended references maplebirchFrameworks.")

    if maplebirch_payload and not maplebirch_payload.defines_maplebirch_frameworks:
        notes.append("static scan did not find a maplebirchFrameworks global definition in the maplebirch payload.")

    if smoke_evidence and smoke_evidence.maplebirch_framework_missing_issue_count:
        if smoke_evidence.maplebirch_index is not None and smoke_evidence.load_order_ok is True:
            return "framework_api_or_global_incompatibility", notes
        return "payload_or_framework_runtime", notes

    if smoke_evidence and smoke_evidence.simple_framework_lookup_issue_count:
        notes.append("browser smoke reproduced Simple Frameworks ModOrder lookup failures.")
        if smoke_evidence.maplebirch_getmod_available is True:
            notes.append("runtime getMod('maplebirch') probe is available.")
        elif smoke_evidence.maplebirch_getmod_available is False:
            notes.append("runtime getMod('maplebirch') probe is not available.")
        if smoke_evidence.simple_framework_getmod_available is True:
            notes.append("runtime getMod('Simple Frameworks') probe resolved a module.")
        if smoke_evidence.simple_framework_getmod_available is False:
            notes.append("runtime getMod('Simple Frameworks') probe is not available.")
        if smoke_evidence.simple_framework_getmod_error:
            notes.append(
                "runtime getMod('Simple Frameworks') probe errored: "
                f"{smoke_evidence.simple_framework_getmod_error}"
            )
        simple_framework_probe = smoke_evidence.runtime_mod_probes.get("Simple Frameworks") or {}
        simple_framework_name = str(simple_framework_probe.get("name") or "").lower()
        simple_framework_alias_resolved = bool(
            smoke_evidence.maplebirch_getmod_available is True
            and smoke_evidence.simple_framework_getmod_available is True
            and simple_framework_name == "maplebirch"
            and not smoke_evidence.simple_framework_getmod_error
        )
        playable = bool(
            smoke_evidence.browser_success is True
            or smoke_evidence.game_ready is True
            or smoke_evidence.enter_game_success is True
            or smoke_evidence.playable_passage
        )
        non_runtime_high_risk_kinds = {
            "branch_profile_mismatch",
            "package_forbidden_slug_token_present",
        }
        runtime_blocking_high_risk = [
            kind
            for kind in smoke_evidence.high_risk_issue_kinds
            if kind not in non_runtime_high_risk_kinds
        ]
        if (
            simple_framework_alias_resolved
            and smoke_evidence.maplebirch_framework_global_observed
            and not runtime_blocking_high_risk
            and playable
        ):
            if smoke_evidence.high_risk_messages:
                notes.append(
                    "non-runtime high-risk smoke findings were ignored for alias resolution: "
                    f"{smoke_evidence.high_risk_issue_kinds}."
                )
            notes.append(
                "Simple Frameworks lookup warnings resolved to maplebirch at runtime and did not block playability."
            )
            if smoke_evidence.playable_passage:
                notes.append(f"browser smoke reached playable passage: {smoke_evidence.playable_passage}.")
            return "simple_framework_alias_resolved_warning", notes
        return "simple_framework_alias_lookup", notes

    return "no_runtime_blocker_observed", notes


def _payload_primary_name(payload: PayloadInspection) -> str:
    for boot in payload.boot_jsons:
        if boot.name:
            return boot.name.lower()
    return Path(payload.path).name.lower()


def build_framework_contract_conclusions(
    payloads: list[PayloadInspection],
    smoke_evidence: SmokeEvidenceSummary | None,
) -> tuple[list[str], str]:
    """Summarize framework contract evidence previously emitted by the trace helper."""
    conclusions: list[str] = []
    by_name = {_payload_primary_name(payload): payload for payload in payloads}
    maplebirch = next((payload for name, payload in by_name.items() if "maplebirch" in name), None)
    cheat = next((payload for name, payload in by_name.items() if "cheat" in name), None)

    if maplebirch and maplebirch.boot_jsons:
        boot = maplebirch.boot_jsons[0]
        conclusions.append(f"maplebirch boot name is `{boot.name}`; alias list is `{boot.aliases}`.")

    if cheat and cheat.boot_jsons:
        deps = [
            item.get("modName")
            for item in cheat.boot_jsons[0].dependencies
            if isinstance(item, dict)
        ]
        conclusions.append(f"cheatExtended boot dependencies do not declare either framework directly: `{deps}`.")

    if cheat:
        if cheat.keyword_hits.get("Simple Frameworks", 0) and cheat.keyword_hits.get("maplebirchFrameworks", 0):
            conclusions.append(
                "cheatExtended code references both `Simple Frameworks` ModOrder lookups and `maplebirchFrameworks` APIs."
            )
        if cheat.keyword_hits.get("CE_options", 0):
            conclusions.append(
                "`CE_options` appears as a SugarCube widget/slot id in cheatExtended, not as a required window global."
            )
        if (
            cheat.ce_options_widget_definitions
            and cheat.ce_options_slot_registrations
            and not cheat.ce_options_definitions
            and not cheat.ce_options_reads
        ):
            conclusions.append(
                "No `window.CE_options`/`State.variables.CE_options` read or assignment was found; "
                "the browser global probe is not the right CE_options contract check."
            )

    if smoke_evidence:
        conclusions.append(f"browser smoke observed runtime globals: `{smoke_evidence.runtime_globals}`.")
        if smoke_evidence.runtime_mod_probes:
            conclusions.append(f"browser smoke observed runtime mod probes: `{smoke_evidence.runtime_mod_probes}`.")
        if smoke_evidence.simple_framework_lookup_issue_count:
            conclusions.append(
                "browser smoke reproduced `ModOrderContainer getByNameOne()` failures for `Simple Frameworks` "
                f"{smoke_evidence.simple_framework_lookup_issue_count} time(s)."
            )
        if smoke_evidence.maplebirch_getmod_available is True:
            conclusions.append("runtime `getMod('maplebirch')` probe resolved a module.")
        if smoke_evidence.simple_framework_getmod_error:
            conclusions.append(
                "runtime `getMod('Simple Frameworks')` probe errored: "
                f"{smoke_evidence.simple_framework_getmod_error}"
            )
        if (
            smoke_evidence.runtime_globals.get("maplebirchFrameworks") == "object"
            and smoke_evidence.runtime_globals.get("CE_options") == "undefined"
        ):
            conclusions.append(
                "v3.1.13 restores the maplebirch global; `window.CE_options` stays undefined because CE_options "
                "is registered as a widget/slot name."
            )

    recommended_fix = (
        "maplebirch-only canary trace first: keep Simple Frameworks out of the build and do not add a "
        "`Simple Frameworks -> maplebirch` alias shim from this evidence alone. Re-run browser smoke with "
        "runtime `getMod('maplebirch')` and `getMod('Simple Frameworks')` probes, then fix load order or "
        "cheatExtended branch logic if the maplebirch branch should have short-circuited. Only revisit an "
        "alias workaround after runtime evidence proves it binds to `maplebirchFrameworks`, not the distinct "
        "`simpleFrameworks` branch. Do not add a `window.CE_options` initializer unless a later trace finds "
        "real global reads; current evidence says CE_options is a widget/slot id."
    )
    return conclusions, recommended_fix


def single_validation_plan() -> list[str]:
    return [
        "Do not add Simple Frameworks or a name alias shim; keep stable/default config unchanged.",
        "Run one canary stable-replacement build for code 33024 with the selected maplebirch override.",
        "Run one HTML smoke on the produced 33024/slugged ZIP.",
        "Run one browser smoke with profile `ucb-cheat-extended-maplebirch` and runtime getMod probes.",
        "If the blocker remains, classify whether it is load order or cheatExtended branch logic before considering any alias workaround.",
        "Stop after that single validation pass; if the same blocker remains, record evidence instead of looping.",
    ]


def build_report(
    payload_paths: list[Path],
    html_smoke_report: Path | None = None,
    browser_smoke_report: Path | None = None,
) -> CanaryPayloadIntrospectionReport:
    payloads = [inspect_payload(path) for path in payload_paths]
    smoke_evidence = summarize_smoke_evidence(html_smoke_report, browser_smoke_report)
    classification, notes = classify_root_cause(payloads, smoke_evidence)
    conclusions, recommended_fix = build_framework_contract_conclusions(payloads, smoke_evidence)
    return CanaryPayloadIntrospectionReport(
        payloads=payloads,
        smoke_evidence=smoke_evidence,
        root_cause_classification=classification,
        notes=notes,
        framework_contract_conclusions=conclusions,
        recommended_canary_fix=recommended_fix,
        single_validation_plan=single_validation_plan(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect canary payloads and smoke evidence")
    parser.add_argument("payload", nargs="*", type=Path, help="Cached upstream payload paths")
    parser.add_argument("--html-smoke-report", type=Path, help="Existing HTML smoke JSON report")
    parser.add_argument("--browser-smoke-report", type=Path, help="Existing browser smoke JSON report")
    parser.add_argument("--output", type=Path, help="Optional JSON report output path")
    args = parser.parse_args()

    report = build_report(args.payload, args.html_smoke_report, args.browser_smoke_report)
    text = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
