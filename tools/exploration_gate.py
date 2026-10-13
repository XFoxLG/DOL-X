"""Fail-closed release/evidence gate for gameplay exploration reports."""

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

from tools.exploration_summary import summarize_report
from tools.sweep_ledger import atomic_write_json


SCHEMA = "dolx.exploration-gate.v1"
IDENTITY_FIELDS = (
    "game_version",
    "target_tag",
    "package_sha256",
    "html_member",
    "package_type",
)
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


def _reports(values: Iterable[Any]) -> list[dict[str, Any]]:
    rows = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise ValueError(f"report {index} is not an object")
        rows.append(dict(value))
    return rows


def _target_identity(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: (report.get("target_manifest") or {}).get("target", {}).get(field)
        for field in IDENTITY_FIELDS
    }


def _manifest_valid(report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    from tools.target_manifest import validate_manifest

    manifest = report.get("target_manifest")
    if not isinstance(manifest, Mapping):
        return False, ["target manifest missing"]
    return validate_manifest(manifest)


def _unattributed(failure: Mapping[str, Any]) -> bool:
    return (
        failure.get("verdict") == "hard_fail"
        and not any(failure.get(key) for key in ("attribution", "upstream", "upstream_reference"))
    )


def _story_graph_classified(payload: Mapping[str, Any] | None) -> bool:
    """Release condition: every dead end and dangling target is classified."""
    if not isinstance(payload, Mapping):
        return False
    blocking = payload.get("blocking") or {}
    return (
        payload.get("mode") == "full"
        and blocking.get("html_provided") is True
        and not blocking.get("unclassified_dead_ends")
        and not blocking.get("unclassified_undefined_targets")
    )


def _traversal_stats_complete(payload: Mapping[str, Any] | None) -> bool:
    """Release condition: traversal statistics carry a natural-track basis."""
    if not isinstance(payload, Mapping) or payload.get("schema") != "dolx.traversal-stats.v1":
        return False
    tracks = payload.get("tracks") or {}
    natural = tracks.get("natural") or {}
    denominators = payload.get("denominators") or {}
    return (
        natural.get("coverage_basis") == "actions"
        and bool(denominators.get("passages"))
        and natural.get("passage_coverage") is not None
    )


def _query_regression_passed(payload: Mapping[str, Any] | None) -> bool:
    if not isinstance(payload, Mapping) or payload.get("schema") != "dolx.query-regression.v1":
        return False
    return not (payload.get("release_blocking") or [])


def _symbolic_reachability_available(payload: Mapping[str, Any] | None) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != "dolx.symbolic_reachability.v1":
        return False
    return payload.get("verdict") != "solver_unavailable"


def _au_contract_passed(payload: Mapping[str, Any] | list[Any] | None) -> bool:
    rows: list[Any]
    if isinstance(payload, Mapping):
        rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        return False
    au_rows = [row for row in rows if isinstance(row, Mapping) and row.get("is_au")]
    if not au_rows:
        return False
    for row in au_rows:
        contract = row.get("au_contract") or {}
        if contract.get("schema") != "dolx.au_contract.v1":
            return False
        if contract.get("errors"):
            return False
        if int(contract.get("framework_face_style_src_fn_export_count") or 0) < 1:
            return False
        if int(contract.get("framework_variant_dir_shim_marker_count") or 0) != 1:
            return False
    return True


def _framework_contract_consistent(payload: Mapping[str, Any] | None) -> bool:
    return isinstance(payload, Mapping) and payload.get("verdict") == "consistent"


def _failure_rows(reports: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        track = report.get("evidence_track")
        for failure in report.get("failures") or []:
            if not isinstance(failure, Mapping):
                continue
            rows.append(
                {
                    "evidence_track": failure.get("evidence_track") or track,
                    **dict(failure),
                }
            )
    return rows


def _verdict_counts(values: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("verdict") or "unknown") for item in values)
    return {verdict: counter.get(verdict, 0) for verdict in VERDICTS}


def _source_surface(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"present": False}
    try:
        raw = Path(path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        index = json.loads(raw.decode("utf-8"))
        stats = index.get("stats") or {}
        passage_names = {
            str(item.get("name") or "")
            for item in (index.get("passages") or [])
            if isinstance(item, Mapping) and item.get("name")
        }
        static_targets = {
            str(edge.get("target"))
            for edge in (index.get("edges") or [])
            if isinstance(edge, Mapping)
            and edge.get("target_kind") == "static"
            and str(edge.get("target") or "").strip() in passage_names
        }
        return {
            "present": True,
            "sha256": digest,
            "source_commit": index.get("source_commit"),
            "passages": stats.get("passages"),
            "edges": stats.get("edges"),
            "static_edges": stats.get("static_edges"),
            "dynamic_edges": stats.get("dynamic_edges"),
            "variable_reads": stats.get("variable_reads"),
            "variable_writes": stats.get("variable_writes"),
            "static_targets": len(static_targets),
        }
    except Exception as exc:  # noqa: BLE001 - gate must name the evidence gap.
        return {"present": False, "error": f"{type(exc).__name__}: {exc}"}


def _file_surface(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"present": False}
    try:
        return {
            "present": True,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        }
    except Exception as exc:  # noqa: BLE001 - gate must name the identity gap.
        return {"present": False, "error": f"{type(exc).__name__}: {exc}"}


def build_gate(
    reports: Iterable[Any],
    *,
    android_summary: Mapping[str, Any] | None = None,
    source_index: Path | None = None,
    mod_inventory: Mapping[str, Any] | None = None,
    mod_passage_sweep: Mapping[str, Any] | None = None,
    release: bool = False,
    assisted_full_coverage: bool = False,
    target: Path | None = None,
    mods_lock: Path | None = None,
    symbolic_reachability: Mapping[str, Any] | None = None,
    story_graph_audit: Mapping[str, Any] | None = None,
    traversal_stats: Mapping[str, Any] | None = None,
    query_regression: Mapping[str, Any] | None = None,
    au_contract: Mapping[str, Any] | list[Any] | None = None,
    framework_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _reports(reports)
    if not rows:
        raise ValueError("gate requires at least one report")

    identities = [_target_identity(row) for row in rows]
    identity_consistent = len({json.dumps(item, sort_keys=True) for item in identities}) == 1
    manifest_results = [_manifest_valid(row) for row in rows]
    identity_complete = all(ok for ok, _diagnostics in manifest_results)
    identity_diagnostics = [
        f"report {index}: {'; '.join(diagnostics[:3])}"
        for index, (ok, diagnostics) in enumerate(manifest_results)
        if not ok
    ]
    if not identity_consistent:
        identity_diagnostics.append("reports do not share one target identity")

    all_runs_complete = all(row.get("status") == "complete" for row in rows)
    failures = _failure_rows(rows)
    unattributed = [item for item in failures if _unattributed(item)]
    natural_rows = [row for row in rows if row.get("evidence_track") in {"natural", "natural_prefix"}]
    assisted_rows = [row for row in rows if row.get("evidence_track") == "assisted"]

    natural_summaries = [summarize_report(row) for row in natural_rows]
    assisted_summaries = [row.get("summary") or {} for row in assisted_rows if isinstance(row.get("summary"), Mapping)]
    source_surface = _source_surface(source_index)
    target_surface = _file_surface(target)
    mods_lock_surface = _file_surface(mods_lock)
    expected_static_targets = source_surface.get("static_targets")
    assisted_result_rows = [
        dict(result)
        for row in assisted_rows
        for result in (row.get("results") or [])
        if isinstance(result, Mapping)
    ]
    target_counts = Counter(
        str(result.get("target"))
        for result in assisted_result_rows
        if result.get("target") is not None
    )
    duplicate_targets = sorted(
        target for target, count in target_counts.items() if count > 1
    )
    assisted_ok_targets = {
        str(result.get("target"))
        for result in assisted_result_rows
        if result.get("target") is not None and result.get("verdict") == "ok"
    }
    assisted_targets_unique = not duplicate_targets
    assisted_static_targets_covered = (
        None
        if expected_static_targets is None
        else (
            int(expected_static_targets) > 0
            and len(assisted_ok_targets) >= int(expected_static_targets)
            and assisted_targets_unique
        )
    )
    android = dict(android_summary or {})
    manifest = rows[0].get("target_manifest") or {}
    inventory = dict(mod_inventory or {})
    inventory_counts = inventory.get("counts") or {}
    inventory_buttons = (inventory.get("mod_buttons") or {}).get("summary") or {}
    inventory_mods = inventory.get("mods") or []
    inventory_errors = inventory.get("errors") or []
    static_missing = inventory.get("static_missing_from_runtime") or []
    unregistered = inventory.get("unregistered_names") or []
    inventory_payload_count_matches = (
        not inventory or len(inventory_mods) == int(manifest.get("embedded_mod_count") or 0)
    )
    mod_inventory_surface_present = bool(inventory and inventory_counts)
    mod_inventory_no_errors = not inventory_errors
    mod_buttons_no_throws = int(inventory_buttons.get("thrown") or 0) == 0
    static_surface_complete = len(static_missing) == 0
    mod_passages_classified = len(unregistered) == 0
    expected_mod_playable = [
        str(name) for name in (inventory.get("playable_names") or []) if str(name).strip()
    ]
    passage_sweep = dict(mod_passage_sweep or {})
    passage_results = [
        dict(result)
        for result in (passage_sweep.get("results") or [])
        if isinstance(result, Mapping)
    ]
    passage_target_counts = Counter(
        str(result.get("name"))
        for result in passage_results
        if result.get("name") is not None
    )
    duplicate_mod_passages = sorted(
        name for name, count in passage_target_counts.items() if count > 1
    )
    attempted_mod_passages = set(passage_target_counts)
    missing_mod_passages = sorted(
        name for name in expected_mod_playable if name not in attempted_mod_passages
    )
    passage_verdict_counts = _verdict_counts(passage_results)
    mod_sweep_completeness_ok = bool(
        (passage_sweep.get("completeness") or {}).get("ok")
    ) if passage_sweep else None
    mod_passage_sweep_present = bool(passage_sweep and passage_results)
    mod_passage_sweep_no_errors = (
        not passage_sweep.get("fatal_error")
        and passage_verdict_counts.get("hard_fail", 0) == 0
        and not duplicate_mod_passages
        and mod_sweep_completeness_ok is not False
    ) if passage_sweep else None
    mod_playable_passages_covered = (
        bool(expected_mod_playable)
        and mod_passage_sweep_present
        and not missing_mod_passages
        and mod_sweep_completeness_ok is not False
        and passage_verdict_counts.get("hard_fail", 0) == 0
        and not duplicate_mod_passages
    ) if inventory else None
    android_gate_ready = bool(
        android.get("verdict") == "ok"
        and android.get("cdp_connected") is True
        and int((android.get("totals") or {}).get("planned") or 0) > 0
        and int((android.get("totals") or {}).get("matched") or 0)
        == int((android.get("totals") or {}).get("planned") or 0)
    )
    source_commit_present = bool((manifest.get("target") or {}).get("source_commit"))
    mods_lock_digest_present = bool(manifest.get("mods_lock_sha256"))
    source_index_digest_present = bool(manifest.get("source_index_sha256"))
    source_index_digest_matches = (
        source_surface.get("present") is True
        and bool(manifest.get("source_index_sha256"))
        and source_surface.get("sha256") == manifest.get("source_index_sha256")
    )
    source_commit_matches_index = (
        source_surface.get("present") is True
        and bool(source_commit_present)
        and bool(source_surface.get("source_commit"))
        and source_surface.get("source_commit") == (manifest.get("target") or {}).get("source_commit")
    )
    expected_package_sha256 = (manifest.get("target") or {}).get("package_sha256")
    expected_mods_lock_sha256 = manifest.get("mods_lock_sha256")
    target_sha256_matches = bool(
        target_surface.get("present")
        and expected_package_sha256
        and target_surface.get("sha256") == expected_package_sha256
    )
    mods_lock_sha256_matches = bool(
        mods_lock_surface.get("present")
        and expected_mods_lock_sha256
        and mods_lock_surface.get("sha256") == expected_mods_lock_sha256
    )
    story_graph_ok = _story_graph_classified(story_graph_audit)
    traversal_ok = _traversal_stats_complete(traversal_stats)
    query_ok = _query_regression_passed(query_regression)
    symbolic_ok = _symbolic_reachability_available(symbolic_reachability)
    au_ok = _au_contract_passed(au_contract)
    framework_ok = _framework_contract_consistent(framework_contract)

    conditions = {
        "identity_complete": identity_complete,
        "identity_consistent": identity_consistent,
        "all_runs_complete": all_runs_complete,
        "no_unattributed_hard_fail": not unattributed,
        "source_commit_present": source_commit_present if release else None,
        "mods_lock_digest_present": mods_lock_digest_present if release else None,
        "source_index_digest_present": source_index_digest_present if release else None,
        "source_index_digest_matches": source_index_digest_matches if release else None,
        "source_commit_matches_index": source_commit_matches_index if release else None,
        "target_sha256_matches": (
            target_sha256_matches if release or target is not None else None
        ),
        "mods_lock_sha256_matches": (
            mods_lock_sha256_matches if release or mods_lock is not None else None
        ),
        "assisted_targets_unique": (
            assisted_targets_unique if release or assisted_full_coverage else None
        ),
        "assisted_static_targets_covered": (
            assisted_static_targets_covered
            if release or assisted_full_coverage
            else None
        ),
        "mod_inventory_surface_present": mod_inventory_surface_present if release else None,
        "mod_payload_count_matches": inventory_payload_count_matches if inventory else None,
        "mod_inventory_no_errors": mod_inventory_no_errors if inventory else None,
        "mod_buttons_no_throws": mod_buttons_no_throws if inventory else None,
        "static_surface_complete": static_surface_complete if inventory else None,
        "mod_passages_classified": mod_passages_classified if inventory else None,
        "mod_passage_sweep_present": (
            mod_passage_sweep_present if release or inventory else None
        ),
        "mod_playable_passages_covered": (
            mod_playable_passages_covered if release or inventory else None
        ),
        "mod_passage_sweep_no_errors": (
            mod_passage_sweep_no_errors if mod_passage_sweep else None
        ),
        "android_gate_ready": android_gate_ready if release else None,
        "story_graph_dead_ends_classified": story_graph_ok if release else None,
        "query_regression_passed": query_ok if release else None,
        "traversal_report_complete": traversal_ok if release else None,
        "symbolic_reachability_available": symbolic_ok if release else None,
        "au_contract_passed": au_ok if release else None,
        "framework_contract_consistent": framework_ok if release else None,
    }
    blocking = [key for key, value in conditions.items() if value is False]
    limitations: list[str] = []
    if source_index is None:
        limitations.append("source index surface was not supplied")
    if source_index is not None and expected_static_targets is None:
        limitations.append("source index could not supply a static target count")
    if not android:
        limitations.append("Android replay evidence was not supplied")
    if release and target is None:
        limitations.append("release target package was not supplied")
    if release and mods_lock is None:
        limitations.append("release mods lock file was not supplied")
    if release and symbolic_reachability is None:
        limitations.append("release symbolic reachability report was not supplied")
    if release and story_graph_audit is None:
        limitations.append("release story graph audit was not supplied")
    if release and traversal_stats is None:
        limitations.append("release traversal statistics were not supplied")
    if release and query_regression is None:
        limitations.append("release query regression report was not supplied")
    if release and au_contract is None:
        limitations.append("release AU contract report was not supplied")
    if release and framework_contract is None:
        limitations.append("release framework contract check was not supplied")
    if not release:
        limitations.append("release gate was not requested")
    if assisted_full_coverage:
        limitations.append("assisted full-coverage gate was requested")

    return {
        "schema": SCHEMA,
        "mode": "release" if release else ("assisted_full_coverage" if assisted_full_coverage else "evidence_only"),
        "target_identity": identities[0],
        "target_manifest": rows[0].get("target_manifest") or {},
        "surface": {
            "embedded_payloads": len(
                (rows[0].get("target_manifest") or {}).get("embedded_payloads") or []
            ),
            "source_index": source_surface,
            "target_package": {
                **target_surface,
                "expected_sha256": expected_package_sha256,
                "matches": target_sha256_matches,
            },
            "mods_lock": {
                **mods_lock_surface,
                "expected_sha256": expected_mods_lock_sha256,
                "matches": mods_lock_sha256_matches,
            },
            "mod_inventory": {
                "present": mod_inventory_surface_present,
                "html_sha256": inventory.get("html_sha256"),
                "counts": inventory_counts,
                "payload_count": len(inventory_mods),
                "errors": inventory_errors,
                "playable_names": inventory.get("playable_names") or [],
                "widget_names": inventory.get("widget_names") or [],
                "unregistered_names": unregistered,
                "static_missing_from_runtime": static_missing,
                "opaque_mods": inventory.get("opaque_mods") or [],
                "mod_buttons": inventory_buttons,
            },
            "mod_passage_sweep": {
                "present": mod_passage_sweep_present,
                "status": passage_sweep.get("status"),
                "completeness": passage_sweep.get("completeness") or {},
                "expected_playable": len(expected_mod_playable),
                "attempted": len(passage_results),
                "missing": missing_mod_passages,
                "duplicate": duplicate_mod_passages,
                "verdicts": passage_verdict_counts,
            },
        },
        "coverage": {
            "natural_runs": len(natural_rows),
            "natural_actions": sum(item["action_count"] for item in natural_summaries),
            "natural_unique_coarse_states": sum(
                int(item.get("unique_coarse_states") or 0) for item in natural_summaries
            ),
            "assisted_runs": len(assisted_rows),
            "assisted_planned": sum(int(item.get("planned") or 0) for item in assisted_summaries),
            "assisted_executed": sum(int(item.get("executed") or 0) for item in assisted_summaries),
            "assisted_ok_targets": len(assisted_ok_targets),
            "assisted_duplicate_targets": duplicate_targets,
            "assisted_expected_static_targets": expected_static_targets,
            "dynamic_edges": next(
                (int(item.get("dynamic_edges") or 0) for item in assisted_summaries if item.get("dynamic_edges") is not None),
                None,
            ),
        },
        "failures": {
            "counts": _verdict_counts(failures),
            "unattributed_hard_failures": [
                {
                    "evidence_track": item.get("evidence_track"),
                    "step": item.get("step"),
                    "detail": item.get("detail"),
                    "semantic_id": (item.get("action") or {}).get("semantic_id")
                    if isinstance(item.get("action"), Mapping)
                    else None,
                }
                for item in unattributed
            ],
        },
        "android": {
            "present": bool(android),
            "verdict": android.get("verdict"),
            "totals": android.get("totals") or {},
            "cdp_connected": android.get("cdp_connected"),
        },
        "gate": {
            "conditions": conditions,
            "blocking": blocking,
            "diagnostics": identity_diagnostics,
        },
        "completion_claim": "release_gate_ready" if release and not blocking else "none",
        "limitations": limitations,
    }


def load_reports(paths: Iterable[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        reports.append(value if isinstance(value, dict) else {"_invalid": value})
    return reports


def write_gate(payload: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "exploration-gate.json"
    md_path = out_dir / "exploration-gate.md"
    atomic_write_json(json_path, payload)
    lines = [
        "# DOL-X exploration gate",
        "",
        f"- mode: **{payload['mode']}**",
        f"- completion claim: **{payload['completion_claim']}**",
        f"- target: {payload['target_identity'].get('game_version')} / {payload['target_identity'].get('target_tag')}",
        "",
        "## gate conditions",
        "",
    ]
    for key, value in payload["gate"]["conditions"].items():
        lines.append(f"- {key}: {value}")
    if payload["gate"]["blocking"]:
        lines += ["", "## blocking", ""]
        lines.extend(f"- {item}" for item in payload["gate"]["blocking"])
    if payload["gate"]["diagnostics"]:
        lines += ["", "## diagnostics", ""]
        lines.extend(f"- {item}" for item in payload["gate"]["diagnostics"])
    if payload["limitations"]:
        lines += ["", "## limitations", ""]
        lines.extend(f"- {item}" for item in payload["limitations"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--android-summary", type=Path)
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--mod-inventory", type=Path)
    parser.add_argument("--mod-passage-sweep", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--mods-lock", type=Path)
    parser.add_argument("--release", action="store_true")
    parser.add_argument(
        "--symbolic-reachability",
        type=Path,
        help="static_reachability_solver.py report (release condition)",
    )
    parser.add_argument(
        "--story-graph-audit",
        type=Path,
        help="story_graph_audit.py report (release condition)",
    )
    parser.add_argument(
        "--traversal-stats",
        type=Path,
        help="traversal_statistics.py report (release condition)",
    )
    parser.add_argument(
        "--query-regression",
        type=Path,
        help="query_regression.py report (release condition)",
    )
    parser.add_argument(
        "--au-contract",
        type=Path,
        help="au_artifact_check.py --output report (release condition)",
    )
    parser.add_argument(
        "--framework-contract",
        type=Path,
        help="framework_contract_check.py report (release condition)",
    )
    parser.add_argument(
        "--assisted-full-coverage",
        action="store_true",
        help="require unique assisted targets to cover every static source target",
    )
    parser.add_argument("--out", type=Path, default=Path(".local/exploration-gate"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    def _load(path: Path | None) -> Any:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None

    android_summary = (
        json.loads(Path(args.android_summary).read_text(encoding="utf-8"))
        if args.android_summary
        else None
    )
    mod_inventory = (
        json.loads(Path(args.mod_inventory).read_text(encoding="utf-8"))
        if args.mod_inventory
        else None
    )
    payload = build_gate(
        load_reports(args.reports),
        android_summary=android_summary,
        source_index=args.source_index,
        mod_inventory=mod_inventory,
        release=args.release,
        mod_passage_sweep=(
            json.loads(Path(args.mod_passage_sweep).read_text(encoding="utf-8"))
            if args.mod_passage_sweep
            else None
        ),
        assisted_full_coverage=args.assisted_full_coverage,
        target=args.target,
        mods_lock=args.mods_lock,
        symbolic_reachability=_load(args.symbolic_reachability),
        story_graph_audit=_load(args.story_graph_audit),
        traversal_stats=_load(args.traversal_stats),
        query_regression=_load(args.query_regression),
        au_contract=_load(args.au_contract),
        framework_contract=_load(args.framework_contract),
    )
    write_gate(payload, args.out)
    blocking = payload["gate"]["blocking"]
    print(f"[exploration-gate] claim={payload['completion_claim']} blocking={blocking}")
    return 0 if not blocking else 2


if __name__ == "__main__":
    raise SystemExit(main())
