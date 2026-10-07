#!/usr/bin/env python3
"""Inventory the mod-provided passages inside a built DOL-X carrier.

``passage_sweep.extract_passages`` parses ``<tw-passagedata>`` from the HTML
*file*, so it only ever sees the vanilla story (15,627 passages on the locked
0.5.11.9 stack). ModLoader merges each embedded mod payload into the story at
runtime instead of writing it back to disk, which is why the sweeps that claim
"15,627 passages ok" never touched a single mod passage.

This tool measures the real surface and classifies it:

* static file passages (vanilla story data)
* runtime ``<tw-passagedata>`` nodes (vanilla + merged mod passages)
* ``SugarCube.Story.lookup('passages')`` titles (playable passages)
* ``SugarCube.Macro.has(name)`` for names that are widget definitions instead
  of playable passages

Every runtime-only name is attributed to an embedded mod by scanning that
mod's twee/text entries for ``:: Name`` definitions. Payloads whose content is
encrypted (``.crypt`` / ``.salt`` / ``.nonce``) are reported as opaque: their
inner passages can only be observed through runtime behaviour, never by
reading the archive.

``--write-list`` emits the playable runtime-only names so
``passage_sweep --only-file <list> --allow-runtime-only`` can sweep them.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):  # allow ``python tools/mod_passage_inventory.py``
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import browser_smoke_test as bst  # noqa: E402
from tools import passage_sweep as ps  # noqa: E402
from tools.artifact_inspection import (  # noqa: E402
    decode_base64_payload,
    load_html_artifact,
    parse_boot_json,
    parse_mod_data_value_zip_list,
)

DEFAULT_OUT = Path(".local/sweep/mod-inventory")
DEFAULT_MAX_ENTRY_BYTES = 2 * 1024 * 1024

# A twee passage header is a line that starts with ``::`` followed by the name
# and an optional ``[tag]`` block. Anchored to line starts so prose that merely
# mentions "::" is not picked up.
TWEE_PASSAGE_LINE = re.compile(
    r"^::\s*(?P<name>[^\[\{\n]+?)\s*(?:\[[^\]]*\])?\s*$", re.MULTILINE
)
TWEE_WIDGET_DECL = re.compile(
    r"<<widget\s+(?:\"(?P<double>[^\"]+)\"|'(?P<single>[^']+)'|(?P<bare>[A-Za-z_][\w.-]*))"
)
TEXT_ENTRY_SUFFIXES = (
    ".twee",
    ".tw",
    ".txt",
    ".md",
    ".json",
    ".js",
    ".css",
    ".html",
)
ENCRYPTED_MARKERS = (".crypt", ".salt", ".nonce")


@dataclass
class ModPayload:
    """One embedded ModLoader payload (a base64 zip inside the HTML)."""

    index: int
    name: str
    version: str | None
    entry_names: list[str] = field(default_factory=list)
    twee_passages: list[str] = field(default_factory=list)
    widget_by_passage: dict[str, str] = field(default_factory=dict)
    encrypted: bool = False
    encryption_markers: list[str] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "index": self.index,
            "name": self.name,
            "version": self.version,
            "entries": len(self.entry_names),
            "twee_passages": len(self.twee_passages),
            "widgets": len(self.widget_by_passage),
            "encrypted": self.encrypted,
        }
        if self.encryption_markers:
            payload["encryption_markers"] = list(self.encryption_markers)
        if self.error:
            payload["error"] = self.error
        return payload


def extract_twee_passage_names(text: str, *, limit: int = 5000) -> list[str]:
    """Return passage names declared by ``:: Name [tags]`` lines in text."""
    return list(extract_twee_passages(text, limit=limit))


def extract_twee_passages(text: str, *, limit: int = 5000) -> dict[str, str]:
    """Split twee text into ``{passage name: body}`` blocks."""
    blocks: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = TWEE_PASSAGE_LINE.match(line)
        if match:
            if current is not None:
                blocks.setdefault(current, "\n".join(body))
            if len(blocks) >= limit:
                current = None
                break
            name = match.group("name").strip()
            current = name if name and len(name) <= 200 else None
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        blocks.setdefault(current, "\n".join(body))
    return blocks


def extract_widget_name(body: str) -> str | None:
    """Return the widget macro declared in a twee passage body, if any."""
    match = TWEE_WIDGET_DECL.search(body)
    if not match:
        return None
    return match.group("double") or match.group("single") or match.group("bare")


def _encryption_markers(entry_names: Iterable[str]) -> list[str]:
    markers: list[str] = []
    for name in entry_names:
        lowered = name.lower()
        if lowered.endswith(ENCRYPTED_MARKERS):
            markers.append(name)
    return markers


def scan_mod_payloads(
    html: str,
    *,
    max_entry_bytes: int = DEFAULT_MAX_ENTRY_BYTES,
) -> tuple[list[ModPayload], list[str]]:
    """Decode every embedded mod payload into name/version/twee records."""
    parsed = parse_mod_data_value_zip_list(html)
    if parsed.error_kind:
        detail = f"{parsed.error_kind}: {parsed.error or ''}".strip()
        return [], [detail]

    payloads: list[ModPayload] = []
    errors: list[str] = []
    for index, entry in enumerate(parsed.entries):
        if not isinstance(entry, str):
            errors.append(f"embedded entry {index} is not a base64 string")
            continue
        try:
            raw = decode_base64_payload(entry)
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                entry_names = zf.namelist()
                boot: dict[str, Any] = {}
                if "boot.json" in entry_names:
                    boot = parse_boot_json(zf.read("boot.json").decode("utf-8-sig"))
                payload = ModPayload(
                    index=index,
                    name=str(boot.get("name") or boot.get("nickName") or f"entry-{index}"),
                    version=str(boot.get("version")) if boot.get("version") is not None else None,
                    entry_names=list(entry_names),
                )
                markers = _encryption_markers(entry_names)
                payload.encryption_markers = markers
                payload.encrypted = bool(markers)
                passages: list[str] = []
                widget_by_passage: dict[str, str] = {}
                for member in entry_names:
                    lowered = member.lower()
                    if not lowered.endswith(TEXT_ENTRY_SUFFIXES):
                        continue
                    try:
                        info = zf.getinfo(member)
                    except KeyError:  # pragma: no cover - namelist/getinfo race
                        continue
                    if info.file_size > max_entry_bytes:
                        continue
                    try:
                        text = zf.read(member).decode("utf-8", "replace")
                    except Exception:  # noqa: BLE001 - best-effort attribution
                        continue
                    for name, body in extract_twee_passages(text).items():
                        passages.append(name)
                        widget = extract_widget_name(body)
                        if widget:
                            widget_by_passage.setdefault(name, widget)
                payload.twee_passages = list(dict.fromkeys(passages))
                payload.widget_by_passage = widget_by_passage
        except Exception as exc:  # noqa: BLE001 - report, never crash the scan
            errors.append(f"embedded entry {index} unreadable: {type(exc).__name__}: {exc}")
            continue
        payloads.append(payload)
    return payloads, errors


def attribute_passages(payloads: list[ModPayload]) -> dict[str, list[str]]:
    """Map passage name -> contributing mod names (sorted, de-duplicated)."""
    attribution: dict[str, list[str]] = {}
    for payload in payloads:
        for name in payload.twee_passages:
            attribution.setdefault(name, [])
            if payload.name not in attribution[name]:
                attribution[name].append(payload.name)
    return {name: sorted(mods) for name, mods in attribution.items()}


def classify_mod_passages(
    static_names: Iterable[str],
    runtime_dom: Iterable[str],
    classification: dict[str, dict[str, Any]],
    *,
    widget_names: dict[str, str] | None = None,
    widget_registry: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Split runtime-only names into playable / widget / unregistered.

    ``widget_names`` maps a mod passage to the widget macro it declares (the
    passage title and the macro name often differ, e.g. ``CE_moneyCheat``
    declares ``<<widget "moneyCheat">>``); ``widget_registry`` records whether
    each declared macro was registered at the time of the snapshot.
    """
    static_set = {str(name) for name in static_names}
    runtime_only = sorted({str(name) for name in runtime_dom} - static_set)
    widget_names = widget_names or {}
    widget_registry = widget_registry or {}
    playable: list[str] = []
    widgets: list[str] = []
    unregistered: list[str] = []
    rows: list[dict[str, Any]] = []
    for name in runtime_only:
        row = classification.get(name) or {}
        tags = str(row.get("tags") or "")
        declared_widget = widget_names.get(name)
        if row.get("storyHas") is True:
            status = "playable"
            playable.append(name)
        elif "widget" in tags.lower() or row.get("macroHas") is True or declared_widget:
            status = "widget"
            widgets.append(name)
        else:
            status = "unregistered"
            unregistered.append(name)
        entry: dict[str, Any] = {"name": name, "status": status, "tags": tags}
        if declared_widget:
            entry["widget"] = declared_widget
            entry["macro_registered"] = bool(widget_registry.get(declared_widget))
        rows.append(entry)
    return {
        "runtime_only": runtime_only,
        "playable": playable,
        "widget": widgets,
        "unregistered": unregistered,
        "rows": rows,
    }


def write_passage_list(path: Path, names: Iterable[str]) -> Path:
    """Write a ``passage_sweep --only-file`` list (empty file when no names)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(str(name) for name in names)
    path.write_text(f"{text}\n" if text else "", encoding="utf-8")
    return path


def _enumerate_script() -> str:
    return r"""
    () => {
      const S = window.SugarCube || {};
      const errors = [];
      let story = [];
      try {
        story = (S.Story && S.Story.lookup)
          ? S.Story.lookup('passages').map((passage) => passage.title)
          : [];
      } catch (error) {
        errors.push('story.lookup: ' + String(error).slice(0, 200));
      }
      const dom = Array.from(document.querySelectorAll('tw-passagedata'))
        .map((node) => node.getAttribute('name') || '');
      return { dom, story, errors };
    }
    """


def _classify_script() -> str:
    return r"""
    (payload) => {
      const S = window.SugarCube || {};
      const names = payload.names || [];
      const widgets = payload.widgets || [];
      const wanted = new Set(names);
      const tagsByName = {};
      for (const node of document.querySelectorAll('tw-passagedata')) {
        const name = node.getAttribute('name');
        if (name && wanted.has(name)) tagsByName[name] = node.getAttribute('tags') || '';
      }
      const out = { passages: {}, widgets: {} };
      for (const name of names) {
        let storyHas = false;
        let macroHas = false;
        try { storyHas = Boolean(S.Story && S.Story.has && S.Story.has(name)); }
        catch (error) { storyHas = false; }
        try { macroHas = Boolean(S.Macro && S.Macro.has && S.Macro.has(name)); }
        catch (error) { macroHas = false; }
        out.passages[name] = { storyHas, macroHas, tags: tagsByName[name] || '' };
      }
      for (const name of widgets) {
        let registered = false;
        try { registered = Boolean(S.Macro && S.Macro.has && S.Macro.has(name)); }
        catch (error) { registered = false; }
        out.widgets[name] = { registered };
      }
      return out;
    }
    """


def measure_runtime(
    html_path: Path,
    *,
    static_names: Iterable[str],
    declared_widgets: Iterable[str] = (),
    boot_steps: int = ps.STARTUP_STEPS,
    deadline_s: float = ps.STARTUP_DEADLINE_S,
    headless: bool = True,
    probe_js: str | None = None,
) -> dict[str, Any]:
    """Boot the carrier once and return the runtime passage surface.

    The classification of runtime-only names happens inside the same session:
    a second cold boot would double the wall-clock cost on CI runners.
    """
    from playwright.sync_api import sync_playwright

    result: dict[str, Any] = {
        "boot": None,
        "probe": None,
        "dom": [],
        "story": [],
        "classification": {},
        "widget_registry": {},
        "errors": [],
    }
    static_set = {str(name) for name in static_names}
    serve_dir = html_path.parent
    with bst._serve_directory(serve_dir) as server, sync_playwright() as pw:
        url = bst._relative_url(server, serve_dir, html_path)
        browser = ps._launch_browser(pw, headless)
        context = browser.new_context()
        context.add_init_script(ps.INIT_HARNESS)
        page = context.new_page()
        try:
            page.goto(url)
            boot = ps._reach_gameplay(page, steps=boot_steps, deadline_s=deadline_s)
            result["boot"] = {
                key: boot.get(key)
                for key in ("steps", "passage", "elapsed_ms", "deadline_hit", "skip_keys")
            }
            if probe_js:
                try:
                    result["probe"] = page.evaluate(probe_js)
                except Exception as exc:  # noqa: BLE001 - probe is best-effort
                    result["errors"].append(f"probe failed: {type(exc).__name__}: {exc}")
            if not boot.get("passage"):
                result["errors"].append(
                    "bootstrap did not leave the startup passage; "
                    "runtime inventory would be empty"
                )
                return result
            data = page.evaluate(_enumerate_script())
            result["dom"] = list(dict.fromkeys(str(name) for name in data.get("dom", [])))
            result["story"] = list(dict.fromkeys(str(name) for name in data.get("story", [])))
            result["errors"].extend(str(item) for item in data.get("errors", []))
            runtime_only = sorted(set(result["dom"]) - static_set)
            if runtime_only:
                data = page.evaluate(
                    _classify_script(),
                    {"names": runtime_only, "widgets": sorted(set(declared_widgets))},
                )
                result["classification"] = data.get("passages", {})
                result["widget_registry"] = {
                    name: bool(row.get("registered"))
                    for name, row in (data.get("widgets") or {}).items()
                }
            return result
        finally:
            browser.close()


def render_markdown(report: dict[str, Any]) -> str:
    counts = report.get("counts", {})
    lines: list[str] = [
        "# Mod passage inventory",
        "",
        f"- target: `{report.get('target')}`",
        f"- html sha256: `{report.get('html_sha256')}`",
        f"- generated: {report.get('generated_at')}",
        "",
        "## Counts",
        "",
        "| 指标 | 数量 |",
        "| --- | --- |",
        f"| 静态文件 passage | {counts.get('static')} |",
        f"| 运行时 DOM passage | {counts.get('runtime_dom')} |",
        f"| 运行时 Story.lookup passage | {counts.get('runtime_story')} |",
        f"| 运行时独有（mod 合并） | {counts.get('runtime_only')} |",
        f"| \\u2513 可游玩 passage | {counts.get('playable')} |",
        f"| \\u2513 widget 定义 | {counts.get('widget')} |",
        f"| \\u2513 未注册（懒加载/入口未触发） | {counts.get('unregistered')} |",
        f"| 声明的 widget 宏 | {counts.get('declared_widgets')} |",
        f"| \\u2513 启动时已注册 | {counts.get('registered_widgets')} |",
        f"| 加密（不透明）mod | {counts.get('encrypted_mods')} |",
        "",
    ]
    rows = report.get("mod_passages", [])
    if rows:
        lines += [
            "## Runtime-only passages",
            "",
            "`widget` = 该 passage 是 `<<widget>>` 定义（标题与宏名可能不同）；"
            "`unregistered` = 定义存在但启动快照时 `Story.has` / widget 注册都还没有"
            "（mod 懒加载，需先触发mod入口再复测）。",
            "",
            "| passage | 状态 | widget 宏 | 启动时已注册 | 来源 mod |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            source = ", ".join(row.get("source_mods") or []) or "(未在 payload 中找到 :: 定义)"
            widget = row.get("widget") or ""
            registered = row.get("macro_registered")
            registered_text = "" if registered is None else ("yes" if registered else "no")
            lines.append(
                f"| {row.get('name')} | {row.get('status')} | {widget} | {registered_text} | {source} |"
            )
        lines.append("")
    widgets = report.get("widgets", [])
    if widgets:
        lines += [
            "## Widget 宏（静态声明 + 启动快照）",
            "",
            "| widget | 来源 mod | 启动时已注册 |",
            "| --- | --- | --- |",
        ]
        for row in widgets:
            lines.append(
                f"| {row.get('widget')} | {row.get('source_mod')} | "
                f"{'yes' if row.get('registered') else 'no'} |"
            )
        lines.append("")
    opaque = report.get("opaque_mods", [])
    if opaque:
        lines += [
            "## 加密 / 不透明 mod",
            "",
            "这些 payload 的内层内容是密文，静态侧只能看到外层文件；"
            "它们的 passage / widget 只能通过运行时行为（Engine A 真机、Engine B MuMu）验证。",
            "",
            "| mod | 版本 | 标记 |",
            "| --- | --- | --- |",
        ]
        for mod in opaque:
            markers = ", ".join(mod.get("encryption_markers") or []) or "?"
            lines.append(f"| {mod.get('name')} | {mod.get('version')} | {markers} |")
        lines.append("")
    errors = report.get("errors") or []
    if errors:
        lines += ["## Errors", ""] + [f"- {item}" for item in errors] + [""]
    return "\n".join(lines)


def build_report(
    html_path: Path,
    *,
    boot_steps: int,
    deadline_s: float,
    headless: bool,
    probe_js: str | None = None,
    write_list: Path | None = None,
) -> dict[str, Any]:
    member, html = load_html_artifact(html_path)
    if html is None:
        raise SystemExit(f"no readable HTML found in {html_path}")
    # ZIP/APK carriers are resolved to a real HTML file (temp-extracted when
    # needed) so the static parse and the local server see the same document.
    resolved_html = ps.resolve_html_path(html_path)

    static_passages, _target = ps.extract_passages(resolved_html)
    static_names = [passage.name for passage in static_passages]
    payloads, scan_errors = scan_mod_payloads(html)
    static_attribution = attribute_passages(payloads)
    widget_names: dict[str, str] = {}
    widget_mods: dict[str, str] = {}
    for payload in payloads:
        for passage_name, widget in payload.widget_by_passage.items():
            widget_names.setdefault(passage_name, widget)
            widget_mods.setdefault(widget, payload.name)

    runtime = measure_runtime(
        resolved_html,
        static_names=static_names,
        declared_widgets=widget_mods,
        boot_steps=boot_steps,
        deadline_s=deadline_s,
        headless=headless,
        probe_js=probe_js,
    )
    split = classify_mod_passages(
        static_names,
        runtime["dom"],
        runtime["classification"],
        widget_names=widget_names,
        widget_registry=runtime["widget_registry"],
    )

    status_by_name = {
        **{name: "playable" for name in split["playable"]},
        **{name: "widget" for name in split["widget"]},
        **{name: "unregistered" for name in split["unregistered"]},
    }
    mod_rows = [
        {
            **row,
            "status": status_by_name.get(row["name"], row.get("status", "unknown")),
            "source_mods": static_attribution.get(row["name"], []),
        }
        for row in split["rows"]
    ]
    widget_rows = [
        {
            "widget": name,
            "source_mod": widget_mods.get(name),
            "registered": bool(runtime["widget_registry"].get(name)),
        }
        for name in sorted(widget_mods)
    ]
    opaque_mods = [
        {
            "name": payload.name,
            "version": payload.version,
            "encryption_markers": payload.encryption_markers,
        }
        for payload in payloads
        if payload.encrypted
    ]

    report: dict[str, Any] = {
        "tool": "dol-x-mod-passage-inventory",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": str(html_path),
        "resolved_html": str(resolved_html),
        "html_member": member,
        "html_sha256": hashlib.sha256(html.encode("utf-8", "replace")).hexdigest(),
        "counts": {
            "static": len(static_names),
            "runtime_dom": len(runtime["dom"]),
            "runtime_story": len(runtime["story"]),
            "runtime_only": len(split["runtime_only"]),
            "playable": len(split["playable"]),
            "widget": len(split["widget"]),
            "unregistered": len(split["unregistered"]),
            "encrypted_mods": len(opaque_mods),
        },
        "static_missing_from_runtime": sorted(set(static_names) - set(runtime["dom"])),
        "mod_passages": mod_rows,
        "widgets": widget_rows,
        "write_list": str(write_list) if write_list else None,
        "playable_names": split["playable"],
        "widget_names": split["widget"],
        "unregistered_names": split["unregistered"],
        "mods": [payload.to_json() for payload in payloads],
        "opaque_mods": opaque_mods,
        "boot": runtime["boot"],
        "probe": runtime["probe"],
        "errors": [*scan_errors, *runtime["errors"]],
    }
    report["counts"]["declared_widgets"] = len(widget_rows)
    report["counts"]["registered_widgets"] = sum(
        1 for row in widget_rows if row["registered"]
    )

    if write_list:
        write_passage_list(write_list, split["playable"])
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target", type=Path, help="built HTML / ZIP / APK carrier")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="report directory")
    p.add_argument("--json", type=Path, default=None, help="explicit JSON report path")
    p.add_argument("--md", type=Path, default=None, help="explicit Markdown report path")
    p.add_argument(
        "--write-list",
        type=Path,
        default=None,
        help="write playable runtime-only passage names for passage_sweep --only-file",
    )
    p.add_argument("--boot-steps", type=int, default=ps.STARTUP_STEPS)
    p.add_argument("--deadline-seconds", type=float, default=ps.STARTUP_DEADLINE_S)
    p.add_argument("--headful", action="store_true", help="run the browser headed")
    p.add_argument(
        "--probe-js",
        type=Path,
        default=None,
        help="optional JS file evaluated after bootstrap and before classification",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.target.exists():
        raise SystemExit(f"target not found: {args.target}")
    probe_js = args.probe_js.read_text(encoding="utf-8") if args.probe_js else None
    report = build_report(
        args.target,
        boot_steps=args.boot_steps,
        deadline_s=args.deadline_seconds,
        headless=not args.headful,
        probe_js=probe_js,
        write_list=args.write_list,
    )
    json_path = args.json or (args.out / "mod-passage-inventory.json")
    md_path = args.md or (args.out / "mod-passage-inventory.md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    counts = report["counts"]
    print(
        "[mod-inventory] "
        f"static={counts['static']} runtime_dom={counts['runtime_dom']} "
        f"runtime_only={counts['runtime_only']} playable={counts['playable']} "
        f"widget={counts['widget']} unregistered={counts['unregistered']} "
        f"encrypted_mods={counts['encrypted_mods']}"
    )
    for name in report["playable_names"]:
        print(f"[mod-inventory] playable: {name}")
    print(f"[mod-inventory] report -> {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
