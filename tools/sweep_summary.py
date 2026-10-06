"""Aggregate shard reports and fail closed on missing or mixed evidence."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import sweep_ledger as sl  # noqa: E402

TOOL = "sweep_summary"
VERDICTS = ("ok", "soft_fail", "hard_fail", "fixture_insufficient", "not_applicable")


def _result_verdict(result: dict[str, Any]) -> str:
    return str(result.get("verdict") or result.get("status") or "unknown")


def _completeness(report: dict[str, Any]) -> tuple[bool, list[str]]:
    completeness = report.get("completeness")
    if isinstance(completeness, dict):
        return bool(completeness.get("ok")), [str(item) for item in completeness.get("diagnostics") or []]
    validation = (report.get("ledger") or {}).get("validation")
    if isinstance(validation, dict):
        return bool(validation.get("ok")), [str(item) for item in validation.get("diagnostics") or []]
    return False, ["report has no completeness block"]


def _identity(report: dict[str, Any]) -> dict[str, Any] | None:
    ledger = report.get("ledger")
    if isinstance(ledger, dict) and isinstance(ledger.get("identity"), dict):
        return ledger["identity"]
    if isinstance(ledger, dict) and isinstance(ledger.get("ledger_identity"), dict):
        return ledger["ledger_identity"]
    identity = report.get("ledger_identity")
    return identity if isinstance(identity, dict) else None


def _comparable_identity(identity: dict[str, Any]) -> dict[str, Any]:
    comparable = dict(identity)
    comparable.pop("plan_digest", None)
    strategy = dict(comparable.get("strategy") or {})
    strategy.pop("shard_index", None)
    strategy.pop("shard_count", None)
    comparable["strategy"] = strategy
    return comparable


def _result_key(result: dict[str, Any]) -> str:
    value = result.get("key")
    if value is not None and str(value):
        return str(value)
    name = result.get("name")
    context = result.get("context")
    if name is not None and str(name):
        return f"{context}#{name}" if context is not None else str(name)
    section = result.get("section")
    index = result.get("index")
    if section is not None and index is not None:
        return f"{section}#{index}"
    return "<missing-key>"


def aggregate_reports(
    reports: Sequence[dict[str, Any]], *, expected_shards: int | None = None
) -> dict[str, Any]:
    errors: list[str] = []
    if expected_shards is not None and len(reports) != expected_shards:
        errors.append(f"expected {expected_shards} shards, got {len(reports)}")
    seen: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    counts: collections.Counter[str] = collections.Counter()
    for index, report in enumerate(reports):
        label = str(report.get("target") or report.get("html_path") or f"report-{index}")
        complete, completeness_diagnostics = _completeness(report)
        if not complete:
            errors.append(f"{label}: incomplete ({'; '.join(completeness_diagnostics[:2])})")
        identity = _identity(report)
        if identity is None:
            errors.append(f"{label}: no ledger identity")
        else:
            identities.append(identity)
        for result in report.get("results") or []:
            if not isinstance(result, dict):
                errors.append(f"{label}: non-object result")
                continue
            key = _result_key(result)
            verdict = _result_verdict(result)
            if key in seen:
                errors.append(f"{label}: duplicate result key {key}")
                continue
            seen[key] = verdict
            counts[verdict] += 1
            results.append(result)
    if identities:
        first = identities[0]
        for index, identity in enumerate(identities[1:], 1):
            for field in ("html_sha256", "fixture_digest"):
                if identity.get(field) != first.get(field):
                    errors.append(
                        f"shard {index}: {field} mismatch: "
                        f"{first.get(field)!r} != {identity.get(field)!r}"
                    )
        by_kind: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for identity in identities:
            by_kind[str(identity.get("kind"))].append(identity)
        for kind, group in by_kind.items():
            comparable = _comparable_identity(group[0])
            for index, identity in enumerate(group[1:], 1):
                ok, diagnostics = sl.identity_matches(
                    comparable, _comparable_identity(identity)
                )
                if not ok:
                    errors.append(
                        f"{kind} shard {index}: identity mismatch: "
                        f"{'; '.join(diagnostics[:3])}"
                    )
    summary = {
        "tool": TOOL,
        "ok": not errors,
        "errors": errors,
        "shards": len(reports),
        "results": len(results),
        "verdict_counts": {verdict: counts.get(verdict, 0) for verdict in VERDICTS},
        "unknown_verdicts": sorted(
            verdict for verdict in counts if verdict not in VERDICTS
        ),
    }
    return {"summary": summary, "results": results, "identities": identities}


def write_summary(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "sweep-summary.json"
    sl.atomic_write_json(json_path, payload)
    summary = payload["summary"]
    lines = [
        "# DOL-X sweep shard summary",
        "",
        f"- ok: **{summary['ok']}**",
        f"- shards: {summary['shards']}",
        f"- results: {summary['results']}",
        "",
        "## verdicts",
        "",
        "| verdict | count |",
        "| --- | --- |",
    ]
    for verdict in VERDICTS:
        lines.append(f"| {verdict} | {summary['verdict_counts'].get(verdict, 0)} |")
    if summary["errors"]:
        lines += ["", "## errors", ""]
        lines.extend(f"- {error}" for error in summary["errors"])
    md_path = out_dir / "sweep-summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate DOL-X sweep shard reports")
    parser.add_argument("reports", nargs="+", type=Path, help="shard JSON reports")
    parser.add_argument("--out", type=Path, default=Path(".local/sweep/summary"))
    parser.add_argument("--expected-shards", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reports: list[dict[str, Any]] = []
    load_errors: list[str] = []
    for path in args.reports:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("root is not an object")
            reports.append(payload)
        except Exception as exc:  # noqa: BLE001 - every shard must be auditable
            load_errors.append(f"{path}: {type(exc).__name__}: {exc}")
    payload = aggregate_reports(reports, expected_shards=args.expected_shards)
    payload["summary"]["errors"] = load_errors + payload["summary"]["errors"]
    payload["summary"]["ok"] = not payload["summary"]["errors"]
    json_path, md_path = write_summary(payload, args.out)
    print(f"[sweep-summary] ok={payload['summary']['ok']} -> {md_path}")
    return 0 if payload["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
