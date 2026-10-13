"""Regression queries over exploration evidence reports.

Reads ``config/exploration-queries.toml`` and a set of evidence reports whose
kinds are auto-detected from their schema:

* ``dolx.au_contract.v1`` (artifact list from ``au_artifact_check --output``)
* ``dol-x-mod-passage-inventory`` (mod passage inventory)
* ``dolx.source-index.v1``
* ``dolx.story-graph-audit.v1``
* ``dolx.traversal-stats.v1``
* ``dolx.symbolic-reachability.v1``

Output schema ``dolx.query-regression.v1``.  ``release``-severity failures,
missing evidence and pending queries are listed in ``release_blocking``; the
CLI exits non-zero in ``--strict`` mode when that list is non-empty.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sweep_ledger import atomic_write_json


SCHEMA = "dolx.query-regression.v1"
QUERIES_SCHEMA = "dolx.exploration-queries.v1"

PATH_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "exists", "not_exists", "empty", "not_empty", "contains"}
SPECIAL_OPS = {
    "passage_exists",
    "mod_present",
    "dead_end_classified",
    "undefined_target_classified",
    "opaque_requires_runtime_query",
    "no_unreachable_targets",
    "target_verdict_in",
}
SCOPED_KINDS = {"au_contract"}


class QueryError(ValueError):
    """Invalid query input; the CLI maps this to exit code 2."""


def load_queries(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("rb") as handle:
        payload = tomllib.load(handle)
    if payload.get("schema") != QUERIES_SCHEMA:
        raise QueryError(f"{path} schema must be {QUERIES_SCHEMA}")
    queries = payload.get("query") or []
    for position, query in enumerate(queries):
        if not isinstance(query, Mapping):
            raise QueryError(f"{path}: query[{position}] is not a table")
        if not query.get("id"):
            raise QueryError(f"{path}: query[{position}] requires an id")
        if query.get("kind") not in {
            "au_contract",
            "mod_inventory",
            "source_index",
            "story_graph",
            "traversal",
            "symbolic_reachability",
        }:
            raise QueryError(f"{path}: query[{position}] has unknown kind {query.get('kind')!r}")
        if query.get("status") == "pending":
            continue
        op = query.get("op")
        if op not in PATH_OPS | SPECIAL_OPS:
            raise QueryError(f"{path}: query[{position}] has unknown op {op!r}")
        if op in PATH_OPS and not query.get("path"):
            raise QueryError(f"{path}: query[{position}] requires a path for op {op!r}")
        if op in SPECIAL_OPS and query.get("path"):
            # Special ops read dedicated fields; a stray path is a mistake.
            raise QueryError(f"{path}: query[{position}] op {op!r} must not set path")
    return [dict(query) for query in queries]


def classify_payload(payload: Any) -> str | None:
    if isinstance(payload, list):
        if payload and isinstance(payload[0], Mapping) and "au_contract" in payload[0]:
            return "au_contract"
        return None
    if not isinstance(payload, Mapping):
        return None
    schema = payload.get("schema")
    mapping = {
        "dolx.source-index.v1": "source_index",
        "dolx.story-graph-audit.v1": "story_graph",
        "dolx.traversal-stats.v1": "traversal",
        "dolx.symbolic_reachability.v1": "symbolic_reachability",
    }
    if schema in mapping:
        return mapping[schema]
    if payload.get("tool") == "dol-x-mod-passage-inventory":
        return "mod_inventory"
    return None


def load_evidence(paths: Iterable[Path]) -> dict[str, list[Any]]:
    evidence: dict[str, list[Any]] = {}
    for path in paths:
        path = Path(path)
        candidates = sorted(path.rglob("*.json")) if path.is_dir() else [path]
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            kind = classify_payload(payload)
            if kind:
                evidence.setdefault(kind, []).append(payload)
    return evidence


def _resolve_path(payload: Any, path: str) -> tuple[bool, Any]:
    value = payload
    for part in str(path).split("."):
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            return False, None
    return True, value


def _evaluate_path_op(op: str, payload: Any, query: Mapping[str, Any]) -> tuple[bool, str]:
    found, value = _resolve_path(payload, query["path"])
    expected = query.get("value")
    if op == "exists":
        return (found and value is not None), f"{query['path']}={value!r}"
    if op == "not_exists":
        return (not found or value is None), f"{query['path']}={value!r}"
    if op == "empty":
        if not found:
            return False, f"{query['path']} is missing"
        return value in (None, "", [], {}), f"{query['path']}={value!r}"
    if op == "not_empty":
        if not found:
            return False, f"{query['path']} is missing"
        return value not in (None, "", [], {}), f"{query['path']}={value!r}"
    if not found:
        return False, f"{query['path']} is missing"
    if op == "eq":
        return value == expected, f"{query['path']}={value!r} vs {expected!r}"
    if op == "ne":
        return value != expected, f"{query['path']}={value!r} vs {expected!r}"
    if op in {"gt", "gte", "lt", "lte"}:
        try:
            left, right = float(value), float(expected)
        except (TypeError, ValueError):
            return False, f"{query['path']}={value!r} is not numeric"
        compare = {
            "gt": left > right,
            "gte": left >= right,
            "lt": left < right,
            "lte": left <= right,
        }[op]
        return compare, f"{query['path']}={value!r} {op} {expected!r}"
    if op == "contains":
        try:
            return expected in value, f"{expected!r} in {query['path']}={value!r}"
        except TypeError:
            return False, f"{query['path']}={value!r} is not a container"
    raise QueryError(f"unhandled op {op!r}")


def _evaluate_special(op: str, payload: Any, query: Mapping[str, Any]) -> tuple[bool, str]:
    if op == "passage_exists":
        names = {
            str(item.get("name"))
            for item in payload.get("passages") or []
            if isinstance(item, Mapping)
        }
        target = str(query.get("passage"))
        return target in names, f"passage {target!r} present={target in names}"
    if op == "mod_present":
        needle = str(query.get("mod_name"))
        names = [str(item.get("name")) for item in payload.get("mods") or [] if isinstance(item, Mapping)]
        matched = [name for name in names if needle.lower() in name.lower()]
        return bool(matched), f"mod {needle!r} matched={matched[:3]}"
    if op == "dead_end_classified":
        blocking = (payload.get("blocking") or {}).get("unclassified_dead_ends") or []
        target = str(query.get("passage"))
        return target not in blocking, f"{target!r} in unclassified_dead_ends={target in blocking}"
    if op == "undefined_target_classified":
        blocking = (payload.get("blocking") or {}).get("unclassified_undefined_targets") or []
        target = str(query.get("target"))
        return target not in blocking, f"{target!r} in unclassified_undefined_targets={target in blocking}"
    if op == "opaque_requires_runtime_query":
        observable = payload.get("au_payload_logic_observable")
        required = payload.get("runtime_query_required")
        if observable:
            return True, "AU payload logic is observable; runtime obligation not required"
        return bool(required), f"logic_observable={observable} runtime_query_required={required}"
    if op == "no_unreachable_targets":
        verdict = payload.get("verdict")
        if verdict == "solver_unavailable":
            return False, "solver_unavailable"
        targets = payload.get("targets") or []
        exhausted = [
            str(item.get("target"))
            for item in targets
            if isinstance(item, Mapping) and item.get("verdict") == "unreachable_within_bound"
        ]
        return not exhausted, f"verdict={verdict} bound_exhausted_targets={exhausted[:5]}"
    if op == "target_verdict_in":
        target = str(query.get("target"))
        allowed = [str(item) for item in query.get("allowed") or []]
        for item in payload.get("targets") or []:
            if isinstance(item, Mapping) and str(item.get("target")) == target:
                verdict = str(item.get("verdict"))
                return verdict in allowed, f"{target!r} verdict={verdict} allowed={allowed}"
        return False, f"target {target!r} not present in report"
    raise QueryError(f"unhandled op {op!r}")


def evaluate_query(
    query: Mapping[str, Any], evidence: Mapping[str, list[Any]]
) -> dict[str, Any]:
    result = {
        "id": query.get("id"),
        "kind": query.get("kind"),
        "severity": query.get("severity") or "informational",
        "status": None,
        "detail": None,
        "observations": [],
    }
    if query.get("status") == "pending":
        result["status"] = "pending"
        result["detail"] = query.get("reason") or "pending"
        return result

    payloads = evidence.get(str(query.get("kind"))) or []
    if not payloads:
        result["status"] = "missing_evidence"
        result["detail"] = f"no {query.get('kind')} evidence supplied"
        return result

    scoped: list[tuple[str, Any]] = []
    if query.get("kind") in SCOPED_KINDS:
        for payload in payloads:
            for item in payload:
                if isinstance(item, Mapping) and item.get("is_au"):
                    scoped.append((str(item.get("target")), item.get("au_contract")))
        if not scoped:
            result["status"] = "missing_evidence"
            result["detail"] = "no AU artifact entries found in au_contract evidence"
            return result
    else:
        scoped = [(str(position), payload) for position, payload in enumerate(payloads)]

    op = str(query.get("op"))
    failures = []
    observations = []
    for label, payload in scoped:
        if op in PATH_OPS:
            ok, detail = _evaluate_path_op(op, payload or {}, query)
        else:
            ok, detail = _evaluate_special(op, payload or {}, query)
        observations.append(f"{label}: {detail}")
        if not ok:
            failures.append(f"{label}: {detail}")
    result["observations"] = observations[:10]
    if failures:
        result["status"] = "failed"
        result["detail"] = "; ".join(failures[:5])
    else:
        result["status"] = "passed"
        result["detail"] = f"all {len(scoped)} evidence entries satisfy the query"
    return result


def run(
    queries: Iterable[Mapping[str, Any]], evidence: Mapping[str, list[Any]]
) -> dict[str, Any]:
    results = [evaluate_query(query, evidence) for query in queries]
    counts = {"queries": len(results)}
    for status in ("passed", "failed", "pending", "missing_evidence"):
        counts[status] = sum(1 for row in results if row["status"] == status)
    release_blocking = [
        row["id"]
        for row in results
        if row["severity"] == "release" and row["status"] in {"failed", "pending", "missing_evidence"}
    ]
    return {
        "schema": SCHEMA,
        "counts": counts,
        "results": results,
        "release_blocking": release_blocking,
        "completion_claim": "none",
        "limitations": [
            "queries assert over recorded evidence; they do not re-run the game",
            "pending queries record required evidence that has not been captured",
            "release_blocking lists release-severity failures, pending and missing evidence",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("evidence", nargs="+", type=Path, help="report files or directories")
    parser.add_argument(
        "--queries", type=Path, default=Path("config/exploration-queries.toml")
    )
    parser.add_argument("--out", type=Path, default=Path(".local/query-regression"))
    parser.add_argument("--strict", action="store_true", help="exit 2 when release queries block")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        queries = load_queries(args.queries)
        evidence = load_evidence(args.evidence)
        if not evidence:
            raise QueryError("no recognised evidence reports found in the given inputs")
        report = run(queries, evidence)
    except QueryError as exc:
        print(f"[query-regression] invalid input: {exc}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "query-regression.json"
    atomic_write_json(json_path, report)
    counts = report["counts"]
    print(
        "[query-regression] passed={passed} failed={failed} pending={pending} "
        "missing={missing} blocking={blocking} report={path}".format(
            passed=counts.get("passed", 0),
            failed=counts.get("failed", 0),
            pending=counts.get("pending", 0),
            missing=counts.get("missing_evidence", 0),
            blocking=report["release_blocking"],
            path=json_path,
        )
    )
    if args.strict and report["release_blocking"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
