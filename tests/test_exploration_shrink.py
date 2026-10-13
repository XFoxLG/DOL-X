"""Failure shrink tests over pure semantic traces."""

from __future__ import annotations

from tools.exploration_shrink import shrink_trace
from tools.exploration_trace import SemanticTrace


def test_shrink_removes_irrelevant_prefix() -> None:
    trace = SemanticTrace.from_actions(
        [
            {"step": 1, "kind": "click", "semantic_id": "before"},
            {"step": 2, "kind": "click", "semantic_id": "before2"},
            {"step": 3, "kind": "click", "semantic_id": "bug"},
            {"step": 4, "kind": "click", "semantic_id": "after"},
        ]
    ).to_json()

    def reproduces(candidate) -> bool:
        return any(action.get("semantic_id") == "bug" for action in candidate.get("actions") or [])

    minimized, attempts = shrink_trace(trace, reproduces)
    assert [action["semantic_id"] for action in minimized["actions"]] == ["bug"]
    assert minimized["trace_digest"] != trace["trace_digest"]
    assert attempts
