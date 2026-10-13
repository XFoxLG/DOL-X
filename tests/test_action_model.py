"""Action discovery and deterministic scoring tests."""

from __future__ import annotations

from tools.action_model import DiscoveredAction, choose_actions, score_action


def test_disabled_actions_never_win() -> None:
    assert score_action({"disabled": True, "semantic_id": "new-edge"}) < 0


def test_uncovered_semantic_edges_are_prioritized() -> None:
    actions = [
        {"semantic_id": "edge:a", "text": "A"},
        {"semantic_id": "edge:b", "text": "B"},
    ]
    selected = choose_actions(actions, seed=7, uncovered_edges=["edge:b"])
    assert selected[0]["semantic_id"] == "edge:b"


def test_overlay_controls_rank_above_passage_controls() -> None:
    actions = [
        {"semantic_id": "passage:link", "scope": "passage", "text": "New dialogue"},
        {"semantic_id": "overlay:button", "scope": "body", "overlay": True, "text": "Close"},
    ]
    selected = choose_actions(actions, seed=11)
    assert selected[0]["semantic_id"] == "overlay:button"


def test_pointer_blocked_actions_are_ignored() -> None:
    actions = [
        {"semantic_id": "underlying:link", "scope": "passage", "pointer_blocked": True},
        {"semantic_id": "overlay:button", "overlay": True, "text": "Close"},
    ]
    selected = choose_actions(actions, seed=13)
    assert [action["semantic_id"] for action in selected] == ["overlay:button"]
    assert score_action({"pointer_blocked": True}) == -1000


def test_discovered_action_hash_is_stable() -> None:
    first = DiscoveredAction("click", "link:a", "Go", "link").to_json()
    second = DiscoveredAction("click", "link:a", "Go", "link").to_json()
    assert first == second
    assert first["text_hash"] == second["text_hash"]
