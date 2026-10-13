"""Summary aggregation tests for gameplay exploration."""

from __future__ import annotations

from tools.exploration_summary import summarize_many, summarize_report


def test_summary_separates_evidence_and_failure_kinds() -> None:
    report = {
        "status": "failed",
        "stop_reason": "frontier_exhausted",
        "evidence_track": "natural",
        "unique_coarse_states": 7,
        "target_manifest": {"target": {"game_version": "0.5.11.9"}},
        "actions": [
            {"verdict": "ok", "kind": "click", "evidence_track": "natural", "passage_after": "A"},
            {"verdict": "hard_fail", "kind": "click", "evidence_track": "assisted", "passage_after": "B"},
        ],
        "failures": [{"verdict": "hard_fail"}],
    }
    summary = summarize_report(report)
    assert summary["verdicts"] == {"hard_fail": 1, "ok": 1}
    assert summary["coverage"]["action_tracks"] == {"assisted": 1, "natural": 1}
    assert summary["coverage"]["passage_first_seen"] == {"A": 1, "B": 1}
    assert summary["completion_claim"] == "none"


def test_batch_totals_do_not_mix_failure_kinds() -> None:
    report = summarize_report({"actions": [{"verdict": "hard_fail"}], "failures": [{"verdict": "hard_fail"}]})
    batch = summarize_many([report, report])
    assert batch["totals"]["actions"] == 2
    assert batch["verdicts"]["hard_fail"] == 2


def test_summary_accepts_action_count_and_action_list() -> None:
    counted = summarize_report({"action_count": 4, "actions": []})
    listed = summarize_report({"actions": [{} for _ in range(4)]})

    assert counted["action_count"] == 4
    assert listed["action_count"] == 4


def test_summary_accepts_failure_count_and_failure_list() -> None:
    counted = summarize_report({"failure_count": 3, "failures": []})
    listed = summarize_report({"failures": [{"verdict": "soft_fail"} for _ in range(3)]})

    assert counted["failure_count"] == 3
    assert listed["failure_count"] == 3


def test_summary_exposes_unattributed_hard_failures() -> None:
    report = {
        "failures": [
            {"verdict": "hard_fail", "step": 1, "detail": "bad", "action": {"semantic_id": "bug"}},
            {
                "verdict": "hard_fail",
                "step": 2,
                "detail": "known",
                "upstream": {"issue": "123"},
            },
        ]
    }
    summary = summarize_report(report)
    assert summary["unattributed_hard_failures"] == [
        {"step": 1, "detail": "bad", "semantic_id": "bug"}
    ]


def test_summary_inherits_run_evidence_track_for_actions() -> None:
    summary = summarize_report(
        {
            "evidence_track": "natural",
            "actions": [{"kind": "click"}, {"kind": "click", "evidence_track": "assisted"}],
        }
    )
    assert summary["coverage"]["action_tracks"] == {"assisted": 1, "natural": 1}
