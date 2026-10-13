"""Aggregate honest coverage and failure summaries for gameplay exploration."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


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

ATTRIBUTION_KEYS = ("attribution", "upstream", "upstream_reference")


def _count(values: Iterable[Any]) -> dict[str, int]:
    counter = Counter(str(value) for value in values)
    return {key: counter[key] for key in sorted(counter)}


def _action_count(report: Mapping[str, Any], actions: list[Any]) -> int:
    counted = report.get("action_count")
    if isinstance(counted, int) and counted >= 0:
        return counted
    return len(actions)


def _failure_count(report: Mapping[str, Any], failures: list[Any]) -> int:
    counted = report.get("failure_count")
    if isinstance(counted, int) and counted >= 0:
        return counted
    return len(failures)


def _unattributed_hard_failures(failures: list[Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in failures
        if item.get("verdict") == "hard_fail"
        and not any(item.get(key) for key in ATTRIBUTION_KEYS)
    ]


def summarize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    actions = report.get("actions") or []
    failures = report.get("failures") or []
    evidence_tracks = [
        item.get("evidence_track") or report.get("evidence_track")
        for item in actions
    ]
    return {
        "schema": "dolx.exploration-summary.v1",
        "target": (report.get("target_manifest") or {}).get("target"),
        "status": report.get("status"),
        "stop_reason": report.get("stop_reason"),
        "evidence_track": report.get("evidence_track"),
        "action_count": _action_count(report, actions),
        "verdicts": _count(item.get("verdict") for item in actions),
        "failure_count": _failure_count(report, failures),
        "failure_kinds": _count(item.get("verdict") for item in failures),
        "unattributed_hard_failures": [
            {
                "step": item.get("step"),
                "detail": item.get("detail"),
                "semantic_id": (item.get("action") or {}).get("semantic_id")
                if isinstance(item.get("action"), Mapping)
                else None,
            }
            for item in _unattributed_hard_failures(failures)
        ],
        "unique_coarse_states": report.get("unique_coarse_states"),
        "coverage": {
            "passage_first_seen": _count(
                item.get("passage_after") for item in actions if item.get("passage_after")
            ),
            "action_kinds": _count(item.get("kind") for item in actions),
            "action_tracks": _count(evidence_tracks),
        },
        "completion_claim": "none",
        "limitations": [
            "natural track only proves semantic reachability through visible controls",
            "assisted surfaces must be reported separately",
            "Android replay must use semantic IDs, not desktop locators",
            "no gate claim is made until unattributed hard failures are zero",
        ],
    }


def summarize_many(reports: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    summaries = [
        report
        if report.get("schema") == "dolx.exploration-summary.v1"
        else summarize_report(report)
        for report in reports
    ]
    return {
        "schema": "dolx.exploration-summary-batch.v1",
        "runs": summaries,
        "totals": {
            "runs": len(summaries),
            "actions": sum(item["action_count"] for item in summaries),
            "failures": sum(item["failure_count"] for item in summaries),
            "unique_coarse_states": sum(
                int(item.get("unique_coarse_states") or 0) for item in summaries
            ),
        },
        "verdicts": {
            verdict: sum(item["verdicts"].get(verdict, 0) for item in summaries)
            for verdict in VERDICTS
        },
    }


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = summarize_many(load_report(path) for path in args.reports)
    encoded = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
