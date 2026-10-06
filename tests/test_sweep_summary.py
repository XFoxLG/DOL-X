"""Unit tests for shard report aggregation."""

from __future__ import annotations

import json

from tools import sweep_ledger as ledger_mod
from tools import sweep_summary


def _identity(shard_index: int, shard_count: int = 2):
    return ledger_mod.run_identity(
        "combat_sweep",
        html_sha256="a" * 64,
        fixture_digest="b" * 64,
        tool_version="combat-sweep-v2",
        plan_digest=f"plan-{shard_index}",
        strategy={"tier": "initiators", "shard_index": shard_index, "shard_count": shard_count},
    )


def _report(index: int, results: list[dict], *, complete: bool = True):
    return {
        "target": "artifact.html",
        "results": results,
        "completeness": {
            "ok": complete,
            "diagnostics": [] if complete else ["missing results: 1"],
            "summary": {"expected": len(results), "completed": len(results)},
        },
        "ledger": {"identity": _identity(index)},
    }


def test_aggregate_accepts_disjoint_identity_matched_shards() -> None:
    payload = sweep_summary.aggregate_reports(
        [
            _report(0, [{"key": "a", "verdict": "ok"}]),
            _report(1, [{"key": "b", "verdict": "soft_fail"}]),
        ],
        expected_shards=2,
    )
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["results"] == 2
    assert payload["summary"]["verdict_counts"]["ok"] == 1
    assert payload["summary"]["verdict_counts"]["soft_fail"] == 1


def test_aggregate_rejects_incomplete_or_missing_shard() -> None:
    payload = sweep_summary.aggregate_reports(
        [_report(0, [{"key": "a", "verdict": "ok"}], complete=False)],
        expected_shards=2,
    )
    assert payload["summary"]["ok"] is False
    assert any("expected 2 shards" in error for error in payload["summary"]["errors"])
    assert any("incomplete" in error for error in payload["summary"]["errors"])


def test_aggregate_rejects_duplicate_keys_across_shards() -> None:
    payload = sweep_summary.aggregate_reports(
        [
            _report(0, [{"key": "same", "verdict": "ok"}]),
            _report(1, [{"key": "same", "verdict": "hard_fail"}]),
        ]
    )
    assert payload["summary"]["ok"] is False
    assert any("duplicate result key" in error for error in payload["summary"]["errors"])


def test_aggregate_rejects_mixed_target_identity() -> None:
    first = _report(0, [{"key": "a", "verdict": "ok"}])
    second = _report(1, [{"key": "b", "verdict": "ok"}])
    second["ledger"]["identity"]["html_sha256"] = "c" * 64
    payload = sweep_summary.aggregate_reports([first, second])
    assert payload["summary"]["ok"] is False
    assert any("identity mismatch" in error for error in payload["summary"]["errors"])


def test_aggregate_accepts_different_axes_on_same_artifact() -> None:
    first = _report(0, [{"key": "a", "verdict": "ok"}])
    second = _report(1, [{"key": "b", "verdict": "ok"}])
    second["ledger"]["identity"] = ledger_mod.run_identity(
        "env_matrix",
        html_sha256="a" * 64,
        fixture_digest="b" * 64,
        tool_version="env-matrix-v2",
        plan_digest="env-plan",
        strategy={"tier": "full", "shard_index": 1, "shard_count": 8},
    )
    payload = sweep_summary.aggregate_reports([first, second])
    assert payload["summary"]["ok"] is True


def test_write_summary_uses_atomic_json_and_markdown(tmp_path) -> None:
    payload = sweep_summary.aggregate_reports(
        [_report(0, [{"key": "a", "verdict": "hard_fail"}])]
    )
    json_path, md_path = sweep_summary.write_summary(payload, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["summary"]["ok"] is True
    assert "# DOL-X sweep shard summary" in md_path.read_text(encoding="utf-8")
