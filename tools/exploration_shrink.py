"""Failure minimization over semantic gameplay traces."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from tools.exploration_trace import SemanticTrace, traces_match


ShrinkPredicate = Callable[[Mapping[str, Any]], bool]


def shrink_trace(
    trace: Mapping[str, Any], predicate: ShrinkPredicate
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    """Binary-delete action blocks while preserving the target failure.

    ``predicate`` receives a candidate trace and returns True when the same
    failure still reproduces.  The original trace is never modified.
    """
    actions = list(trace.get("actions") or [])
    current_indices = list(range(len(actions)))
    attempts: list[Mapping[str, Any]] = []

    def candidate(indices: list[int]) -> dict[str, Any]:
        return SemanticTrace(tuple(actions[index] for index in indices)).to_json()

    size = max(1, len(current_indices) // 2)
    while size >= 1:
        offset = 0
        while offset < len(current_indices):
            block = current_indices[offset : offset + size]
            if not block:
                break
            indices = [index for index in current_indices if index not in set(block)]
            test = candidate(indices)
            attempts.append(test)
            if indices and predicate(test):
                current_indices = indices
            else:
                offset += size
        size //= 2

    minimized = candidate(current_indices)
    return minimized, attempts
