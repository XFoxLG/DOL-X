"""Pure tests for traversal statistics over exploration reports."""

from __future__ import annotations

import json
from pathlib import Path

from tools.traversal_statistics import main


def _natural(actions: list[dict], failures: list | None = None) -> dict:
    return {
        "schema": "dolx.exploration.v1",
        "status": "complete",
        "evidence_track": "natural",
        "actions": actions,
        "failures": failures or [],
        "unique_coarse_states": 3,
    }


def _action(before: str, after: str, verdict: str = "ok") -> dict:
    return {
        "step": 1,
        "kind": "link",
        "passage_before": before,
        "passage_after": after,
        "fingerprint_after": f"fp-{after}",
        "verdict": verdict,
    }


def _assisted(results: list[dict]) -> dict:
    return {
        "schema": "dolx.assisted-exploration.v1",
        "status": "complete",
        "evidence_track": "assisted",
        "results": results,
        "summary": {"planned": len(results), "executed": len(results)},
    }


def _index() -> dict:
    return {
        "schema": "dolx.source-index.v1",
        "passages": [{"name": name} for name in ("A", "B", "C", "D")],
        "edges": [
            {"source": "A", "target": "B", "target_kind": "static"},
            {"source": "B", "target": "C", "target_kind": "static"},
            {"source": "A", "target": "B", "target_kind": "static"},
            {"source": "A", "target": None, "target_kind": "dynamic"},
        ],
    }


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_natural_track_coverage(tmp_path: Path) -> None:
    index_path = _write(tmp_path, "index.json", _index())
    report_path = _write(
        tmp_path,
        "natural.json",
        _natural([_action("A", "B"), _action("B", "D"), _action("A", "A")]),
    )
    out = tmp_path / "out"
    assert (
        main(
            [
                str(report_path),
                "--source-index",
                str(index_path),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    report = json.loads((out / "traversal-stats.json").read_text(encoding="utf-8"))
    track = report["tracks"]["natural"]
    assert track["passages_visited"] == 3  # A, B, D
    assert track["transitions_observed"] == 2  # A->B, B->D (A->A dropped)
    assert track["static_transitions_observed"] == 1
    assert track["dynamic_observed"] == 1
    assert report["denominators"] == {"passages": 4, "static_edges": 2}
    assert track["edge_coverage"] == 0.5


def test_assisted_results_only_basis(tmp_path: Path) -> None:
    report_path = _write(
        tmp_path,
        "assisted.json",
        _assisted(
            [
                {"target": "X", "verdict": "ok", "fingerprint": "f1"},
                {"target": "Y", "verdict": "hard_fail", "fingerprint": "f2"},
            ]
        ),
    )
    out = tmp_path / "out"
    assert main([str(report_path), "--out", str(out)]) == 0
    report = json.loads((out / "traversal-stats.json").read_text(encoding="utf-8"))
    track = report["tracks"]["assisted"]
    assert track["coverage_basis"] == "results_only"
    assert track["results_by_verdict"]["ok"] == 1
    assert track["results_by_verdict"]["hard_fail"] == 1
    assert track["passage_coverage"] is None
    assert track["edge_coverage"] is None


def test_directory_scan_skips_non_reports(tmp_path: Path) -> None:
    _write(tmp_path, "target-manifest.json", {"schema": "dolx.target.v1"})
    _write(tmp_path, "natural.json", _natural([_action("A", "B")]))
    out = tmp_path / "out"
    assert main([str(tmp_path), "--out", str(out)]) == 0
    report = json.loads((out / "traversal-stats.json").read_text(encoding="utf-8"))
    assert report["totals"]["runs"] == 1


def test_empty_input_is_invalid(tmp_path: Path) -> None:
    _write(tmp_path, "target-manifest.json", {"schema": "dolx.target.v1"})
    assert main([str(tmp_path), "--out", str(tmp_path / "out")]) == 2
