"""Pure tests for source-edge assisted exploration planning."""

from __future__ import annotations

import pytest

from tools.assisted_explorer import plan_source_edges, summarize_results


def _source_index() -> dict:
    return {
        "passages": [{"name": "Bedroom"}, {"name": "Combat"}],
        "edges": [
            {
                "target": "Bedroom",
                "target_kind": "static",
                "path": "game/start.twee",
                "line": 10,
                "kind": "wiki_link",
                "owner": None,
            },
            {
                "target": "Bedroom",
                "target_kind": "static",
                "path": "game/start.twee",
                "line": 20,
                "kind": "wiki_link",
            },
            {
                "target": None,
                "target_kind": "dynamic",
                "path": "game/combat.twee",
                "line": 30,
            },
            {"target": "Bad", "target_kind": "unknown", "path": "x", "line": 1},
        ]
    }


def test_plan_collapses_duplicate_targets_and_keeps_dynamic_count() -> None:
    plan, stats = plan_source_edges(_source_index())
    assert stats == {
        "source_edges": 4,
        "static_targets": 1,
        "planned": 1,
        "dynamic_edges": 2,
        "invalid_edges": 0,
        "unresolved_static_targets": 0,
    }
    assert plan[0]["target"] == "Bedroom"
    assert [item["line"] for item in plan[0]["source_refs"]] == [10, 20]
    assert plan[0]["assistance"] == ["source_edge"]


def test_plan_limit_is_deterministic() -> None:
    plan, stats = plan_source_edges(_source_index(), limit=0)
    assert plan == []
    assert stats["planned"] == 0


def test_plan_shards_are_deterministic_and_reassemble() -> None:
    index = _source_index()
    index["passages"] = [{"name": name} for name in ("A", "B", "C", "D", "E")]
    index["edges"] = [
        {"target": name, "target_kind": "static", "path": "game.twee", "line": number}
        for number, name in enumerate(("A", "B", "C", "D", "E"), 1)
    ]
    first, first_stats = plan_source_edges(index, shard_index=0, shard_count=2)
    second, second_stats = plan_source_edges(index, shard_index=1, shard_count=2)
    combined = [item["target"] for item in first] + [item["target"] for item in second]
    assert combined == ["A", "C", "E", "B", "D"]
    assert first_stats["planned"] == 3
    assert second_stats["planned"] == 2
    assert first_stats["static_targets"] == 5
    assert second_stats["static_targets"] == 5

    with pytest.raises(ValueError, match="shard index"):
        plan_source_edges(index, shard_index=2, shard_count=2)


def test_summary_is_assisted_only_and_never_natural() -> None:
    results = [
        {"target": "Bedroom", "verdict": "ok", "evidence_track": "assisted"},
        {"target": "Combat", "verdict": "hard_fail", "evidence_track": "assisted"},
    ]
    summary = summarize_results(results, {"planned": 2, "dynamic_edges": 7})
    assert summary == {
        "planned": 2,
        "executed": 2,
        "verdicts": {"hard_fail": 1, "ok": 1},
        "assisted_target_coverage": 1,
        "dynamic_edges": 7,
        "shard": {"index": None, "count": None},
        "completion_claim": "assisted_only",
    }
