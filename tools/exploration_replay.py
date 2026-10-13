"""Semantic replay for gameplay exploration failures and shrink candidates."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from tools.exploration_oracle import classify_node
from tools.exploration_runtime import (
    RuntimeSession,
    perform_action,
    reveal_page_actions,
    snapshot_runtime,
)
from tools.exploration_trace import SemanticTrace


def match_trace_action(
    expected: Mapping[str, Any],
    candidates: Iterable[Mapping[str, Any]],
) -> tuple[str, Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    """Match a saved semantic action against runtime candidates.

    Matching order is semantic id, then id/name/href/value identity, then role
    plus text hash.  Runtime action indices are never part of the match key.
    """
    candidate_rows = [dict(item) for item in candidates]
    semantic_matches = [
        item for item in candidate_rows if item.get("semantic_id") == expected.get("semantic_id")
    ]
    if len(semantic_matches) == 1:
        return "matched", semantic_matches[0], semantic_matches
    if len(semantic_matches) > 1:
        return "ambiguous", None, semantic_matches

    identity = {
        key: expected[key]
        for key in ("id", "name", "href", "value")
        if expected.get(key) is not None
    }
    if identity:
        identity_matches = [
            item
            for item in candidate_rows
            if all(item.get(key) == value for key, value in identity.items())
        ]
        if len(identity_matches) == 1:
            return "matched", identity_matches[0], identity_matches
        if len(identity_matches) > 1:
            return "ambiguous", None, identity_matches

    role = expected.get("role")
    text_hash = expected.get("text_hash")
    text_matches = [
        item
        for item in candidate_rows
        if role is not None
        and item.get("role") == role
        and (
            item.get("text_hash") == text_hash
            or (
                text_hash is not None
                and __import__("hashlib").sha256(
                    str(item.get("text") or "").encode("utf-8")
                ).hexdigest()
                == text_hash
            )
        )
    ]
    if len(text_matches) == 1:
        return "matched", text_matches[0], text_matches
    if len(text_matches) > 1:
        return "ambiguous", None, text_matches
    return "unmatched", None, []


def replay_semantic_trace(
    target: Any,
    trace: Mapping[str, Any],
    *,
    headless: bool = True,
) -> dict[str, Any]:
    """Replay a natural semantic trace from a fresh real-game Start.

    This is not a source-code shortcut.  The runner bootstraps through the same
    visible UI, then matches every saved action against live runtime candidates
    before executing it.  The result keeps a separate replay evidence track so a
    replay cannot be mixed into a fresh natural exploration.
    """
    saved_actions = list(trace.get("actions") or [])
    result: dict[str, Any] = {
        "schema": "dolx.exploration-replay.v1",
        "evidence_track": "natural_prefix",
        "continuation": "semantic_trace_replay",
        "replayed": False,
        "planned_actions": len(saved_actions),
        "completed_actions": 0,
        "failure_kind": None,
        "detail": None,
        "last_action": None,
    }
    if not saved_actions:
        result["detail"] = "trace has no actions"
        return result

    with RuntimeSession(target, headless=headless) as session:
        bootstrap = session.bootstrap_natural(max_steps=300, deadline_s=240)
        result["bootstrap"] = bootstrap
        if not bootstrap.get("ok"):
            result["failure_kind"] = "infrastructure_fail"
            result["detail"] = "natural bootstrap did not reach gameplay"
            return result
        page = session.page
        for step_number, expected in enumerate(saved_actions, start=1):
            reveal_page_actions(page)
            before = snapshot_runtime(page, session.new_observations())
            status, candidate, evidence = match_trace_action(expected, before.actions)
            if status != "matched" or candidate is None:
                result["failure_kind"] = "infrastructure_fail"
                result["detail"] = f"semantic action {step_number} was {status}"
                result["evidence"] = evidence
                result["last_action"] = dict(expected)
                return result
            try:
                action_result = perform_action(page, candidate)
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                page.wait_for_timeout(120)
                reveal_page_actions(page)
                after = snapshot_runtime(page, session.new_observations())
            except Exception as exc:  # noqa: BLE001 - replayed product failures are evidence.
                result["failure_kind"] = "hard_fail"
                result["detail"] = f"{type(exc).__name__}: {exc}"
                result["last_action"] = dict(expected)
                result["completed_actions"] = step_number
                return result
            after_snapshot = {
                "finished": True,
                "observations": session.new_observations(),
                **after.fingerprint,
            }
            verdict, detail, diagnostics = classify_node(after_snapshot)
            result["completed_actions"] = step_number
            result["last_action"] = dict(expected)
            if verdict != "ok":
                result["failure_kind"] = verdict
                result["detail"] = detail
                result["diagnostics"] = diagnostics
                return result
        result["replayed"] = True
        return result


def replay_reproduces(replay: Mapping[str, Any], failure: Mapping[str, Any]) -> bool:
    """Decide whether a replay reproduces the same semantic product failure.

    Matching by action semantic id avoids treating two unrelated failures at the
    same passage as one bug.  Oracle failures without an action only compare
    verdict and detail.
    """
    if not replay.get("replayed"):
        return False
    if replay.get("failure_kind") != failure.get("verdict"):
        return False
    expected_action = failure.get("action") if isinstance(failure.get("action"), Mapping) else {}
    replay_action = replay.get("last_action") if isinstance(replay.get("last_action"), Mapping) else {}
    if not expected_action and not replay_action:
        return str(replay.get("detail") or "") == str(failure.get("detail") or "")
    return str(replay_action.get("semantic_id") or "") == str(
        expected_action.get("semantic_id") or ""
    )
