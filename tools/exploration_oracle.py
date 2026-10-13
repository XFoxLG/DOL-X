"""Runtime observation and invariant classification for gameplay exploration."""

from __future__ import annotations

from typing import Any, Mapping


HARD_ERROR_KINDS = {"error", "unhandledrejection", "pageerror"}


def classify_observations(snapshot: Mapping[str, Any]) -> tuple[str, str]:
    errors = [
        item for item in snapshot.get("observations") or [] if item.get("kind") in HARD_ERROR_KINDS
    ]
    if errors:
        return "hard_fail", " | ".join(str(item.get("message") or "") for item in errors)[:400]
    if snapshot.get("passage_missing"):
        return "hard_fail", "active passage missing from SugarCube Story"
    if snapshot.get("empty_passage"):
        return "soft_fail", "passage rendered empty"
    if not snapshot.get("finished"):
        return "soft_fail", "passage render did not complete"
    return "ok", ""


def check_state_invariants(snapshot: Mapping[str, Any]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    variables = snapshot.get("variables") or {}
    if not isinstance(variables, Mapping):
        return False, ["variables is not an object"]
    for key in ("day", "month", "year"):
        value = variables.get(key)
        if value is not None and not isinstance(value, (int, float)):
            problems.append(f"{key} is not numeric")
    location = variables.get("location")
    if location is not None and not isinstance(location, (str, int)):
        problems.append("location has an invalid type")
    combat = variables.get("combat")
    if combat not in (None, 0, 1):
        problems.append("combat is not boolean-like")
    return not problems, problems


def classify_node(snapshot: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    verdict, detail = classify_observations(snapshot)
    invariants_ok, invariant_diagnostics = check_state_invariants(snapshot)
    if verdict == "ok" and not invariants_ok:
        verdict = "hard_fail"
        detail = "; ".join(invariant_diagnostics)
    return verdict, detail, invariant_diagnostics
