"""Pure tests for private failure archive generation."""

from __future__ import annotations

import json
from pathlib import Path

from tools.exploration_archive import (
    failure_signature,
    plan_failure_archive,
    public_failure_summary,
    state_diff_digest,
    write_failure_archive,
)


def _manifest(package: str = "a" * 64) -> dict:
    return {
        "schema": "dolx.target.v1",
        "target": {
            "game_version": "0.5.11.9",
            "target_tag": "v0.5.11.9-1.0.0a-0915",
            "package_sha256": package,
            "source_commit": None,
        },
        "mods_lock_sha256": "b" * 64,
        "runner_revision": "dol-x-exploration-agent-v1",
    }


def _failure(detail: str = "TimeoutError: click") -> dict:
    return {
        "schema": "dolx.exploration.v1",
        "verdict": "hard_fail",
        "detail": detail,
        "evidence_track": "natural",
        "action": {
            "semantic_id": "Tutorial:button:continue",
            "kind": "button",
        },
        "trace": {
            "actions": [
                {"step": 1, "semantic_id": "Start2:link:continue"},
                {"step": 2, "semantic_id": "Tutorial:button:continue"},
            ]
        },
    }


def test_failure_signature_changes_when_target_identity_changes() -> None:
    failure = _failure()
    first = failure_signature(failure=failure, manifest=_manifest(), seed=7)
    second = failure_signature(failure=failure, manifest=_manifest("c" * 64), seed=7)
    third = failure_signature(failure=failure, manifest=_manifest(), seed=8)
    assert first == failure_signature(failure=failure, manifest=_manifest(), seed=7)
    assert first != second
    assert first != third


def test_archive_plan_contains_required_files_and_private_state() -> None:
    failure = _failure()
    before = {"passage": "Tutorial", "variables": {"combat": 1}, "fingerprint": {"exact_hash": "e1"}}
    after = {"passage": "Tutorial", "variables": {"combat": 2}, "fingerprint": {"exact_hash": "e2"}}
    archive = plan_failure_archive(
        failure=failure,
        manifest=_manifest(),
        seed=7,
        before=before,
        after=after,
        observations=[
            {"kind": "console.error", "message": "boom"},
            {"kind": "pageerror", "message": "bad"},
            {"kind": "requestfailed", "url": "/x.png"},
        ],
        screenshots=[Path("screenshots/step-0002.png")],
    )
    assert set(archive["files"]) >= {
        "failure.json",
        "original-trace.jsonl",
        "minimized-trace.jsonl",
        "state-before.json",
        "state-after.json",
        "console.log",
        "page-errors.json",
        "network-failures.json",
        "screenshots.json",
    }
    assert archive["private_files"] == ["state-after.json", "state-before.json"]
    assert archive["files"]["page-errors.json"] == [{"kind": "pageerror", "message": "bad"}]
    assert archive["files"]["original-trace.jsonl"] == failure["trace"]["actions"]


def test_write_failure_archive_is_idempotent(tmp_path: Path) -> None:
    failure = _failure()
    archive = plan_failure_archive(failure=failure, manifest=_manifest(), seed=7)
    root = write_failure_archive(tmp_path, archive)
    failure_path = root / "failure.json"
    original = json.loads(failure_path.read_text(encoding="utf-8"))
    assert original["failure"]["verdict"] == "hard_fail"
    assert (root / "original-trace.jsonl").read_text(encoding="utf-8").count("\n") == 2

    # The default preserves an existing archive; explicit overwrite regenerates.
    assert write_failure_archive(tmp_path, archive) == root
    assert json.loads(failure_path.read_text(encoding="utf-8")) == original
    write_failure_archive(tmp_path, archive, overwrite=True)
    assert json.loads(failure_path.read_text(encoding="utf-8")) == original


def test_public_summary_omits_full_state_but_keeps_digests() -> None:
    failure = _failure()
    before = {"passage": "Tutorial", "variables": {"private": "x"}, "fingerprint": {"exact_hash": "e1"}}
    after = {"passage": "Tutorial", "variables": {"private": "y"}, "fingerprint": {"exact_hash": "e2"}}
    archive = plan_failure_archive(
        failure=failure,
        manifest=_manifest(),
        seed=7,
        before=before,
        after=after,
    )
    summary = public_failure_summary(archive)
    encoded = json.dumps(summary)
    assert "private" not in encoded
    assert summary["state"]["before"]["variable_keys"] == 1
    assert summary["state"]["before"]["exact_hash"] == "e1"
    assert summary["trace"]["original_actions"] == 2
    assert summary["completion_claim"] == "none"


def test_empty_inputs_do_not_crash() -> None:
    failure = _failure(detail="")
    archive = plan_failure_archive(failure=failure, manifest=_manifest())
    assert archive["signature"]
    assert state_diff_digest(None, None)
    assert public_failure_summary(archive)["state"]["before"]["present"] is False
