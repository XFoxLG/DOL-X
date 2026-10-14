"""Traversal statistics over exploration reports per evidence track.

Schema ``dolx.traversal-stats.v1``.  Accepts any mix of:

* ``dolx.exploration.v1`` reports (natural / checkpoint tracks) with an
  ``actions`` array carrying ``passage_before`` / ``passage_after``;
* ``dolx.assisted-exploration.v1`` reports with a ``results`` array;
* directories, which are scanned for matching ``*.json`` files
  (non-report files such as ``target-manifest.json`` are skipped).

Passage visits and observed transitions come from structured action fields
only.  Assisted results that carry no passage sequence are counted by
verdict, and their coverage is marked ``not_observable`` instead of being
guessed from target labels.

When ``--source-index`` is supplied, coverage denominators come from the
index: distinct passage names and distinct valid static ``(source, target)``
pairs.  An observed transition that is missing from the static set is
reported as ``dynamic_observed`` — it can be legitimate (runtime navigation)
and must not be read as a defect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.exploration_summary import dayloop_observation
from tools.sweep_ledger import atomic_write_json


SCHEMA = "dolx.traversal-stats.v1"
EXPLORATION_SCHEMA = "dolx.exploration.v1"
ASSISTED_SCHEMA = "dolx.assisted-exploration.v1"
VERDICTS = (
    "ok",
    "hard_fail",
    "soft_fail",
    "fixture_insufficient",
    "not_applicable",
    "infrastructure_fail",
    "source_gap",
    "accepted_upstream",
)


class TraversalError(ValueError):
    """Invalid statistics input; the CLI maps this to exit code 2."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def iter_report_paths(inputs: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        item = Path(item)
        if item.is_dir():
            paths.extend(sorted(item.rglob("*.json")))
        elif item.is_file():
            paths.append(item)
        else:
            raise TraversalError(f"{item} does not exist")
    return paths


def load_report(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TraversalError(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        return None
    schema = payload.get("schema")
    if schema in {EXPLORATION_SCHEMA, ASSISTED_SCHEMA}:
        return dict(payload)
    return None


def _coverage_track() -> dict[str, Any]:
    return {
        "runs": 0,
        "actions": 0,
        "actions_by_verdict": Counter(),
        "results_by_verdict": Counter(),
        "passages": set(),
        "transitions": set(),
        "unique_fingerprints": set(),
        "unique_coarse_states": 0,
        "failures": 0,
        "coverage_basis": None,
        "dayloop_observed": False,
        "dayloop_samples": 0,
        "dayloop_monotone_all": True,
        "dayloop_rollover_any": False,
    }


def _track_name(report: Mapping[str, Any]) -> str:
    track = report.get("evidence_track")
    if track:
        return str(track)
    return "assisted" if report.get("schema") == ASSISTED_SCHEMA else "unknown"


def collect(
    reports: Iterable[dict[str, Any]],
    *,
    source_index: Mapping[str, Any] | None = None,
    source_index_sha256: str | None = None,
) -> dict[str, Any]:
    tracks: dict[str, dict[str, Any]] = {}
    for report in reports:
        track = _track_name(report)
        stats = tracks.setdefault(track, _coverage_track())
        stats["runs"] += 1
        stats["failures"] += len(report.get("failures") or [])
        if isinstance(report.get("unique_coarse_states"), int):
            stats["unique_coarse_states"] += int(report["unique_coarse_states"])

        actions = report.get("actions") or []
        if actions:
            stats["coverage_basis"] = stats["coverage_basis"] or "actions"
        for action in actions:
            if not isinstance(action, Mapping):
                continue
            stats["actions"] += 1
            stats["actions_by_verdict"][str(action.get("verdict") or "unknown")] += 1
            before, after = action.get("passage_before"), action.get("passage_after")
            if before:
                stats["passages"].add(str(before))
            if after:
                stats["passages"].add(str(after))
            if before and after and str(before) != str(after):
                stats["transitions"].add((str(before), str(after)))
            fingerprint = action.get("fingerprint_after")
            if fingerprint:
                stats["unique_fingerprints"].add(str(fingerprint))

        dayloop = dayloop_observation(actions)
        if dayloop.get("observed"):
            stats["dayloop_observed"] = True
            stats["dayloop_samples"] += int(dayloop.get("samples") or 0)
            stats["dayloop_monotone_all"] = bool(
                stats["dayloop_monotone_all"] and dayloop.get("minute_monotone")
            )
            stats["dayloop_rollover_any"] = bool(
                stats["dayloop_rollover_any"] or dayloop.get("day_rollover")
            )

        results = report.get("results") or []
        if results and stats["coverage_basis"] is None:
            stats["coverage_basis"] = "results_only"
        for result in results:
            if not isinstance(result, Mapping):
                continue
            stats["results_by_verdict"][str(result.get("verdict") or "unknown")] += 1
            fingerprint = result.get("fingerprint")
            if fingerprint:
                stats["unique_fingerprints"].add(str(fingerprint))

    denominators: dict[str, Any] = {"passages": None, "static_edges": None}
    static_edges: set[tuple[str, str]] = set()
    if source_index is not None:
        names = {
            str(item.get("name"))
            for item in source_index.get("passages") or []
            if isinstance(item, Mapping) and item.get("name")
        }
        for edge in source_index.get("edges") or []:
            if not isinstance(edge, Mapping):
                continue
            if edge.get("target_kind") != "static":
                continue
            source, target = edge.get("source"), edge.get("target")
            if source and target and str(target) in names:
                static_edges.add((str(source), str(target)))
        denominators = {"passages": len(names), "static_edges": len(static_edges)}

    encoded_tracks: dict[str, Any] = {}
    for track, stats in sorted(tracks.items()):
        passages = stats["passages"]
        transitions = stats["transitions"]
        observed_static = {row for row in transitions if row in static_edges}
        observed_dynamic = transitions - observed_static
        encoded_tracks[track] = {
            "runs": stats["runs"],
            "actions": stats["actions"],
            "actions_by_verdict": {
                verdict: stats["actions_by_verdict"].get(verdict, 0) for verdict in VERDICTS
            }
            | {
                key: value
                for key, value in stats["actions_by_verdict"].items()
                if key not in VERDICTS
            },
            "results_by_verdict": {
                verdict: stats["results_by_verdict"].get(verdict, 0) for verdict in VERDICTS
            }
            | {
                key: value
                for key, value in stats["results_by_verdict"].items()
                if key not in VERDICTS
            },
            "passages_visited": len(passages),
            "passage_coverage": (
                round(len(passages) / denominators["passages"], 6)
                if denominators["passages"]
                else None
            ),
            "transitions_observed": len(transitions),
            "static_transitions_observed": len(observed_static),
            "dynamic_observed": len(observed_dynamic),
            "edge_coverage": (
                round(len(observed_static) / denominators["static_edges"], 6)
                if denominators["static_edges"]
                else None
            ),
            "unique_fingerprints": len(stats["unique_fingerprints"]),
            "unique_coarse_states": stats["unique_coarse_states"],
            "failures": stats["failures"],
            "coverage_basis": stats["coverage_basis"] or "not_observable",
            "dayloop": {
                "observed": stats["dayloop_observed"],
                "samples": stats["dayloop_samples"],
                "minute_monotone": (
                    stats["dayloop_monotone_all"] if stats["dayloop_observed"] else None
                ),
                "day_rollover": (
                    stats["dayloop_rollover_any"] if stats["dayloop_observed"] else None
                ),
                # full_day 只在「至少一条运行真实跨过一天，且所有观测到的运行
                # 时钟都单调向前」时为 true；没有时钟样本时保持 None 语义。
                "full_day": bool(
                    stats["dayloop_observed"]
                    and stats["dayloop_monotone_all"]
                    and stats["dayloop_rollover_any"]
                )
                if stats["dayloop_observed"]
                else None,
            },
        }

    limitations = [
        "passage and transition coverage come from structured action fields only; "
        "assisted results without a passage sequence are counted by verdict",
        "transitions missing from the static edge set are reported as dynamic_observed; "
        "runtime navigation is expected there and is not a defect signal",
        "no completion claim: coverage percentages describe recorded evidence, not proof "
        "that unexplored states are unreachable",
    ]
    return {
        "schema": SCHEMA,
        "source_index_sha256": source_index_sha256,
        "denominators": denominators,
        "tracks": encoded_tracks,
        "totals": {
            "runs": sum(track["runs"] for track in encoded_tracks.values()),
            "actions": sum(track["actions"] for track in encoded_tracks.values()),
            "unique_fingerprints": len(
                set().union(*(stats["unique_fingerprints"] for stats in tracks.values()))
                if tracks
                else set()
            ),
        },
        "completion_claim": "none",
        "limitations": limitations,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path, help="report files or directories")
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--out", type=Path, default=Path(".local/traversal-stats"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = iter_report_paths(args.reports)
        reports = [report for report in (load_report(path) for path in paths) if report]
        if not reports:
            raise TraversalError("no exploration reports found in the given inputs")
        source_index = None
        source_index_sha256 = None
        if args.source_index:
            raw = Path(args.source_index).read_bytes()
            source_index = json.loads(raw.decode("utf-8"))
            source_index_sha256 = _sha256(raw)
        report = collect(
            reports,
            source_index=source_index,
            source_index_sha256=source_index_sha256,
        )
    except TraversalError as exc:
        print(f"[traversal-stats] invalid input: {exc}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "traversal-stats.json"
    atomic_write_json(json_path, report)
    print(
        "[traversal-stats] tracks={tracks} runs={runs} report={path}".format(
            tracks=",".join(report["tracks"]),
            runs=report["totals"]["runs"],
            path=json_path,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
