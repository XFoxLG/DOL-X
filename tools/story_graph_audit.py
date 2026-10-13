"""Story-graph integrity audit over a source index (networkx).

Categories (schema ``dolx.story-graph-audit.v1``):

* ``dead_ends``: referenced passages with no usable static out-edge.
  Exit evidence is classified in layers before anything is called a defect:
  dynamic edges, navigation macros (``pass``/``endevent``/``return``/
  ``next``/``passage``), JS exits, dangling references, navigation widgets,
  the DoL ``effects`` transition widget, settings UI and state widgets
  (``endcombat``/``endevent``).  Only ``dangling_exit`` and ``sealed``
  entries are defect candidates.
* ``undefined_targets``: static references whose target passage is absent.
* ``self_loops``: passages linking to themselves.
* ``defined_without_inbound``: passages no static edge points at.
* ``unreachable_from_entry``: static BFS from the entry (default ``Start``).
  This is informational: DoL's entry navigation is dynamic
  (``$settingsExitPassage``), so the class cannot prove player unreachability.
* Non-executable edges (block comments, HTML comments, ``<<if false>>``
  guards) are removed before the graph is built and reported separately in
  ``non_executable_edges``; text that can never run must not create nodes,
  dangling targets or exits.  This mirrors ``static_reachability_solver``.

Defect candidates are matched against an accepted-upstream list
(``config/accepted-upstream-graph-defects.toml``) by ``category`` plus
``passage``/``target``; everything else stays ``unclassified`` so the
release exploration gate fails closed.  An entry without a reason or any
evidence reference is rejected — the list is not a mute switch.

The HTML body scan (``--html``) is required for the widget/effects/settings
exit layers.  Without it the report is ``index_only`` and the gate must not
claim release readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import networkx as nx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.source_index import HTML_PASSAGE_RE, _html_name
from tools.static_reachability_solver import filter_executable_edges
from tools.sweep_ledger import atomic_write_json


SCHEMA = "dolx.story-graph-audit.v1"
ACCEPTED_SCHEMA = "dolx.accepted-graph-defects.v1"

NAV_FLOW_RE = re.compile(r"<<\s*(?:pass|endevent|return|next|passage)\b", re.IGNORECASE)
JS_EXIT_RE = re.compile(
    r"Engine\.play|State\.display|Config\.navigation|location\.href|\.dialogclose",
    re.IGNORECASE,
)
WIDGET_DEF_RE = re.compile(
    r"<<\s*widget\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", re.IGNORECASE
)
WIDGET_BODY_RE = re.compile(r"<</widget>>", re.IGNORECASE)
WIDGET_NAV_RE = re.compile(
    r"<<\s*(?:goto|link|button|pass|endevent|return|passage)\b|Engine\.play|State\.display",
    re.IGNORECASE,
)
EFFECTS_RE = re.compile(r"<<\s*effects\b", re.IGNORECASE)
SETTINGS_RE = re.compile(r"<<\s*settings(?:Start)?\b", re.IGNORECASE)
STATE_WIDGET_RE = re.compile(r"<<\s*(?:endcombat|endevent)\b", re.IGNORECASE)
# Widget names may contain hyphens (``<<stallShop-main>>``); a plain \w* walk
# would silently truncate them to ``stallShop`` and miss the exit.
CALL_RE = re.compile(r"<<\s*([A-Za-z_][\w-]*)")

# endcombat/endevent clean up combat/event state.  A passage that calls them
# still needs its own navigation, so they must not mask a missing exit.
STATEFUL_WIDGETS = frozenset({"endcombat", "endevent", "startcombat", "combat"})

DEFECT_CLASSES = ("dangling_exit", "sealed")


class AuditError(ValueError):
    """Raised for invalid audit input; the CLI maps this to exit code 2."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_index(path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    index = json.loads(raw.decode("utf-8"))
    if not isinstance(index, Mapping) or index.get("schema") != "dolx.source-index.v1":
        raise AuditError(f"{path} is not a dolx.source-index.v1 document")
    if not isinstance(index.get("passages"), list) or not isinstance(index.get("edges"), list):
        raise AuditError(f"{path} lacks passages/edges arrays")
    return dict(index), _sha256(raw)


def load_html_passages(path: Path) -> tuple[dict[str, str], str]:
    import html as html_module

    raw = Path(path).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    bodies: dict[str, str] = {}
    for match in HTML_PASSAGE_RE.finditer(text):
        name = _html_name(match.group("attrs"))
        if name is not None:
            bodies[html_module.unescape(name)] = html_module.unescape(match.group("body"))
    if not bodies:
        raise AuditError(f"{path} contains no <tw-passagedata> bodies")
    return bodies, _sha256(raw)


def load_accepted(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).exists():
        return []
    with Path(path).open("rb") as handle:
        payload = tomllib.load(handle)
    if payload.get("schema") != ACCEPTED_SCHEMA:
        raise AuditError(f"{path} schema must be {ACCEPTED_SCHEMA}")
    entries = payload.get("accepted") or []
    for position, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise AuditError(f"{path}: accepted[{position}] is not a table")
        if not entry.get("reason") or not entry.get("evidence"):
            raise AuditError(
                f"{path}: accepted[{position}] requires a reason and at least one evidence reference"
            )
        if entry.get("category") not in {"dead_end", "undefined_target", "self_loop", "defined_without_inbound"}:
            raise AuditError(f"{path}: accepted[{position}] has unknown category {entry.get('category')!r}")
        if not (entry.get("passage") or entry.get("target")):
            raise AuditError(f"{path}: accepted[{position}] requires a passage or target key")
    return [dict(entry) for entry in entries]


def match_accepted(
    accepted: Iterable[Mapping[str, Any]], category: str, key: str
) -> dict[str, Any] | None:
    for entry in accepted:
        if entry.get("category") != category:
            continue
        if entry.get("passage") == key or entry.get("target") == key:
            return dict(entry)
    return None


def build_graph(index: Mapping[str, Any]) -> dict[str, Any]:
    names = [str(item.get("name") or "") for item in index.get("passages") or []]
    names = [name for name in names if name]
    nameset = set(names)
    graph = nx.DiGraph()
    graph.add_nodes_from(names)
    dynamic_sources: set[str] = set()
    dangling: dict[str, list[dict[str, Any]]] = {}
    valid_edges: list[dict[str, Any]] = []
    raw_edges = [edge for edge in index.get("edges") or [] if isinstance(edge, Mapping)]
    root_value = index.get("root")
    root = Path(str(root_value)) if root_value else None
    executable_edges, non_executable_edges = filter_executable_edges(raw_edges, root=root)
    for edge in executable_edges:
        kind = edge.get("target_kind")
        source = edge.get("source")
        target = edge.get("target")
        if kind == "dynamic":
            if source:
                dynamic_sources.add(str(source))
            continue
        if kind != "static":
            continue
        if target in nameset:
            graph.add_edge(str(source), str(target))
            valid_edges.append(dict(edge))
        elif target:
            dangling.setdefault(str(target), []).append(dict(edge))
    return {
        "graph": graph,
        "names": names,
        "nameset": nameset,
        "dynamic_sources": dynamic_sources,
        "dangling": dangling,
        "valid_edges": valid_edges,
        "non_executable": non_executable_edges,
    }


def collect_navigation_widgets(bodies: Mapping[str, str]) -> dict[str, str]:
    defined: dict[str, tuple[str, str]] = {}
    for passage_name, body in bodies.items():
        for match in WIDGET_DEF_RE.finditer(body):
            name = match.group(1) or match.group(2) or match.group(3)
            if not name or name in STATEFUL_WIDGETS:
                continue
            rest = body[match.end():]
            end = WIDGET_BODY_RE.search(rest)
            widget_body = rest[: end.start()] if end else rest
            defined[name] = (widget_body, passage_name)

    nav_widgets: dict[str, str] = {
        name: passage_name
        for name, (widget_body, passage_name) in defined.items()
        if WIDGET_NAV_RE.search(widget_body)
    }
    # DoL chains navigation through several widget levels (shops call `-main`
    # widgets, event endings call `destinationeventend`, and so on).  A widget
    # that only calls other navigation widgets still hands the player a way
    # out, so grow the set to a fixed point.
    changed = True
    while changed:
        changed = False
        known = set(nav_widgets)
        for name, (widget_body, passage_name) in defined.items():
            if name in known:
                continue
            if set(CALL_RE.findall(widget_body)) & known:
                nav_widgets[name] = passage_name
                changed = True
    return nav_widgets


def _folded_names(names: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    casefold_map: dict[str, str] = {}
    detokenized_map: dict[str, str] = {}

    def detokenize(value: str) -> str:
        tokens = []
        for token in value.split():
            if len(token) > 3 and token.lower().endswith("s"):
                token = token[:-1]
            tokens.append(token)
        return " ".join(tokens).casefold()

    for name in names:
        casefold_map.setdefault(name.casefold(), name)
        detokenized_map.setdefault(detokenize(name), name)
    return casefold_map, detokenized_map


def near_match_hint(target: str, folded: tuple[dict[str, str], dict[str, str]]) -> str | None:
    casefold_map, detokenized_map = folded
    hit = casefold_map.get(str(target).casefold())
    if hit:
        return f"case_mismatch:{hit}"

    def detokenize(value: str) -> str:
        tokens = []
        for token in value.split():
            if len(token) > 3 and token.lower().endswith("s"):
                token = token[:-1]
            tokens.append(token)
        return " ".join(tokens).casefold()

    hit = detokenized_map.get(detokenize(str(target)))
    if hit:
        return f"near_match:{hit}"
    return None


def classify_exit(
    name: str,
    body: str,
    *,
    nav_widget_names: set[str],
    dangling_sources: set[str],
) -> str:
    # Widget definition pages are not player navigation targets.
    if name.startswith("Widgets") and WIDGET_DEF_RE.search(body):
        return "widget_definition"
    if NAV_FLOW_RE.search(body):
        return "navigation_macro_exit"
    if JS_EXIT_RE.search(body):
        return "js_exit"
    if name in dangling_sources:
        return "dangling_exit"
    if set(CALL_RE.findall(body)) & nav_widget_names:
        return "widget_exit"
    if EFFECTS_RE.search(body):
        return "effects_exit"
    if SETTINGS_RE.search(body):
        return "settings_exit"
    if STATE_WIDGET_RE.search(body):
        return "state_widget_exit"
    return "sealed"


def _edge_evidence(
    rows: Iterable[Mapping[str, Any]],
    limit: int,
    *,
    extra: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    evidence = []
    for row in rows:
        item = {
            "source": row.get("source"),
            "target": row.get("target"),
            "kind": row.get("kind"),
            "macro": row.get("macro"),
            "path": row.get("path"),
            "line": row.get("line"),
            "expression": (str(row.get("expression") or ""))[:200] or None,
        }
        for field in extra:
            item[field] = row.get(field)
        evidence.append(item)
        if len(evidence) >= limit:
            break
    return evidence


def audit(
    index: Mapping[str, Any],
    *,
    source_index_sha256: str,
    html_path: Path | None = None,
    accepted: Iterable[Mapping[str, Any]] = (),
    entry: str = "Start",
    max_samples: int = 50,
) -> dict[str, Any]:
    accepted = [dict(entry_row) for entry_row in accepted]
    built = build_graph(index)
    graph: nx.DiGraph = built["graph"]
    nameset: set[str] = built["nameset"]
    dynamic_sources: set[str] = built["dynamic_sources"]
    dangling: dict[str, list[dict[str, Any]]] = built["dangling"]
    folded = _folded_names(built["names"])

    html_sha256: str | None = None
    bodies: dict[str, str] = {}
    mode = "index_only"
    if html_path is not None:
        bodies, html_sha256 = load_html_passages(html_path)
        mode = "full"

    nav_widgets = collect_navigation_widgets(bodies) if bodies else {}
    nav_widget_names = set(nav_widgets)
    dangling_sources = set()
    for rows in dangling.values():
        for row in rows:
            if row.get("source"):
                dangling_sources.add(str(row["source"]))

    out_edges_by_source: dict[str, list[dict[str, Any]]] = {}
    for edge in built["valid_edges"]:
        out_edges_by_source.setdefault(str(edge.get("source")), []).append(edge)

    candidates = [
        name
        for name in graph.nodes
        if graph.out_degree(name) == 0
        and graph.in_degree(name) > 0
        and name not in dynamic_sources
    ]
    exit_classes = Counter()
    dead_ends: list[dict[str, Any]] = []
    for name in sorted(candidates):
        body = bodies.get(name, "") if bodies else ""
        if not bodies:
            # Without bodies every candidate is conservative: dangling exits
            # are still hard evidence, everything else is undocumented.
            klass = "dangling_exit" if name in dangling_sources else "sealed"
        else:
            klass = classify_exit(
                name,
                body,
                nav_widget_names=nav_widget_names,
                dangling_sources=dangling_sources,
            )
        exit_classes[klass] += 1
        if klass not in DEFECT_CLASSES:
            continue
        matched = match_accepted(accepted, "dead_end", name)
        dangling_target_hints = {
            str(row.get("target")): hint
            for row in dangling.get(name, [])
            if row.get("target")
            for hint in [near_match_hint(str(row["target"]), folded)]
            if hint
        }
        dead_ends.append(
            {
                "passage": name,
                "class": klass,
                "status": "accepted" if matched else "unclassified",
                "accepted": matched,
                "in_degree": graph.in_degree(name),
                "out_edges": _edge_evidence(dangling.get(name, []), 10),
                "in_edges": _edge_evidence(
                    (
                        edge
                        for edge in index.get("edges") or []
                        if isinstance(edge, Mapping) and edge.get("target") == name
                    ),
                    10,
                ),
                "dangling_target_hints": dangling_target_hints,
            }
        )

    undefined_targets: list[dict[str, Any]] = []
    for target in sorted(dangling):
        rows = dangling[target]
        sources = sorted({str(row.get("source")) for row in rows if row.get("source")})
        matched = match_accepted(accepted, "undefined_target", target)
        undefined_targets.append(
            {
                "target": target,
                "status": "accepted" if matched else "unclassified",
                "accepted": matched,
                "source_passages": sources,
                "reference_count": len(rows),
                "references": _edge_evidence(rows, 20),
                "near_match_hint": near_match_hint(target, folded),
            }
        )

    self_loops = [name for name in graph.nodes if graph.has_edge(name, name)]
    self_loop_rows = []
    for name in sorted(self_loops)[:max_samples]:
        matched = match_accepted(accepted, "self_loop", name)
        self_loop_rows.append(
            {"passage": name, "status": "accepted" if matched else "unclassified"}
        )

    inbound = [name for name in graph.nodes if graph.in_degree(name) == 0]
    without_inbound_rows = []
    for name in sorted(inbound)[:max_samples]:
        matched = match_accepted(accepted, "defined_without_inbound", name)
        without_inbound_rows.append(
            {"passage": name, "status": "accepted" if matched else "unclassified"}
        )

    statically_reachable = (
        set(nx.descendants(graph, entry)) | {entry} if entry in graph else set()
    )
    unreachable_with_inbound = [
        name
        for name in graph.nodes
        if name not in statically_reachable and graph.in_degree(name) > 0
    ]

    unclassified_dead_ends = [row for row in dead_ends if row["status"] == "unclassified"]
    unclassified_targets = [
        row for row in undefined_targets if row["status"] == "unclassified"
    ]
    limitations = [
        "unreachable_from_entry is informational: DoL entry navigation is dynamic, "
        "so static BFS cannot prove player unreachability",
        "dead-end exit layers are heuristics over passage bodies; the release gate "
        "requires --html so widget/effects/settings layers are available",
    ]
    if mode == "index_only":
        limitations.append(
            "index_only mode: navigation macros were not scannable from bodies, so "
            "every non-dangling candidate is reported as sealed"
        )
    if built["non_executable"]:
        limitations.append(
            "non-executable edges (comments / <<if false>> guards) were removed "
            "before graph construction and are listed under non_executable_edges"
        )

    return {
        "schema": SCHEMA,
        "mode": mode,
        "source_commit": index.get("source_commit"),
        "source_index_sha256": source_index_sha256,
        "source_index_root": index.get("root"),
        "html_sha256": html_sha256,
        "entry": entry,
        "counts": {
            "passages": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "static_edges": len(built["valid_edges"]),
            "dynamic_edges": sum(
                1
                for edge in index.get("edges") or []
                if isinstance(edge, Mapping) and edge.get("target_kind") == "dynamic"
            ),
            "dead_end_candidates": len(candidates),
            "dead_end_exit_classes": dict(sorted(exit_classes.items())),
            "dead_ends": len(dead_ends),
            "undefined_targets": len(undefined_targets),
            "non_executable_edges": len(built["non_executable"]),
            "self_loops": len(self_loops),
            "defined_without_inbound": len(inbound),
            "statically_reachable_from_entry": len(statically_reachable),
            "unreachable_with_inbound": len(unreachable_with_inbound),
        },
        "dead_ends": dead_ends,
        "undefined_targets": undefined_targets,
        "self_loops": {
            "count": len(self_loops),
            "samples": self_loop_rows,
            "truncated": len(self_loops) > len(self_loop_rows),
        },
        "defined_without_inbound": {
            "count": len(inbound),
            "samples": without_inbound_rows,
            "truncated": len(inbound) > len(without_inbound_rows),
        },
        "unreachable_from_entry": {
            "count_with_inbound": len(unreachable_with_inbound),
            "samples": sorted(unreachable_with_inbound)[:max_samples],
            "truncated": len(unreachable_with_inbound) > max_samples,
        },
        "non_executable_edges": {
            "count": len(built["non_executable"]),
            "samples": _edge_evidence(
                built["non_executable"],
                max_samples,
                extra=("non_executable",),
            ),
            "truncated": len(built["non_executable"]) > max_samples,
        },
        "accepted_sources": [
            {
                "category": row.get("category"),
                "key": row.get("passage") or row.get("target"),
                "reason": row.get("reason"),
                "evidence": list(row.get("evidence") or []),
            }
            for row in accepted
        ],
        "blocking": {
            "unclassified_dead_ends": [row["passage"] for row in unclassified_dead_ends],
            "unclassified_undefined_targets": [row["target"] for row in unclassified_targets],
            "html_provided": mode == "full",
        },
        "completion_claim": "none",
        "limitations": limitations,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source_index", type=Path)
    parser.add_argument("--html", type=Path, help="target game HTML for body-level exit layers")
    parser.add_argument(
        "--accepted",
        type=Path,
        default=Path("config/accepted-upstream-graph-defects.toml"),
    )
    parser.add_argument("--entry", default="Start")
    parser.add_argument("--max-samples", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path(".local/story-graph-audit"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        index, index_sha = load_index(args.source_index)
        accepted = load_accepted(args.accepted)
        report = audit(
            index,
            source_index_sha256=index_sha,
            html_path=args.html,
            accepted=accepted,
            entry=args.entry,
            max_samples=args.max_samples,
        )
    except AuditError as exc:
        print(f"[story-graph-audit] invalid input: {exc}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "story-graph-audit.json"
    atomic_write_json(json_path, report)
    blocking = report["blocking"]
    print(
        "[story-graph-audit] mode={mode} dead_ends={de} undefined={ut} "
        "unclassified_dead_ends={ude} unclassified_undefined={uut} report={path}".format(
            mode=report["mode"],
            de=report["counts"]["dead_ends"],
            ut=report["counts"]["undefined_targets"],
            ude=len(blocking["unclassified_dead_ends"]),
            uut=len(blocking["unclassified_undefined_targets"]),
            path=json_path,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
