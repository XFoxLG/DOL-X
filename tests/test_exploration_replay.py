"""Semantic replay and failure-shrink reproduction tests."""

from __future__ import annotations

import json

import pytest
from types import SimpleNamespace

from tools import exploration_replay
from tools.exploration_replay import (
    match_trace_action,
    replay_reproduces,
    replay_semantic_trace,
)
from tools.exploration_trace import SemanticTrace
from tools.exploration_agent import _archive_failure


def test_match_prefers_semantic_id_then_identity_then_text_hash() -> None:
    expected = {"step": 1, "semantic_id": "A:link:one", "role": "link", "text_hash": "hash-a"}
    assert match_trace_action(expected, [{"semantic_id": "A:link:one", "index": 3}])[0] == "matched"

    expected = {
        "step": 2,
        "semantic_id": "missing",
        "role": "button",
        "text_hash": "hash-button",
        "id": "only-id",
    }
    status, candidate, _ = match_trace_action(
        expected,
        [
            {"semantic_id": "wrong", "id": "other-id", "index": 1},
            {"semantic_id": "wrong", "id": "only-id", "index": 2},
        ],
    )
    assert status == "matched"
    assert candidate is not None
    assert candidate["index"] == 2

    expected = {
        "step": 3,
        "semantic_id": "missing",
        "role": "button",
        "text_hash": __import__("hashlib").sha256(b"same").hexdigest(),
    }
    status, candidate, _ = match_trace_action(
        expected,
        [{"semantic_id": "wrong", "role": "button", "text": "same", "index": 4}],
    )
    assert status == "matched"
    assert candidate is not None
    assert candidate["index"] == 4


def test_match_rejects_ambiguous_and_missing_actions() -> None:
    expected = {"semantic_id": "same"}
    assert match_trace_action(expected, [{"semantic_id": "same"}, {"semantic_id": "same"}])[0] == "ambiguous"
    assert match_trace_action(expected, [{"semantic_id": "different"}])[0] == "unmatched"


def test_replay_reproduces_compares_semantic_failure() -> None:
    failure = {"verdict": "hard_fail", "action": {"semantic_id": "bug"}}
    replay = {
        "replayed": True,
        "failure_kind": "hard_fail",
        "last_action": {"semantic_id": "bug"},
    }
    assert replay_reproduces(replay, failure)
    assert not replay_reproduces({**replay, "failure_kind": "soft_fail"}, failure)
    assert not replay_reproduces(
        {**replay, "last_action": {"semantic_id": "other"}}, failure
    )


class _FakeRuntimeSession:
    def __init__(self, expected_calls: dict[str, list[dict]]) -> None:
        self.expected_calls = expected_calls
        self.page = self
        self.matched: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def bootstrap_natural(self, **kwargs):
        return {"ok": True}

    def new_observations(self):
        return []

    def wait_for_load_state(self, state, timeout):
        return None

    def wait_for_timeout(self, timeout):
        return None

    def perform(self, candidate):
        self.matched.append(str(candidate["semantic_id"]))


def test_replay_semantic_trace_executes_saved_actions(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession(_FakeRuntimeSession):
        def reveal(self):
            return None

        def snapshot(self):
            return {
                "fingerprint": {
                    "coarse": {"passage": "A"},
                    "exact_hash": "hash",
                    "coarse_hash": "coarse",
                },
                "actions": [{"semantic_id": "A:link:one", "index": 2, "kind": "link"}],
            }

    session = FakeSession({})

    def fake_session(*args, **kwargs):
        return session

    def fake_snapshot(runtime, observations=None):
        snapshot = session.snapshot()
        return SimpleNamespace(actions=snapshot["actions"], fingerprint=snapshot["fingerprint"])

    def fake_perform(runtime, candidate):
        session.perform(candidate)
        return {"elapsed_ms": 1}

    monkeypatch.setattr(exploration_replay, "RuntimeSession", fake_session)
    monkeypatch.setattr(exploration_replay, "snapshot_runtime", fake_snapshot)
    monkeypatch.setattr(exploration_replay, "perform_action", fake_perform)

    trace = SemanticTrace.from_actions(
        [{"step": 1, "kind": "link", "semantic_id": "A:link:one"}]
    ).to_json()
    result = replay_semantic_trace("target.html", trace)

    assert result["replayed"] is True
    assert result["completed_actions"] == 1
    assert session.matched == ["A:link:one"]


def test_failure_archive_can_use_replay_shrink(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.exploration_archive import public_failure_summary

    manifest = {"schema": "dolx.target.v1", "target": {"package_sha256": "a" * 64}}
    failure = {
        "verdict": "hard_fail",
        "detail": "bug",
        "action": {"semantic_id": "bug"},
        "trace": {
            "actions": [
                {"step": 1, "kind": "link", "semantic_id": "before"},
                {"step": 2, "kind": "button", "semantic_id": "bug"},
            ]
        },
    }
    calls: list[list[str]] = []

    def fake_replay(target, trace, *, headless=True):
        actions = [item.get("semantic_id") for item in trace.get("actions") or []]
        calls.append(actions)
        return {
            "replayed": True,
            "failure_kind": "hard_fail",
            "last_action": {"semantic_id": "bug"},
        }

    monkeypatch.setattr("tools.exploration_agent.replay_semantic_trace", fake_replay)
    monkeypatch.setattr(
        "tools.exploration_agent.replay_reproduces",
        lambda replay, failure: "bug" in calls[-1],
    )
    _archive_failure(
        out_dir=tmp_path,
        target="target.html",
        failure=failure,
        manifest=manifest,
        seed=1,
        before={"passage": "A"},
        after={"passage": "B"},
        shrink_failures=True,
    )

    archives = list(tmp_path.glob("failure-*"))
    assert len(archives) == 1
    minimized = [
        json.loads(line)
        for line in (archives[0] / "minimized-trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert minimized == [{"step": 2, "kind": "button", "semantic_id": "bug"}]
    summary = public_failure_summary(
        {
            "directory": archives[0].name,
            "signature": "sig",
            "files": {
                "failure.json": {"failure": failure},
                "original-trace.jsonl": failure["trace"]["actions"],
                "minimized-trace.jsonl": minimized,
            },
        }
    )
    assert summary["trace"]["minimized_actions"] == 1
