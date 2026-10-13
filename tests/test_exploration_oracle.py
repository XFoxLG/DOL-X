"""Runtime oracle classification tests."""

from __future__ import annotations

from tools.exploration_oracle import check_state_invariants, classify_node


def test_unhandled_errors_are_hard_failures() -> None:
    verdict, detail, diagnostics = classify_node(
        {"observations": [{"kind": "error", "message": "ReferenceError: bad"}], "finished": True}
    )
    assert verdict == "hard_fail"
    assert "ReferenceError" in detail
    assert diagnostics == []


def test_invalid_core_state_is_hard_fail() -> None:
    verdict, detail, diagnostics = classify_node(
        {
            "finished": True,
            "variables": {"day": "tomorrow", "combat": "maybe"},
        }
    )
    assert verdict == "hard_fail"
    assert diagnostics == ["day is not numeric", "combat is not boolean-like"]


def test_valid_node_is_ok() -> None:
    verdict, detail, diagnostics = classify_node(
        {"finished": True, "variables": {"day": 3, "combat": 0}}
    )
    assert verdict == "ok"
    assert detail == ""
    assert diagnostics == []
