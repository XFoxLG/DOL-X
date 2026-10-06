"""Unit tests for the resumable sweep ledger."""

from __future__ import annotations

import json

import pytest

from tools import sweep_ledger as ledger_mod


def _identity(**overrides):
    values = {
        "html_sha256": "a" * 64,
        "fixture_digest": "b" * 64,
        "tool_version": "test-1",
        "plan_digest": "c" * 64,
        "strategy": {"tier": "full", "shard": [0, 2]},
    }
    values.update(overrides)
    return ledger_mod.run_identity("combat", **values)


def _ledger(identity, keys, results=None):
    return {
        "status": "running",
        "identity": identity,
        "plan_digest": identity["plan_digest"],
        "planned_keys": list(keys),
        "results": list(results or []),
        "completed": [],
    }


def test_run_identity_matches_ignores_key_order() -> None:
    identity = _identity()
    reordered = dict(reversed(list(identity.items())))
    ok, diagnostics = ledger_mod.identity_matches(identity, reordered)
    assert ok is True
    assert diagnostics == []


def test_identity_mismatch_reports_each_field() -> None:
    expected = _identity()
    actual = _identity(html_sha256="d" * 64, strategy={"tier": "daily"})
    ok, diagnostics = ledger_mod.identity_matches(expected, actual)
    assert ok is False
    assert any("html_sha256" in item for item in diagnostics)
    assert any("strategy" in item for item in diagnostics)


def test_plan_digest_is_order_sensitive() -> None:
    first = ledger_mod.plan_digest(["a", "b"], {"tier": "full"})
    second = ledger_mod.plan_digest(["b", "a"], {"tier": "full"})
    assert first != second


def test_corrupt_checkpoint_is_not_resumable(tmp_path) -> None:
    path = tmp_path / "combat-ledger.json"
    path.write_text("{not json", encoding="utf-8")
    loaded = ledger_mod.load_ledger(path)
    assert loaded["status"] == "corrupt"
    ok, diagnostics, results = ledger_mod.validate_resume(
        _identity(), "c" * 64, ["a"], loaded
    )
    assert ok is False
    assert results == []
    assert diagnostics


def test_legacy_completed_keys_without_results_are_rejected() -> None:
    identity = _identity()
    checkpoint = _ledger(identity, ["a", "b"])
    checkpoint["completed"] = ["a", "b"]
    ok, diagnostics, results = ledger_mod.validate_resume(
        identity, identity["plan_digest"], ["a", "b"], checkpoint
    )
    assert ok is False
    assert results == []
    assert any("completed keys but no result" in item for item in diagnostics)


def test_resume_requires_identity_and_plan_match() -> None:
    identity = _identity()
    checkpoint = _ledger(identity, ["a"], [{"key": "a", "verdict": "ok"}])
    checkpoint["plan_digest"] = "different"
    ok, diagnostics, results = ledger_mod.validate_resume(
        identity, identity["plan_digest"], ["a"], checkpoint
    )
    assert ok is False
    assert results == []
    assert any("plan_digest" in item for item in diagnostics)


def test_resume_reports_duplicate_and_extra_keys() -> None:
    identity = _identity()
    checkpoint = _ledger(
        identity,
        ["a", "b"],
        [
            {"key": "a", "verdict": "ok"},
            {"key": "a", "verdict": "soft_fail"},
            {"key": "extra", "verdict": "ok"},
        ],
    )
    ok, diagnostics, results = ledger_mod.validate_resume(
        identity, identity["plan_digest"], ["a", "b"], checkpoint
    )
    assert ok is False
    assert results == []
    assert any("duplicate result differs" in item for item in diagnostics)
    assert any("not in plan" in item for item in diagnostics)


def test_merge_result_recomputes_completed_from_results(tmp_path) -> None:
    identity = _identity()
    checkpoint = _ledger(identity, ["a", "b"])
    assert ledger_mod.merge_result(checkpoint, ["a", "b"], {"key": "b", "verdict": "ok"})
    assert ledger_mod.merge_result(checkpoint, ["a", "b"], {"key": "a", "verdict": "soft_fail"})
    assert [item["key"] for item in checkpoint["results"]] == ["a", "b"]
    assert checkpoint["completed"] == ["a", "b"]
    assert ledger_mod.merge_result(checkpoint, ["a", "b"], {"key": "extra"}) is False
    ledger_mod.save_ledger(tmp_path / "ledger.json", checkpoint)
    loaded = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert [item["key"] for item in loaded["results"]] == ["a", "b"]


def test_validate_complete_rejects_missing_duplicate_and_extra() -> None:
    ok, diagnostics, summary = ledger_mod.validate_complete(
        ["a", "b"],
        [
            {"key": "a", "verdict": "ok"},
            {"key": "a", "verdict": "ok"},
            {"key": "extra", "verdict": "ok"},
        ],
    )
    assert ok is False
    assert summary["missing"] == 1
    assert summary["duplicates"] == 1
    assert summary["extra"] == 1
    assert diagnostics


def test_validate_complete_accepts_exact_key_set() -> None:
    ok, diagnostics, summary = ledger_mod.validate_complete(
        ["a", "b"], [{"key": "a"}, {"key": "b"}]
    )
    assert ok is True
    assert diagnostics == []
    assert summary["status"] == "complete"


def test_atomic_write_json_leaves_valid_file(tmp_path) -> None:
    path = tmp_path / "nested" / "ledger.json"
    ledger_mod.atomic_write_json(path, {"ok": True, "value": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True, "value": 1}
    assert not list(path.parent.glob("*.tmp"))


def test_validate_resume_accepts_unique_matching_results() -> None:
    identity = _identity()
    checkpoint = _ledger(
        identity,
        ["a", "b"],
        [{"key": "a", "verdict": "ok"}, {"key": "b", "verdict": "soft_fail"}],
    )
    ok, diagnostics, results = ledger_mod.validate_resume(
        identity, identity["plan_digest"], ["a", "b"], checkpoint
    )
    assert ok is True
    assert diagnostics == []
    assert [item["key"] for item in results] == ["a", "b"]


def test_validate_complete_allow_missing_keeps_status_incomplete() -> None:
    ok, diagnostics, summary = ledger_mod.validate_complete(
        ["a", "b"], [{"key": "a"}], allow_missing=True
    )
    assert ok is True
    assert diagnostics == []
    assert summary["missing"] == 1
    assert summary["status"] == "incomplete_allowed"


@pytest.mark.parametrize("bad", [None, [], "string"])
def test_identity_matches_rejects_non_objects(bad) -> None:
    ok, diagnostics = ledger_mod.identity_matches(_identity(), bad)
    assert ok is False
    assert diagnostics
