#!/usr/bin/env python3
"""DOL-X combat coverage ledger (static, engine A).

``tools/combat_sweep.py`` answers "can this initiator actually start a fight".
This tool answers the audit question that has to hold *before* a multi-hour
sweep is worth anything: **for every one of the ~1,570 scanned initiator rows,
what is the source evidence for how it is reached, and what did the last run
say about it?**

Each row gets a deterministic classification built only from the artifact text:

* ``sexual_encounter`` - the passage is a consensual sex scene gated by
  ``$sexstart``; it reuses the combat renderer but has no enemy-defeat
  objective, so the combat axis records it as ``not_applicable``.
* ``widget_definition`` - the macro call sits inside a ``<<widget "x">>`` body
  in a widget-library passage; it is not a clickable entry by itself.
* ``entry`` - the passage itself carries a combat starter macro
  (``<<maninit>>`` / ``<<beastCombatInit>>`` / ...).
* ``entry_via_link`` - the passage only generates; one in-passage link leads to
  a passage that starts combat (``find_combat_link_target``).
* ``helper_only`` - no starter and no link; the row is a generation/init macro
  that the game calls from elsewhere.
* ``unresolved`` - nothing derivable from the artifact: no starter, no link and
  no predecessor chain. This is the fail-closed bucket that must stay empty or
  be listed with a reason.

``derivation_kind`` records which game-side preamble the sweep replays
(``upstream_predecessor`` / ``synthetic_generator`` / ``named_npc`` / ...), so
the coverage claim "this row can be entered" can be audited against the exact
``<<generate1>>``-style chain in the JSON.

``--report`` joins a previous ``combat_sweep`` JSON so the ledger also carries
the last runtime verdict per row. The ledger never rewrites the report and
never treats "not_applicable" as proof by itself.

Usage:
    python tools/combat_ledger.py <target.html|zip> \
        --report .local/sweep/full-1006-combat/combat-sweep.json \
        --out .local/sweep/combat-ledger
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import combat_sweep as cs  # noqa: E402
from tools import passage_sweep as ps  # noqa: E402


TOOL = "combat_ledger"
DEFAULT_OUT = Path(".local/sweep/combat-ledger")
# ``<<set $NPCList[0] to $dock_dog>>`` restores a beast the current scene never
# generated itself (the dog was cloned in an earlier scene). When the row is a
# token-less ``beastCombatInit`` and no static beast token exists, that saved
# variable is the only source evidence of where the beast comes from.
SAVED_NPC_RE = re.compile(r"<<set\s+\$NPCList\[\d+\]\s+to\s+\$([A-Za-z_][\w.]*)\s*>>")


def candidate_precursors(
    passage: str,
    *,
    passage_bodies: Mapping[str, str],
    widget_bodies: Mapping[str, str],
    max_depth: int = cs.DEEP_PRECURSOR_DEPTH,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Unverified beast tokens found in the upstream link graph.

    A token-less ``<<beastCombatInit>>`` reads whatever ``$beasttype`` the real
    playthrough set earlier, so a token found three or four links back is a
    *hypothesis*: the ledger records it (with depth, passage and widget
    provenance) so "not covered" rows come with a concrete next experiment.
    Thin wrapper over ``combat_sweep.deep_beast_precursors`` so the ledger and
    the sweep always agree on the candidate set.
    """
    return cs.deep_beast_precursors(
        passage,
        passage_bodies=passage_bodies,
        widget_bodies=widget_bodies,
        max_depth=max_depth,
        limit=limit,
    )


ENTRY_SHAPES = (
    "entry",
    "entry_via_link",
    "sexual_encounter",
    "widget_definition",
    "helper_only",
    "unresolved",
)
DERIVATION_KINDS = (
    "upstream_predecessor",
    "deep_predecessor",
    "synthetic_generator",
    "named_npc",
    "named_npc_plus_generator",
    "beast_token",
    "named_beast_npc",
    "self_generation",
    "not_needed",
    "unresolved",
    "other",
)


def derivation_kind(basis: str | None, reason: str | None) -> str:
    """Map a ``derive_precursor`` basis string to an auditable kind."""
    if not basis:
        if reason and "no NPC hand/frontarm dependency" in reason:
            # Deliberate: wraith / swarm / stalk / plant scenes drive their own
            # action widgets and never touch ``$NPCList`` hand state.
            return "not_needed"
        return "unresolved" if reason else "not_needed"
    head = basis.split("|", 1)[0]
    if head.startswith("deep-predecessor:"):
        # Low-confidence: the token was found 3-4 link hops back (or inside a
        # widget a parent calls), not in the entry's immediate predecessor.
        return "deep_predecessor"
    if head.startswith("predecessor:"):
        return "upstream_predecessor"
    if head.startswith("debug-menu:"):
        return "synthetic_generator"
    if head.startswith("title-npc:"):
        return "named_npc_plus_generator" if "+generate" in head else "named_npc"
    if head.startswith("row-token-nnpc:"):
        return "named_beast_npc"
    if head.startswith("title-nnpc:"):
        return "named_beast_npc"
    if head.startswith("row-token:"):
        return "beast_token"
    if head.startswith("self-generation:"):
        return "self_generation"
    return "other"


def widget_spans(body: str) -> list[tuple[int, int, str]]:
    """``(start, end, name)`` for every ``<<widget>>`` definition in ``body``."""
    return [
        (match.start(), match.end(), str(match.group(1)))
        for match in cs.WIDGET_DEF_RE.finditer(str(body or ""))
    ]


def call_site(row: Mapping[str, Any], body: str) -> tuple[str, str | None]:
    """``("widget", name)`` when the row's macro call is inside a widget def.

    Matching is on macro name plus the row's (already truncated) args prefix,
    which is exactly what ``scan_initiators`` recorded.
    """
    macro = str(row.get("macro") or "")
    args = str(row.get("args") or "")
    if not macro:
        return "passage", None
    spans = widget_spans(body)
    for match in cs.MACRO_CALL_RE.finditer(str(body or "")):
        if match.group(1) != macro:
            continue
        call_args = match.group(2).strip()
        if args and not call_args.startswith(args):
            continue
        for start, end, name in spans:
            if start <= match.start() < end:
                return "widget", name
        return "passage", None
    return "passage", None


def classify_row(
    row: Mapping[str, Any],
    *,
    passage_bodies: Mapping[str, str],
    widget_bodies: Mapping[str, str],
    named_npcs: Sequence[str],
) -> dict[str, Any]:
    """Static classification for one initiator row (no browser)."""
    passage = str(row.get("passage") or "")
    body = str(passage_bodies.get(passage) or "")
    site, widget_name = call_site(row, body)
    # Source evidence for "where does this scene's beast come from" also lives
    # one link-hop back: ``Docks Watch Dog`` itself only restores
    # ``$NPCList[0] = $dock_dog``; the clone was created in ``Docks Watch``.
    evidence_bodies = [(passage, body)]
    for parent in cs._link_predecessors(passage, passage_bodies)[:4]:
        evidence_bodies.append((str(parent), str(passage_bodies.get(parent) or "")))
    saved_refs: dict[str, str] = {}
    for parent, parent_body in evidence_bodies:
        for name in SAVED_NPC_RE.findall(parent_body):
            saved_refs.setdefault(name, parent)
    derived = cs.derive_precursor(
        row,
        passage_bodies=passage_bodies,
        named_npcs=named_npcs,
        widget_bodies=widget_bodies,
    )
    basis = derived.get("basis")
    reason = derived.get("reason")
    kind_state = derivation_kind(basis, reason)
    sexual_reason = (
        cs.sexual_encounter_reason(row, passage_bodies)
        if site != "widget" and not row.get("non_scene")
        else None
    )
    starters = list(row.get("combat_starters") or [])
    link_target = None
    if site != "widget" and not starters:
        link_target = cs.find_combat_link_target(dict(row), passage_bodies)
    if sexual_reason is not None:
        shape = "sexual_encounter"
    elif site == "widget":
        shape = "widget_definition"
    elif starters:
        shape = "entry"
    elif link_target:
        shape = "entry_via_link"
    elif basis or kind_state == "not_needed":
        shape = "helper_only"
    else:
        shape = "unresolved"
    candidates: list[dict[str, Any]] = []
    if kind_state in ("unresolved", "deep_predecessor"):
        candidates = candidate_precursors(
            passage, passage_bodies=passage_bodies, widget_bodies=widget_bodies
        )
    return {
        "key": row.get("key"),
        "kind": row.get("kind"),
        "token": row.get("token"),
        "passage": passage,
        "macro": row.get("macro"),
        "args": row.get("args"),
        "entry_flags": list(row.get("entry_flags") or []),
        "combat_starters": starters,
        "call_site": site,
        "widget": widget_name,
        "entry_shape": shape,
        "sexual_scene_reason": sexual_reason,
        "link_target": link_target,
        "derivation_kind": kind_state,
        "precursor_basis": basis,
        "precursor_reason": reason,
        "precursor_widgets": derived.get("widgets"),
        "saved_npc_refs": sorted(saved_refs),
        "saved_npc_sources": saved_refs,
        "uses_beasttype": any("<<beasttype" in item for _, item in evidence_bodies),
        "candidate_precursors": candidates,
    }


def join_report(
    rows: Sequence[dict[str, Any]], report: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Attach runtime verdicts by initiator key; never invent a verdict."""
    summary: dict[str, Any] = {"report": None, "joined": 0, "unknown": 0}
    if not report:
        return summary
    results = {
        str(item.get("key")): item
        for item in report.get("results") or []
        if item.get("key")
    }
    summary["report"] = {
        "target": report.get("target"),
        "tier": report.get("tier"),
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "verdict_counts": report.get("verdict_counts"),
    }
    for row in rows:
        item = results.get(str(row.get("key")))
        if item is None:
            row["runtime"] = None
            summary["unknown"] += 1
            continue
        row["runtime"] = {
            "verdict": item.get("verdict"),
            "detail": item.get("detail"),
            "missing": item.get("missing"),
            "combat": item.get("combat"),
        }
        summary["joined"] += 1
    return summary


def summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    shape_counts = collections.Counter(row["entry_shape"] for row in rows)
    derivation_counts = collections.Counter(row["derivation_kind"] for row in rows)
    kind_counts = collections.Counter(str(row["kind"]) for row in rows)
    crosstab: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = crosstab.setdefault(
            str(row["kind"]), collections.Counter()  # type: ignore[arg-type]
        )
        bucket[str(row["entry_shape"])] += 1
    verdict_by_derivation: dict[str, dict[str, int]] = {}
    for row in rows:
        runtime = row.get("runtime")
        if not runtime:
            continue
        bucket = verdict_by_derivation.setdefault(
            str(row["derivation_kind"]), collections.Counter()  # type: ignore[arg-type]
        )
        bucket[str(runtime.get("verdict"))] += 1
    return {
        "total": len(rows),
        "entry_shapes": {shape: shape_counts.get(shape, 0) for shape in ENTRY_SHAPES},
        "derivation_kinds": {
            kind: derivation_counts.get(kind, 0) for kind in DERIVATION_KINDS
        },
        "by_kind": dict(sorted(kind_counts.items())),
        "kind_by_shape": {
            kind: dict(sorted(bucket.items()))
            for kind, bucket in sorted(crosstab.items())
        },
        "verdict_by_derivation": {
            kind: dict(sorted(bucket.items()))
            for kind, bucket in sorted(verdict_by_derivation.items())
        },
    }


def work_list(rows: Sequence[dict[str, Any]], limit: int = 120) -> list[dict[str, Any]]:
    """Rows that need fixture/predecessor work, in a stable order."""
    todo = [
        row
        for row in rows
        if row["entry_shape"] in ("unresolved", "helper_only")
        or row["derivation_kind"] in ("synthetic_generator", "unresolved")
    ]
    todo.sort(
        key=lambda row: (
            str(row["derivation_kind"]),
            str(row["kind"]),
            str(row["passage"]),
        )
    )
    return todo[:limit]


def not_covered(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows with no static derivation at all — the honest "未覆盖" list.

    These are not silently dropped: every one carries the reason string from
    ``derive_precursor`` plus whatever source evidence the entry passage holds
    (saved-NPC restores such as ``$dock_dog``, ``$beasttype`` usage).
    """
    todo = [row for row in rows if row["derivation_kind"] == "unresolved"]
    todo.sort(key=lambda row: (str(row["kind"]), str(row["passage"])))
    return todo


def deep_derivations(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows whose fixture comes from the low-confidence deep fallback."""
    todo = [row for row in rows if row["derivation_kind"] == "deep_predecessor"]
    todo.sort(key=lambda row: (str(row["kind"]), str(row["passage"])))
    return todo


def render_markdown(ledger: Mapping[str, Any], *, limit: int = 120) -> str:
    lines: list[str] = []
    lines.append("# Combat coverage ledger (static)")
    lines.append("")
    lines.append(f"- tool: `{ledger['tool']}`")
    lines.append(f"- target: `{ledger['target']}`")
    lines.append(f"- html: `{ledger['html_path']}`")
    lines.append(f"- html sha256: `{ledger['html_sha256']}`")
    lines.append(f"- generated: {ledger['generated_at']}")
    lines.append(f"- rows: **{ledger['summary']['total']}**")
    drift = ledger.get("drift") or {}
    lines.append(f"- 口径 drift ok: `{drift.get('ok')}` ({drift.get('count', 0)} diffs)")
    lines.append("")
    lines.append("## Entry shapes")
    lines.append("")
    lines.append("| shape | rows |")
    lines.append("| --- | --- |")
    for shape in ENTRY_SHAPES:
        lines.append(f"| `{shape}` | {ledger['summary']['entry_shapes'].get(shape, 0)} |")
    lines.append("")
    lines.append("## Derivation kinds")
    lines.append("")
    lines.append("| kind | rows |")
    lines.append("| --- | --- |")
    for kind in DERIVATION_KINDS:
        count = ledger["summary"]["derivation_kinds"].get(kind, 0)
        if count:
            lines.append(f"| `{kind}` | {count} |")
    lines.append("")
    runtime = ledger.get("runtime_join") or {}
    if runtime.get("report"):
        lines.append("## Runtime join")
        lines.append("")
        lines.append(f"- report: `{runtime['report'].get('target')}` "
                     f"({runtime['report'].get('started_at')} .. "
                     f"{runtime['report'].get('finished_at')})")
        lines.append(f"- joined: {runtime.get('joined')} / "
                     f"unknown: {runtime.get('unknown')}")
        counts = runtime["report"].get("verdict_counts") or {}
        lines.append(f"- verdicts: `{json.dumps(counts, ensure_ascii=False)}`")
        lines.append("")
        lines.append("| derivation | verdict | rows |")
        lines.append("| --- | --- | --- |")
        for kind, bucket in ledger["summary"]["verdict_by_derivation"].items():
            for verdict, count in bucket.items():
                lines.append(f"| `{kind}` | `{verdict}` | {count} |")
        lines.append("")
    todo = ledger.get("work_list") or []
    lines.append(f"## Work list (first {len(todo)} of "
                 f"{ledger['summary']['work_total']})")
    lines.append("")
    lines.append("| key | shape | derivation | basis / reason |")
    lines.append("| --- | --- | --- | --- |")
    for row in todo:
        evidence = row.get("precursor_basis") or row.get("precursor_reason") or ""
        evidence = str(evidence).replace("|", "\\|")
        lines.append(
            f"| `{row['key']}` | `{row['entry_shape']}` | "
            f"`{row['derivation_kind']}` | {evidence} |"
        )
    lines.append("")
    lines.append("Full per-row source evidence lives in `combat-ledger.json`; "
                 "each row also carries `args` / `entry_flags` / `combat_starters`.")
    lines.append("")
    uncovered = ledger.get("not_covered") or []
    lines.append(f"## Not covered (no static derivation): {len(uncovered)}")
    lines.append("")
    if uncovered:
        lines.append(
            "| key | entry shape | reason | saved NPC | beasttype | candidate tokens (unverified) |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in uncovered:
            reason = str(row.get("precursor_reason") or "").replace("|", "\\|")
            sources = row.get("saved_npc_sources") or {}
            saved = ", ".join(
                f"`${item}` @ `{sources.get(item, '?')}`"
                for item in row.get("saved_npc_refs") or []
            )
            candidates = ", ".join(
                f"`{item.get('token')}` @ `{item.get('source')}`"
                f"(d{item.get('depth')}/{item.get('via')})"
                for item in row.get("candidate_precursors") or []
            )
            lines.append(
                f"| `{row['key']}` | `{row['entry_shape']}` | {reason} | "
                f"{saved or '-'} | {'yes' if row.get('uses_beasttype') else '-'} | "
                f"{candidates or '-'} |"
            )
    else:
        lines.append("(none)")
    lines.append("")
    deep = ledger.get("deep_derivations") or []
    lines.append(
        f"## Deep (low-confidence) derivations: {len(deep)}"
    )
    lines.append("")
    if deep:
        lines.append(
            "Token-less beast rows whose `$beasttype` source sits 3-4 link hops back "
            "(or inside a widget a parent calls). The sweep replays this chain and "
            "tags the result `confidence: low`; the candidate list below is the "
            "audit trail."
        )
        lines.append("")
        lines.append("| key | basis | token | candidates |")
        lines.append("| --- | --- | --- | --- |")
        for row in deep:
            basis = str(row.get("precursor_basis") or "").replace("|", "\\|")
            candidates = ", ".join(
                f"`{item.get('token')}` @ `{item.get('source')}`"
                f"(d{item.get('depth')}/{item.get('via')})"
                for item in row.get("candidate_precursors") or []
            )
            lines.append(
                f"| `{row['key']}` | {basis} | "
                f"`{row.get('token') or '-'}` | {candidates or '-'} |"
            )
    else:
        lines.append("(none)")
    lines.append("")
    return "\n".join(lines)


def build_ledger(
    target: Path,
    *,
    report_path: Path | None = None,
    fixture_path: Path | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    html_text, _ = ps._html_payload(target)
    html_path = ps.resolve_html_path(target)
    if manifest is None:
        manifest = cs.scan_initiators(html_text)
    rows = [dict(row) for row in manifest.get("rows") or []]
    passage_bodies: dict[str, str] = {}
    for passage in ps.extract_passages(target)[0]:
        passage_bodies[passage.name] = passage.body
    widget_bodies = cs.build_widget_index(passage_bodies)
    named_npcs: list[str] = []
    if fixture_path is not None and Path(fixture_path).exists():
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        variables = payload.get("variables") or {}
        named_npcs = [
            str(item) for item in (variables.get("NPCNameList") or []) if str(item).strip()
        ]
    report = None
    if report_path is not None:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    classified = [
        classify_row(
            row,
            passage_bodies=passage_bodies,
            widget_bodies=widget_bodies,
            named_npcs=named_npcs,
        )
        for row in rows
    ]
    runtime_join = join_report(classified, report)
    summary = summarise(classified)
    summary["work_total"] = len(work_list(classified, limit=len(classified) or 1))
    uncovered = not_covered(classified)
    deep = deep_derivations(classified)
    summary["not_covered_total"] = len(uncovered)
    summary["deep_total"] = len(deep)
    ledger = {
        "tool": TOOL,
        "target": str(target),
        "html_path": str(html_path),
        "html_sha256": ps.file_sha256(html_path),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "manifest": {
            "total": manifest.get("total"),
            "passages": manifest.get("passages"),
            "by_kind": manifest.get("by_kind"),
            "by_token": manifest.get("by_token"),
        },
        "drift": manifest.get("drift"),
        "runtime_join": runtime_join,
        "summary": summary,
        "work_list": work_list(classified),
        "not_covered": uncovered,
        "deep_derivations": deep,
        "rows": classified,
    }
    return ledger


def write_outputs(ledger: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "combat-ledger.json"
    md_path = out_dir / "combat-ledger.md"
    json_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(render_markdown(ledger), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DOL-X combat coverage ledger (static, engine A)"
    )
    parser.add_argument("target", type=Path, help="built .html or .zip to audit")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="reuse a scan_initiators JSON instead of re-scanning (optional)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="join a previous combat_sweep JSON (runtime verdicts)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="fixture JSON (NPCNameList feeds named-NPC derivation)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--fail-on-unresolved",
        action="store_true",
        help="exit 1 when the unresolved bucket is non-empty (CI gate)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.target.exists():
        print(f"[ledger] target does not exist: {args.target}")
        return 2
    manifest = None
    if args.manifest is not None:
        if not args.manifest.exists():
            print(f"[ledger] manifest does not exist: {args.manifest}")
            return 2
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ledger = build_ledger(
        args.target,
        report_path=args.report,
        fixture_path=args.fixture,
        manifest=manifest,
    )
    json_path, md_path = write_outputs(ledger, args.out)
    summary = ledger["summary"]
    print(
        f"[ledger] rows={summary['total']} "
        f"unresolved={summary['entry_shapes'].get('unresolved', 0)} "
        f"deep={summary.get('deep_total', 0)} "
        f"work_list={summary['work_total']}",
        flush=True,
    )
    print(f"[ledger] wrote {json_path} and {md_path}", flush=True)
    drift = ledger.get("drift") or {}
    if not drift.get("ok", True):
        print(
            f"[ledger] schema drift: {drift.get('count')} differences vs expectations",
            flush=True,
        )
    if args.fail_on_unresolved and summary["entry_shapes"].get("unresolved", 0):
        print("[ledger] unresolved rows present; failing (--fail-on-unresolved)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
