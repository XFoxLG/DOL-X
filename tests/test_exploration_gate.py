"""Fail-closed gate tests over exploration evidence."""

from __future__ import annotations

import hashlib
import json

from tools.exploration_gate import build_gate, main


def _manifest(package: str = "a" * 64) -> dict:
    return {
        "schema": "dolx.target.v1",
        "identity_ok": True,
        "target": {
            "game_version": "0.5.11.9",
            "target_tag": "v0.5.11.9-1.0.0a-0915",
            "package_sha256": package,
            "html_member": "Degrees of Lewdity.html",
            "package_type": "derived",
            "source_commit": "c" * 64,
        },
        "embedded_payloads": [{"name": "Mod"}],
        "embedded_mod_count": 1,
        "mods_lock_sha256": "d" * 64,
        "source_index_sha256": "e" * 64,
    }


def _identity_files(tmp_path, manifest: dict | None = None):
    manifest = manifest or _manifest()
    target = tmp_path / "target.zip"
    mods_lock = tmp_path / "mods.lock.json"
    target.write_bytes(b"package")
    mods_lock.write_text("{}", encoding="utf-8")
    manifest["target"]["package_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest["mods_lock_sha256"] = hashlib.sha256(mods_lock.read_bytes()).hexdigest()
    return manifest, target, mods_lock


def _natural(manifest: dict | None = None) -> dict:
    return {
        "schema": "dolx.exploration.v1",
        "status": "complete",
        "evidence_track": "natural",
        "target_manifest": manifest or _manifest(),
        "actions": [{"verdict": "ok", "kind": "click", "evidence_track": "natural"}],
        "failures": [],
        "unique_coarse_states": 3,
    }


def _assisted(manifest: dict | None = None) -> dict:
    return {
        "schema": "dolx.assisted-exploration.v1",
        "status": "complete",
        "evidence_track": "assisted",
        "target_manifest": manifest or _manifest(),
        "results": [
            {"target": f"Target-{index}", "verdict": "ok"} for index in range(5)
        ],
        "summary": {
            "planned": 5,
            "executed": 5,
            "verdicts": {"ok": 5},
            "assisted_target_coverage": 5,
            "dynamic_edges": 7,
        },
        "failures": [],
    }


def _assisted_with_targets(targets: list[dict], manifest: dict | None = None) -> dict:
    report = _assisted(manifest)
    report["results"] = [
        {"target": row["target"], "verdict": row["verdict"]} for row in targets
    ]
    report["summary"] = {
        **report["summary"],
        "planned": len(targets),
        "executed": len(targets),
        "assisted_target_coverage": len(
            {row["target"] for row in targets if row["verdict"] == "ok"}
        ),
    }
    return report


def _source_index_file(tmp_path, targets: list[str]):
    path = tmp_path / "source-index.json"
    path.write_text(
        json.dumps(
            {
                "stats": {"passages": len(targets), "edges": len(targets)},
                "source_commit": "c" * 64,
                "passages": [{"name": name} for name in targets],
                "edges": [
                    {
                        "target": name,
                        "target_kind": "static",
                        "path": "game.twee",
                        "line": number,
                    }
                    for number, name in enumerate(targets, 1)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _manifest_for_source_index(source_index) -> dict:
    manifest = _manifest()
    manifest["source_index_sha256"] = hashlib.sha256(
        source_index.read_bytes()
    ).hexdigest()
    return manifest


def _inventory(mods: int = 1) -> dict:
    return {
        "html_sha256": "f" * 64,
        "counts": {"static": 2, "runtime_dom": 4, "runtime_only": 2},
        "mods": [{"name": f"mod-{i}"} for i in range(mods)],
        "errors": [],
        "static_missing_from_runtime": [],
        "unregistered_names": [],
        "playable_names": ["Food Preference"],
        "widget_names": ["CE_Wardrobe"],
        "opaque_mods": [],
        "mod_buttons": {"summary": {"candidates": 2, "thrown": 0}},
    }


def _mod_passage_sweep(names: list[tuple[str, str]], *, complete: bool = True) -> dict:
    return {
        "status": "complete" if complete else "failed",
        "results": [{"name": name, "verdict": verdict} for name, verdict in names],
        "completeness": {"ok": complete},
    }


def _symbolic_reachability(verdict: str = "reachable") -> dict:
    return {
        "schema": "dolx.symbolic_reachability.v1",
        "verdict": verdict,
        "start": "Start",
        "targets": ["Start2"],
    }


def _story_graph_audit(
    *,
    dead_ends: list[str] | None = None,
    undefined: list[str] | None = None,
    html_provided: bool = True,
    mode: str = "full",
) -> dict:
    return {
        "schema": "dolx.story-graph-audit.v1",
        "mode": mode,
        "blocking": {
            "html_provided": html_provided,
            "unclassified_dead_ends": list(dead_ends or []),
            "unclassified_undefined_targets": list(undefined or []),
        },
    }


def _traversal_stats(
    *,
    basis: str = "actions",
    passages: int = 10,
    coverage: float | None = 0.5,
) -> dict:
    return {
        "schema": "dolx.traversal-stats.v1",
        "tracks": {
            "natural": {"coverage_basis": basis, "passage_coverage": coverage},
        },
        "denominators": {"passages": passages, "static_edges": 4},
    }


def _query_regression(release_blocking: list[str] | None = None) -> dict:
    return {
        "schema": "dolx.query-regression.v1",
        "release_blocking": list(release_blocking or []),
    }


def _au_contract(
    *,
    export_count: int = 1,
    shim_count: int = 1,
    errors: list[str] | None = None,
    is_au: bool = True,
) -> list[dict]:
    return [
        {
            "is_au": is_au,
            "au_contract": {
                "schema": "dolx.au_contract.v1",
                "errors": list(errors or []),
                "framework_face_style_src_fn_export_count": export_count,
                "framework_variant_dir_shim_marker_count": shim_count,
            },
        }
    ]


def _framework_contract(verdict: str = "consistent") -> dict:
    return {"schema": "dolx.framework-contract.v1", "verdict": verdict}


def _extended_evidence(**overrides) -> dict:
    """Release evidence added by the external-benchmark fusion plan."""
    evidence = {
        "symbolic_reachability": _symbolic_reachability(),
        "story_graph_audit": _story_graph_audit(),
        "traversal_stats": _traversal_stats(),
        "query_regression": _query_regression(),
        "au_contract": _au_contract(),
        "framework_contract": _framework_contract(),
    }
    evidence.update(overrides)
    return evidence


def test_evidence_gate_blocks_unattributed_hard_fail() -> None:
    report = _natural()
    report["failures"] = [
        {
            "verdict": "hard_fail",
            "step": 2,
            "detail": "boom",
            "action": {"semantic_id": "bug"},
        }
    ]
    gate = build_gate([report, _assisted()], source_index=None)

    assert gate["mode"] == "evidence_only"
    assert gate["completion_claim"] == "none"
    assert gate["gate"]["blocking"] == ["no_unattributed_hard_fail"]
    assert gate["failures"]["counts"]["hard_fail"] == 1
    assert gate["failures"]["unattributed_hard_failures"][0]["semantic_id"] == "bug"
    assert gate["coverage"]["assisted_ok_targets"] == 5


def test_release_gate_requires_complete_android_semantics(tmp_path) -> None:
    android = {
        "verdict": "ok",
        "cdp_connected": True,
        "totals": {"planned": 2, "matched": 2, "ambiguous": 0, "unmapped": 0},
        "apk_sha256": "9" * 64,
    }
    tmp_source = _source_index_file(tmp_path, ["A"])
    manifest = _manifest_for_source_index(tmp_source)
    manifest, target, mods_lock = _identity_files(tmp_path, manifest)
    manifest["target"]["apk_sha256"] = "9" * 64
    gate = build_gate(
        [_natural(manifest), _assisted(manifest)],
        source_index=tmp_source,
        android_summary=android,
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        release=True,
        target=target,
        mods_lock=mods_lock,
        **_extended_evidence(),
    )

    assert gate["mode"] == "release"
    assert gate["gate"]["blocking"] == []
    assert gate["completion_claim"] == "release_gate_ready"
    assert gate["android"]["present"] is True


def _android_summary_with_apk(apk_sha256: str | None) -> dict:
    summary = {
        "verdict": "ok",
        "cdp_connected": True,
        "totals": {"planned": 2, "matched": 2, "ambiguous": 0, "unmapped": 0},
    }
    if apk_sha256 is not None:
        summary["apk_sha256"] = apk_sha256
    return summary


def _release_gate_with_android_apk(
    tmp_path,
    *,
    manifest_apk_sha256: str | None,
    summary_apk_sha256: str | None,
    release: bool = True,
) -> dict:
    source_index = _source_index_file(tmp_path, ["A"])
    manifest = _manifest_for_source_index(source_index)
    manifest, target, mods_lock = _identity_files(tmp_path, manifest)
    if manifest_apk_sha256 is not None:
        manifest["target"]["apk_sha256"] = manifest_apk_sha256
    return build_gate(
        [_natural(manifest), _assisted(manifest)],
        android_summary=_android_summary_with_apk(summary_apk_sha256),
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        source_index=source_index,
        release=release,
        target=target,
        mods_lock=mods_lock,
        **_extended_evidence(),
    )


def test_release_gate_android_apk_sha256_match_unblocks(tmp_path) -> None:
    gate = _release_gate_with_android_apk(
        tmp_path,
        manifest_apk_sha256="a" * 64,
        summary_apk_sha256="a" * 64,
    )

    assert gate["gate"]["conditions"]["android_apk_sha256_matches"] is True
    assert gate["gate"]["conditions"]["android_gate_ready"] is True
    assert gate["gate"]["blocking"] == []
    assert gate["completion_claim"] == "release_gate_ready"


def test_release_gate_android_apk_sha256_missing_on_either_side_blocks(tmp_path) -> None:
    for manifest_sha, summary_sha in ((None, "a" * 64), ("a" * 64, None), (None, None)):
        gate = _release_gate_with_android_apk(
            tmp_path,
            manifest_apk_sha256=manifest_sha,
            summary_apk_sha256=summary_sha,
        )

        assert gate["gate"]["conditions"]["android_apk_sha256_matches"] is False
        assert gate["gate"]["conditions"]["android_gate_ready"] is False
        assert {
            "android_apk_sha256_matches",
            "android_gate_ready",
        } <= set(gate["gate"]["blocking"])
        assert gate["completion_claim"] == "none"


def test_release_gate_android_apk_sha256_mismatch_blocks(tmp_path) -> None:
    gate = _release_gate_with_android_apk(
        tmp_path,
        manifest_apk_sha256="a" * 64,
        summary_apk_sha256="b" * 64,
    )

    assert gate["gate"]["conditions"]["android_apk_sha256_matches"] is False
    assert gate["gate"]["conditions"]["android_gate_ready"] is False
    assert {
        "android_apk_sha256_matches",
        "android_gate_ready",
    } <= set(gate["gate"]["blocking"])


def test_non_release_gate_ignores_apk_sha256_pairing(tmp_path) -> None:
    gate = _release_gate_with_android_apk(
        tmp_path,
        manifest_apk_sha256="a" * 64,
        summary_apk_sha256="b" * 64,
        release=False,
    )

    assert gate["gate"]["conditions"]["android_apk_sha256_matches"] is None
    assert gate["gate"]["conditions"]["android_gate_ready"] is None
    assert "android_apk_sha256_matches" not in gate["gate"]["blocking"]
    assert "android_gate_ready" not in gate["gate"]["blocking"]


def test_release_gate_requires_actual_target_and_mods_lock(tmp_path) -> None:
    android = {
        "verdict": "ok",
        "cdp_connected": True,
        "totals": {"planned": 1, "matched": 1},
    }
    gate = build_gate(
        [_natural(), _assisted()],
        android_summary=android,
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        release=True,
    )

    assert gate["surface"]["target_package"]["present"] is False
    assert gate["surface"]["mods_lock"]["present"] is False
    assert {"target_sha256_matches", "mods_lock_sha256_matches"} <= set(
        gate["gate"]["blocking"]
    )
    assert "release target package was not supplied" in gate["limitations"]
    assert "release mods lock file was not supplied" in gate["limitations"]


def test_release_gate_blocks_actual_target_and_mods_lock_drift(tmp_path) -> None:
    android = {
        "verdict": "ok",
        "cdp_connected": True,
        "totals": {"planned": 1, "matched": 1},
    }
    target = tmp_path / "target.zip"
    mods_lock = tmp_path / "mods.lock.json"
    target.write_bytes(b"wrong-package")
    mods_lock.write_text("{}", encoding="utf-8")
    gate = build_gate(
        [_natural(), _assisted()],
        android_summary=android,
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        release=True,
        target=target,
        mods_lock=mods_lock,
    )

    assert gate["surface"]["target_package"]["matches"] is False
    assert gate["surface"]["mods_lock"]["matches"] is False
    assert {"target_sha256_matches", "mods_lock_sha256_matches"} <= set(
        gate["gate"]["blocking"]
    )


def test_release_gate_blocks_identity_drift_and_incomplete_android(tmp_path) -> None:
    android = {
        "verdict": "partial",
        "cdp_connected": True,
        "totals": {"planned": 2, "matched": 1, "ambiguous": 0, "unmapped": 1},
    }
    manifest, target, mods_lock = _identity_files(tmp_path)
    drifted_manifest = _manifest("b" * 64)
    gate = build_gate(
        [_natural(manifest), _assisted(drifted_manifest)],
        android_summary=android,
        release=True,
        target=target,
        mods_lock=mods_lock,
    )

    assert set(gate["gate"]["blocking"]) >= {
        "identity_consistent",
        "android_gate_ready",
    }
    assert gate["completion_claim"] == "none"


def test_release_gate_requires_source_and_source_index_identity(tmp_path) -> None:
    manifest = _manifest()
    manifest["target"]["source_commit"] = None
    manifest["mods_lock_sha256"] = None
    manifest["source_index_sha256"] = None
    manifest, target, mods_lock = _identity_files(tmp_path, manifest)
    manifest["target"]["apk_sha256"] = "5" * 64
    gate = build_gate(
        [_natural(manifest), _assisted(manifest)],
        android_summary={
            "verdict": "ok",
            "cdp_connected": True,
            "totals": {"planned": 1, "matched": 1},
            "apk_sha256": "5" * 64,
        },
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        release=True,
        target=target,
        mods_lock=mods_lock,
        **_extended_evidence(),
    )

    assert set(gate["gate"]["blocking"]) == {
        "source_commit_present",
        "source_index_digest_present",
        "source_index_digest_matches",
        "source_commit_matches_index",
    }
    assert gate["completion_claim"] == "none"


def test_release_gate_requires_clean_mod_inventory_surface(tmp_path) -> None:
    inventory = _inventory()
    inventory["mods"] = [{"name": "one"}, {"name": "two"}]
    inventory["errors"] = ["payload scan failed"]
    inventory["static_missing_from_runtime"] = ["Missing"]
    inventory["unregistered_names"] = ["Lazy"]
    inventory["mod_buttons"]["summary"]["thrown"] = 1
    manifest, target, mods_lock = _identity_files(tmp_path)
    gate = build_gate(
        [_natural(manifest), _assisted(manifest)],
        mod_inventory=inventory,
        release=True,
        target=target,
        mods_lock=mods_lock,
    )

    assert set(gate["gate"]["blocking"]) >= {
        "mod_payload_count_matches",
        "mod_inventory_no_errors",
        "mod_buttons_no_throws",
        "static_surface_complete",
        "mod_passages_classified",
    }
    assert gate["surface"]["mod_inventory"]["opaque_mods"] == []


def test_release_gate_requires_full_unique_static_assisted_coverage(
    tmp_path,
) -> None:
    android = {
        "verdict": "ok",
        "cdp_connected": True,
        "totals": {"planned": 2, "matched": 2},
    }
    source_index = _source_index_file(tmp_path, ["A", "B"])
    manifest = _manifest_for_source_index(source_index)
    manifest, target, mods_lock = _identity_files(tmp_path)
    complete = build_gate(
        [
            _natural(manifest),
            _assisted_with_targets(
                [{"target": "A", "verdict": "ok"}, {"target": "B", "verdict": "ok"}]
                , manifest
            ),
        ],
        android_summary=android,
        mod_inventory=_inventory(),
        source_index=source_index,
        release=True,
        target=target,
        mods_lock=mods_lock,
    )
    assert complete["coverage"]["assisted_ok_targets"] == 2
    assert complete["coverage"]["assisted_expected_static_targets"] == 2
    assert "assisted_static_targets_covered" not in complete["gate"]["blocking"]

    partial = build_gate(
        [
            _natural(manifest),
            _assisted_with_targets([{"target": "A", "verdict": "ok"}], manifest),
        ],
        android_summary=android,
        mod_inventory=_inventory(),
        source_index=source_index,
        release=True,
        target=target,
        mods_lock=mods_lock,
    )
    assert "assisted_static_targets_covered" in partial["gate"]["blocking"]
    assert partial["completion_claim"] == "none"


def test_release_gate_blocks_duplicate_assisted_targets(tmp_path) -> None:
    android = {
        "verdict": "ok",
        "cdp_connected": True,
        "totals": {"planned": 2, "matched": 2},
    }
    source_index = _source_index_file(tmp_path, ["A"])
    manifest = _manifest_for_source_index(source_index)
    manifest, target, mods_lock = _identity_files(tmp_path, manifest)
    gate = build_gate(
        [
            _natural(manifest),
            _assisted_with_targets(
                [{"target": "A", "verdict": "ok"}, {"target": "A", "verdict": "ok"}],
                manifest,
            ),
        ],
        android_summary=android,
        mod_inventory=_inventory(),
        source_index=source_index,
        release=True,
        target=target,
        mods_lock=mods_lock,
    )

    assert set(gate["gate"]["blocking"]) >= {
        "assisted_targets_unique",
        "assisted_static_targets_covered",
    }
    assert gate["coverage"]["assisted_duplicate_targets"] == ["A"]


def test_assisted_full_coverage_gate_does_not_require_release_or_android(
    tmp_path,
) -> None:
    source_index = _source_index_file(tmp_path, ["A"])
    gate = build_gate(
        [_natural(), _assisted_with_targets([{"target": "A", "verdict": "ok"}])],
        mod_inventory=_inventory(),
        source_index=source_index,
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        assisted_full_coverage=True,
    )

    assert gate["mode"] == "assisted_full_coverage"
    assert gate["gate"]["blocking"] == []
    assert gate["gate"]["conditions"]["assisted_static_targets_covered"] is True
    assert gate["gate"]["conditions"]["android_gate_ready"] is None


def test_release_gate_requires_playable_mod_passage_sweep(tmp_path) -> None:
    manifest, target, mods_lock = _identity_files(tmp_path)
    complete = build_gate(
        [_natural(manifest), _assisted(manifest)],
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        release=True,
        target=target,
        mods_lock=mods_lock,
    )
    assert complete["gate"]["conditions"]["mod_playable_passages_covered"] is True
    assert "mod_playable_passages_covered" not in complete["gate"]["blocking"]

    missing = build_gate(
        [_natural(manifest), _assisted(manifest)],
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([]),
        release=True,
        target=target,
        mods_lock=mods_lock,
    )
    assert missing["surface"]["mod_passage_sweep"]["missing"] == ["Food Preference"]
    assert "mod_passage_sweep_present" in missing["gate"]["blocking"]
    assert "mod_playable_passages_covered" in missing["gate"]["blocking"]

    broken = build_gate(
        [_natural(manifest), _assisted(manifest)],
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "hard_fail")]),
        release=True,
        target=target,
        mods_lock=mods_lock,
    )
    assert "mod_passage_sweep_no_errors" in broken["gate"]["blocking"]
    assert "mod_playable_passages_covered" in broken["gate"]["blocking"]


def _release_build(tmp_path, **evidence):
    manifest, target, mods_lock = _identity_files(tmp_path)
    return build_gate(
        [_natural(manifest), _assisted(manifest)],
        mod_inventory=_inventory(),
        mod_passage_sweep=_mod_passage_sweep([("Food Preference", "ok")]),
        release=True,
        target=target,
        mods_lock=mods_lock,
        **_extended_evidence(**evidence),
    )


def test_release_gate_requires_extended_reports(tmp_path) -> None:
    """Every new release condition fails closed when its report is absent."""
    gate = _release_build(tmp_path, **{key: None for key in _extended_evidence()})

    assert {
        "story_graph_dead_ends_classified",
        "query_regression_passed",
        "traversal_report_complete",
        "symbolic_reachability_available",
        "au_contract_passed",
        "framework_contract_consistent",
    } <= set(gate["gate"]["blocking"])
    for limitation in (
        "release symbolic reachability report was not supplied",
        "release story graph audit was not supplied",
        "release traversal statistics were not supplied",
        "release query regression report was not supplied",
        "release AU contract report was not supplied",
        "release framework contract check was not supplied",
    ):
        assert limitation in gate["limitations"]


def test_release_gate_story_graph_and_symbolic_conditions(tmp_path) -> None:
    clean = _release_build(tmp_path)
    assert "story_graph_dead_ends_classified" not in clean["gate"]["blocking"]
    assert "symbolic_reachability_available" not in clean["gate"]["blocking"]

    dirty = _release_build(
        tmp_path,
        story_graph_audit=_story_graph_audit(
            dead_ends=["Balloon Stand"],
            undefined=["Maze Final"],
        ),
        symbolic_reachability=_symbolic_reachability("solver_unavailable"),
    )
    assert {
        "story_graph_dead_ends_classified",
        "symbolic_reachability_available",
    } <= set(dirty["gate"]["blocking"])

    index_only = _release_build(
        tmp_path,
        story_graph_audit=_story_graph_audit(mode="index_only", html_provided=False),
    )
    assert "story_graph_dead_ends_classified" in index_only["gate"]["blocking"]

    bounded = _release_build(
        tmp_path,
        symbolic_reachability=_symbolic_reachability("unreachable_within_bound"),
    )
    assert "symbolic_reachability_available" not in bounded["gate"]["blocking"]


def test_release_gate_traversal_and_query_conditions(tmp_path) -> None:
    clean = _release_build(tmp_path)
    assert "traversal_report_complete" not in clean["gate"]["blocking"]
    assert "query_regression_passed" not in clean["gate"]["blocking"]

    results_only = _release_build(
        tmp_path,
        traversal_stats=_traversal_stats(basis="results_only"),
    )
    assert "traversal_report_complete" in results_only["gate"]["blocking"]

    no_denominator = _release_build(
        tmp_path,
        traversal_stats=_traversal_stats(passages=0, coverage=None),
    )
    assert "traversal_report_complete" in no_denominator["gate"]["blocking"]

    failing_query = _release_build(
        tmp_path,
        query_regression=_query_regression(["story-graph-no-unclassified-dead-ends"]),
    )
    assert "query_regression_passed" in failing_query["gate"]["blocking"]


def test_release_gate_au_and_framework_contract_conditions(tmp_path) -> None:
    clean = _release_build(tmp_path)
    assert "au_contract_passed" not in clean["gate"]["blocking"]
    assert "framework_contract_consistent" not in clean["gate"]["blocking"]

    missing_export = _release_build(tmp_path, au_contract=_au_contract(export_count=0))
    assert "au_contract_passed" in missing_export["gate"]["blocking"]

    missing_shim = _release_build(tmp_path, au_contract=_au_contract(shim_count=0))
    assert "au_contract_passed" in missing_shim["gate"]["blocking"]

    errors = _release_build(
        tmp_path,
        au_contract=_au_contract(errors=["framework face style export is missing"]),
    )
    assert "au_contract_passed" in errors["gate"]["blocking"]

    non_au = _release_build(tmp_path, au_contract=_au_contract(is_au=False))
    assert "au_contract_passed" in non_au["gate"]["blocking"]

    for verdict in ("content_version_mismatch", "unregistered_version"):
        mismatch = _release_build(
            tmp_path,
            framework_contract=_framework_contract(verdict),
        )
        assert "framework_contract_consistent" in mismatch["gate"]["blocking"]


def test_release_gate_cli_loads_extended_reports(tmp_path) -> None:
    source_index = _source_index_file(tmp_path, ["A"])
    manifest = _manifest_for_source_index(source_index)
    manifest, target, mods_lock = _identity_files(tmp_path, manifest)
    manifest["target"]["apk_sha256"] = "7" * 64

    def _write(name: str, payload) -> str:
        path = tmp_path / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    natural = _write("natural.json", _natural(manifest))
    assisted = _write("assisted.json", _assisted(manifest))
    inventory = _write("inventory.json", _inventory())
    sweep = _write(
        "sweep.json",
        _mod_passage_sweep([("Food Preference", "ok")]),
    )
    android = _write(
        "android.json",
        {
            "verdict": "ok",
            "cdp_connected": True,
            "totals": {"planned": 1, "matched": 1},
            "apk_sha256": "7" * 64,
        },
    )
    evidence = _extended_evidence()
    evidence_paths = {
        name: _write(f"{name}.json", payload) for name, payload in evidence.items()
    }

    out_dir = tmp_path / "gate"
    exit_code = main(
        [
            natural,
            assisted,
            "--source-index",
            str(source_index),
            "--mod-inventory",
            inventory,
            "--mod-passage-sweep",
            sweep,
            "--android-summary",
            android,
            "--target",
            str(target),
            "--mods-lock",
            str(mods_lock),
            "--symbolic-reachability",
            evidence_paths["symbolic_reachability"],
            "--story-graph-audit",
            evidence_paths["story_graph_audit"],
            "--traversal-stats",
            evidence_paths["traversal_stats"],
            "--query-regression",
            evidence_paths["query_regression"],
            "--au-contract",
            evidence_paths["au_contract"],
            "--framework-contract",
            evidence_paths["framework_contract"],
            "--release",
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads(
        (out_dir / "exploration-gate.json").read_text(encoding="utf-8")
    )
    assert payload["mode"] == "release"
    assert payload["completion_claim"] == "release_gate_ready"
    assert payload["gate"]["blocking"] == []
