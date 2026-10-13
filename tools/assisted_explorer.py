#!/usr/bin/env python3
"""Source-edge assisted explorer for deep DOL-X coverage.

The natural explorer may never reach a passage because a player has not yet
earned a rare state.  This runner deliberately uses the source index and the
game's own ``Engine.play`` to prove that a passage can render under a valid
fixture.  Every result is tagged ``assisted``; it must never be counted as
``natural`` reachability.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

if __package__ in (None, ""):  # allow ``python tools/assisted_explorer.py``
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import passage_sweep as ps
from tools.exploration_archive import plan_failure_archive, write_failure_archive
from tools.exploration_runtime import RuntimeSession, snapshot_runtime
from tools.sweep_ledger import atomic_write_json
from tools.target_manifest import build_manifest, validate_manifest


SCHEMA = "dolx.assisted-exploration.v1"
RUNNER_VERSION = "dol-x-assisted-explorer-v1"


def source_refs(edge: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "path": edge.get("path"),
            "line": edge.get("line"),
            "kind": edge.get("kind"),
            "macro": edge.get("macro"),
            "owner": edge.get("owner"),
        }
    ]


def plan_source_edges(
    source_index: Mapping[str, Any],
    *,
    limit: int | None = None,
    shard_index: int | None = None,
    shard_count: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collapse static source edges into one assisted plan row per target."""
    passage_names = {
        str(item.get("name") or "")
        for item in (source_index.get("passages") or [])
        if isinstance(item, Mapping) and item.get("name")
    }
    grouped: dict[str, dict[str, Any]] = {}
    dynamic = 0
    invalid = 0
    unresolved = 0
    for edge in source_index.get("edges") or []:
        if not isinstance(edge, Mapping):
            invalid += 1
            continue
        target = edge.get("target")
        if edge.get("target_kind") != "static" or not str(target or "").strip():
            dynamic += 1
            continue
        target_name = str(target)
        if target_name not in passage_names:
            unresolved += 1
            continue
        row = grouped.setdefault(
            target_name,
            {"target": target_name, "source_refs": [], "assistance": ["source_edge"]},
        )
        refs = source_refs(edge)
        if refs[0] not in row["source_refs"]:
            row["source_refs"].append(refs[0])
    rows = sorted(grouped.values(), key=lambda item: item["target"])
    if limit is not None:
        rows = rows[: max(0, limit)]
    stats: dict[str, Any] = {
        "source_edges": len(source_index.get("edges") or []),
        "static_targets": len(grouped),
        "dynamic_edges": dynamic,
        "invalid_edges": invalid,
        "unresolved_static_targets": unresolved,
    }
    if shard_count is not None:
        if shard_count <= 0:
            raise ValueError("shard count must be positive")
        if shard_index is None or not 0 <= shard_index < shard_count:
            raise ValueError("shard index must be between zero and shard count - 1")
        stats["shard_index"] = shard_index
        stats["shard_count"] = shard_count
        rows = rows[shard_index::shard_count]
    if limit is not None:
        rows = rows[: max(0, limit)]
    stats["planned"] = len(rows)
    return rows, stats


def _fixture_json(path: Path) -> str:
    from tools.fixture_ladder import load_fixture

    fixture = load_fixture(path)
    variables = fixture.get("variables") if isinstance(fixture, Mapping) else None
    if not isinstance(variables, dict) or not variables:
        raise ValueError(f"fixture has no variables object: {path}")
    return json.dumps(
        {"variables": variables},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def summarize_results(results: list[dict[str, Any]], stats: Mapping[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for result in results:
        verdict = str(result.get("verdict") or "unknown")
        counts[verdict] = counts.get(verdict, 0) + 1
    return {
        "planned": stats.get("planned"),
        "executed": len(results),
        "verdicts": counts,
        "assisted_target_coverage": len(
            {result.get("target") for result in results if result.get("verdict") == "ok"}
        ),
        "dynamic_edges": stats.get("dynamic_edges"),
        "shard": {
            "index": stats.get("shard_index"),
            "count": stats.get("shard_count"),
        },
        "completion_claim": "assisted_only",
    }


def run_source_edges(
    target: Path,
    *,
    source_index_path: Path,
    fixture_path: Path,
    out_dir: Path,
    limit: int | None = None,
    seed: int = 1719,
    expected_version: str | None = None,
    tag: str | None = None,
    mods_lock: Path | None = None,
    build_toml: Path | None = None,
    source_commit: str | None = None,
    headless: bool = True,
    timeout_ms: int = 8000,
    shard_index: int | None = None,
    shard_count: int | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    target = Path(target)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_index = json.loads(Path(source_index_path).read_text(encoding="utf-8"))
    plan, stats = plan_source_edges(
        source_index,
        limit=limit,
        shard_index=shard_index,
        shard_count=shard_count,
    )
    manifest = build_manifest(
        target,
        expected_version=expected_version,
        mods_lock=mods_lock,
        build_toml=build_toml,
        source_commit=source_commit,
        source_index=source_index_path,
        runner_revision=RUNNER_VERSION,
        tag=tag,
    )
    atomic_write_json(out_dir / "target-manifest.json", manifest)
    identity_ok, diagnostics = validate_manifest(manifest)
    existing_results: list[dict[str, Any]] = []
    resume_error: str | None = None
    report_path = out_dir / "assisted-exploration-report.json"
    if resume and identity_ok and report_path.exists():
        try:
            previous = json.loads(report_path.read_text(encoding="utf-8"))
            previous_manifest = previous.get("target_manifest") or {}
            previous_shard = (previous.get("summary") or {}).get("shard") or {}
            same_identity = (
                previous.get("schema") == SCHEMA
                and previous.get("evidence_track") == "assisted"
                and (previous_manifest.get("target") or {}).get("package_sha256")
                == manifest.get("target", {}).get("package_sha256")
                and previous_manifest.get("source_index_sha256")
                == manifest.get("source_index_sha256")
                and previous_shard
                == {
                    "index": stats.get("shard_index"),
                    "count": stats.get("shard_count"),
                }
            )
            if same_identity and isinstance(previous.get("results"), list):
                existing_results = [
                    dict(result)
                    for result in previous["results"]
                    if isinstance(result, Mapping)
                ]
                seen_targets = {
                    str(result.get("target"))
                    for result in existing_results
                    if result.get("target") is not None
                }
                plan = [
                    entry
                    for entry in plan
                    if str(entry.get("target")) not in seen_targets
                ]
                stats["resumed_results"] = len(existing_results)
        except Exception as exc:  # noqa: BLE001 - resume must not kill the new run.
            resume_error = f"{type(exc).__name__}: {exc}"
    else:
        resume_error = None
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "runner": RUNNER_VERSION,
        "status": "infrastructure_fail" if not identity_ok else "running",
        "evidence_track": "assisted",
        "seed": seed,
        "target_manifest": manifest,
        "source_index_sha256": manifest.get("source_index_sha256"),
        "plan": {"stats": stats, "entries": plan},
        "results": existing_results,
    }
    if not identity_ok:
        report["diagnostics"] = diagnostics
        report["summary"] = summarize_results([], stats)
        atomic_write_json(
            out_dir / "assisted-exploration-report.json",
            report,
            validate_readback=False,
        )
        return report
    if resume_error:
        report["resume_error"] = resume_error

    encoded_fixture = _fixture_json(fixture_path)
    with RuntimeSession(target, headless=headless) as session:
        page = session.page
        boot = session.bootstrap_natural(max_steps=300, deadline_s=240)
        if not boot.get("ok"):
            report.update(
                {
                    "status": "infrastructure_fail",
                    "stop_reason": "bootstrap_failed",
                    "bootstrap": boot,
                    "summary": summarize_results([], stats),
                }
            )
            atomic_write_json(
                out_dir / "assisted-exploration-report.json",
                report,
                validate_readback=False,
            )
            return report
        loaded = page.evaluate(ps.LOAD_FIXTURE, encoded_fixture)
        if not loaded.get("ok"):
            report.update(
                {
                    "status": "infrastructure_fail",
                    "stop_reason": "fixture_load_failed",
                    "fixture_load": loaded,
                    "summary": summarize_results([], stats),
                }
            )
            atomic_write_json(
                out_dir / "assisted-exploration-report.json",
                report,
                validate_readback=False,
            )
            return report

        report["status"] = "running"
        for entry in plan:
            target_name = str(entry["target"])
            result: dict[str, Any] = {
                "target": target_name,
                "evidence_track": "assisted",
                "assistance": ["source_edge", "fixture_restore", "engine_play"],
                "source_refs": entry.get("source_refs") or [],
            }
            before = None
            after = None
            try:
                page.evaluate(ps.RESTORE_FIXTURE)
                page.evaluate(ps.PLAY_PASSAGE, {"name": target_name})
                page.wait_for_function(
                    "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                    timeout=timeout_ms,
                )
                probe = page.evaluate(ps.PROBE)
                verdict, detail = ps.classify(
                    probe,
                    landed_ok=str(probe.get("passage") or "") == target_name,
                )
                result["verdict"] = verdict
                result["detail"] = detail
                result["errors"] = probe.get("errors") or []
                result["probe"] = {
                    key: value
                    for key, value in probe.items()
                    if key in {"passage", "done", "textLen", "linkCount", "childCount", "hasPassageNode"}
                }
            except Exception as exc:  # noqa: BLE001 - one edge must not kill a run
                result["verdict"] = "hard_fail"
                result["detail"] = f"{type(exc).__name__}: {exc}"
                result["errors"] = [{"kind": "pageerror", "message": str(exc)[:1000]}]

            try:
                before = snapshot_runtime(page, session.new_observations())
                after = snapshot_runtime(page, session.new_observations())
                result["fingerprint"] = after.fingerprint.get("exact_hash")
                result["coarse_hash"] = after.fingerprint.get("coarse_hash")
            except Exception as exc:  # noqa: BLE001 - render evidence remains valid
                result["runtime_snapshot_error"] = f"{type(exc).__name__}: {exc}"

            if result.get("verdict") == "hard_fail":
                failure = {
                    "schema": SCHEMA,
                    "verdict": "hard_fail",
                    "detail": result.get("detail"),
                    "evidence_track": "assisted",
                    "assistance": result.get("assistance"),
                    "action": {"semantic_id": f"source-edge:{target_name}", "kind": "engine_play"},
                    "trace": {"actions": []},
                    "source_refs": result.get("source_refs") or [],
                }
                archive = plan_failure_archive(
                    failure=failure,
                    manifest=manifest,
                    seed=seed,
                    before={"passage": target_name, **(before.fingerprint if before else {})},
                    after={"passage": target_name, **(after.fingerprint if after else {})},
                    observations=session.new_observations(),
                    source_refs=result.get("source_refs") or [],
                )
                try:
                    write_failure_archive(out_dir / "failures", archive)
                    result["failure_archive"] = archive["directory"]
                except Exception:
                    result["failure_archive_error"] = True
            report["results"].append(result)
            # Long shards must not lose every completed target if the browser,
            # runner, or host is killed before the final report is written.
            report["summary"] = summarize_results(report["results"], stats)
            report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            atomic_write_json(
                out_dir / "assisted-exploration-report.json",
                report,
                validate_readback=False,
            )
        report["status"] = "complete"
        report["summary"] = summarize_results(report["results"], stats)
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write_json(
        out_dir / "assisted-exploration-report.json",
        report,
        validate_readback=False,
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--source-index", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=1719)
    parser.add_argument("--expect-version")
    parser.add_argument("--tag")
    parser.add_argument("--mods-lock", type=Path)
    parser.add_argument("--build-toml", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=8000)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse matching results from an interrupted shard report",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_source_edges(
        args.target,
        source_index_path=args.source_index,
        fixture_path=args.fixture,
        out_dir=args.out,
        limit=args.limit,
        seed=args.seed,
        expected_version=args.expect_version,
        tag=args.tag,
        mods_lock=args.mods_lock,
        build_toml=args.build_toml,
        source_commit=args.source_commit,
        headless=not args.headed,
        timeout_ms=args.timeout_ms,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        resume=args.resume,
    )
    print(json.dumps({"status": report["status"], "executed": report["summary"]["executed"], "out": str(args.out)}))
    return 0 if report["status"] == "complete" and not report["summary"]["verdicts"].get("hard_fail") else 2


if __name__ == "__main__":
    raise SystemExit(main())
