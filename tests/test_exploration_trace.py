"""Semantic trace normalization tests."""

from __future__ import annotations

from tools.exploration_trace import SemanticTrace, traces_match


def test_trace_drops_locators_and_is_deterministic() -> None:
    action = {
        "step": 1,
        "kind": "click",
        "semantic_id": "link:Go",
        "role": "link",
        "text": "Go",
        "locator": {"css": "#volatile"},
        "passage_before": "Start",
        "passage_after": "Bedroom",
    }
    first = SemanticTrace.from_actions([action]).to_json()
    second = SemanticTrace.from_actions([action]).to_json()
    assert first["trace_digest"] == second["trace_digest"]
    assert first["actions"][0]["semantic_id"] == "link:Go"
    assert "locator" not in first["actions"][0]


def test_subsequence_preserves_semantics() -> None:
    trace = SemanticTrace.from_actions(
        [
            {"step": 1, "kind": "click", "semantic_id": "a"},
            {"step": 2, "kind": "click", "semantic_id": "b"},
        ]
    )
    shrunk = trace.subsequence([1]).to_json()
    assert shrunk["actions"][0]["semantic_id"] == "b"
    assert traces_match(shrunk, shrunk)
