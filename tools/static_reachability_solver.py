#!/usr/bin/env python3
"""Symbolic bounded playtrace reachability over the static passage graph (ASP).

Answers "is there a playtrace of at most N steps from a start passage to a target
passage, and what is one witness trace?" using `clingo`, in the same family as the
DendryScope symbolic-playtesting approach.

Verdict precedence, which the release gate relies on:

1. ``solver_unavailable`` - ``clingo`` is missing. Never degraded to a negative.
2. ``invalid_input`` - the index is missing or is not ``dolx.source-index.v1``.
3. ``reachable`` - the solver returned a concrete witness. A witness is proof, so
   unknown dynamic edges cannot downgrade it.
4. ``unknown_dynamic_edges`` - no static witness exists AND the index contains
   dynamic edges that the encoding cannot represent. This is not a negative.
5. ``unreachable_within_bound`` - no static witness AND nothing dynamic is left
   unexplained. **This is not a proof of unreachability.** ``bound_is_not_proof``
   is always true for this verdict and the report states the bound explicitly.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sweep_ledger import atomic_write_json


SCHEMA = "dolx.symbolic_reachability.v1"
INDEX_SCHEMA = "dolx.source-index.v1"
DEFAULT_BOUND = 120
VERDICT_REACHABLE = "reachable"
VERDICT_BOUNDED_NEGATIVE = "unreachable_within_bound"
VERDICT_NO_SOLVER = "solver_unavailable"
VERDICT_UNKNOWN_DYNAMIC = "unknown_dynamic_edges"
VERDICT_INVALID = "invalid_input"

BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# SugarCube closes a conditional with <</if>>. Nested conditionals are not modelled
# here; the parser only drops the outermost span, which is conservative for the
# literal <<if false>> / <<if 0>> guards this filter exists for.
FALSE_IF_RE = re.compile(
    r"<<\s*if\s+(?:false|0)\s*>>.*?(?:<<\s*/\s*if\s*>>|$)",
    re.DOTALL | re.IGNORECASE,
)


def load_index(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source index must be a JSON object")
    if value.get("schema") != INDEX_SCHEMA:
        raise ValueError(
            f"source index schema must be {INDEX_SCHEMA!r}, got {value.get('schema')!r}"
        )
    return value


def _newline_positions(text: str) -> list[int]:
    return [index for index, char in enumerate(text) if char == "\n"]


def _line_span(
    positions: list[int],
    start: int,
    end: int,
) -> tuple[int, int]:
    # Bisect instead of text.count: a built HTML root can be ~48 MB with thousands
    # of matches, and counting from offset zero each time is O(n) per match.
    return (
        bisect.bisect_right(positions, start - 1) + 1,
        bisect.bisect_right(positions, end - 1) + 1,
    )


def non_executable_line_ranges(text: str) -> list[tuple[int, int, str]]:
    """Return line ranges whose edges must never be treated as traversable."""
    ranges: list[tuple[int, int, str]] = []
    positions = _newline_positions(text)
    for label, pattern in (
        ("block_comment", BLOCK_COMMENT_RE),
        ("html_comment", HTML_COMMENT_RE),
        ("false_conditional", FALSE_IF_RE),
    ):
        for match in pattern.finditer(text):
            start, end = _line_span(positions, match.start(), match.end())
            ranges.append((start, end, label))
    return ranges


def _prepare_ranges(text: str) -> tuple[list[int], list[tuple[int, int, str]]]:
    ranges = sorted(non_executable_line_ranges(text))
    return [start for start, _end, _label in ranges], ranges


def _in_ranges(
    line: int,
    prepared: tuple[list[int], list[tuple[int, int, str]]],
) -> str | None:
    starts, ranges = prepared
    index = bisect.bisect_right(starts, line) - 1
    if index >= 0:
        start, end, label = ranges[index]
        if start <= line <= end:
            return label
    return None


def _prepare_comment_spans(
    text: str,
) -> tuple[str, list[tuple[int, int, str]], list[int], list[int]]:
    """Character-level spans of dead text, plus the newline index for line math.

    Line-granularity filtering is wrong for DoL: a single source line can carry
    an inline ``/* ... */`` comment next to a live ``<<link>>`` (the compiled
    HTML puts a whole passage on one line).  Dead text must therefore be judged
    by how much of the line the spans actually cover.
    """
    spans: list[tuple[int, int, str]] = []
    for label, pattern in (
        ("block_comment", BLOCK_COMMENT_RE),
        ("html_comment", HTML_COMMENT_RE),
        ("false_conditional", FALSE_IF_RE),
    ):
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end(), label))
    spans.sort(key=lambda item: item[0])
    return text, spans, [start for start, _end, _label in spans], _newline_positions(text)


def _line_is_dead(
    line: int,
    prepared: tuple[str, list[tuple[int, int, str]], list[int], list[int]],
) -> str | None:
    """Return the dead-text label only when the whole line is covered."""
    text, spans, starts, positions = prepared
    if not spans or not isinstance(line, int) or line < 1:
        return None
    start = positions[line - 2] + 1 if line >= 2 and line - 2 < len(positions) else 0
    end = positions[line - 1] if line - 1 < len(positions) else len(text)
    if start >= end:
        return None
    index = max(bisect.bisect_right(starts, start) - 1, 0)
    merged: list[tuple[int, int, str]] = []
    while index < len(spans) and spans[index][0] < end:
        span_start, span_end, label = spans[index]
        index += 1
        if span_end <= start:
            continue
        left = max(span_start, start)
        right = min(span_end, end)
        if merged and left <= merged[-1][1]:
            previous_left, previous_right, previous_label = merged[-1]
            merged[-1] = (previous_left, max(previous_right, right), previous_label)
        else:
            merged.append((left, right, label))
    if not merged:
        return None
    cursor = start
    for left, right, _label in merged:
        if text[cursor:left].strip():
            return None
        cursor = max(cursor, right)
    if text[cursor:end].strip():
        return None
    return merged[0][2]


def filter_executable_edges(
    edges: Iterable[Mapping[str, Any]],
    *,
    root: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split edges into executable ones and those that only exist in dead text."""
    cache: dict[
        str, tuple[str, list[tuple[int, int, str]], list[int], list[int]]
    ] = {}
    executable: list[dict[str, Any]] = []
    non_executable: list[dict[str, Any]] = []
    for edge in edges:
        path = str(edge.get("path") or "")
        line = edge.get("line")
        label = None
        if root is not None and path and isinstance(line, int):
            if path not in cache:
                resolved = _resolve_source(Path(root), path)
                try:
                    cache[path] = _prepare_comment_spans(
                        resolved.read_text(encoding="utf-8", errors="replace")
                    )
                except OSError:
                    cache[path] = ("", [], [], [])
            label = _line_is_dead(line, cache[path])
        if label is None:
            executable.append(dict(edge))
        else:
            non_executable.append({**dict(edge), "non_executable": label})
    return executable, non_executable


def _resolve_source(root: Path, path: str) -> Path:
    """Resolve one index member against a directory or a single-file root.

    ``tools.source_index`` stores the bare file name when the root it scanned was a
    file (for example a built ``Degrees of Lewdity.html``), so the member path has
    to be resolved against the root's parent, or the root itself.
    """
    base = root.parent if root.is_file() else root
    candidate = base / path
    if candidate.is_file():
        return candidate
    if root.is_file() and Path(path).name == root.name:
        return root
    return candidate


def build_graph(
    index: Mapping[str, Any],
) -> dict[str, Any]:
    """Return nodes, traversable static edges, excluded dynamic edges and dangling."""
    passages = [
        str(item.get("name"))
        for item in (index.get("passages") or ())
        if isinstance(item, Mapping) and item.get("name")
    ]
    nodes = sorted(set(passages))
    known = set(nodes)

    raw_edges = [item for item in (index.get("edges") or ()) if isinstance(item, Mapping)]
    root_value = index.get("root")
    root = Path(root_value) if root_value else None
    executable, _non_executable = filter_executable_edges(raw_edges, root=root)

    edges: list[dict[str, Any]] = []
    dynamic: list[dict[str, Any]] = []
    dangling: list[dict[str, Any]] = []
    for edge in executable:
        target = edge.get("target")
        source = edge.get("source")
        if not source or not target:
            continue
        if str(edge.get("target_kind")) == "dynamic":
            dynamic.append(dict(edge))
            continue
        if str(target) not in known:
            dangling.append(dict(edge))
            continue
        edges.append(dict(edge))
    return {
        "nodes": nodes,
        "edges": edges,
        "dynamic_edges": dynamic,
        "dangling": dangling,
        "non_executable": _non_executable,
    }


def _asp_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def encode(
    nodes: Iterable[str],
    edges: Iterable[Mapping[str, Any]],
    *,
    start: str,
    target: str,
    bound: int,
) -> str:
    """Encode a bounded path from ``start`` to ``target``.

    The target gets a synthetic self-loop so a shorter path can be padded to the
    bound. Nothing else is padded, so every hop before the first arrival at the
    target is a real edge, and a bounded negative is a genuine UNSAT of this
    encoding rather than a modelling artefact.
    """
    lines = [f"time(0..{bound})."]
    for node in nodes:
        lines.append(f"node({_asp_string(node)}).")
    for edge in edges:
        lines.append(
            f"edge({_asp_string(str(edge.get('source')))},"
            f"{_asp_string(str(edge.get('target')))})."
        )
    lines.append(f"edge({_asp_string(target)},{_asp_string(target)}).")
    lines.append(f"start({_asp_string(start)}).")
    lines.append(f"target({_asp_string(target)}).")
    lines.append("at(0,S) :- start(S).")
    lines.append(
        "1 { move(T,S,D) : edge(S,D) } 1 :- at(T,S), time(T), T < "
        + str(bound)
        + "."
    )
    lines.append("at(T+1,D) :- move(T,_,D), time(T+1).")
    lines.append(":- not ok.")
    lines.append("ok :- at(T,N), target(N), time(T).")
    return "\n".join(lines) + "\n"


def _import_clingo() -> tuple[Any | None, str | None, str]:
    try:
        import clingo  # noqa: PLC0415 - lazy so the tool imports without the wheel
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, f"{type(exc).__name__}: {exc}", ""
    return clingo, None, str(getattr(clingo, "__version__", "") or "")


def solve_target(
    graph: Mapping[str, Any],
    *,
    start: str,
    target: str,
    bound: int,
    shortest: bool = False,
) -> dict[str, Any]:
    clingo, error, version = _import_clingo()
    row: dict[str, Any] = {"target": target, "bound": bound}
    if clingo is None:
        row["verdict"] = VERDICT_NO_SOLVER
        row["steps"] = None
        row["witness"] = None
        row["error"] = error
        return row

    edges = graph["edges"]
    nodes = graph["nodes"]
    edge_lookup = {
        (str(edge.get("source")), str(edge.get("target"))): edge for edge in edges
    }

    def attempt(limit: int) -> tuple[str, list[dict[str, Any]] | None]:
        program = encode(nodes, edges, start=start, target=target, bound=limit)
        control = clingo.Control(["--models=1", "--warn=none"])
        control.add("base", [], program)
        control.ground([("base", [])])
        moves: list[tuple[int, str, str]] = []

        def collect(model: Any) -> None:
            for atom in model.symbols(atoms=True):
                if atom.name != "move":
                    continue
                step = atom.arguments[0].number
                source = str(atom.arguments[1]).strip('"')
                dest = str(atom.arguments[2]).strip('"')
                moves.append((step, source, dest))

        result = control.solve(on_model=collect)
        if not result.satisfiable:
            return "unsat", None
        ordered = sorted(moves)
        hops: list[dict[str, Any]] = []
        for step, source, dest in ordered:
            if source == target == dest:
                break  # padding self-loop: the path already arrived
            edge = edge_lookup.get((source, dest))
            if edge is None:
                return "invalid_witness", None
            hops.append(
                {
                    "step": step,
                    "source": source,
                    "target": dest,
                    "kind": edge.get("kind"),
                    "macro": edge.get("macro"),
                    "path": edge.get("path"),
                    "line": edge.get("line"),
                }
            )
        return "sat", hops

    status, hops = attempt(bound)
    if status == "invalid_witness":
        row["verdict"] = VERDICT_INVALID
        row["steps"] = None
        row["witness"] = None
        row["error"] = "solver returned a move that is not a static source edge"
        return row
    if status == "unsat":
        row["verdict"] = None  # resolved by the caller against dynamic edges
        row["steps"] = None
        row["witness"] = None
        return row

    if shortest and hops is not None:
        low, high = 0, len(hops)
        best = hops
        while low < high:
            mid = (low + high) // 2
            sub_status, sub_hops = attempt(mid)
            if sub_status == "sat" and sub_hops is not None:
                best = sub_hops
                high = mid
            else:
                low = mid + 1
        hops = best

    row["verdict"] = VERDICT_REACHABLE
    row["steps"] = len(hops or ())
    row["witness"] = hops
    return row


def build_report(
    index: Mapping[str, Any],
    *,
    start: str | None = None,
    targets: Iterable[str] | None = None,
    bound: int = DEFAULT_BOUND,
    shortest: bool = False,
) -> dict[str, Any]:
    graph = build_graph(index)
    nodes = graph["nodes"]
    resolved_start = start or ("Start" if "Start" in set(nodes) else (nodes[0] if nodes else ""))
    requested = [str(item) for item in (targets or ())]
    if not requested:
        requested = list(nodes)

    rows = []
    for target in requested:
        row = solve_target(
            graph,
            start=resolved_start,
            target=target,
            bound=bound,
            shortest=shortest,
        )
        if row.get("verdict") is None:
            # No static witness. Only now may unknown dynamic edges block a negative.
            if graph["dynamic_edges"]:
                row["verdict"] = VERDICT_UNKNOWN_DYNAMIC
                row["detail"] = (
                    f"{len(graph['dynamic_edges'])} dynamic edge(s) cannot be "
                    "encoded; a static witness was not found, so the bound alone "
                    "does not prove unreachability."
                )
            else:
                row["verdict"] = VERDICT_BOUNDED_NEGATIVE
                row["bound_exhausted"] = True
                row["bound_is_not_proof"] = True
                row["detail"] = (
                    f"no static playtrace of at most {bound} steps; this is a bound "
                    "result, not a proof of unreachability"
                )
        rows.append(row)

    verdicts = [str(row["verdict"]) for row in rows]
    if VERDICT_REACHABLE in verdicts:
        verdict = VERDICT_REACHABLE
    elif VERDICT_NO_SOLVER in verdicts:
        verdict = VERDICT_NO_SOLVER
    elif VERDICT_INVALID in verdicts:
        verdict = VERDICT_INVALID
    elif VERDICT_UNKNOWN_DYNAMIC in verdicts:
        verdict = VERDICT_UNKNOWN_DYNAMIC
    elif verdicts:
        verdict = VERDICT_BOUNDED_NEGATIVE
    else:
        verdict = VERDICT_INVALID

    return {
        "schema": SCHEMA,
        "source_commit": index.get("source_commit"),
        "root": index.get("root"),
        "start": resolved_start,
        "bound": bound,
        "bound_is_not_proof": verdict == VERDICT_BOUNDED_NEGATIVE,
        "verdict": verdict,
        "targets": rows,
        "dynamic_edge_count": len(graph["dynamic_edges"]),
        "dynamic_edges": graph["dynamic_edges"][:200],
        "dangling_edge_count": len(graph["dangling"]),
        "dangling_edges": graph["dangling"][:200],
        "non_executable_edge_count": len(graph["non_executable"]),
        "solver": {
            "available": all(
                row["verdict"] != VERDICT_NO_SOLVER for row in rows
            ),
            "version": _import_clingo()[2],
            "status": verdict,
        },
        "stats": {
            "passages": len(nodes),
            "static_edges": len(graph["edges"]),
            "dynamic_edges": len(graph["dynamic_edges"]),
            "dangling_edges": len(graph["dangling"]),
            "non_executable_edges": len(graph["non_executable"]),
            "targets": len(rows),
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("index", type=Path, help="dolx.source-index.v1 JSON file")
    parser.add_argument("--start", default=None)
    parser.add_argument("--target", action="append", default=None)
    parser.add_argument("--bound", type=int, default=DEFAULT_BOUND)
    parser.add_argument(
        "--shortest",
        action="store_true",
        help="binary-search the shortest witness instead of the first model",
    )
    parser.add_argument("--out", type=Path, default=Path(".local/static-reachability"))
    return parser.parse_args(argv)


def write_report(payload: Mapping[str, Any], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "static-reachability.json"
    atomic_write_json(path, payload)
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        index = load_index(args.index)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"static reachability failed: {exc}", file=sys.stderr)
        return 2
    report = build_report(
        index,
        start=args.start,
        targets=args.target,
        bound=args.bound,
        shortest=args.shortest,
    )
    path = write_report(report, args.out)
    print(
        f"verdict: {report['verdict']} (bound {report['bound']}, "
        f"{report['stats']['passages']} passages, "
        f"{report['stats']['static_edges']} static edges)"
    )
    print(f"report: {path}")
    return 0 if report["verdict"] != VERDICT_INVALID else 1


if __name__ == "__main__":
    raise SystemExit(main())
